"""Real stdio processes and loopback TLS; only the inference backend is substituted."""
import asyncio
import base64
import json
import os
import sys
import threading
from pathlib import Path

import httpx

from image_test_harness import https_server
from services.gateway import create_app
from scripts.build_image_client_bundle import build_bundle


def test_tb06_mcp_resume_stdio_kill_restart_and_save_recovery(owner_env,tmp_path):
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

    with https_server(app,tmp_path) as (port,cert_path):
        try:
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
            release.set()
