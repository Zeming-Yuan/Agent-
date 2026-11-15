import asyncio
import json
import time
import httpx
from fastapi.testclient import TestClient
from services.gateway import create_app

AUTH={'Authorization':'Bearer test-secret-token'}


def test_cancelling_running_image_is_targeted_and_next_job_can_finish(tmp_path):
    running=[];submitted=[];interrupts=[]
    # External inference is the only fake; real HTTP routes, store and worker run.
    from PIL import Image
    import io
    buf=io.BytesIO();Image.new('RGB',(8,8),'red').save(buf,format='PNG')
    def backend(req):
        if req.url.path=='/system_stats':return httpx.Response(200,json={'system':{}})
        path=req.url.path
        if path=='/queue' and req.method=='GET':
            return httpx.Response(200,json={'queue_running':[[0,pid,{}, {}, []] for pid in running],'queue_pending':[]})
        if path=='/interrupt':
            body=json.loads(req.content);interrupts.append(body)
            pid=body.get('prompt_id')
            if pid in running:running.remove(pid)
            return httpx.Response(200,json={})
        if path=='/prompt':
            assert not running,'previous GPU work leaked across cancellation'
            pid='gpu-'+str(len(submitted));submitted.append(pid);running.append(pid)
            return httpx.Response(200,json={'prompt_id':pid})
        if path.startswith('/history/'):
            pid=path.rsplit('/',1)[-1]
            if pid=='gpu-0':return httpx.Response(200,json={})
            if pid in running:running.remove(pid)
            return httpx.Response(200,json={pid:{'status':{'status_str':'success','completed':True,'messages':[]},'outputs':{'9':{'images':[{'filename':'done.png','subfolder':'','type':'output'}]}}}})
        if path=='/view':return httpx.Response(200,content=buf.getvalue())
        return httpx.Response(200,json={})
    with TestClient(create_app(tmp_path,'test-secret-token',transport=httpx.MockTransport(backend),audio_enabled=False,images_enabled=True)) as c:
        def submit():return c.post('/v1/tasks',headers=AUTH,json={'kind':'image_generate','options':{'prompt':'x'}}).json()['id']
        first=submit()
        for _ in range(100):
            if running:break
            time.sleep(.02)
        assert running==['gpu-0']
        c.post('/v1/tasks/'+first+'/cancel',headers=AUTH)
        second=submit()
        for _ in range(150):
            state=c.get('/v1/tasks/'+second,headers=AUTH).json()
            if state['status'] in ('completed','failed'):break
            time.sleep(.02)
        assert state['status']=='completed',state
        assert c.get('/v1/tasks/'+first,headers=AUTH).json()['status']=='cancelled'
        assert {'prompt_id':'gpu-0'} in interrupts
        assert all(x.get('prompt_id') for x in interrupts[1:])
