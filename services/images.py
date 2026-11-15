"""Single-owner ComfyUI worker, fixed image graphs and private output storage."""
import asyncio
import contextlib
import io
import logging
import os
import time
import uuid
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from fastapi import HTTPException

from .image_resources import ReleaseUnconfirmed, ResourceWaitExpired
from .image_telemetry import record_cached_nodes, record_current_task, task_event, task_transition

LOG=logging.getLogger('agent-mm.images')
Image.MAX_IMAGE_PIXELS=16_000_000


def validate_image(data):
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format not in ('PNG','JPEG','WEBP') or image.width*image.height>16_000_000:
                raise ValueError('Use PNG/JPEG/WebP up to 16 megapixels')
            image.load()
    except (OSError,Image.DecompressionBombError,Image.DecompressionBombWarning) as exc:
        raise ValueError('Invalid or oversized image') from exc


def compose_image(background, foreground=None, title=''):
    validate_image(background)
    canvas=Image.open(io.BytesIO(background)).convert('RGBA')
    if foreground:
        validate_image(foreground)
        product=Image.open(io.BytesIO(foreground)).convert('RGBA')
        low,high=product.getchannel('A').getextrema()
        if low==255 or high==0: raise ValueError('Product foreground must be a visible transparent PNG')
        product.thumbnail((int(canvas.width*.75),int(canvas.height*.7)),Image.Resampling.LANCZOS)
        canvas.alpha_composite(product,((canvas.width-product.width)//2,int(canvas.height*.9)-product.height))
    if title:
        path=os.getenv('IMAGE_FONT','/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc')
        font=ImageFont.truetype(path,max(18,canvas.width//18))
        draw=ImageDraw.Draw(canvas)
        while draw.textbbox((0,0),title,font=font)[2]>canvas.width*.9 and font.size>12:
            font=ImageFont.truetype(path,font.size-2)
        draw.text((canvas.width//2,canvas.height*.07),title,font=font,anchor='mt',fill='white',stroke_width=2,stroke_fill='black')
    result=io.BytesIO();canvas.convert('RGB').save(result,format='PNG');return result.getvalue()


def workflow(options, prefix, images=()):
    width,height=map(int,options['size'].split('x'))
    edit=bool(images)
    graph={
        '1':{'class_type':'UNETLoader','inputs':{'unet_name':'qwen_image_edit_2511_bf16.safetensors' if edit else 'z_image_turbo_bf16.safetensors','weight_dtype':'default'}},
        '2':{'class_type':'CLIPLoader','inputs':{'clip_name':'qwen_2.5_vl_7b.safetensors' if edit else 'qwen_3_4b.safetensors','type':'qwen_image' if edit else 'lumina2','device':'default'}},
        '3':{'class_type':'VAELoader','inputs':{'vae_name':'qwen_image_vae.safetensors' if edit else 'ae.safetensors'}},
        '6':{'class_type':'EmptySD3LatentImage','inputs':{'width':width,'height':height,'batch_size':1}},
        '7':{'class_type':'KSampler','inputs':{'model':['10',0],'positive':['4',0],'negative':['5',0],'latent_image':['6',0],
             'seed':options['seed'],'steps':(40 if options['quality']=='high' else 20) if edit else 8,
             'cfg':4.0 if edit else 1.0,'sampler_name':'euler' if edit else 'res_multistep','scheduler':'simple','denoise':1.0}},
        '8':{'class_type':'VAEDecode','inputs':{'samples':['7',0],'vae':['3',0]}},
        '9':{'class_type':'SaveImage','inputs':{'images':['8',0],'filename_prefix':prefix}},
        '10':{'class_type':'ModelSamplingAuraFlow','inputs':{'model':['1',0],'shift':3.1 if edit else 3.0}},
    }
    if edit:
        graph['11']={'class_type':'CFGNorm','inputs':{'model':['10',0],'strength':1.0}}
        graph['7']['inputs']['model']=['11',0]
        if options['quality']=='fast':
            graph['12']={'class_type':'LoraLoaderModelOnly','inputs':{'model':['11',0],'lora_name':'Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors','strength_model':1.0}}
            graph['7']['inputs'].update(model=['12',0],steps=4,cfg=1.0)
        graph['4']={'class_type':'TextEncodeQwenImageEditPlus','inputs':{'clip':['2',0],'vae':['3',0],'prompt':options['prompt']}}
        graph['5']={'class_type':'TextEncodeQwenImageEditPlus','inputs':{'clip':['2',0],'vae':['3',0],'prompt':''}}
        for index,name in enumerate(images):
            node=str(20+index);graph[node]={'class_type':'LoadImage','inputs':{'image':name}}
            for target in ('4','5'):graph[target]['inputs'][f'image{index+1}']=[node,0]
    else:
        graph['4']={'class_type':'CLIPTextEncode','inputs':{'clip':['2',0],'text':options['prompt']}}
        graph['5']={'class_type':'ConditioningZeroOut','inputs':{'conditioning':['4',0]}}
    return graph


def memory_available():
    for line in Path('/proc/meminfo').read_text().splitlines():
        if line.startswith('MemAvailable:'): return int(line.split()[1])*1024
    return 0


async def clear_backend(client,url,prompt_id=None):
    # Dedicated private ComfyUI instance: startup may clear leftovers, task cleanup is targeted.
    if prompt_id:
        r=await client.post(url+'/queue',json={'delete':[prompt_id]},timeout=10);r.raise_for_status()
        r=await client.post(url+'/interrupt',json={'prompt_id':prompt_id},timeout=10);r.raise_for_status()
    else:
        r=await client.post(url+'/queue',json={'clear':True},timeout=10);r.raise_for_status()
        r=await client.post(url+'/interrupt',json={},timeout=10);r.raise_for_status()
    for _ in range(150):
        r=await client.get(url+'/queue',timeout=10);r.raise_for_status();state=r.json()
        ids=[x[1] for x in state['queue_running']+state['queue_pending']]
        if (prompt_id not in ids) if prompt_id else not ids: return
        await asyncio.sleep(.2)
    raise RuntimeError('Image backend did not stop; queue held for safety')


class SubmissionUncertain(RuntimeError):
    """Stop admission until the dedicated backend and gateway are restarted."""


class BackendExecutionFailed(RuntimeError):
    """Sanitized execution failure belonging to the current prompt."""


class CleanupUncertain(RuntimeError):
    """Serial control cannot be released to another image task."""


async def settled_post(client,url,**kwargs):
    # Do not abandon server-side validation/enqueue when the caller is cancelled.
    request=asyncio.create_task(client.post(url,timeout=30,**kwargs))
    try:
        return await asyncio.shield(request)
    except asyncio.CancelledError:
        try:
            await asyncio.shield(request)
        except (Exception,asyncio.CancelledError) as exc:
            raise SubmissionUncertain('Backend submission outcome unknown; restart image backend and gateway') from exc
        raise
    except Exception as exc:
        raise SubmissionUncertain('Backend submission outcome unknown; restart image backend and gateway') from exc


async def settle(coro):
    """Wait for owned cleanup or file I/O through repeated native cancellation."""
    job=asyncio.create_task(coro)
    interrupted=False
    while not job.done():
        try:
            await asyncio.shield(job)
        except asyncio.CancelledError:
            interrupted=True
        except Exception:
            break
    result=job.result()
    if interrupted:raise asyncio.CancelledError
    return result


def cleanup_scratch(store,tid=None,names=()):
    output=store.root/'comfy'/'output'/'agent-mm'
    for path in output.glob((tid or 'task-')+'*.png'):
        if path.is_file():path.unlink(missing_ok=True)
    inputs=store.root/'comfy'/'input'
    if tid is None:
        for path in inputs.glob('file-*.png'):
            if path.is_file():path.unlink(missing_ok=True)
    else:
        for name in names:
            if Path(name).name==name:(inputs/name).unlink(missing_ok=True)


def reclaim_result(store, fid, *, owner):
    """Failure to reclaim an owned, undelivered result is uncertain cleanup."""
    try:
        store.delete_file(fid,owner=owner)
    except Exception as exc:
        if isinstance(exc,HTTPException) and exc.status_code==404:
            return
        raise CleanupUncertain('Image result reclamation unconfirmed; operator recovery required') from exc


async def process_image(item,store,client,url,*,unload_models=True,event_stream_factory=None, admission=None):
    opts=item['options'];tid=item['id'];pid=None;submitted=False;names=[];watcher=None;saved_fid=None;result_ready=False;backend_failed=False;events_lost=False
    streams=contextlib.AsyncExitStack()
    owner=store.worker_task(tid)['owner']
    if admission is None and memory_available()<20*1024**3:raise RuntimeError('Image admission: available memory below 20GiB')
    try:
        if admission is not None:await asyncio.to_thread(admission.validate_inputs,item,store)
        for fid in opts['image_ids']:
            data=await asyncio.to_thread(store.path(fid,owner=owner).read_bytes)
            await asyncio.to_thread(validate_image,data)
            expected=fid+'.png';names.append(expected)
            r=await settled_post(client,url+'/upload/image',files={'image':(expected,data,'image/png')},data={'type':'input','overwrite':'true'})
            r.raise_for_status();uploaded=r.json()
            name=uploaded['name'];folder=uploaded.get('subfolder','')
            if Path(name).name!=name or folder:raise RuntimeError('Invalid image backend upload path')
            names[-1]=name
        if unload_models:
            r=await settled_post(client,url+'/free',json={'unload_models':True,'free_memory':True});r.raise_for_status()
        if admission is None:task_event(store,tid,{'type':'stage','stage':'loading'})
        # ComfyUI requires a canonical UUID. Hold it before sending any bytes.
        pid=str(uuid.uuid4())
        if event_stream_factory is not None:
            from .comfy_events import normalize_event
            try:
                stream=await streams.enter_async_context(event_stream_factory(url,tid))
            except Exception:
                stream=None;events_lost=True
                task_event(store,tid,{'type':'observation_lost'})
            async def observe():
                nonlocal backend_failed,events_lost
                active_node=None
                try:
                    async for raw in stream.events():
                        record_cached_nodes(store,tid,pid,raw)
                        event=normalize_event(raw,pid,active_node)
                        if event is not None:
                            if event['type']=='backend_error':backend_failed=True
                            else:
                                task=task_event(store,tid,event)
                                if 'node' in event and task['stage']==event['stage']:
                                    active_node=event['node']
                    events_lost=True
                    task_event(store,tid,{'type':'observation_lost'})
                except Exception:
                    events_lost=True
                    task_event(store,tid,{'type':'observation_lost'})
            if stream is not None:watcher=asyncio.create_task(observe())
        if admission is not None:
            if not await admission.prepare(item,store,client,url):return None
            if memory_available()<20*1024**3:raise ResourceWaitExpired('Image memory fell below20GiB before start')
            current=store.worker_task(tid)
            claimed=task_transition(store,tid,status='running',stage='loading',expected_seq=current['stage_seq'])
            if claimed['status'] != 'running':return None
            if events_lost:task_event(store,tid,{'type':'observation_lost'})
        record_current_task(store,tid,prompt_id=pid,event='submit_started')
        if admission is not None:admission.recheck(item)
        submitted=True
        r=await settled_post(client,url+'/prompt',json={'prompt':workflow(opts,'agent-mm/'+tid,names),'client_id':tid,'prompt_id':pid})
        r.raise_for_status();pid=r.json()['prompt_id']
        deadline=time.monotonic()+900
        while time.monotonic()<deadline:
            if backend_failed:raise BackendExecutionFailed('Image backend execution failed')
            r=await client.get(url+'/history/'+pid);r.raise_for_status();history=r.json().get(pid)
            if history:
                status=history.get('status',{})
                if status.get('status_str')=='error': raise RuntimeError('Image inference failed')
                if status.get('completed'):
                    task_event(store,tid,{'type':'stage','stage':'saving'})
                    output=history['outputs']['9']['images'][0]
                    if output.get('type')!='output' or Path(output['filename']).name!=output['filename']:
                        raise RuntimeError('Invalid image output reference')
                    r=await client.get(url+'/view',params={k:output[k] for k in ('filename','subfolder','type')})
                    r.raise_for_status()
                    if len(r.content)>32*1024*1024:raise RuntimeError('Generated image too large')
                    fg=await asyncio.to_thread(store.path(opts['foreground_file_id'],owner=owner).read_bytes) if opts['foreground_file_id'] else None
                    data=await asyncio.to_thread(compose_image,r.content,fg,opts['title'])
                    fid='file-'+uuid.uuid4().hex;saved_fid=fid
                    await settle(asyncio.to_thread(store.save_generated,fid,data,'generated.png',owner=owner))
                    result_ready=True
                    return {'file_id':fid,'content_url':'/v1/files/'+fid+'/content','mime_type':'image/png',
                            'model':'spark-image-edit' if opts['image_ids'] else 'spark-image','seed':opts['seed'],'quality':opts['quality'],
                            'note':'编辑结果需核对商品标识、外形与文字。' if opts['image_ids'] else '透明前景合成保留商品外观。' if fg else 'AI生成图片。'}
            await asyncio.sleep(.5)
        raise TimeoutError('Image inference timeout')
    finally:
        record_current_task(store,tid,operation='cleanup',event='cleanup_started')
        def discard_result():
            if saved_fid:
                reclaim_result(store,saved_fid,owner=owner)
        async def cleanup():
            try:
                if watcher:
                    watcher.cancel()
                    with contextlib.suppress(asyncio.CancelledError):await watcher
                try:
                    await streams.aclose()
                except Exception:
                    task_event(store,tid,{'type':'observation_lost'})
                if submitted:
                    await clear_backend(client,url,pid)
                    response=await client.post(url+'/history',json={'delete':[pid]},timeout=10)
                    response.raise_for_status()
            finally:
                cleanup_scratch(store,tid,names)
        try:
            await settle(cleanup())
        except asyncio.CancelledError:
            discard_result()
            raise
        except Exception as exc:
            discard_result()
            raise CleanupUncertain('Image cleanup unconfirmed; operator recovery required') from exc
        if not result_ready:discard_result()



async def image_worker(store,client,url,active,*,event_stream_factory=None,admission=None):
    initialized=False
    while True:
        if not initialized:
            try:
                await clear_backend(client,url)
                r=await client.post(url+'/history',json={'clear':True},timeout=10);r.raise_for_status()
                cleanup_scratch(store)
                initialized=True
            except Exception:
                LOG.warning('Image startup cleanup unconfirmed; admission stopped')
                return
        item=store.next_task(image=True)
        if item is None:
            await asyncio.sleep(.2);continue
        tid=item['id']
        job=asyncio.create_task(process_image(item,store,client,url,unload_models=False,
                                            event_stream_factory=event_stream_factory,admission=admission));active[tid]=job
        try:
            result=await job
            if result is None:continue
            task=store.worker_task(tid)
            if task['cancel_requested']:
                reclaim_result(store,result['file_id'],owner=task['owner'])
                task_transition(store,tid,status='cancelled',stage='cancelled',expected_seq=task['stage_seq'])
            else:
                task_transition(store,tid,status='completed',stage='completed',expected_seq=task['stage_seq'],result=result)
        except asyncio.CancelledError:
            task=store.worker_task(tid)
            if task['cancel_requested']:
                task_transition(store,tid,status='cancelled',stage='cancelled',expected_seq=task['stage_seq'])
                if asyncio.current_task().cancelling():raise
            elif task['status']=='queued':
                # No inference was submitted. Preserve the accepted intent for restart.
                raise
            else:
                store.update(tid,status='failed',error='Image worker interrupted')
                record_current_task(store,tid)
                raise
        except BackendExecutionFailed:
            task_event(store,tid,{'type':'failed','error':'Image backend execution failed',
                             'blocked_reason':'backend_execution_error'})
            initialized=False
        except ReleaseUnconfirmed:
            task_event(store,tid,{'type':'failed','error':'Model release unconfirmed; operator recovery required',
                                  'blocked_reason':'release_unconfirmed'})
            return
        except ResourceWaitExpired as exc:
            task_event(store,tid,{'type':'failed','error':str(exc),'blocked_reason':'resource_wait_expired'})
        except SubmissionUncertain:
            LOG.exception('image backend outcome uncertain; admission stopped')
            task_event(store,tid,{'type':'failed','error':'Image submission outcome unknown; restart image backend and gateway',
                             'blocked_reason':'submission_unknown'})
            return
        except CleanupUncertain:
            LOG.exception('image cleanup unconfirmed; admission stopped')
            task_event(store,tid,{'type':'failed','error':'Image cleanup unconfirmed; restart image backend and gateway',
                             'blocked_reason':'cleanup_unconfirmed'})
            return
        except Exception as exc:
            LOG.exception('image task %s failed (%s)',tid,type(exc).__name__)
            task_event(store,tid,{'type':'failed','error':'Image processing failed; see service log'})
            initialized=False
        finally:
            active.pop(tid,None)
