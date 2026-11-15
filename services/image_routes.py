"""OpenAI image endpoints backed by durable local tasks."""
import asyncio
import base64
import json
import time
from fastapi import File, Form, HTTPException, Request, UploadFile
from pydantic import ValidationError
from .image_options import ImageGenerationBody, ImageOptions


def register_image_routes(app, store, upload_lock, submit_image, ensure_image_available):
    async def wait_result(task, request):
        tid=task['id']
        deadline=time.monotonic()+570
        while True:
            state=store.task(tid,owner=request.state.principal.owner)
            if state['status']=='completed':
                fid=state['result']['file_id']
                return {'created':state['updated'],'data':[{'b64_json':base64.b64encode(store.path(fid,owner=request.state.principal.owner).read_bytes()).decode(),
                        'file_id':fid}],'task_id':tid}
            if state['status'] in ('failed','cancelled'):
                raise HTTPException(503 if state['status']=='failed' else 409,state['error'] or 'Image task cancelled')
            if await request.is_disconnected():
                raise asyncio.CancelledError()
            if time.monotonic()>deadline:
                # Work persists; return the ID so a timeout never causes a blind duplicate.
                raise HTTPException(504,{'message':'Image task still pending; poll task_id','task_id':tid})
            await asyncio.sleep(.15)

    @app.post('/v1/images/generations')
    async def generate(body: ImageGenerationBody, request: Request):
        if body.image_ids: raise HTTPException(422,'Use /v1/images/edits for reference images')
        options=ImageOptions.model_validate(body.model_dump(exclude={'model','n','response_format'}))
        if options.foreground_file_id:
            store.file(options.foreground_file_id,owner=request.state.principal.owner)
        task=await submit_image('image_generate',options,request.headers.get('idempotency-key'),request.state.principal.owner)
        return await wait_result(task,request)

    @app.post('/v1/images/edits')
    async def edit(request: Request, image: list[UploadFile] | None = File(None),
                   image_array: list[UploadFile] | None = File(None,alias='image[]'),
                   prompt: str = Form(...), model: str = Form('spark-image-edit'),
                   size: str = Form('1024x1024'), quality: str = Form('standard'),
                   n: int = Form(1), response_format: str = Form('b64_json'), seed: int = Form(0)):
        # Without a replay key there is no existing request to recover. Preserve
        # early offline rejection before writing multipart reference files.
        if not request.headers.get('idempotency-key'):
            await ensure_image_available()
        image=(image or [])+(image_array or [])
        fields=await request.form()
        unsupported=set(fields)-{'image','image[]','prompt','model','size','quality','n','response_format','seed'}
        if unsupported:raise HTTPException(422,'Unsupported edit fields: '+','.join(sorted(unsupported)))
        if model!='spark-image-edit': raise HTTPException(404,'Use spark-image-edit')
        if n!=1 or response_format!='b64_json' or not 1<=len(image)<=3:
            raise HTTPException(422,'Use 1 to 3 images, n=1, response_format=b64_json')
        try:
            options=ImageOptions(prompt=prompt,size=size,quality=quality,seed=seed)
        except ValidationError as exc:
            raise HTTPException(422,str(exc))
        ids=[];created=[];task=None
        try:
            from .images import validate_image
            async with upload_lock:
                try:
                    # Serialize reference ownership until admission commits or rolls back.
                    for file in image:
                        data=await file.read(12*1024*1024+1)
                        if len(data)>12*1024*1024: raise HTTPException(413,'Each image must be <=12MiB')
                        try: await asyncio.to_thread(validate_image,data)
                        except ValueError as exc: raise HTTPException(422,str(exc))
                        item, is_new=store.save_reference(data,owner=request.state.principal.owner)
                        fid=item['id']
                        if is_new: created.append(fid)
                        ids.append(fid)
                    options.image_ids=ids
                    task=await submit_image('image_edit',options,request.headers.get('idempotency-key'),request.state.principal.owner)
                except BaseException:
                    for fid in created:
                        try:store.delete_file(fid,owner=request.state.principal.owner)
                        except HTTPException as exc:
                            if exc.status_code not in (404,409):raise
                    raise
            return await wait_result(task,request)
        finally:
            for file in image: await file.close()
