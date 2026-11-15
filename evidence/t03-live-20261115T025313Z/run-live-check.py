"""Live TCP/TLS/MCP and CPU worker acceptance; never starts a model service."""
import asyncio, hashlib, io, json, os, socket, ssl, subprocess, sys, threading, time, uuid
from datetime import datetime, timezone
from pathlib import Path
import httpx
from PIL import Image
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

BASE=Path('/home/clusteradmin/Desktop/Agent多模态服务')
PYTHON=BASE/'.venv/bin/python'
RUN='t03-live-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
PRIVATE=BASE/'.private'/RUN
EVIDENCE=BASE/'evidence'/RUN
PRIVATE.mkdir(mode=0o700); EVIDENCE.mkdir()
URL='https://127.0.0.1:18444'
CA=BASE/'certificates/agent-root-ca.crt'
report={'run_id':RUN,'started_utc':datetime.now(timezone.utc).isoformat(),
        'scope':'real localhost HTTPS using existing project CA, real processes/SQLite/files/CPU PDF worker/MCP stdio; NO model loading',
        'not_verified':['physical image generation/editing','Windows/macOS actual Harness','production release/recovery','memory calibration'],
        'checks':[]}
processes=[]; logs=[]; raw_keys=[]; key_ids=[]; queued=[]
stop_sample=threading.Event(); samples=[]

def available():
    return int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))*1024

def sample():
    while not stop_sample.is_set():
        samples.append({'utc':datetime.now(timezone.utc).isoformat(),'available_bytes':available()})
        stop_sample.wait(1)

def check(name, condition, **facts):
    report['checks'].append({'name':name,'passed':bool(condition),**facts})
    if not condition: raise RuntimeError('Live check failed: '+name)

def unit_state():
    units=['ltx-worker','ltx-resource-guard','agent-mm-image','agent-mm-image-memory-guard','agent-mm-gateway','agent-mm-https']
    return {u:subprocess.run(['systemctl','--user','is-active',u],capture_output=True,text=True).stdout.strip() for u in units}

def cli(*args):
    result=subprocess.run([str(PYTHON),'-m','services.identity','--db',str(PRIVATE/'keys.sqlite3'),*map(str,args)],cwd=BASE,capture_output=True,text=True,timeout=15)
    if result.returncode: raise RuntimeError('Key CLI failed: '+result.stderr[:200])
    return result.stdout.strip()

def issue(owner,name):
    target=PRIVATE/(name+'.key'); key_id=cli('issue','--owner',owner,'--out',target)
    raw=target.read_text().strip();raw_keys.append(raw);key_ids.append(key_id)
    return raw,target,key_id

def launch(args, name, env=None):
    stream=(PRIVATE/(name+'.log')).open('w');logs.append(stream)
    p=subprocess.Popen(list(map(str,args)),cwd=BASE,env=env,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
    processes.append(p);return p

def stop(p):
    if p.poll() is None:
        p.terminate()
        try:p.wait(timeout=15)
        except subprocess.TimeoutExpired:p.kill();p.wait(timeout=5)

def start_gateway(workers):
    env=dict(os.environ);env.pop('MAIN_TOKEN_FILE',None)
    env.update(PYTHONPATH=str(PRIVATE)+os.pathsep+str(BASE),LIVE_ROOT=str(PRIVATE),LIVE_WORKERS='1' if workers else '0',
               IMAGE_URL='http://127.0.0.1:18013',MAIN_URL='http://127.0.0.1:18010')
    p=launch([PYTHON,'-m','uvicorn','live_app:app','--factory','--host','127.0.0.1','--port','18018','--no-access-log'],
             'gateway-'+('worker' if workers else 'queue'),env)
    deadline=time.monotonic()+20
    while time.monotonic()<deadline:
        if p.poll() is not None:raise RuntimeError('Gateway process exited')
        try:
            with socket.create_connection(('127.0.0.1',18018),timeout=.3):return p
        except OSError:time.sleep(.1)
    raise RuntimeError('Gateway readiness deadline')

def pdf_fixture():
    text='Live T03 private document. Selectable text verifies actual CPU PDF extraction without any vision model.'
    stream=f'BT /F1 12 Tf 30 100 Td ({text}) Tj ET'.encode()
    objects=[b'<< /Type /Catalog /Pages 2 0 R >>',b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 800 200] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
        b'<< /Length '+str(len(stream)).encode()+b' >>\nstream\n'+stream+b'\nendstream']
    pdf=b'%PDF-1.4\n';offsets=[]
    for n,obj in enumerate(objects,1):offsets.append(len(pdf));pdf+=str(n).encode()+b' 0 obj\n'+obj+b'\nendobj\n'
    xref=len(pdf);pdf+=b'xref\n0 6\n0000000000 65535 f \n'+b''.join(f'{x:010d} 00000 n \n'.encode() for x in offsets)
    pdf+=f'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode()
    return text,pdf

def auth(raw):return {'Authorization':'Bearer '+raw} if raw else {}

def req(c,method,path,raw,**kwargs):
    if available()<20*1024**3:raise RuntimeError('Aborted: less than20GiB available; other workloads unchanged')
    return c.request(method,path,headers={**auth(raw),**kwargs.pop('headers',{})},**kwargs)

def submit(c,raw,fid,key,prompt='fixture'):
    return req(c,'POST','/v1/tasks',raw,headers={'Idempotency-Key':key},json={'kind':'pdf','file_id':fid,'options':{'prompt':prompt}})

def upload(c,raw,data):
    r=req(c,'POST','/v1/files',raw,files={'file':('live.pdf',data,'application/pdf')})
    check('upload-own-file',r.status_code==200,status=r.status_code)
    return r.json()['id']

def wait_done(c,raw,tid):
    deadline=time.monotonic()+30
    while time.monotonic()<deadline:
        r=req(c,'GET','/v1/tasks/'+tid,raw)
        if r.status_code!=200:raise RuntimeError('Own task unavailable')
        task=r.json()
        if task['status'] in ('completed','failed','cancelled'):
            check('CPU-worker-completed-real-task',task['status']=='completed',task_id=tid,status=task['status'])
            return task
        time.sleep(.1)
    raise RuntimeError('PDF worker deadline')

async def mcp_checks(config,foreign_tid,png):
    params=StdioServerParameters(command=str(PYTHON),args=[str(BASE/'client/spark_image_tools.py'),'--config',str(config)])
    with (PRIVATE/'mcp.log').open('w') as errlog:
        async with stdio_client(params,errlog=errlog) as (read,write):
            async with ClientSession(read,write) as session:
                init=await session.initialize();listed=await session.list_tools()
                check('real-MCP-stdio-tool-discovery',{'generate_image','edit_image','get_image_task','cancel_image_task'}<=set(t.name for t in listed.tools),protocol=init.protocolVersion)
                for tool,args,code in [('generate_image',{'prompt':'Live offline backend safety check'},503),
                    ('edit_image',{'prompt':'Change background','image_paths':[str(png)]},503),
                    ('get_image_task',{'task_id':foreign_tid,'wait_seconds':0},404),
                    ('cancel_image_task',{'task_id':foreign_tid},404)]:
                    result=await session.call_tool(tool,args)
                    message=' '.join(x.text for x in result.content if x.type=='text')
                    check('MCP-'+tool+'-expected-'+str(code),result.isError and ('HTTP '+str(code)) in message,expected_http=code)

before=unit_state();report['services_before']=before
thread=threading.Thread(target=sample,daemon=True);thread.start()
try:
    for port in [18018,18444,18013]:
        with socket.socket() as sock:check('port-initially-unused-'+str(port),sock.connect_ex(('127.0.0.1',port))!=0)
    check('image-model-not-running',before['agent-mm-image']!='active')
    source=Path('/home/clusteradmin/.codex/workspaces/agent-mm-issue-2-20261115')
    report['source_commit']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip()
    names=['services/gateway.py','services/store.py','services/identity.py','services/image_routes.py','services/images.py','services/media.py','client/spark_image_tools.py']
    report['runtime_sha256']={name:hashlib.sha256((BASE/name).read_bytes()).hexdigest() for name in names}
    check('runtime-matches-merged-source',all((BASE/name).read_bytes()==subprocess.check_output(['git','show','HEAD:'+name],cwd=source) for name in names))
    root_hash=hashlib.sha256(CA.read_bytes()).hexdigest();report['trusted_ca_sha256']=root_hash
    legacy,_,_=issue('live-legacy','legacy')
    a,a_path,a_id=issue('live-A','A');b,b_path,b_id=issue('live-B','B')
    check('key-files-private',all((p.stat().st_mode & 0o777)==0o600 for p in PRIVATE.glob('*.key')))
    (PRIVATE/'live_app.py').write_text('from pathlib import Path\nimport os\nfrom services.gateway import create_app\nfrom services.identity import KeyRegistry\ndef app():\n root=Path(os.environ["LIVE_ROOT"])\n return create_app(root/"runtime",(root/"legacy.key").read_text().strip(),key_registry=KeyRegistry(root/"keys.sqlite3"),identity_mode="staging",audio_enabled=False,images_enabled=True,run_worker=os.environ["LIVE_WORKERS"]=="1")\n')
    gateway=start_gateway(True)
    (PRIVATE/'Caddyfile').write_text('''{\n admin off\n auto_https disable_redirects\n skip_install_trust\n servers {\n  protocols h1 h2\n }\n}\nhttps://127.0.0.1:18444 {\n bind 127.0.0.1\n tls internal\n header -Server\n request_body {\n  max_size 65MB\n }\n reverse_proxy 127.0.0.1:18018\n}\n''')
    env=dict(os.environ);env.update(XDG_DATA_HOME=str(BASE/'.private/data'),XDG_CONFIG_HOME=str(PRIVATE/'caddy-config'))
    caddy=launch([Path.home()/'.local/bin/caddy','run','--config',PRIVATE/'Caddyfile','--adapter','caddyfile'],'caddy',env)
    context=ssl.create_default_context(cafile=str(CA))
    with httpx.Client(base_url=URL,verify=context,trust_env=False,timeout=15) as c:
        deadline=time.monotonic()+20
        while True:
            try:r=req(c,'GET','/v1/me',a);break
            except httpx.ConnectError:
                if time.monotonic()>deadline:raise
                time.sleep(.2)
        check('trusted-existing-CA-real-HTTPS',r.status_code==200 and r.json()=={'owner':'live-A'},http=r.http_version)
        try:
            with httpx.Client(verify=True,trust_env=False,timeout=3) as untrusted:untrusted.get(URL+'/v1/me')
            rejected=False
        except httpx.ConnectError:rejected=True
        check('untrusted-CA-rejected',rejected)
        for bad in ['', 'not-a-valid-key']:
            r=req(c,'GET','/v1/me',bad);check('unknown-key401',r.status_code==401 and r.headers.get('www-authenticate')=='Bearer' and bool(r.headers.get('x-request-id')))
        check('B-own-identity',req(c,'GET','/v1/me',b).json()=={'owner':'live-B'})
        text,pdf=pdf_fixture();(EVIDENCE/'fixture.pdf').write_bytes(pdf)
        files={o:upload(c,k,pdf) for o,k in [('A',a),('B',b)]}
        check('same-content-separate-owner-files',files['A']!=files['B'])
        missing='file-'+'f'*32
        for method,suffix in [('GET','/content'),('DELETE','')]:
            foreign=req(c,method,'/v1/files/'+files['A']+suffix,b);absent=req(c,method,'/v1/files/'+missing+suffix,b)
            check('foreign-file-'+method+'-uniform404',foreign.status_code==absent.status_code==404 and foreign.json()==absent.json())
        foreign=submit(c,b,files['A'],'foreign');absent=submit(c,b,missing,'foreign')
        check('foreign-media-reference-uniform404',foreign.status_code==absent.status_code==404 and foreign.json()==absent.json())
        tasks={}
        for o,k in [('A',a),('B',b)]:
            first=submit(c,k,files[o],'shared-live-key');check(o+'-task-accepted',first.status_code==202)
            tasks[o]=wait_done(c,k,first.json()['id'])
            check(o+'-real-PDF-text',tasks[o]['result']['pages'][0]['text']==text)
            (EVIDENCE/('task-'+o+'.json')).write_text(json.dumps(tasks[o],ensure_ascii=False,indent=2)+'\n')
            check(o+'-real-file-byte-download',req(c,'GET','/v1/files/'+files[o]+'/content',k).content==pdf)
            new_fid=upload(c,k,pdf)
            replay=submit(c,k,new_fid,'shared-live-key')
            check(o+'-content-replay-new-upload-ID',replay.status_code==202 and replay.json()['id']==tasks[o]['id'])
            check(o+'-changed-payload409',submit(c,k,new_fid,'shared-live-key','changed').status_code==409)
        check('cross-owner-same-request-key-independent',tasks['A']['id']!=tasks['B']['id'])
        for o,k,other in [('A',a,b),('B',b,a)]:
            for method,suffix in [('GET',''),('POST','/cancel')]:
                foreign=req(c,method,'/v1/tasks/'+tasks[o]['id']+suffix,other)
                absent=req(c,method,'/v1/tasks/task-missing'+suffix,other)
                check(o+'-foreign-task-'+method+'-uniform404',foreign.status_code==absent.status_code==404 and foreign.json()==absent.json())
        new_a,new_a_path,new_a_id=issue('live-A','A-rotated');cli('revoke','--key-id',a_id)
        check('revoked-key401',req(c,'GET','/v1/tasks/'+tasks['A']['id'],a).status_code==401)
        a=new_a
        check('rotation-retains-owner-and-original-result',req(c,'GET','/v1/me',a).json()=={'owner':'live-A'} and req(c,'GET','/v1/tasks/'+tasks['A']['id'],a).json()['result']==tasks['A']['result'])
        check('rotated-key-original-file200',req(c,'GET','/v1/files/'+files['A']+'/content',a).status_code==200)
        forged=req(c,'POST','/v1/tasks',b,json={'kind':'pdf','file_id':files['B'],'owner':'live-A'})
        check('forged-owner422',forged.status_code==422)
        r=req(c,'POST','/v1/tasks',a,json={'kind':'image_generate','options':{'prompt':'offline real network check'}})
        check('real-offline-image-backend503',r.status_code==503,detail=r.json()['detail'])
        png=EVIDENCE/'reference.png';Image.new('RGB',(64,64),'green').save(png)
        config=PRIVATE/'mcp-B.json';config.write_text(json.dumps({'base_url':URL+'/v1','api_key_file':str(b_path),'ca_file':str(CA),'output_dir':str(PRIVATE/'mcp-output')}));config.chmod(0o600)
        asyncio.run(mcp_checks(config,tasks['A']['id'],png))
        # Real queue admission/cancellation with worker intentionally disabled, no fake completion.
        stop(gateway);gateway=start_gateway(False)
        for i in range(4):
            owner=i%2;key=[a,b][owner];fid=[files['A'],files['B']][owner]
            r=submit(c,key,fid,'capacity-'+str(i));check('global-slot-'+str(i),r.status_code==202)
            queued.append((key,r.json()['id']))
        r=submit(c,a,files['A'],'capacity-0');check('full-queue-replay-does-not-occupy-slot',r.status_code==202 and r.json()['id']==queued[0][1])
        r=submit(c,b,files['B'],'fifth');check('global-fifth429-retry-after',r.status_code==429 and r.headers.get('retry-after')=='10')
        check('foreign-cancel-cannot-free-slot',req(c,'POST','/v1/tasks/'+queued[0][1]+'/cancel',b).status_code==404)
        check('queue-still-full-after-foreign-cancel',submit(c,b,files['B'],'sixth').status_code==429)
        r=req(c,'POST','/v1/tasks/'+queued[0][1]+'/cancel',a);check('own-cancel200',r.status_code==200 and r.json()['status']=='cancelled')
        r=submit(c,b,files['B'],'fifth');check('own-cancel-frees-one-slot',r.status_code==202);queued.append((b,r.json()['id']))
        for key,tid in queued:req(c,'POST','/v1/tasks/'+tid+'/cancel',key)
        report['task_ids']={o:t['id'] for o,t in tasks.items()}
        report['downloaded_source_pdf_sha256']=hashlib.sha256(pdf).hexdigest()
    report['status']='passed-with-model-and-desktop-tests-not-run'
except BaseException as exc:
    report['status']='failed';report['failure_type']=type(exc).__name__;report['failure']=str(exc)[:500]
finally:
    for p in reversed(processes):stop(p)
    for stream in logs:stream.close()
    revoked=[]
    for key_id in key_ids:
        try:cli('revoke','--key-id',key_id);revoked.append(key_id)
        except Exception:pass
    report['cleanup']={'owned_processes_stopped':all(p.poll() is not None for p in processes),'test_keys_revoked':len(revoked)==len(key_ids),'services_after':unit_state()}
    report['cleanup']['original_service_states_preserved']=report['cleanup']['services_after']==before
    report['trusted_ca_unchanged']=hashlib.sha256(CA.read_bytes()).hexdigest()==report.get('trusted_ca_sha256')
    log_data=b''.join(p.read_bytes() for p in PRIVATE.glob('*.log'))
    report['raw_credentials_absent_from_service_logs']=all(k.encode() not in log_data for k in raw_keys)
    for p in PRIVATE.glob('*.key'):p.unlink()
    for p in PRIVATE.glob('mcp-*.json'):p.unlink()
    stop_sample.set();thread.join(timeout=2)
    report['min_available_gib_observed']=round(min(x['available_bytes'] for x in samples)/1024**3,3)
    report['sampling_note']='1Hz observed availability only; not a profile/memory-safety calibration'
    boundary_ok=(report['cleanup']['owned_processes_stopped'] and report['cleanup']['test_keys_revoked']
                 and report['cleanup']['original_service_states_preserved'] and report['trusted_ca_unchanged']
                 and report['raw_credentials_absent_from_service_logs'])
    report['cleanup_and_credential_checks_passed']=boundary_ok
    if not boundary_ok:
        report['status']='failed';report['failure']='Cleanup/credential boundary check failed'
    report['finished_utc']=datetime.now(timezone.utc).isoformat()
    report['checks_passed']=sum(x['passed'] for x in report['checks'])
    (EVIDENCE/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    (EVIDENCE/'memory-observed.json').write_text(json.dumps(samples,indent=2)+'\n')
    print(json.dumps({'evidence':str(EVIDENCE),'status':report['status'],'checks_passed':report['checks_passed'],
                      'failure':report.get('failure'),'cleanup':report['cleanup']},ensure_ascii=False,indent=2))
    if report['status']=='failed':sys.exit(1)
