"""Real stdio processes and loopback TLS; only the inference backend is substituted."""
import asyncio
import base64
import datetime
import ipaddress
import json
import os
import socket
import sys
import threading
import time
from pathlib import Path

import httpx
import uvicorn
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from services.gateway import create_app
from scripts.build_image_client_bundle import build_bundle


def test_tb06_mcp_resume_stdio_kill_restart_and_save_recovery(owner_env,tmp_path):
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'T06 ephemeral test')])
    now=datetime.datetime.now(datetime.timezone.utc)
    cert=(x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
          .serial_number(x509.random_serial_number()).not_valid_before(now-datetime.timedelta(minutes=1))
          .not_valid_after(now+datetime.timedelta(hours=1))
          .add_extension(x509.BasicConstraints(ca=True,path_length=None),critical=True)
          .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]),critical=False)
          .sign(key,hashes.SHA256()))
    cert_path=tmp_path/'test-ca.crt';cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path=tmp_path/'test-tls.key'
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
    key_path.chmod(0o600)
    backend=owner_env.new_backend()
    app=create_app(owner_env.root,owner_env.keys['legacy'],key_registry=owner_env.registry,
        identity_mode='staging',transport=httpx.MockTransport(backend),run_worker=True,audio_enabled=False,images_enabled=True)
    accepted=threading.Event();release=threading.Event()

    @app.middleware('http')
    async def lose_first_response(request,call_next):
        response=await call_next(request)
        if request.url.path=='/v1/tasks' and request.method=='POST' and not accepted.is_set():
            accepted.set()
            await asyncio.to_thread(release.wait,10)
        return response

    sock=socket.socket();sock.bind(('127.0.0.1',0))
    port=sock.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,ssl_certfile=str(cert_path),
        ssl_keyfile=str(key_path),log_level='error',access_log=False))
    thread=threading.Thread(target=lambda:asyncio.run(server.serve(sockets=[sock])),daemon=True)
    thread.start()
    try:
        deadline=time.monotonic()+5
        while not server.started and time.monotonic()<deadline:threading.Event().wait(.01)
        assert server.started
        personal_key=tmp_path/'personal.key';personal_key.write_text(owner_env.keys['A'])
        blocked=tmp_path/'不可写 pictures';blocked.write_text('directory blocked by a file')
        config=tmp_path/'personal.json'
        config.write_text(json.dumps({'base_url':f'https://127.0.0.1:{port}/v1','api_key_file':str(personal_key),
                                     'ca_file':str(cert_path),'output_dir':str(blocked)}))
        import zipfile
        bundle=build_bundle(config,{},tmp_path/'personal.zip')
        with zipfile.ZipFile(bundle) as archive:archive.extractall(tmp_path/'installed')
        installed=tmp_path/'installed/SparkImageTools'

        async def run():
            processes=[]
            async def start():
                # Run from an unrelated cwd with no source PYTHONPATH.
                env={k:v for k,v in os.environ.items() if k!='PYTHONPATH'}
                proc=await asyncio.create_subprocess_exec(sys.executable,str(installed/'spark_image_tools.py'),
                    '--config',str(installed/'spark-image.json'),cwd=tmp_path,env=env,
                    stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL)
                processes.append(proc)
                await send(proc,1,'initialize',{'protocolVersion':'2025-11-25','capabilities':{},'clientInfo':{'name':'tb06','version':'1'}})
                await receive(proc)
                proc.stdin.write(b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n');await proc.stdin.drain()
                return proc
            async def send(proc,ident,method,params):
                proc.stdin.write((json.dumps({'jsonrpc':'2.0','id':ident,'method':method,'params':params})+'\n').encode())
                await proc.stdin.drain()
            async def receive(proc):
                line=await asyncio.wait_for(proc.stdout.readline(),10)
                assert line,'MCP process exited'
                response=json.loads(line)
                assert 'error' not in response,response
                return response['result']
            try:
                first=await start()
                await send(first,2,'tools/call',{'name':'generate_image','arguments':{'prompt':'fixture','request_id':'stdio-recover'}})
                assert await asyncio.to_thread(accepted.wait,5)
                first.kill();await first.wait();release.set()
                second=await start();assert first.pid!=second.pid
                await send(second,2,'tools/call',{'name':'list_image_tasks','arguments':{}})
                listing=await receive(second)
                state=json.loads(next(c['text'] for c in listing['content'] if c['type']=='text'))
                assert state['requests']==[{'request_id':'stdio-recover','task_id':None}]
                tid=state['data'][0]['id']
                await send(second,3,'tools/call',{'name':'generate_image','arguments':{'prompt':'fixture','request_id':'stdio-recover'}})
                replay=await receive(second)
                assert not replay.get('isError')
                assert json.loads(next(c['text'] for c in replay['content'] if c['type']=='text'))['id']==tid
                await send(second,4,'tools/call',{'name':'get_image_task','arguments':{'task_id':tid,'wait_seconds':20}})
                failed=await receive(second)
                assert failed['isError']
                blocked.unlink();blocked.mkdir()
                await send(second,5,'tools/call',{'name':'get_image_task','arguments':{'task_id':tid,'wait_seconds':20}})
                result=await receive(second)
                assert not result.get('isError')
                image=next(c for c in result['content'] if c['type']=='image')
                assert base64.b64decode(image['data'])==backend.png
                assert next(blocked.glob('*.png')).read_bytes()==backend.png
                assert len(backend.jobs)==1
                assert owner_env.keys['A'].encode() not in (installed/'requests.sqlite3').read_bytes()
            finally:
                release.set()
                for proc in processes:
                    if proc.returncode is None:proc.terminate();await asyncio.wait_for(proc.wait(),5)
        asyncio.run(run())
    finally:
        release.set();server.should_exit=True;thread.join(timeout=5);sock.close()
        assert not thread.is_alive(),'TLS test server failed to stop'
