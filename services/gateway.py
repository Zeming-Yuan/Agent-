"""OpenAI-compatible LAN gateway. No tools are executed by this service."""
import asyncio
import contextlib
import hmac
import json
import logging
import os
import re
import sqlite3
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
import httpx
import anyio
from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from .store import Store
from .identity import KeyRegistry
from .ownership import preflight_ownership, inspect_contract, require_scoped_requests
from .image_options import ImageOptions

LOG = logging.getLogger('agent-mm')


class Options(BaseModel):
    model_config = ConfigDict(extra='forbid')
    language: str = Field(default='zh', pattern=r'^[a-z]{2,3}$')
    prompt: str = Field(default='请用中文描述听到的声音及其时间线。', max_length=2000)


class TaskBody(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: Literal['transcribe', 'audio_understand', 'pdf', 'video', 'image_generate', 'image_edit']
    file_id: str | None = Field(default=None, pattern=r'^file-[a-f0-9]{32}$')
    options: dict = Field(default_factory=dict)


def create_app(root: Path, token: str, *, transport=None, run_worker=True,
               max_upload_bytes=64*1024*1024, max_pending=4, context_window=32768,
               audio_enabled=True, images_enabled=False,
               key_registry: KeyRegistry | None = None, identity_mode: str = 'legacy',
               event_stream_factory=None):
    if identity_mode not in ('legacy', 'staging', 'strict'):
        raise ValueError('identity_mode must be legacy, staging or strict')
    if identity_mode == 'strict':
        try:
            # An already contracted store may contain work interrupted by a
            # crash. Validate ownership first; lifespan recover fails running
            # tasks before either worker can claim queued work.
            inspect_contract(Path(root) / 'state.sqlite3', allow_running=True)
        except (OSError, sqlite3.Error):
            raise ValueError('strict requires completed owner migration') from None
        if key_registry is None:
            raise ValueError('strict requires explicit key registry')
    if identity_mode != 'strict' and (Path(root) / 'state.sqlite3').exists():
        report = preflight_ownership(Path(root) / 'state.sqlite3')
        if any(report[key] for key in ('unowned_files', 'unowned_tasks', 'unowned_idempotency_records')):
            raise ValueError('owner migration required; startup cannot claim unowned data')
        uri = (Path(root) / 'state.sqlite3').resolve().as_uri() + '?mode=ro'
        with contextlib.closing(sqlite3.connect(uri, uri=True)) as db:
            require_scoped_requests(db)
    if identity_mode != 'strict' and len(token) < 16:
        raise ValueError('Agent token must contain at least 16 characters')
    if type(context_window) is not int or not 1 <= context_window <= 262144:
        raise ValueError('Context window must be within the model native limit')
    store = Store(root, max_pending)
    if key_registry is None:
        key_registry = KeyRegistry(store.root / 'keys.sqlite3')
        key_registry.register('legacy', token)
    ownership_report = preflight_ownership(store.db)
    LOG.info('ownership_preflight unowned_files=%s unowned_tasks=%s unowned_idempotency_records=%s running_tasks=%s',
             ownership_report['unowned_files'], ownership_report['unowned_tasks'],
             ownership_report['unowned_idempotency_records'], ownership_report['running_tasks'])
    active = {}
    main_slots = asyncio.Semaphore(2)
    audio_slots = asyncio.Semaphore(1)
    upload_lock = asyncio.Lock()
    client = None
    main_url = os.getenv('MAIN_URL', 'http://127.0.0.1:18010')
    whisper_url = os.getenv('WHISPER_URL', 'http://127.0.0.1:18011')
    omni_url = os.getenv('OMNI_URL', 'http://127.0.0.1:18012')
    image_url = os.getenv('IMAGE_URL', 'http://127.0.0.1:18013')
    main_token_file = os.getenv('MAIN_TOKEN_FILE')
    main_headers = {'Authorization':'Bearer ' + Path(main_token_file).read_text().strip()} if main_token_file else {}

    async def worker():
        from .media import process_task
        while True:
            item = store.next_task()
            if item is None:
                await asyncio.sleep(.25)
                continue
            tid = item['id']
            store.update(tid, status='running')
            job = asyncio.create_task(process_task(item, store, client, main_url, whisper_url, omni_url, main_headers, main_slots, audio_enabled=audio_enabled))
            active[tid] = job
            try:
                result = await job
                store.update(tid, status='completed', progress=1, result=result)
            except asyncio.CancelledError:
                if store.worker_task(tid)['status'] != 'cancelled':
                    store.update(tid, status='failed', error='Worker interrupted')
                    raise
            except Exception as exc:
                LOG.exception('media task %s failed (%s)', tid, type(exc).__name__)
                store.update(tid, status='failed', error=f'{type(exc).__name__}: media processing failed; see service log')
            finally:
                active.pop(tid, None)

    @asynccontextmanager
    async def lifespan(app):
        nonlocal client
        client = httpx.AsyncClient(timeout=httpx.Timeout(600, connect=5), transport=transport, trust_env=False)
        store.recover()
        task = asyncio.create_task(worker()) if run_worker else None
        image_task = None
        app.state.image_worker = None
        if images_enabled and run_worker:
            from .images import image_worker
            from .comfy_events import ComfyEventStream
            image_task = asyncio.create_task(image_worker(store, client, image_url, active,
                                                         event_stream_factory=event_stream_factory or ComfyEventStream))
            app.state.image_worker=image_task
        yield
        if image_task:
            image_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await image_task
        if task:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        await client.aclose()

    app = FastAPI(title='Dual Spark capability gateway', lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.store = store

    @app.middleware('http')
    async def guard(request, call_next):
        rid = request.headers.get('x-request-id','')
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', rid):
            rid = uuid.uuid4().hex
        request.state.request_id = rid
        authorization = request.headers.get('authorization', '')
        # RFC 9110 scheme names are case-insensitive; RFC 6750 allows 1*SP.
        scheme, separator, credential = authorization.partition(' ')
        bearer = scheme.casefold() == 'bearer' and bool(separator)
        credential = credential.lstrip(' ').rstrip(' \t')
        principal = key_registry.resolve(credential) if bearer else None
        authenticated = principal is not None and (identity_mode != 'legacy' or principal.owner == 'legacy')
        if not authenticated:
            formatted_match = bearer and hmac.compare_digest(credential.strip().encode(), token.encode())
            # Only diagnostic booleans: never emit headers, tokens or token hashes.
            LOG.warning('%s authentication_denied peer=%s method=%s header_present=%s bearer_scheme=%s formatted_key_matches=%s',
                        rid, request.client.host if request.client else 'unknown', request.method,
                        bool(authorization), bearer, formatted_match)
            return JSONResponse({'error':{'message':'Invalid API key','type':'authentication_error'}}, 401,
                                headers={'X-Request-ID':rid, 'WWW-Authenticate':'Bearer'})
        request.state.principal = principal
        # Caddy also caps the complete request, including chunked uploads.
        length = request.headers.get('content-length', '0')
        if not length.isdigit() or int(length) > max_upload_bytes + 1024*1024:
            return JSONResponse({'error':{'message':'Request too large'}}, 413)
        response = await call_next(request)
        response.headers['x-request-id'] = rid
        LOG.info('%s %s %s %s', rid, request.method, request.url.path, response.status_code)
        return response

    @app.get('/v1/me')
    async def me(request: Request):
        return {'owner': request.state.principal.owner}

    @app.get('/health')
    async def health():
        async def check(url):
            try:
                r = await client.get(url+'/health', timeout=3, headers=main_headers if url==main_url else {})
                if r.is_success and not r.content and url==main_url:
                    return {'status':'ready'}
                return r.json() if r.is_success else {'status':'unavailable'}
            except (httpx.HTTPError, ValueError):
                return {'status':'unavailable'}
        backends={'main':await check(main_url)}
        if audio_enabled:
            backends.update(zip(('whisper','omni'),await asyncio.gather(check(whisper_url),check(omni_url))))
        if images_enabled:
            try:
                r=await client.get(image_url+'/system_stats',timeout=3)
                backends['image']={'status':'ready' if r.is_success and 'system' in r.json() else 'unavailable'}
            except (httpx.HTTPError,ValueError):
                backends['image']={'status':'unavailable'}
        if images_enabled and app.state.image_worker is not None and app.state.image_worker.done():
            backends['image']={'status':'unavailable','reason':'Image worker stopped; restart backend and gateway'}
        ready=(backends['main']=={} or backends['main'].get('status') in ('ready','ok')) and all(s.get('status')=='ready' for name,s in backends.items() if name!='main')
        return JSONResponse({'status':'ready' if ready else 'degraded','backends':backends},200 if ready else 503)

    @app.get('/v1/models')
    async def models():
        names=['spark-main']
        if audio_enabled: names += ['whisper-large-v3-turbo','qwen2.5-omni-7b']
        if images_enabled: names += ['spark-image','spark-image-edit']
        return {'object':'list','data':[{'id':m,'object':'model','created':0,'owned_by':'local-spark',
            **({'max_model_len':context_window} if m=='spark-main' else {}),
            **({'capabilities':['image_generation' if m=='spark-image' else 'image_edit']} if m.startswith('spark-image') else {})} for m in names]}

    async def ensure_image_available():
        worker = app.state.image_worker
        if worker is not None and worker.done():
            raise HTTPException(503, 'Image worker unavailable; operator must restore the backend and gateway')
        try:
            response = await client.get(image_url+'/system_stats', timeout=3)
            if not response.is_success or 'system' not in response.json():
                raise ValueError('Not ready')
        except (httpx.HTTPError, ValueError):
            raise HTTPException(503, 'Image backend unavailable; do not repeatedly submit new tasks')

    async def submit_image(kind, options, idem, owner):
        if idem and len(idem) > 128:
            raise HTTPException(422, 'Idempotency key too long')
        refs = options.image_ids + ([options.foreground_file_id] if options.foreground_file_id else [])
        for fid in refs:
            store.file(fid, owner=owner)
        source = refs[0] if refs else None
        payload = options.model_dump()
        if idem:
            fingerprint = store.request_fingerprint(kind, source, payload, owner=owner)
            existing = store.lookup_request(owner, idem, fingerprint)
            if existing is not None:
                return existing
        await ensure_image_available()
        return store.submit(kind, source, payload, idem, owner=owner)

    @app.post('/v1/chat/completions')
    async def chat(request: Request):
        raw = await request.body()
        if len(raw) > 16*1024*1024:
            raise HTTPException(413, 'Chat request too large')
        try:
            body = json.loads(raw)
            json.dumps(body, allow_nan=False)
        except ValueError:
            raise HTTPException(422,'Invalid JSON or non-finite number')
        if not isinstance(body, dict):
            raise HTTPException(422,'Expected JSON object')
        if body.get('model') not in ('spark-main', 'Qwen3.6-35B-A3B-NVFP4'):
            raise HTTPException(404,'Unknown chat model; use spark-main')
        body['model'] = 'spark-main'
        # Local inference does not implement stored-completion retrieval.
        # SDKs may explicitly send the OpenAI default, store=false (or null).
        store_output = body.pop('store', None)
        if store_output is not None and type(store_output) is not bool:
            raise HTTPException(422,'store must be a boolean or null')
        if store_output is True:
            raise HTTPException(422,'Stored completions are unavailable; set store=false')
        messages = body.get('messages')
        if not isinstance(messages, list) or not messages or len(messages)>200:
            raise HTTPException(422,'Expected 1 to 200 messages')
        # Block SSRF through vLLM's remote media loader; images are inline data only.
        for message in messages:
            if not isinstance(message, dict):
                raise HTTPException(422,'Invalid message')
            content = message.get('content')
            if isinstance(content,list):
                for part in content:
                    if not isinstance(part,dict) or part.get('type') not in ('text','image_url'):
                        raise HTTPException(422,'Only text and inline images supported')
                    if part.get('type')=='image_url':
                        image_url = part.get('image_url',{})
                        url = image_url.get('url','') if isinstance(image_url,dict) else ''
                        if not re.match(r'^data:image/(png|jpeg|webp);base64,',url):
                            raise HTTPException(422,'Use inline image data; remote media URLs are disabled')
        # Do not accept local paths, templates or arbitrary vLLM media configuration.
        allowed = {'model','messages','stream','stream_options','tools','tool_choice','parallel_tool_calls','temperature','top_p','top_k','max_tokens','max_completion_tokens','stop','seed','presence_penalty','frequency_penalty','repetition_penalty','response_format','chat_template_kwargs','enable_thinking'}
        if body.keys()-allowed:
            raise HTTPException(422,'Unsupported completion fields: '+','.join(sorted(body.keys()-allowed)))
        if 'chat_template_kwargs' in body and (not isinstance(body['chat_template_kwargs'],dict) or body['chat_template_kwargs'].keys()-{'enable_thinking'}):
            raise HTTPException(422,'Only enable_thinking template option is supported')
        body.setdefault('chat_template_kwargs', {'enable_thinking':False})
        await acquire(main_slots)
        try:
            headers = {**main_headers,'X-Request-ID':request.state.request_id}
            budget_headers = await adapt_output_budget(client, main_url, body, headers, context_window)
            req = client.build_request('POST', main_url+'/v1/chat/completions', json=body, headers=headers)
            upstream = await client.send(req, stream=True)
        except httpx.HTTPError:
            main_slots.release()
            raise HTTPException(503,'Main model unavailable')
        except BaseException:
            main_slots.release()
            raise
        if not upstream.is_success or not body.get('stream'):
            try:
                data = await upstream.aread()
                return Response(data, upstream.status_code, media_type=upstream.headers.get('content-type','application/json'),headers=budget_headers)
            finally:
                await close_main_response(upstream, main_slots)
        async def chunks():
            async for chunk in upstream.aiter_bytes():
                yield chunk
        return ModelStreamingResponse(chunks(), upstream=upstream, semaphore=main_slots,
                                      media_type='text/event-stream',headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no',**budget_headers})

    @app.post('/v1/files')
    async def upload(request: Request, file: UploadFile = File(...), purpose: str = Form('assistants')):
        async with upload_lock:
            fid = 'file-' + uuid.uuid4().hex
            path = store.files / fid
            size = 0
            created = False
            # Total storage bound across uploads; private directory is not an unbounded cache.
            with store.connect() as db:
                used = db.execute('SELECT coalesce(sum(bytes),0) FROM files').fetchone()[0]
            try:
                with path.open('xb') as out:
                    created = True
                    while chunk := await file.read(1024*1024):
                        size += len(chunk)
                        if size > max_upload_bytes or used+size > 2*1024**3:
                            raise HTTPException(413,'File/storage limit exceeded')
                        out.write(chunk)
                if size==0:
                    raise HTTPException(422,'Empty file')
                item = store.add_file(fid,file.filename or 'upload',size,owner=request.state.principal.owner)
                return {'id':fid,'object':'file','bytes':size,'created_at':item['created'],'filename':item['name'],'purpose':purpose}
            except BaseException:
                if created:
                    path.unlink(missing_ok=True)
                raise
            finally:
                await file.close()

    @app.get('/v1/files/{fid}/content')
    async def content(fid: str, request: Request):
        path=store.path(fid,owner=request.state.principal.owner)
        with path.open('rb') as source: signature=source.read(8)
        mime='image/png' if signature==b'\x89PNG\r\n\x1a\n' else 'application/octet-stream'
        return FileResponse(path,media_type=mime,headers={'X-Content-Type-Options':'nosniff'})

    @app.delete('/v1/files/{fid}')
    async def delete(fid: str, request: Request):
        store.delete_file(fid,owner=request.state.principal.owner)
        return {'id':fid,'object':'file','deleted':True}

    @app.post('/v1/tasks', status_code=202)
    async def submit(body: TaskBody, request: Request):
        idem = request.headers.get('idempotency-key')
        if idem and len(idem)>128:
            raise HTTPException(422,'Idempotency key too long')
        from pydantic import ValidationError
        try:
            if body.kind in ('image_generate','image_edit'):
                if not images_enabled: raise HTTPException(410,'Image generation is disabled')
                opts=ImageOptions.model_validate(body.options)
                if body.kind=='image_edit' and not opts.image_ids:
                    raise HTTPException(422,'Image editing requires image_ids')
                if body.kind=='image_generate' and opts.image_ids:
                    raise HTTPException(422,'Use image_edit for reference images')
                return await submit_image(body.kind, opts, idem, request.state.principal.owner)
            if body.kind in ('transcribe','audio_understand') and not audio_enabled:
                raise HTTPException(410,'Audio capabilities have been retired')
            if not body.file_id: raise HTTPException(422,'file_id is required')
            opts=Options.model_validate(body.options)
        except ValidationError as exc:
            raise HTTPException(422,str(exc))
        return store.submit(body.kind,body.file_id,opts.model_dump(),idem,owner=request.state.principal.owner)

    @app.get('/v1/tasks')
    async def tasks(request: Request, status: str | None = None, after: str | None = None,
                    limit: int = Query(20, ge=1, le=100)):
        return store.list_tasks(request.state.principal.owner, status=status, after=after, limit=limit)

    @app.get('/v1/tasks/{tid}')
    async def status(tid: str, request: Request):
        return store.task(tid, owner=request.state.principal.owner)

    @app.post('/v1/tasks/{tid}/cancel')
    async def cancel(tid: str, request: Request):
        task = store.task(tid, owner=request.state.principal.owner)
        if task['kind'] in ('image_generate', 'image_edit'):
            task, changed = store.request_cancel(tid, owner=request.state.principal.owner)
            if changed and tid in active:
                active[tid].cancel()
            return task
        if task['status'] in ('queued','running'):
            task = store.update(tid,status='cancelled')
            if tid in active:
                active[tid].cancel()
        return task

    @app.post('/v1/audio/transcriptions')
    async def transcribe(request: Request, file: UploadFile = File(...), model: str = Form(...),
                         language: str = Form('zh'), response_format: str = Form('json')):
        if not audio_enabled:
            raise HTTPException(410,'Audio capabilities have been retired')
        if model != 'whisper-large-v3-turbo':
            raise HTTPException(404,'Unknown transcription model')
        if response_format not in ('json','verbose_json','text'):
            raise HTTPException(422,'Supported formats: json, verbose_json, text')
        await acquire(audio_slots)
        try:
            data = await file.read(max_upload_bytes+1)
            await file.close()
            if len(data)>max_upload_bytes:
                raise HTTPException(413,'Audio too large')
            try:
                r = await client.post(whisper_url+'/transcribe',files={'file':('audio',data)},data={'language':language},headers={'X-Request-ID':request.state.request_id})
            except httpx.HTTPError:
                raise HTTPException(503,'Whisper unavailable')
            if not r.is_success:
                return Response(r.content,r.status_code,media_type='application/json')
            result=r.json()
            if response_format=='text':
                return Response(result['text'],media_type='text/plain')
            return result if response_format=='verbose_json' else {'text':result['text']}
        finally:
            audio_slots.release()

    if images_enabled:
        from .image_routes import register_image_routes
        register_image_routes(app, store, upload_lock, submit_image, ensure_image_available)
    return app


async def adapt_output_budget(client, main_url, body, headers, context_window=32768):
    """Repair whole-window output limits without changing history or tool messages."""
    for field in ('max_tokens', 'max_completion_tokens'):
        value = body.get(field)
        if value is not None and (type(value) is not int or value < 1):
            raise HTTPException(422, field+' must be a positive integer or null')
    requested = body.pop('max_completion_tokens', None)
    legacy = body.pop('max_tokens', None)
    body['max_tokens'] = requested if requested is not None else legacy if legacy is not None else 1024
    if body['max_tokens'] < context_window:
        return {}
    payload = {key:body[key] for key in ('model','messages','tools','chat_template_kwargs') if key in body}
    payload['add_generation_prompt'] = True
    counted = await client.post(main_url+'/tokenize',json=payload,headers=headers)
    if not counted.is_success:
        raise HTTPException(400 if counted.status_code in (400,422) else 503,
                            'Input token counting failed; check input or model availability')
    try:
        count = counted.json()['count']
        if type(count) is not int or count < 0:
            raise ValueError('Invalid token count')
    except (ValueError, KeyError, TypeError):
        raise HTTPException(503,'Model tokenizer returned an invalid token count')
    remaining = context_window-count
    if remaining < 1:
        raise HTTPException(400, f'Input uses {count} tokens; context window is {context_window}. Reduce history, system prompt or tools to leave room for output.')
    body['max_tokens'] = remaining
    LOG.info('%s output_budget_adjusted requested=%s input_tokens=%s max_output_tokens=%s context_window=%s',
             headers['X-Request-ID'], requested if requested is not None else legacy, count, remaining, context_window)
    return {'X-Context-Window':str(context_window), 'X-Input-Tokens':str(count), 'X-Max-Output-Tokens':str(remaining)}


class ModelStreamingResponse(StreamingResponse):
    """Own upstream cleanup even when disconnect occurs before body iteration."""
    def __init__(self, content, *, upstream, semaphore, **kwargs):
        super().__init__(content, **kwargs)
        self.upstream = upstream
        self.semaphore = semaphore

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            await close_main_response(self.upstream, self.semaphore)


async def close_main_response(response, semaphore):
    try:
        # Streaming disconnects cancel Starlette's AnyIO scope; shield resource cleanup.
        with anyio.move_on_after(5, shield=True):
            await response.aclose()
    finally:
        semaphore.release()


async def acquire(semaphore):
    try:
        await asyncio.wait_for(semaphore.acquire(),timeout=10)
    except TimeoutError:
        raise HTTPException(429,'Model busy',headers={'Retry-After':'5'})


def application():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s')
    mode = os.getenv('AGENT_IDENTITY_MODE')
    if mode not in ('legacy', 'staging', 'strict'):
        raise ValueError('explicit valid identity mode required (AGENT_IDENTITY_MODE)')
    base = Path(__file__).resolve().parents[1]
    root = base / '.private' / 'runtime'
    registry = None
    if mode == 'strict':
        inspect_contract(root / 'state.sqlite3', allow_running=True)
        registry_path = root / 'keys.sqlite3'
        if registry_path.is_symlink() or not registry_path.is_file():
            raise ValueError('strict requires existing explicit key registry')
        registry = KeyRegistry(registry_path)
        token = ''  # strict authenticates only the supplied registry, never the shared key file.
    else:
        token = (base / '.private' / 'agent-api.key').read_text().strip()
    return create_app(root, token, key_registry=registry, identity_mode=mode,
                      context_window=int(os.getenv('MAIN_CONTEXT_TOKENS','200000')),
                      audio_enabled=os.getenv('AUDIO_ENABLED','0')=='1',
                      images_enabled=os.getenv('IMAGES_ENABLED','1')=='1')
