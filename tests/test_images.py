import asyncio
import base64
import io
import json
import time
from PIL import Image
import httpx
from fastapi.testclient import TestClient
from services.gateway import create_app
AUTH={'Authorization':'Bearer test-secret-token'}


def png(color='red',size=(32,32)):
    stream=io.BytesIO(); Image.new('RGB',size,color).save(stream,format='PNG'); return stream.getvalue()


def test_sync_image_result_persisted_and_edit_workflow_uses_reference(tmp_path):
    payloads=[]
    def backend(req):
        if req.url.path=='/system_stats':return httpx.Response(200,json={'system':{}})
        path=req.url.path
        if path=='/prompt':
            payloads.append(json.loads(req.content))
            return httpx.Response(200,json={'prompt_id':'gpu-job'})
        if path=='/history/gpu-job':
            return httpx.Response(200,json={'gpu-job':{'status':{'completed':True,'status_str':'success','messages':[]},'outputs':{'9':{'images':[{'filename':'one.png','subfolder':'','type':'output'}]}}}})
        if path=='/view': return httpx.Response(200,content=png(),headers={'Content-Type':'image/png'})
        if path=='/upload/image': return httpx.Response(200,json={'name':'reference.png','subfolder':''})
        if path=='/queue': return httpx.Response(200,json={'queue_running':[],'queue_pending':[]})
        return httpx.Response(200,json={})
    with TestClient(create_app(tmp_path,'test-secret-token',transport=httpx.MockTransport(backend),audio_enabled=False,images_enabled=True)) as c:
        r=c.post('/v1/images/generations',headers=AUTH,json={'model':'spark-image','prompt':'白色桌面上的玻璃水杯','seed':11})
        assert r.status_code==200, r.text
        assert Image.open(io.BytesIO(base64.b64decode(r.json()['data'][0]['b64_json']))).size==(32,32)
        fid=r.json()['data'][0]['file_id']
        assert c.get('/v1/files/'+fid+'/content',headers=AUTH).headers['content-type']=='image/png'
        r=c.post('/v1/images/edits',headers=AUTH,data={'model':'spark-image-edit','prompt':'将杯子改成蓝色'},files={'image':('cup.png',png(),'image/png')})
        assert r.status_code==200,r.text
        classes=[x['class_type'] for x in payloads[-1]['prompt'].values()]
        assert 'TextEncodeQwenImageEditPlus' in classes and 'LoadImage' in classes


def test_backend_failure_marks_image_task_failed_without_output(tmp_path):
    def backend(req):
        if req.url.path=='/system_stats':return httpx.Response(200,json={'system':{}})
        if req.url.path=='/queue': return httpx.Response(200,json={'queue_running':[],'queue_pending':[]})
        if req.url.path in ('/interrupt','/history'): return httpx.Response(200,json={})
        return httpx.Response(500,json={'error':'CUDA OOM'})
    with TestClient(create_app(tmp_path,'test-secret-token',transport=httpx.MockTransport(backend),audio_enabled=False,images_enabled=True)) as c:
        r=c.post('/v1/tasks',headers=AUTH,json={'kind':'image_generate','options':{'prompt':'x'}})
        tid=r.json()['id']
        for _ in range(100):
            state=c.get('/v1/tasks/'+tid,headers=AUTH).json()
            if state['status']=='failed': break
            time.sleep(.02)
        assert state['status']=='failed' and state['result'] is None


def test_composition_preserves_product_and_rejects_opaque_product():
    from services.images import compose_image
    bg=png('blue',(128,128))
    buf=io.BytesIO(); fg=Image.new('RGBA',(16,16),(255,0,0,255)); fg.putpixel((0,0),(0,0,0,0)); fg.save(buf,format='PNG')
    out=Image.open(io.BytesIO(compose_image(bg,buf.getvalue(),'')))
    assert out.getpixel((64,110))[:3]==(255,0,0)
    import pytest
    with pytest.raises(ValueError,match='transparent'):
        compose_image(bg,png(),'')


def test_edit_retry_with_idempotency_key_reuses_task_and_reference(tmp_path):
    submitted=[]
    def backend(req):
        if req.url.path=='/system_stats':return httpx.Response(200,json={'system':{}})
        if req.url.path=='/queue':return httpx.Response(200,json={'queue_running':[],'queue_pending':[]})
        if req.url.path=='/prompt':
            submitted.append(True);return httpx.Response(200,json={'prompt_id':'edit'})
        if req.url.path=='/upload/image':return httpx.Response(200,json={'name':'reference.png','subfolder':''})
        if req.url.path=='/history/edit':return httpx.Response(200,json={'edit':{'status':{'completed':True,'status_str':'success'},'outputs':{'9':{'images':[{'filename':'done.png','subfolder':'','type':'output'}]}}}})
        if req.url.path=='/view':return httpx.Response(200,content=png())
        return httpx.Response(200,json={})
    with TestClient(create_app(tmp_path,'test-secret-token',transport=httpx.MockTransport(backend),audio_enabled=False,images_enabled=True)) as c:
        kwargs={'headers':{**AUTH,'Idempotency-Key':'edit-retry'},'data':{'model':'spark-image-edit','prompt':'蓝色杯子'},'files':{'image':('cup.png',png(),'image/png')}}
        first=c.post('/v1/images/edits',**kwargs)
        second=c.post('/v1/images/edits',**kwargs)
        assert first.status_code==second.status_code==200,(first.text,second.text)
        assert first.json()['task_id']==second.json()['task_id']
        assert len(submitted)==1


def test_upload_storage_quota_rechecks_generated_file_commit(tmp_path):
    from services.store import Store
    from fastapi import HTTPException
    import pytest
    store=Store(tmp_path)
    # A competing generated result already used the remaining allocation.
    store.add_file('file-'+'f'*32,'existing.png',2*1024**3-4)
    with pytest.raises(HTTPException) as failure:
        store.add_file('file-'+'a'*32,'upload.png',5)
    assert failure.value.status_code==413


def test_image_submission_uses_uuid_and_cancel_during_post_cleans_up(tmp_path):
    import uuid
    from services.images import process_image
    from services.store import Store
    from services.image_options import ImageOptions
    store=Store(tmp_path)
    item=store.submit('image_generate',None,ImageOptions(prompt='x').model_dump(),None)
    accepted=[];interrupted=[];running=[]
    async def check():
        entered=asyncio.Event();release=asyncio.Event()
        async def backend(req):
            if req.url.path=='/prompt':
                value=json.loads(req.content)['prompt_id']
                try:
                    assert str(uuid.UUID(value))==value
                except (ValueError,AssertionError):
                    entered.set();return httpx.Response(400,json={'error':'prompt_id must be UUID'})
                entered.set();await release.wait()
                accepted.append(value);running.append(value)
                return httpx.Response(200,json={'prompt_id':value})
            if req.url.path=='/interrupt':
                pid=json.loads(req.content).get('prompt_id');interrupted.append(pid)
                if pid in running:running.remove(pid)
            if req.url.path=='/queue':return httpx.Response(200,json={'queue_running':[[0,p,{}, {}, []] for p in running],'queue_pending':[]})
            return httpx.Response(200,json={})
        async with httpx.AsyncClient(transport=httpx.MockTransport(backend)) as c:
            job=asyncio.create_task(process_image(item,store,c,'http://127.0.0.1:18013'))
            await asyncio.wait_for(entered.wait(),1);job.cancel()
            await asyncio.sleep(.02)
            release.set()
            import pytest
            with pytest.raises(asyncio.CancelledError):await job
    asyncio.run(check())
    assert len(accepted)==1 and interrupted==accepted and not running


def test_rejected_edit_releases_only_new_unreferenced_uploads(tmp_path):
    with TestClient(create_app(tmp_path,'test-secret-token',run_worker=False,audio_enabled=False,images_enabled=True,max_pending=1)) as c:
        c.post('/v1/tasks',headers=AUTH,json={'kind':'image_generate','options':{'prompt':'x'}})
        r=c.post('/v1/images/edits',headers=AUTH,data={'prompt':'edit'},files={'image':('new.png',png())})
        assert r.status_code==429
        store=c.app.state.store
        with store.connect() as db:assert db.execute('SELECT count(*) FROM files').fetchone()[0]==0
        assert not list(store.files.iterdir())


def test_openai_sdk_image_array_reaches_image_edit_task(tmp_path):
    with TestClient(create_app(tmp_path,'test-secret-token',run_worker=False,audio_enabled=False,images_enabled=True,max_pending=1)) as c:
        # Fill the queue: correct multipart parsing reaches admission and returns429, not422 missing image.
        c.post('/v1/tasks',headers=AUTH,json={'kind':'image_generate','options':{'prompt':'x'}})
        r=c.post('/v1/images/edits',headers=AUTH,data={'prompt':'edit'},files=[('image[]',('one.png',png())),('image[]',('two.png',png('blue')))])
        assert r.status_code==429,r.text


def test_failed_reference_upload_removes_previous_comfy_scratch(tmp_path):
    from services.store import Store
    from services.images import process_image
    from services.image_options import ImageOptions
    store=Store(tmp_path);ids=['file-'+'1'*32,'file-'+'2'*32]
    for fid,color in zip(ids,['red','blue']):store.save_generated(fid,png(color),fid+'.png')
    item=store.submit('image_edit',ids[0],ImageOptions(prompt='x',image_ids=ids).model_dump(),None)
    folder=store.root/'comfy'/'input';folder.mkdir(parents=True)
    uploaded=[]
    def backend(req):
        if req.url.path=='/system_stats':return httpx.Response(200,json={'system':{}})
        if req.url.path=='/upload/image':
            if uploaded:return httpx.Response(500)
            uploaded.append('ref.png');(folder/'ref.png').write_bytes(png())
            return httpx.Response(200,json={'name':'ref.png','subfolder':''})
        return httpx.Response(200,json={})
    async def check():
        async with httpx.AsyncClient(transport=httpx.MockTransport(backend)) as c:
            import pytest
            with pytest.raises(httpx.HTTPStatusError):await process_image(item,store,c,'http://127.0.0.1:18013')
    asyncio.run(check())
    assert not list(folder.iterdir())


def test_unsupported_mask_is_rejected_before_any_edit_is_submitted(tmp_path):
    with TestClient(create_app(tmp_path,'test-secret-token',run_worker=False,audio_enabled=False,images_enabled=True,max_pending=1)) as c:
        c.post('/v1/tasks',headers=AUTH,json={'kind':'image_generate','options':{'prompt':'x'}})
        r=c.post('/v1/images/edits',headers=AUTH,data={'prompt':'只修改遮罩处'},files={'image':('image.png',png()),'mask':('mask.png',png())})
        assert r.status_code==422
        assert 'mask' in r.text
        with c.app.state.store.connect() as db:assert db.execute('SELECT count(*) FROM tasks').fetchone()[0]==1


def test_same_image_model_keeps_weights_between_jobs(tmp_path):
    frees=[]
    def backend(req):
        if req.url.path=='/system_stats':return httpx.Response(200,json={'system':{}})
        if req.url.path=='/queue':return httpx.Response(200,json={'queue_running':[],'queue_pending':[]})
        if req.url.path=='/free':frees.append(True)
        if req.url.path=='/prompt':return httpx.Response(200,json={'prompt_id':'job'})
        if req.url.path=='/history/job':return httpx.Response(200,json={'job':{'status':{'completed':True,'status_str':'success'},'outputs':{'9':{'images':[{'filename':'done.png','subfolder':'','type':'output'}]}}}})
        if req.url.path=='/view':return httpx.Response(200,content=png())
        return httpx.Response(200,json={})
    with TestClient(create_app(tmp_path,'test-secret-token',transport=httpx.MockTransport(backend),audio_enabled=False,images_enabled=True)) as c:
        for text in ('one','two'):
            assert c.post('/v1/images/generations',headers=AUTH,json={'prompt':text}).status_code==200
    # Reset only on model changes. Clearing every time destroys warm inference latency.
    assert len(frees)==1


def test_fast_editor_uses_acceleration_without_altering_standard_editor():
    from services.images import workflow
    from services.image_options import ImageOptions
    fast=workflow(ImageOptions(prompt='换背景',quality='fast').model_dump(),'test',['reference.png'])
    standard=workflow(ImageOptions(prompt='换背景',quality='standard').model_dump(),'test',['reference.png'])
    fast_sampling=next(x['inputs'] for x in fast.values() if x['class_type']=='KSampler')
    normal_sampling=next(x['inputs'] for x in standard.values() if x['class_type']=='KSampler')
    assert fast_sampling['steps']==4 and fast_sampling['cfg']==1.0
    assert normal_sampling['steps']==20 and normal_sampling['cfg']==4.0
    assert any(x['class_type']=='LoraLoaderModelOnly' for x in fast.values())
    assert not any(x['class_type']=='LoraLoaderModelOnly' for x in standard.values())
