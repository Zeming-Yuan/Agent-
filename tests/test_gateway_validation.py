import json
import time
from fastapi.testclient import TestClient
import httpx
from services.gateway import create_app

AUTH={'Authorization':'Bearer test-secret-token'}


def test_whole_context_output_limit_uses_remaining_budget_and_preserves_input(tmp_path):
    seen=[]
    def backend(request):
        body=json.loads(request.content)
        seen.append((request.url.path,body))
        if request.url.path=='/tokenize':
            return httpx.Response(200,json={'count':12000})
        return httpx.Response(200,content=b'data: [DONE]\n\n',headers={'content-type':'text/event-stream'})
    app=create_app(tmp_path,'test-secret-token',run_worker=False,transport=httpx.MockTransport(backend))
    messages=[{'role':'system','content':'Keep this history intact.'},{'role':'user','content':'hello'}]
    tools=[{'type':'function','function':{'name':'lookup','parameters':{'type':'object'}}}]
    with TestClient(app) as c:
        for field in ('max_tokens','max_completion_tokens'):
            r=c.post('/v1/chat/completions',headers=AUTH,json={'model':'spark-main','messages':messages,'tools':tools,field:32768,'stream':True})
            assert r.status_code==200 and r.content==b'data: [DONE]\n\n'
            assert r.headers.get('x-max-output-tokens')=='20768'
            counted,generated=seen[-2:]
            assert counted[0]=='/tokenize'
            assert counted[1]['messages']==messages and counted[1]['tools']==tools
            assert counted[1]['chat_template_kwargs']=={'enable_thinking':False}
            assert generated[1]['messages']==messages
            assert generated[1]['max_tokens']==20768
            assert 'max_completion_tokens' not in generated[1]


def test_full_input_is_rejected_without_losing_slots_or_truncating(tmp_path):
    chats=[]
    def backend(request):
        if request.url.path=='/tokenize':
            return httpx.Response(200,json={'count':32768})
        chats.append(json.loads(request.content))
        return httpx.Response(200,json={'ok':True})
    app=create_app(tmp_path,'test-secret-token',run_worker=False,transport=httpx.MockTransport(backend))
    with TestClient(app) as c:
        for _ in range(3):
            r=c.post('/v1/chat/completions',headers=AUTH,json={'model':'spark-main','messages':[{'role':'user','content':'full context'}],'max_tokens':32768})
            assert r.status_code==400
            assert '32768' in r.json()['detail']
        assert not chats
        r=c.post('/v1/chat/completions',headers=AUTH,json={'model':'spark-main','messages':[{'role':'user','content':'hi'}],'max_tokens':64})
        assert r.status_code==200
        assert chats[0]['max_tokens']==64


def test_explicit_completion_limit_is_not_overridden_by_default(tmp_path):
    seen=[]
    def backend(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200,json={'ok':True})
    app=create_app(tmp_path,'test-secret-token',run_worker=False,transport=httpx.MockTransport(backend))
    with TestClient(app) as c:
        r=c.post('/v1/chat/completions',headers=AUTH,json={'model':'spark-main','messages':[{'role':'user','content':'hi'}],'max_completion_tokens':2048})
        assert r.status_code==200
        assert seen[-1]['max_tokens']==2048
        assert 'max_completion_tokens' not in seen[-1]
        for value in (0,-1,True,'32768'):
            r=c.post('/v1/chat/completions',headers=AUTH,json={'model':'spark-main','messages':[{'role':'user','content':'hi'}],'max_tokens':value})
            assert r.status_code==422


def test_configured_200k_window_is_used_for_discovery_and_output_budget(tmp_path):
    seen=[]
    def backend(request):
        if request.url.path=='/tokenize':
            return httpx.Response(200,json={'count':196000})
        seen.append(json.loads(request.content))
        return httpx.Response(200,json={'ok':True})
    app=create_app(tmp_path,'test-secret-token',run_worker=False,context_window=200000,transport=httpx.MockTransport(backend))
    with TestClient(app) as c:
        models=c.get('/v1/models',headers=AUTH).json()['data']
        assert next(m for m in models if m['id']=='spark-main')['max_model_len']==200000
        r=c.post('/v1/chat/completions',headers=AUTH,json={'model':'spark-main','messages':[{'role':'user','content':'long'}],'max_tokens':200000})
        assert r.status_code==200
        assert r.headers['x-context-window']=='200000'
        assert seen[-1]['max_tokens']==4000


def test_tokenizer_failure_releases_slots_before_next_request(tmp_path):
    def backend(request):
        if request.url.path=='/tokenize':
            return httpx.Response(200,json={'count':'invalid'})
        return httpx.Response(200,json={'ok':True})
    app=create_app(tmp_path,'test-secret-token',run_worker=False,transport=httpx.MockTransport(backend))
    with TestClient(app) as c:
        for _ in range(3):
            r=c.post('/v1/chat/completions',headers=AUTH,json={'model':'spark-main','messages':[{'role':'user','content':'hello'}],'max_tokens':32768})
            assert r.status_code==503
        assert c.post('/v1/chat/completions',headers=AUTH,json={'model':'spark-main','messages':[{'role':'user','content':'hello'}],'max_tokens':32}).status_code==200


def test_stream_disconnect_before_response_start_does_not_exhaust_slots(tmp_path):
    import asyncio
    import pytest
    from starlette.requests import Request, ClientDisconnect
    app=create_app(tmp_path,'test-secret-token',run_worker=False,transport=httpx.MockTransport(
        lambda r:httpx.Response(200,content=b'data: [DONE]\n\n',headers={'content-type':'text/event-stream'})))
    chat=next(route.endpoint for route in app.routes if route.path=='/v1/chat/completions')
    def request(stream):
        payload=json.dumps({'model':'spark-main','messages':[{'role':'user','content':'hi'}],'stream':stream}).encode()
        async def receive():
            return {'type':'http.request','body':payload,'more_body':False}
        return Request({'type':'http','method':'POST','path':'/v1/chat/completions','headers':[],
                        'state':{'request_id':'stream-start-test'},'asgi':{'spec_version':'2.4'}},receive)
    async def check():
        async with app.router.lifespan_context(app):
            for _ in range(2):
                req=request(True)
                response=await chat(req)
                async def send(message):
                    if message['type']=='http.response.start':
                        raise OSError('Client disconnected before body iteration')
                with pytest.raises(ClientDisconnect):
                    await response(req.scope,req.receive,send)
            response=await asyncio.wait_for(chat(request(False)),timeout=.5)
            assert response.status_code==200
    asyncio.run(check())


def test_store_disabled_is_accepted_without_forwarding_storage_option(tmp_path):
    seen=[]
    def backend(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, content=b'data: [DONE]\n\n', headers={'content-type':'text/event-stream'})
    app=create_app(tmp_path,'test-secret-token',run_worker=False,transport=httpx.MockTransport(backend))
    with TestClient(app) as c:
        for stream in (False, True):
            for store in (False, None):
                r=c.post('/v1/chat/completions',headers=AUTH,json={'model':'spark-main','messages':[{'role':'user','content':'hi'}],'store':store,'stream':stream})
                assert r.status_code==200
                assert r.content==b'data: [DONE]\n\n'
    assert len(seen)==4
    assert all('store' not in body for body in seen)


def test_unsupported_storage_is_rejected_before_inference(tmp_path):
    seen=[]
    def backend(request):
        seen.append(request)
        return httpx.Response(200,json={})
    app=create_app(tmp_path,'test-secret-token',run_worker=False,transport=httpx.MockTransport(backend))
    with TestClient(app) as c:
        for store in (True, 'false', 0, {}, []):
            r=c.post('/v1/chat/completions',headers=AUTH,json={'model':'spark-main','messages':[{'role':'user','content':'hi'}],'store':store})
            assert r.status_code==422
            assert 'store' in r.json()['detail']
    assert not seen


def test_full_model_name_routes_to_canonical_alias_and_unknown_is_helpful(tmp_path):
    seen=[]
    def backend(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200,json={'choices':[{'message':{'content':'ok'}}]})
    app=create_app(tmp_path,'test-secret-token',run_worker=False,transport=httpx.MockTransport(backend))
    with TestClient(app) as c:
        r=c.post('/v1/chat/completions',headers=AUTH,json={'model':'Qwen3.6-35B-A3B-NVFP4','messages':[{'role':'user','content':'hi'}]})
        assert r.status_code==200
        assert r.json()['choices'][0]['message']['content']=='ok'
        assert seen[0]['model']=='spark-main'
        r=c.post('/v1/chat/completions',headers=AUTH,json={'model':'unavailable-model','messages':[{'role':'user','content':'hi'}]})
        assert r.status_code==404
        assert 'spark-main' in r.json()['detail']


def test_server_config_cannot_be_set_by_client(tmp_path):
    app=create_app(tmp_path,'test-secret-token',run_worker=False,transport=httpx.MockTransport(lambda r:httpx.Response(200,json={})))
    with TestClient(app) as c:
        for extra in ({'chat_template':'malicious'},{'mm_processor_kwargs':{'min_pixels':999999999}}, {'chat_template_kwargs':{'anything':True}}):
            r=c.post('/v1/chat/completions',headers=AUTH,json={'model':'spark-main','messages':[{'role':'user','content':'hi'}],**extra})
            assert r.status_code==422
        r=c.post('/v1/chat/completions',headers=AUTH,json=['invalid'])
        assert r.status_code==422


def test_main_unavailable_reports_503(tmp_path):
    def offline(request):
        raise httpx.ConnectError('offline',request=request)
    app=create_app(tmp_path,'test-secret-token',run_worker=False,transport=httpx.MockTransport(offline))
    with TestClient(app) as c:
        assert c.get('/health',headers=AUTH).status_code==503
        r=c.post('/v1/chat/completions',headers=AUTH,json={'model':'spark-main','messages':[{'role':'user','content':'hi'}]})
        assert r.status_code==503


def test_worker_failure_and_cancel_do_not_lose_task(tmp_path):
    # Invalid PDF must be marked failed durably; worker must remain alive for subsequent tasks.
    app=create_app(tmp_path,'test-secret-token',transport=httpx.MockTransport(lambda r:httpx.Response(503)))
    with TestClient(app) as c:
        fid=c.post('/v1/files',headers=AUTH,files={'file':('bad.pdf',b'not pdf')}).json()['id']
        task=c.post('/v1/tasks',headers=AUTH,json={'kind':'pdf','file_id':fid}).json()
        for _ in range(100):
            result=c.get('/v1/tasks/'+task['id'],headers=AUTH).json()
            if result['status'] in ('failed','completed'):
                break
            time.sleep(.02)
        assert result['status']=='failed' and result['error']
        second=c.post('/v1/tasks',headers=AUTH,json={'kind':'pdf','file_id':fid}).json()
        assert c.post('/v1/tasks/'+second['id']+'/cancel',headers=AUTH).json()['status']=='cancelled'
        time.sleep(.3)
        assert c.get('/v1/tasks/'+second['id'],headers=AUTH).json()['status']=='cancelled'


def test_invalid_json_numbers_do_not_exhaust_model_slots(tmp_path):
    app=create_app(tmp_path,'test-secret-token',run_worker=False,transport=httpx.MockTransport(lambda r:httpx.Response(200,json={'ok':True})))
    with TestClient(app,raise_server_exceptions=False) as c:
        body=b'{"model":"spark-main","messages":[{"role":"user","content":"hi"}],"temperature":NaN}'
        for _ in range(2):
            assert c.post('/v1/chat/completions',headers={**AUTH,'Content-Type':'application/json'},content=body).status_code==422
        assert c.post('/v1/chat/completions',headers=AUTH,json={'model':'spark-main','messages':[{'role':'user','content':'hi'}]}).status_code==200


def test_cancelled_scope_still_closes_upstream_and_releases_slot():
    import asyncio
    import anyio
    from services.gateway import close_main_response
    class Upstream:
        closed=False
        async def aclose(self):
            await anyio.sleep(.01)
            self.closed=True
    async def check():
        upstream=Upstream()
        semaphore=asyncio.Semaphore(0)
        with anyio.CancelScope() as scope:
            scope.cancel()
            await close_main_response(upstream,semaphore)
        assert upstream.closed and semaphore._value==1
    anyio.run(check)


def test_upload_quota_is_atomic_across_concurrent_requests(tmp_path):
    import asyncio
    from io import BytesIO
    from starlette.datastructures import UploadFile
    from starlette.routing import request_response
    app=create_app(tmp_path,'test-secret-token',run_worker=False)
    store=app.state.store
    store.add_file('file-'+'f'*32,'quota-fixture',2*1024**3-3*1024**2)
    upload=next(route.endpoint for route in app.routes if route.path=='/v1/files' and 'POST' in route.methods)
    class SlowFile(UploadFile):
        async def read(self,size=-1):
            await asyncio.sleep(.02)
            return await super().read(size)
    async def check():
        files=[SlowFile(filename='audio',file=BytesIO(b'x'*(2*1024**2))) for _ in range(2)]
        result=await asyncio.gather(*(upload(file=f,purpose='assistants') for f in files),return_exceptions=True)
        assert sum(isinstance(r,dict) for r in result)==1
        assert any(getattr(r,'status_code',None)==413 for r in result)
        with store.connect() as db:
            assert db.execute('select sum(bytes) from files').fetchone()[0]<=2*1024**3
    asyncio.run(check())


def test_health_requires_audio_backends_to_report_ready(tmp_path):
    app=create_app(tmp_path,'test-secret-token',run_worker=False,transport=httpx.MockTransport(lambda r:httpx.Response(200,json={})))
    with TestClient(app) as c:
        assert c.get('/health',headers=AUTH).status_code==503


def test_vllm_empty_200_health_body_is_ready(tmp_path):
    def backend(request):
        return httpx.Response(200,content=b'') if request.url.port==18010 else httpx.Response(200,json={'status':'ready'})
    app=create_app(tmp_path,'test-secret-token',run_worker=False,transport=httpx.MockTransport(backend))
    with TestClient(app) as c:
        assert c.get('/health',headers=AUTH).status_code==200
