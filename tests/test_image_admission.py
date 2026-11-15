import httpx
from fastapi.testclient import TestClient
from services.gateway import create_app

AUTH={'Authorization':'Bearer test-secret-token'}

def test_unavailable_backend_rejects_new_image_jobs_without_queuing(tmp_path):
    def backend(req):
        if req.url.path=='/system_stats':raise httpx.ConnectError('offline',request=req)
        return httpx.Response(200,json={'status':'ready'})
    application=create_app(tmp_path,'test-secret-token',transport=httpx.MockTransport(backend),audio_enabled=False,images_enabled=True,run_worker=False)
    with TestClient(application) as c:
        for url,body in [('/v1/tasks',{'kind':'image_generate','options':{'prompt':'computer'}}),('/v1/images/generations',{'model':'spark-image','prompt':'computer'})]:
            r=c.post(url,headers=AUTH,json=body)
            assert r.status_code==503,r.text
            assert 'unavailable' in r.text.lower()
        r=c.post('/v1/images/edits',headers=AUTH,data={'prompt':'blue product'},files={'image':('source.png',b'image','image/png')})
        assert r.status_code==503,r.text
        assert application.state.store.next_task(image=True) is None
