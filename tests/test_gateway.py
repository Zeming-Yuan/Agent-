import json
import time
from pathlib import Path
import httpx
from fastapi.testclient import TestClient
from services.gateway import create_app


def client_for(tmp_path, handler=None, **kw):
    def upstream(request):
        if handler:
            return handler(request)
        return httpx.Response(200, json={'status':'ready'})
    return TestClient(create_app(tmp_path, 'test-secret-token', transport=httpx.MockTransport(upstream), **kw))

AUTH = {'Authorization': 'Bearer test-secret-token'}


def test_auth_rejections_are_traceable_without_logging_credentials(tmp_path, caplog):
    import logging
    with caplog.at_level(logging.INFO, logger='agent-mm'), client_for(tmp_path) as c:
        for headers in ({}, {'Authorization':'Bearer private-wrong-credential'},
                        {'Authorization':'Basic private-wrong-credential'}):
            r = c.get('/v1/models', headers=headers)
            assert r.status_code == 401
            assert r.headers.get('x-request-id')
            assert r.headers.get('www-authenticate') == 'Bearer'
            assert r.headers['x-request-id'] in caplog.text
    denied = [r.message for r in caplog.records if 'authentication_denied' in r.message]
    assert len(denied) == 3
    assert 'header_present=False' in denied[0]
    assert 'formatted_key_matches=False' in denied[1]
    assert 'bearer_scheme=False' in denied[2]
    assert 'private-wrong-credential' not in caplog.text
    assert 'test-secret-token' not in caplog.text


def test_bearer_scheme_case_and_spaces_preserve_exact_key_check(tmp_path):
    with client_for(tmp_path) as c:
        for value in ('bearer test-secret-token', 'BEARER test-secret-token',
                      'bEaReR   test-secret-token', 'Bearer test-secret-token '):
            assert c.get('/v1/models', headers={'Authorization':value}).status_code == 200
        for value in ('Bearer TEST-SECRET-TOKEN', 'Bearer test-secret-token-wrong',
                      'Basic test-secret-token', 'Bearer "test-secret-token"',
                      'Bearer Bearer test-secret-token', 'Bearertest-secret-token'):
            assert c.get('/v1/models', headers={'Authorization':value}).status_code == 401


def test_auth_required_and_request_id(tmp_path):
    with client_for(tmp_path) as c:
        assert c.get('/v1/models').status_code == 401
        assert c.get('/v1/models', headers={'Authorization':'Bearer wrong'}).status_code == 401
        r=c.get('/v1/models',headers=AUTH)
        assert r.status_code == 200
        assert r.headers['x-request-id']
        assert {m['id'] for m in r.json()['data']} >= {'spark-main','whisper-large-v3-turbo'}


def test_chat_stream_tool_calls_preserved_and_remote_images_blocked(tmp_path):
    seen=[]
    chunk='data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_1","function":{"name":"search","arguments":"{}"}}]}}]}\n\ndata: [DONE]\n\n'
    def handle(req):
        seen.append(json.loads(req.content))
        return httpx.Response(200, content=chunk, headers={'content-type':'text/event-stream'})
    with client_for(tmp_path,handle) as c:
        body={'model':'spark-main','messages':[{'role':'user','content':'search'}],'stream':True,'tools':[{'type':'function','function':{'name':'search','parameters':{'type':'object'}}}]}
        r=c.post('/v1/chat/completions',headers=AUTH,json=body)
        assert r.status_code==200 and r.text==chunk
        assert seen[0]['tools']==body['tools'] and seen[0]['stream'] is True
        body['messages'][0]['content']=[{'type':'image_url','image_url':{'url':'http://169.254.169.254/latest/meta-data'}}]
        assert c.post('/v1/chat/completions',headers=AUTH,json=body).status_code==422
        body['model']='cloud-model'
        assert c.post('/v1/chat/completions',headers=AUTH,json=body).status_code==404


def test_upstream_failure_is_not_success(tmp_path):
    with client_for(tmp_path,lambda req:httpx.Response(503,json={'error':'loading'})) as c:
        r=c.post('/v1/chat/completions',headers=AUTH,json={'model':'spark-main','messages':[{'role':'user','content':'hi'}]})
        assert r.status_code==503


def test_upload_limit_paths_and_delete(tmp_path):
    with client_for(tmp_path,max_upload_bytes=10) as c:
        assert c.post('/v1/files',headers=AUTH,files={'file':('../../escape',b'01234567890')}).status_code==413
        r=c.post('/v1/files',headers=AUTH,files={'file':('../../escape',b'hello')})
        assert r.status_code==200
        fid=r.json()['id']
        assert not (tmp_path.parent/'escape').exists()
        assert c.get('/v1/files/'+fid+'/content',headers=AUTH).content==b'hello'
        assert c.get('/v1/files/not-real/content',headers=AUTH).status_code==404
        assert c.delete('/v1/files/'+fid,headers=AUTH).status_code==200
        assert c.get('/v1/files/'+fid+'/content',headers=AUTH).status_code==404


def test_task_idempotency_cancel_and_persistence(tmp_path):
    # A deferred worker is a test injection: no GPU or model is involved in these state tests.
    with client_for(tmp_path,run_worker=False) as c:
        fid=c.post('/v1/files',headers=AUTH,files={'file':('a.wav',b'audio')}).json()['id']
        headers={**AUTH,'Idempotency-Key':'same-task'}
        body={'kind':'transcribe','file_id':fid}
        a=c.post('/v1/tasks',headers=headers,json=body)
        b=c.post('/v1/tasks',headers=headers,json=body)
        assert a.status_code==202 and a.json()['id']==b.json()['id']
        assert c.post('/v1/tasks',headers=headers,json={**body,'kind':'audio_understand'}).status_code==409
        assert c.delete('/v1/files/'+fid,headers=AUTH).status_code==409
        tid=a.json()['id']
        assert c.post('/v1/tasks/'+tid+'/cancel',headers=AUTH).json()['status']=='cancelled'
        assert c.get('/v1/tasks/'+tid,headers=AUTH).json()['status']=='cancelled'
    with client_for(tmp_path,run_worker=False) as c:
        assert c.get('/v1/tasks/'+tid,headers=AUTH).json()['status']=='cancelled'


def test_bounded_task_queue_and_invalid_options(tmp_path):
    with client_for(tmp_path,run_worker=False,max_pending=1) as c:
        fid=c.post('/v1/files',headers=AUTH,files={'file':('a.wav',b'audio')}).json()['id']
        assert c.post('/v1/tasks',headers=AUTH,json={'kind':'not-allowed','file_id':fid}).status_code==422
        assert c.post('/v1/tasks',headers=AUTH,json={'kind':'transcribe','file_id':fid,'options':{'url':'http://example.com'}}).status_code==422
        assert c.post('/v1/tasks',headers=AUTH,json={'kind':'transcribe','file_id':fid}).status_code==202
        assert c.post('/v1/tasks',headers=AUTH,json={'kind':'audio_understand','file_id':fid}).status_code==429
