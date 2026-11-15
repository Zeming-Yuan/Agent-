"""T06 public bridge/MCP recovery against the real owner-aware HTTP app."""
import asyncio
import json
import io
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import httpx
import pytest
from PIL import Image

from client.spark_image_tools import ImageBridge, build_server

CA = Path(__file__).resolve().parents[1] / 'certificates/agent-root-ca.crt'


class GatewayTransport(httpx.AsyncBaseTransport):
    """Keep real auth, SQLite, routes and worker; inject only network loss."""
    def __init__(self, gateway, *, journal=None, drop_submit=False):
        self.gateway = gateway
        self.journal = journal
        self.drop_submit = drop_submit
        self.requests = []
        self.download_fault = None

    async def handle_async_request(self, request):
        self.requests.append(request)
        if request.url.path.endswith('/content') and self.download_fault:
            if self.download_fault == 'network':raise httpx.ReadError('download interrupted',request=request)
            return httpx.Response(200,content=b'\x89PNG\r\n\x1a\ntruncated')
        if request.method == 'POST' and request.url.path == '/v1/tasks':
            from client.request_journal import RequestJournal
            identity=self.gateway.get('/v1/me',headers=dict(request.headers)).json()
            service=str(request.url.copy_with(path='/v1',query=None))
            records = RequestJournal(self.journal, service, identity['owner']).pending()
            assert request.headers['idempotency-key'] in {r['request_id'] for r in records}
        response = await asyncio.to_thread(
            self.gateway.request, request.method, str(request.url),
            headers=dict(request.headers), content=await request.aread())
        if self.drop_submit and request.method == 'POST' and request.url.path == '/v1/tasks':
            self.drop_submit = False
            assert response.status_code == 202, response.text
            raise httpx.ReadError('accepted response lost', request=request)
        return httpx.Response(response.status_code, headers=response.headers, content=response.content)


def bridge_for(env, tmp_path, transport, *, owner='A', service='https://spark.invalid/v1'):
    return ImageBridge(service, env.keys[owner], CA, tmp_path/'out',
                       journal_path=tmp_path/'requests.sqlite3', transport=transport)


def test_tb06_lost_response_replays_after_bridge_restart(owner_env, tmp_path):
    backend = owner_env.new_backend()
    with owner_env.client(backend=backend, run_worker=True) as gateway:
        transport = GatewayTransport(gateway, journal=tmp_path/'requests.sqlite3', drop_submit=True)

        async def run():
            one = bridge_for(owner_env, tmp_path, transport)
            try:
                with pytest.raises(Exception, match='accepted response lost'):
                    await build_server(one).call_tool('generate_image', {'prompt':'fixture', 'request_id':'r1'})
            finally:
                await one.close()
            original = gateway.get('/v1/tasks', headers=owner_env.auth('A')).json()['data'][0]['id']
            two = bridge_for(owner_env, tmp_path, transport)
            try:
                result = await build_server(two).call_tool('generate_image', {'prompt':'fixture', 'request_id':'r1'})
                content = result[0] if isinstance(result, tuple) else result
                state = json.loads(next(x.text for x in content if x.type == 'text'))
                assert state['id'] == original
                owner_env.wait_task(gateway, original, 'A', lambda t: t['status'] == 'completed')
                assert len(backend.jobs) == 1
            finally:
                await two.close()
        asyncio.run(run())


@pytest.mark.parametrize('kind',['image_edit','image_generate'])
def test_tb06_reference_recovery_reuses_upload_and_content_identity(owner_env, tmp_path, kind):
    backend = owner_env.new_backend()
    source = tmp_path/'素材 one.png'
    png = io.BytesIO()
    foreground = Image.new('RGBA',(8,8),(0,0,0,0))
    foreground.putpixel((3,3),(0,200,0,255))
    foreground.save(png,format='PNG')
    source.write_bytes(png.getvalue())
    with owner_env.client(backend=backend,run_worker=True) as gateway:
        transport = GatewayTransport(gateway,journal=tmp_path/'requests.sqlite3',drop_submit=True)
        async def invoke(bridge):
            if kind == 'image_edit':
                return text_state(await build_server(bridge).call_tool('edit_image',{'prompt':'fixture','image_paths':[str(source)],'request_id':'ref'}))
            return text_state(await build_server(bridge).call_tool('generate_image',{'prompt':'fixture','foreground_path':str(source),'request_id':'ref'}))
        async def run():
            one = bridge_for(owner_env,tmp_path,transport)
            try:
                with pytest.raises(Exception,match='accepted response lost'):
                    await invoke(one)
            finally:
                await one.close()
            original = gateway.get('/v1/tasks',headers=owner_env.auth('A')).json()['data'][0]
            owner_env.wait_task(gateway,original['id'],'A',lambda t:t['status']=='completed')
            two = bridge_for(owner_env,tmp_path,transport)
            try:
                replay = await invoke(two)
                assert replay['id'] == original['id']
                uploads = [r for r in transport.requests if r.method=='POST' and r.url.path=='/v1/files']
                assert len(uploads) == 1
                fid = original['options']['image_ids'][0] if kind=='image_edit' else original['options']['foreground_file_id']
                assert gateway.delete('/v1/files/'+fid,headers=owner_env.auth('A')).status_code == 200
                replay = await invoke(two)
                assert replay['id'] == original['id']
                assert len(backend.jobs) == 1
                assert len([r for r in transport.requests if r.method=='POST' and r.url.path=='/v1/files']) == 2
            finally:
                await two.close()
        asyncio.run(run())


def test_tb06_new_intent_and_conflict(owner_env, tmp_path):
    with owner_env.client() as gateway:
        transport = GatewayTransport(gateway, journal=tmp_path/'requests.sqlite3')

        async def run():
            bridge = bridge_for(owner_env, tmp_path, transport)
            try:
                first = await bridge.generate('fixture','1024x1024',0,'','',request_id='r')
                replay = await bridge.generate('fixture','1024x1024',0,'','',request_id='r')
                assert replay['id'] == first['id']
                count = len(transport.requests)
                with pytest.raises(ValueError, match='different input'):
                    await bridge.generate('changed','1024x1024',0,'','',request_id='r')
                assert not any(r.method == 'POST' for r in transport.requests[count:])
                new = await bridge.generate('fixture','1024x1024',0,'','')
                assert new['id'] != first['id']
                assert new['request_id'] != 'r'
                from client.request_journal import RequestJournal
                records = RequestJournal(tmp_path/'requests.sqlite3','https://spark.invalid/v1','A').pending()
                assert {r['task_id'] for r in records} == {first['id'],new['id']}
                assert owner_env.keys['A'].encode() not in (tmp_path/'requests.sqlite3').read_bytes()
            finally:
                await bridge.close()
        asyncio.run(run())


def test_tb06_direct_bridge_entrypoint_runs_outside_source_cwd(tmp_path):
    script = Path(__file__).resolve().parents[1]/'client/spark_image_tools.py'
    env = {k:v for k,v in os.environ.items() if k != 'PYTHONPATH'}
    result = subprocess.run([sys.executable,str(script),'--help'],cwd=tmp_path,env=env,
                            capture_output=True,text=True,timeout=10)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('request_id',['', 'a'*129, 'bad\nheader', '中文'])
def test_tb06_invalid_request_identity_never_submits(owner_env, tmp_path, request_id):
    with owner_env.client() as gateway:
        transport = GatewayTransport(gateway, journal=tmp_path/'requests.sqlite3')
        async def run():
            bridge = bridge_for(owner_env, tmp_path, transport)
            try:
                with pytest.raises(ValueError, match='request_id'):
                    await bridge.generate('fixture','1024x1024',0,'','',request_id=request_id)
                assert not any(r.method == 'POST' for r in transport.requests)
                assert gateway.get('/v1/tasks',headers=owner_env.auth('A')).json()['data'] == []
            finally:
                await bridge.close()
        asyncio.run(run())


def text_state(result):
    content = result[0] if isinstance(result,tuple) else result
    return json.loads(next(x.text for x in content if x.type=='text'))


def test_tb06_mcp_owner_service_partition_rotation_and_server_recovery(owner_env, tmp_path):
    with owner_env.client() as gateway:
        transport=GatewayTransport(gateway,journal=tmp_path/'requests.sqlite3')
        async def run():
            one=bridge_for(owner_env,tmp_path,transport)
            try:
                original=await one.generate('fixture','1024x1024',0,'','',request_id='same')
                source=tmp_path/'edit.png'; source.write_bytes(owner_env.new_backend().png)
                edited=text_state(await build_server(one).call_tool('edit_image',{'prompt':'fixture','image_paths':[str(source)],'request_id':'edit'}))
                assert edited['request_id']=='edit'
                listing=text_state(await build_server(one).call_tool('list_image_tasks',{'status':'queued','limit':1}))
                assert listing['data'][0]['id']==original['id']
                assert listing['has_more'] and listing['next_cursor']==original['id']
            finally:
                await one.close()
            owner_env.keys['A']=owner_env.registry.issue('A')
            for owner,service,want_ids,want_requests in [
                ('A','https://spark.invalid/v1',{original['id'],edited['id']},{'same','edit'}),
                ('B','https://spark.invalid/v1',set(),set()),
                ('A','https://other.invalid/v1',{original['id'],edited['id']},set())]:
                bridge=bridge_for(owner_env,tmp_path,transport,owner=owner,service=service)
                try:
                    listing=text_state(await build_server(bridge).call_tool('list_image_tasks',{}))
                    assert {t['id'] for t in listing['data']}==want_ids
                    assert {r['request_id'] for r in listing['requests']}==want_requests
                finally:
                    await bridge.close()
            (tmp_path/'requests.sqlite3').unlink()
            restored=bridge_for(owner_env,tmp_path,transport)
            try:
                listing=text_state(await build_server(restored).call_tool('list_image_tasks',{}))
                assert {t['id'] for t in listing['data']}=={original['id'],edited['id']}
                assert listing['requests']==[]
            finally:
                await restored.close()
        asyncio.run(run())


@pytest.mark.parametrize('fault',['network','invalid_png','permission','disk','directory'])
def test_tb06_save_failure_preserves_completed_and_existing_target(owner_env,tmp_path,monkeypatch,fault):
    backend=owner_env.new_backend()
    with owner_env.client(backend=backend,run_worker=True) as gateway:
        transport=GatewayTransport(gateway,journal=tmp_path/'requests.sqlite3')
        async def run():
            bridge=bridge_for(owner_env,tmp_path,transport)
            try:
                state=await bridge.generate('fixture','1024x1024',0,'','',request_id='save')
                done=owner_env.wait_task(gateway,state['id'],'A',lambda t:t['status']=='completed')
                fid=done['result']['file_id']
                target=tmp_path/'out'/(fid+'.png');target.parent.mkdir();target.write_bytes(b'old-result')
                with monkeypatch.context() as patch:
                    def fail(*args,**kwargs):
                        if fault=='disk':raise OSError(28,'No space left on device')
                        raise PermissionError('read-only destination')
                    if fault in ('network','invalid_png'):transport.download_fault=fault
                    elif fault=='permission':patch.setattr('os.replace',fail)
                    elif fault=='disk':patch.setattr('os.fsync',fail)
                    else:patch.setattr('tempfile.mkstemp',fail)
                    with pytest.raises(Exception):
                        await build_server(bridge).call_tool('get_image_task',{'task_id':state['id'],'wait_seconds':0})
                    assert target.read_bytes()==b'old-result'
                    assert set(target.parent.iterdir())=={target}
                transport.download_fault=None
                result=await build_server(bridge).call_tool('get_image_task',{'task_id':state['id'],'wait_seconds':0})
                content=result[0] if isinstance(result,tuple) else result
                import base64
                image=next(x for x in content if x.type=='image')
                assert base64.b64decode(image.data)==backend.png==target.read_bytes()
                assert gateway.get('/v1/tasks/'+state['id'],headers=owner_env.auth('A')).json()['status']=='completed'
                assert len(backend.jobs)==1
                assert len([r for r in transport.requests if r.method=='POST' and r.url.path=='/v1/tasks'])==1
            finally:
                await bridge.close()
        asyncio.run(run())


def test_tb06_personal_bundle_is_explicit_and_runs_stdio_outside_repo(tmp_path):
    from scripts.build_image_client_bundle import build_bundle
    personal=tmp_path/'personal';personal.mkdir()
    (personal/'key').write_text('test-personal-credential')
    (personal/'ca.crt').write_bytes(CA.read_bytes())
    config=personal/'config.json'
    config.write_text(json.dumps({'base_url':'https://spark.invalid/v1','api_key_file':'key',
                                 'ca_file':'ca.crt','output_dir':str(tmp_path/'自定义 pictures')}))
    asset=tmp_path/'README.md';asset.write_text('Personal installation instructions')
    target=tmp_path/'deliver'/'personal.zip'
    result=build_bundle(config,{'README.md':asset},target)
    assert result==target
    with zipfile.ZipFile(target) as archive:
        assert set(archive.namelist())=={'SparkImageTools/'+name for name in [
            'spark_image_tools.py','client/__init__.py','client/spark_image_tools.py','client/request_journal.py',
            'api_key','agent-root-ca.crt','spark-image.json','requirements.txt','README.md']}
        assert archive.read('SparkImageTools/api_key')==b'test-personal-credential'
        bundled=json.loads(archive.read('SparkImageTools/spark-image.json'))
        assert bundled['api_key_file']=='api_key' and bundled['journal_path']=='requests.sqlite3'
        archive.extractall(tmp_path/'unpacked')
    installed=tmp_path/'unpacked/SparkImageTools'
    from mcp import ClientSession,StdioServerParameters
    from mcp.client.stdio import stdio_client
    async def run():
        env={k:v for k,v in os.environ.items() if k!='PYTHONPATH'}
        params=StdioServerParameters(command=sys.executable,args=[str(installed/'spark_image_tools.py'),'--config',str(installed/'spark-image.json')],cwd=str(tmp_path),env=env)
        async with stdio_client(params) as (read,write):
            async with ClientSession(read,write) as session:
                await session.initialize()
                tools=(await session.list_tools()).tools
                assert {t.name for t in tools}=={'generate_image','edit_image','get_image_task','cancel_image_task','list_image_tasks'}
                assert 'request_id' in next(t for t in tools if t.name=='edit_image').inputSchema['properties']
    asyncio.run(run())
    with pytest.raises(FileExistsError):build_bundle(config,{},target)
    assert not list(target.parent.glob('.bundle-*'))


def test_tb06_bundle_rejects_runtime_and_credential_assets(tmp_path):
    from scripts.build_image_client_bundle import build_bundle
    key=tmp_path/'personal.key';key.write_text('test-personal-credential')
    other=tmp_path/'other-owner.key';other.write_text('test-other-owner-credential')
    config=tmp_path/'config.json'
    config.write_text(json.dumps({'base_url':'https://spark.invalid/v1','api_key_file':str(key),'ca_file':str(CA)}))
    for name,source in [('README.md',other),('requests.sqlite3',other),('../README.md',other),('api_key',other)]:
        target=tmp_path/'rejected.zip'
        with pytest.raises(ValueError):build_bundle(config,{name:source},target)
        assert not target.exists()


@pytest.mark.parametrize('name',[
    './spark_image_tools.py','./client/request_journal.py','Client/extra.py','docs//helper.py','C:/helper.py',
    'client./request_journal.py','Client /request_journal.py','spark?image?tools.py',
    'spark<image>tools.py','spark_image_tools.py\x00extra.py','docs\x01/helper.py','CON.py',
    'spark_image_tools.py/helper.py','api_key/helper.py',
])
def test_tb06_bundle_cannot_replace_public_modules_through_path_aliases(tmp_path,name):
    from scripts.build_image_client_bundle import build_bundle
    key=tmp_path/'key';key.write_text('test-personal-credential')
    config=tmp_path/'config.json'
    config.write_text(json.dumps({'base_url':'https://spark.invalid/v1','api_key_file':str(key),'ca_file':str(CA)}))
    asset=tmp_path/'helper.py';asset.write_text('raise RuntimeError("entrypoint replaced")')
    with pytest.raises(ValueError):build_bundle(config,{name:asset},tmp_path/'rejected.zip')
    assert not (tmp_path/'rejected.zip').exists()


@pytest.mark.parametrize('conflicting',[False,True])
def test_tb06_concurrent_clients_keep_one_request_mapping(owner_env,tmp_path,conflicting):
    backend=owner_env.new_backend()
    with owner_env.client(backend=backend,run_worker=True) as gateway:
        transport=GatewayTransport(gateway,journal=tmp_path/'requests.sqlite3')
        async def run():
            bridges=[bridge_for(owner_env,tmp_path,transport) for _ in range(2)]
            try:
                results=await asyncio.gather(
                    bridges[0].generate('fixture','1024x1024',0,'','',request_id='race'),
                    bridges[1].generate('other' if conflicting else 'fixture','1024x1024',0,'','',request_id='race'),
                    return_exceptions=True)
                valid=[r for r in results if isinstance(r,dict)]
                assert len(valid)==(1 if conflicting else 2)
                assert len({r['id'] for r in valid})==1
                if conflicting:assert any(isinstance(r,ValueError) for r in results)
                owner_env.wait_task(gateway,valid[0]['id'],'A',lambda t:t['status']=='completed')
                assert len(backend.jobs)==1
                from client.request_journal import RequestJournal
                assert RequestJournal(tmp_path/'requests.sqlite3','https://spark.invalid/v1','A').pending()==[{'request_id':'race','task_id':valid[0]['id']}]
            finally:
                for bridge in bridges:await bridge.close()
        asyncio.run(run())


@pytest.mark.parametrize('service',['https://raw-secret@spark.invalid/v1','https://spark.invalid/v1?secret=/v1','https://spark.invalid/v1#secret/v1'])
def test_tb06_service_identity_rejects_credentials_and_query(tmp_path,service):
    with pytest.raises(ValueError):
        ImageBridge(service,'test-secret-token',CA,tmp_path,journal_path=tmp_path/'j.sqlite3')


def test_tb06_journal_never_replaces_an_accepted_task(tmp_path):
    from client.request_journal import RequestJournal
    journal=RequestJournal(tmp_path/'j.sqlite3','svc','A')
    journal.prepare('r','fp',{})
    journal.accepted('r','task-original')
    journal.accepted('r','task-original')
    with pytest.raises(ValueError):journal.accepted('r','task-other')
    assert journal.pending()==[{'request_id':'r','task_id':'task-original'}]


def test_tb06_auth_scope_and_deleted_results_do_not_resubmit(owner_env,tmp_path):
    backend=owner_env.new_backend()
    with owner_env.client(backend=backend,run_worker=True) as gateway:
        transport=GatewayTransport(gateway,journal=tmp_path/'requests.sqlite3')
        async def run():
            a=bridge_for(owner_env,tmp_path,transport)
            b=bridge_for(owner_env,tmp_path,transport,owner='B')
            try:
                original=await a.generate('fixture','1024x1024',0,'','',request_id='shared')
                other=await b.generate('fixture','1024x1024',0,'','',request_id='shared')
                assert original['id']!=other['id']
                with pytest.raises(RuntimeError,match='404'):await b.task(original['id'],0)
                with pytest.raises(RuntimeError,match='404'):await b.list_tasks(after=original['id'])
                done=owner_env.wait_task(gateway,original['id'],'A',lambda t:t['status']=='completed')
                owner_env.wait_task(gateway,other['id'],'B',lambda t:t['status']=='completed')
                before=len([r for r in transport.requests if r.method=='POST'])
                gateway.delete('/v1/files/'+done['result']['file_id'],headers=owner_env.auth('A'))
                with pytest.raises(RuntimeError,match='404'):await a.task(original['id'],0)
                assert len([r for r in transport.requests if r.method=='POST'])==before
                principal=owner_env.registry.resolve(owner_env.keys['A']);owner_env.registry.revoke(principal.key_id)
                with pytest.raises(RuntimeError,match='401'):await a.list_tasks()
                assert len(backend.jobs)==2
            finally:
                await a.close();await b.close()
        asyncio.run(run())


def test_tb06_unwritable_journal_prevents_submission(owner_env,tmp_path):
    with owner_env.client() as gateway:
        transport=GatewayTransport(gateway,journal=tmp_path/'requests.sqlite3')
        blocked=tmp_path/'blocked';blocked.write_text('not a directory')
        async def run():
            bridge=ImageBridge('https://spark.invalid/v1',owner_env.keys['A'],CA,tmp_path/'out',journal_path=blocked/'j.sqlite3',transport=transport)
            try:
                with pytest.raises(OSError):await bridge.generate('fixture','1024x1024',0,'','')
                assert not any(r.method=='POST' for r in transport.requests)
                assert gateway.get('/v1/tasks',headers=owner_env.auth('A')).json()['data']==[]
            finally:await bridge.close()
        asyncio.run(run())
