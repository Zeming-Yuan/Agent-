import time
import httpx
from fastapi.testclient import TestClient
from services.gateway import create_app
AUTH={'Authorization':'Bearer test-secret-token'}


def test_unknown_submit_outcome_halts_image_admission_and_degrades_health(tmp_path):
    def backend(req):
        if req.url.path=='/prompt':raise httpx.ReadTimeout('unknown acceptance',request=req)
        if req.url.path=='/queue':return httpx.Response(200,json={'queue_running':[],'queue_pending':[]})
        if req.url.path=='/system_stats':return httpx.Response(200,json={'system':{}})
        return httpx.Response(200,json={'status':'ready'})
    with TestClient(create_app(tmp_path,'test-secret-token',transport=httpx.MockTransport(backend),audio_enabled=False,images_enabled=True)) as c:
        first=c.post('/v1/tasks',headers=AUTH,json={'kind':'image_generate','options':{'prompt':'one'}}).json()['id']
        second=c.post('/v1/tasks',headers=AUTH,json={'kind':'image_generate','options':{'prompt':'two'}}).json()['id']
        for _ in range(100):
            state=c.get('/v1/tasks/'+first,headers=AUTH).json()
            if state['status']=='failed':break
            time.sleep(.02)
        assert state['status']=='failed' and 'unknown' in state['error']
        assert c.get('/v1/tasks/'+second,headers=AUTH).json()['status']=='queued'
        assert c.get('/health',headers=AUTH).status_code==503

        rejected=c.post('/v1/tasks',headers=AUTH,json={'kind':'image_generate','options':{'prompt':'new'}})
        assert rejected.status_code==503
        assert 'unavailable' in rejected.text.lower()
        assert c.app.state.store.next_task(image=True)['id']==second
