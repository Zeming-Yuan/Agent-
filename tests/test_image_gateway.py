import json
import httpx
from fastapi.testclient import TestClient
from image_test_harness import image_app as create_app

AUTH={'Authorization':'Bearer test-secret-token'}

def app(tmp_path, handler=None, **kwargs):
    def upstream(req):
        if handler:
            return handler(req)
        if req.url.path=='/system_stats':
            return httpx.Response(200,json={'system':{'comfyui_version':'0.33.2'}})
        return httpx.Response(200,json={'status':'ready'})
    return TestClient(create_app(tmp_path,'test-secret-token',transport=httpx.MockTransport(upstream),
                                 audio_enabled=False, images_enabled=True, **kwargs))

def test_image_profile_has_no_audio_health_or_discovery_dependency(tmp_path):
    seen=[]
    def backend(req):
        seen.append(req.url.port)
        return httpx.Response(200,json={'system':{}} if req.url.path=='/system_stats' else {'status':'ready'})
    with app(tmp_path,backend,run_worker=False) as c:
        r=c.get('/health',headers=AUTH)
        assert r.status_code==200
        assert set(r.json()['backends'])=={'main','image'}
        assert 18011 not in seen and 18012 not in seen
        models=c.get('/v1/models',headers=AUTH).json()['data']
        assert {x['id'] for x in models}=={'spark-main','spark-image','spark-image-edit'}
        assert next(x for x in models if x['id']=='spark-image-edit')['capabilities']==['image_edit']
        fid=c.post('/v1/files',headers=AUTH,files={'file':('a.wav',b'old audio')}).json()['id']
        assert c.post('/v1/tasks',headers=AUTH,json={'kind':'transcribe','file_id':fid}).status_code==410
        assert c.post('/v1/audio/transcriptions',headers=AUTH,data={'model':'whisper-large-v3-turbo'},files={'file':('x.wav',b'a')}).status_code==410

def test_image_task_validation_idempotency_queue_and_cancel(tmp_path):
    with app(tmp_path,run_worker=False,max_pending=1) as c:
        body={'kind':'image_generate','options':{'prompt':'一张电商背景，中央留白'}}
        h={**AUTH,'Idempotency-Key':'image-one'}
        a=c.post('/v1/tasks',headers=h,json=body)
        assert a.status_code==202
        assert a.json()['file_id'] is None
        assert c.post('/v1/tasks',headers=h,json=body).json()['id']==a.json()['id']
        assert c.post('/v1/tasks',headers=AUTH,json=body).status_code==429
        tid=a.json()['id']
        assert c.post(f'/v1/tasks/{tid}/cancel',headers=AUTH).json()['status']=='cancelled'
        for options in ({'prompt':'x','size':'8192x8192'},{'prompt':'x','n':4},{'prompt':'x','workflow':{}},{'prompt':'x','image_ids':['http://evil']}):
            assert c.post('/v1/tasks',headers=AUTH,json={'kind':'image_generate','options':options}).status_code==422
        assert c.post('/v1/tasks',headers=AUTH,json={'kind':'image_edit','options':{'prompt':'换背景'}}).status_code==422
        assert c.post('/v1/images/generations',headers=AUTH,json={'model':'spark-main','prompt':'x'}).status_code in (404,422)
        assert c.post('/v1/images/generations',headers=AUTH,json={'model':'spark-image','prompt':'x','n':2}).status_code==422

def test_edit_references_cannot_be_deleted_while_queued(tmp_path):
    with app(tmp_path,run_worker=False) as c:
        ids=[c.post('/v1/files',headers=AUTH,files={'file':('x.png',b'image')}).json()['id'] for _ in range(2)]
        r=c.post('/v1/tasks',headers=AUTH,json={'kind':'image_edit','options':{'prompt':'将图一商品放进图二场景','image_ids':ids}})
        assert r.status_code==202
        for fid in ids:
            assert c.delete('/v1/files/'+fid,headers=AUTH).status_code==409
        c.post('/v1/tasks/'+r.json()['id']+'/cancel',headers=AUTH)
        assert c.delete('/v1/files/'+ids[1],headers=AUTH).status_code==200
