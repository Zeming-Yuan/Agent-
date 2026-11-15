import pytest

def test_tb07_cancel_waits_until_backend_stopped(owner_env):
    backend = owner_env.new_backend(hold=True, hold_stop=True)
    with owner_env.client(backend=backend, run_worker=True) as c:
        tid = owner_env.submit(c, 'A').json()['id']
        assert backend.started.wait(2)
        try:
            response = c.post('/v1/tasks/' + tid + '/cancel', headers=owner_env.auth('A'))
            assert response.json()['status'] == 'running'
            assert response.json()['stage'] == 'cancelling'
            # Repeated cancellation must not interrupt the cleanup itself.
            again = c.post('/v1/tasks/' + tid + '/cancel', headers=owner_env.auth('A'))
            assert again.json()['stage_seq'] == response.json()['stage_seq']
            second = owner_env.submit(c, 'B').json()['id']
            assert len(backend.jobs) == 1
            assert c.get('/v1/tasks/' + second, headers=owner_env.auth('B')).json()['status'] == 'queued'
        finally:
            backend.release_stop.set()
        done = owner_env.wait_task(c, tid, 'A', lambda t: t['status'] == 'cancelled')
        assert done['stage'] == 'cancelled'
        backend.finish.set()
        owner_env.wait_task(c, second, 'B', lambda t: t['status'] == 'completed')


def test_tb07_shutdown_during_cancel_waits_for_cleanup(owner_env):
    import asyncio
    import json
    import threading
    import time

    backend = owner_env.new_backend(hold=True, hold_stop=True)
    stopping = threading.Event()
    async def external(request):
        if request.url.path == '/interrupt' and json.loads(request.content).get('prompt_id'):
            stopping.set()
        return await backend(request)
    with owner_env.client(backend=external, run_worker=True) as c:
        tid = owner_env.submit(c).json()['id']
        assert backend.started.wait(2)
        c.post('/v1/tasks/' + tid + '/cancel', headers=owner_env.auth('A'))
        assert stopping.wait(2)
        try:
            c.portal.call(c.app.state.image_worker.cancel)
            # Give the cancellation a turn while the external stop remains blocked.
            time.sleep(.05)
            task = c.get('/v1/tasks/' + tid, headers=owner_env.auth('A')).json()
            assert task['status'] == 'running'
            assert task['stage'] == 'cancelling'
        finally:
            backend.release_stop.set()
            # Also terminates the pre-fix worker that swallowed its first shutdown.
            c.portal.call(c.app.state.image_worker.cancel)
        owner_env.wait_task(c, tid, 'A', lambda t: t['status'] == 'cancelled')
        deadline = time.monotonic() + 2
        while not c.app.state.image_worker.done() and time.monotonic() < deadline:
            time.sleep(.01)
        assert c.app.state.image_worker.done()
        assert not backend.running


def test_tb07_cancel_and_completion_have_one_terminal(owner_env):
    import asyncio
    import json
    import threading

    backend = owner_env.new_backend()
    cleanup_entered = threading.Event()
    cancel_entered = threading.Event()
    release = threading.Event()
    gates = {}
    async def external(request):
        if request.url.path == '/history' and json.loads(request.content).get('delete'):
            cleanup_entered.set()
            await asyncio.to_thread(release.wait, 3)
            gates['cancel'].set()
        return await backend(request)
    with owner_env.client(backend=external, run_worker=True) as c:
        # A request-delivery gate at the HTTP boundary models cancellation
        # arriving exactly as the last external cleanup request returns.
        for route in c.app.routes:
            if getattr(route, 'path', None) == '/v1/tasks/{tid}/cancel':
                original = route.dependant.call
                async def delayed(tid, request):
                    gates['cancel'] = asyncio.Event()
                    jobs = [t for t in asyncio.all_tasks() if t.get_coro().__name__ == 'process_image']
                    assert len(jobs) == 1
                    job = jobs[0]
                    cancel_entered.set()
                    await gates['cancel'].wait()
                    while not job.done():
                        await asyncio.sleep(0)
                    response = await original(tid, request)
                    assert response['status'] == 'running'
                    assert response['stage'] == 'cancelling'
                    return response
                route.dependant.call = delayed
                break
        tid = owner_env.submit(c).json()['id']
        assert cleanup_entered.wait(2)
        responses = []
        sender = threading.Thread(target=lambda: responses.append(c.post('/v1/tasks/' + tid + '/cancel', headers=owner_env.auth('A'))))
        sender.start()
        try:
            assert cancel_entered.wait(2)
        finally:
            release.set()
        sender.join(3)
        assert not sender.is_alive()
        route.dependant.call = original
        done = owner_env.wait_task(c, tid, 'A', lambda t: t['status'] in ('completed', 'cancelled'))
        assert c.post('/v1/tasks/' + tid + '/cancel', headers=owner_env.auth('A')).json()['status'] == done['status']


def test_tb07_task_read_is_one_committed_snapshot(owner_env, monkeypatch):
    from contextlib import contextmanager
    import threading

    with owner_env.client() as c:
        tid = owner_env.submit(c).json()['id']
        store = c.app.state.store
        connect = store.connect
        querying = threading.get_ident()
        fired = False
        @contextmanager
        def traced_connection():
            nonlocal fired
            with connect() as db:
                def on_read(sql):
                    nonlocal fired
                    if (not fired and threading.get_ident() == querying
                            and sql.startswith('SELECT') and 'task_runtime' in sql):
                        fired = True
                        # A second HTTP request commits cancellation at the database read boundary.
                        response = c.post('/v1/tasks/' + tid + '/cancel', headers=owner_env.auth('A'))
                        assert response.status_code == 200
                db.set_trace_callback(on_read)
                yield db
        monkeypatch.setattr(store, 'connect', traced_connection)
        task = store.task(tid, owner='A')
        assert fired
        assert (task['status'], task['stage']) in (('queued', 'queued'), ('cancelled', 'cancelled'))


def test_tb07_waiting_backend_exposes_stage_and_no_invented_steps(owner_env):
    backend = owner_env.new_backend(hold=True)
    with owner_env.client(backend=backend, run_worker=True) as c:
        tid = owner_env.submit(c).json()['id']
        assert backend.started.wait(2)
        try:
            task = c.get('/v1/tasks/' + tid, headers=owner_env.auth('A')).json()
            assert task['stage'] == 'loading'
            assert task['step'] is None and task['steps'] is None
            assert task['stage_started_at'] <= task['stage_updated_at']
        finally:
            backend.finish.set()


def test_tb07_stages_cannot_regress_and_survive_restart(owner_env):
    with owner_env.client() as c:
        tid = owner_env.submit(c).json()['id']
        store = c.app.state.store
        loading = store.transition(tid, status='running', stage='loading', expected_seq=0)
        generating = store.transition(tid, status='running', stage='generating', expected_seq=loading['stage_seq'])
        late = store.transition(tid, status='running', stage='loading', expected_seq=generating['stage_seq'])
        assert late == generating
    with owner_env.client() as c:
        task = c.get('/v1/tasks/' + tid, headers=owner_env.auth('A')).json()
        assert task['status'] == 'failed'  # conservative restart, never resume GPU work
        assert task['stage'] == 'failed'
        assert task['stage_seq'] > generating['stage_seq']


def test_tb07_sampling_events_belong_to_prompt_and_never_regress(owner_env):
    import uuid
    backend = owner_env.new_backend(hold=True)
    with owner_env.client(backend=backend, run_worker=True, event_stream_factory=backend.event_stream) as c:
        tid = owner_env.submit(c).json()['id']
        assert backend.started.wait(2)
        assert backend.events_connected.is_set()  # subscription precedes prompt
        pid = backend.jobs[0]['prompt_id']
        def emit(kind, **data):
            backend.events_to_emit.put({'type': kind, 'data': {'prompt_id': pid, **data}})
        try:
            emit('executing', node='7')
            emit('progress', node='7', value=2, max=8)
            sampling = owner_env.wait_task(c, tid, 'A', lambda t: t.get('step') == 2)
            assert sampling['stage'] == 'generating'
            assert sampling['steps'] == 8
            emit('progress', node='7', value=2, max=8)  # duplicate
            emit('progress', node='7', value=1, max=8)  # delayed
            emit('progress', node='7', value=8, max=8, prompt_id=str(uuid.uuid4()))
            emit('executing', node='2')  # delayed loader
            emit('progress', node='7', value=3, max=8)
            next_sample = owner_env.wait_task(c, tid, 'A', lambda t: t.get('step') == 3)
            assert next_sample['stage_started_at'] == sampling['stage_started_at']
            sampling = next_sample
            emit('executing', node='8')  # VAE decode / save boundary
            saving = owner_env.wait_task(c, tid, 'A', lambda t: t['stage'] == 'saving')
            assert saving['stage_seq'] == sampling['stage_seq'] + 1
            assert saving['step'] is None and saving['steps'] is None
            emit('progress', node='7', value=8, max=8)
            emit('executing', node='7')
        finally:
            backend.finish.set()
        done = owner_env.wait_task(c, tid, 'A', lambda t: t['status'] == 'completed')
        result = c.get(done['result']['content_url'], headers=owner_env.auth('A'))
        assert result.status_code == 200
        assert c.get(done['result']['content_url'], headers=owner_env.auth('B')).status_code == 404
        assert c.post('/v1/tasks/' + tid + '/cancel', headers=owner_env.auth('A')).json()['status'] == 'completed'


def test_tb07_real_websocket_subscribes_before_prompt_and_filters_reconnect(owner_env, monkeypatch):
    import asyncio
    import json
    import threading
    from websockets.asyncio.server import serve

    backend = owner_env.new_backend(hold=True)
    listening = threading.Event()
    subscribed = threading.Event()
    stopped = threading.Event()
    address = {}
    paths = []
    async def handler(ws):
        paths.append(ws.request.path)
        await asyncio.sleep(.05)  # upgrade may finish before Comfy registers its client socket
        subscribed.set()
        await ws.send(json.dumps({'type': 'status', 'data': {'sid': ws.request.path.split('=')[1], 'status': {}}}))
        while not backend.jobs:
            await asyncio.sleep(.01)
        pid = backend.jobs[0]['prompt_id']
        await ws.send(b'preview-not-progress')
        await ws.send('{malformed-json')
        await ws.send(json.dumps({'type': 'executing', 'data': {'node': '7'}}))  # reconnect lacks owner
        await ws.send(json.dumps({'type': 'progress', 'data': {'prompt_id': pid, 'value': 7, 'max': 8}}))
        await ws.send(json.dumps({'type': 'executing', 'data': {'prompt_id': pid, 'node': '7'}}))
        await ws.send(json.dumps({'type': 'progress', 'data': {'prompt_id': pid, 'node': '7', 'value': 3, 'max': 8}}))
        await ws.wait_closed()
    async def server():
        async with serve(handler, '127.0.0.1', 0) as service:
            address['port'] = service.sockets[0].getsockname()[1]
            listening.set()
            while not stopped.is_set():
                await asyncio.sleep(.01)
    thread = threading.Thread(target=lambda: asyncio.run(server()), daemon=True)
    thread.start()
    assert listening.wait(2)
    monkeypatch.setenv('IMAGE_URL', 'http://127.0.0.1:' + str(address['port']))
    async def external(request):
        if request.url.path == '/prompt':
            assert subscribed.is_set(), 'HTTP submission preceded websocket subscription'
        return await backend(request)
    try:
        with owner_env.client(backend=external, run_worker=True) as c:
            tid = owner_env.submit(c).json()['id']
            try:
                sample = owner_env.wait_task(c, tid, 'A', lambda t: t.get('step') == 3)
                assert sample['steps'] == 8
                assert paths == ['/ws?clientId=' + tid]
            finally:
                backend.finish.set()
            owner_env.wait_task(c, tid, 'A', lambda t: t['status'] == 'completed')
    finally:
        stopped.set()
        thread.join(3)
        assert not thread.is_alive()


def test_tb07_stop_failure_halts_admission_but_preserves_queries(owner_env):
    import httpx
    import json
    import threading
    backend = owner_env.new_backend(hold=True)
    reject_stop = threading.Event(); reject_stop.set()
    async def external(request):
        if request.url.path == '/interrupt' and json.loads(request.content).get('prompt_id') and reject_stop.is_set():
            return httpx.Response(503, json={'error': 'cannot confirm stop'})
        return await backend(request)
    with owner_env.client(backend=external, run_worker=True) as c:
        tid = owner_env.submit(c, request_key='keep-original').json()['id']
        assert backend.started.wait(2)
        second = owner_env.submit(c, 'B').json()['id']
        try:
            c.post('/v1/tasks/' + tid + '/cancel', headers=owner_env.auth('A'))
            failed = owner_env.wait_task(c, tid, 'A', lambda t: t['status'] == 'failed')
            assert failed['stage'] == 'failed'
            assert failed['blocked_reason'] == 'cleanup_unconfirmed'
            assert c.get('/health', headers=owner_env.auth('A')).status_code == 503
            assert owner_env.submit(c).status_code == 503
            assert owner_env.submit(c, request_key='keep-original').json()['id'] == tid
            assert c.get('/v1/tasks/' + second, headers=owner_env.auth('B')).json()['status'] == 'queued'
            assert len(backend.jobs) == 1
        finally:
            reject_stop.clear()
            backend.finish.set()


def test_tb07_save_is_durable_before_success_and_failure_is_not_completed(owner_env, monkeypatch):
    import os
    from pathlib import Path
    injected = []
    original = os.fsync
    def fail_generated(fd):
        target = Path('/proc/self/fd/' + str(fd)).resolve()
        if target.parent == owner_env.root / 'files':
            injected.append(target)
            raise OSError('synthetic fsync failure')
        return original(fd)
    monkeypatch.setattr(os, 'fsync', fail_generated)
    with owner_env.client(run_worker=True) as c:
        tid = owner_env.submit(c).json()['id']
        done = owner_env.wait_task(c, tid, 'A', lambda t: t['status'] in ('completed', 'failed'))
        assert done['status'] == 'failed'
        assert done['stage'] == 'failed'
        assert done['result'] is None
        assert len(injected) == 1
        assert not injected[0].exists()


@pytest.mark.parametrize('failure', ['open', 'closed', 'error'])
def test_tb07_event_failure_keeps_truthful_stage_and_still_cleans_backend(owner_env, failure):
    import asyncio
    backend = owner_env.new_backend(hold=True)
    class BrokenEvents:
        def __init__(self, url, client_id): pass
        async def __aenter__(self):
            if failure == 'open': raise OSError('synthetic connection failure')
            return self
        async def __aexit__(self, *exc): return False
        async def events(self):
            while not backend.jobs: await asyncio.sleep(.01)
            if failure == 'closed': return
            raise OSError('synthetic event disconnect')
            yield
    with owner_env.client(backend=backend, run_worker=True, event_stream_factory=BrokenEvents) as c:
        tid = owner_env.submit(c).json()['id']
        try:
            task = owner_env.wait_task(c, tid, 'A', lambda t: t.get('blocked_reason') == 'events_unavailable')
            assert task['status'] == 'running' and task['stage'] == 'loading'
            assert task['step'] is None and task['steps'] is None
        finally:
            backend.finish.set()
        done = owner_env.wait_task(c, tid, 'A', lambda t: t['status'] == 'completed')
        assert c.get(done['result']['content_url'], headers=owner_env.auth('A')).status_code == 200
        assert not backend.running


def test_tb07_cancel_during_slow_save_remains_queryable_and_holds_next_job(owner_env, monkeypatch):
    import os
    import threading
    from pathlib import Path
    backend = owner_env.new_backend()
    entered = threading.Event(); release = threading.Event(); replied = threading.Event()
    generated = []
    original = os.fsync
    def hold_save(fd):
        path = Path('/proc/self/fd/' + str(fd)).resolve()
        if path.parent == owner_env.root / 'files' and not generated:
            generated.append(path.name)
            entered.set()
            assert release.wait(3), 'test save gate timed out'
        return original(fd)
    monkeypatch.setattr(os, 'fsync', hold_save)
    with owner_env.client(backend=backend, run_worker=True) as c:
        tid = owner_env.submit(c).json()['id']
        assert entered.wait(2)
        responses = []
        def cancel():
            responses.append(c.post('/v1/tasks/' + tid + '/cancel', headers=owner_env.auth('A')))
            replied.set()
        sender = threading.Thread(target=cancel); sender.start()
        try:
            timely = replied.wait(.5)
            if timely:
                assert responses[0].json()['stage'] == 'cancelling'
                assert c.get('/v1/tasks/' + tid, headers=owner_env.auth('A')).json()['status'] == 'running'
                second = owner_env.submit(c, 'B').json()['id']
                assert len(backend.jobs) == 1
        finally:
            release.set()
            sender.join(3)
        assert timely, 'saving blocked the HTTP cancel/query interface'
        owner_env.wait_task(c, tid, 'A', lambda t: t['status'] == 'cancelled')
        assert c.get('/v1/files/' + generated[0] + '/content', headers=owner_env.auth('A')).status_code == 404
        owner_env.wait_task(c, second, 'B', lambda t: t['status'] == 'completed')


def test_tb07_mcp_reports_chinese_stages_without_fake_percentage(owner_env, tmp_path):
    import asyncio
    import json
    from client.spark_image_tools import ImageBridge, build_server
    from test_tb06_mcp_resume import GatewayTransport, CA
    backend = owner_env.new_backend(hold=True)
    with owner_env.client(backend=backend, run_worker=True, event_stream_factory=backend.event_stream) as c:
        tid = owner_env.submit(c).json()['id']
        assert backend.started.wait(2)
        async def run():
            bridge = ImageBridge('https://spark.invalid/v1', owner_env.keys['A'], CA, tmp_path / 'out',
                journal_path=tmp_path/'journal.sqlite3', transport=GatewayTransport(c))
            try:
                server = build_server(bridge)
                result = await server.call_tool('get_image_task', {'task_id': tid, 'wait_seconds': 0})
                contents = result[0] if isinstance(result, tuple) else result
                state = json.loads(next(item.text for item in contents if item.type == 'text'))
                assert state['stage_text'] == '加载模型'
                assert state['stage_wait_seconds'] >= 0
                assert 'progress' not in state
                assert '%' not in json.dumps(state, ensure_ascii=False)
                backend.events_to_emit.put({'type': 'executing', 'data': {'prompt_id': backend.jobs[0]['prompt_id'], 'node': '7'}})
                backend.events_to_emit.put({'type': 'progress', 'data': {'prompt_id': backend.jobs[0]['prompt_id'], 'node': '7', 'value': 2, 'max': 8}})
                owner_env.wait_task(c, tid, 'A', lambda t: t.get('step') == 2)
                result = await server.call_tool('get_image_task', {'task_id': tid, 'wait_seconds': 0})
                contents = result[0] if isinstance(result, tuple) else result
                state = json.loads(next(item.text for item in contents if item.type == 'text'))
                assert state['stage_text'] == '生成图片'
                assert (state['step'], state['steps']) == (2, 8)
            finally:
                await bridge.close()
        try:
            asyncio.run(run())
        finally:
            backend.finish.set()


def test_tb07_cancelled_profile_cannot_reuse_previous_model_assumption(owner_env):
    backend = owner_env.new_backend()
    frees = []
    async def external(request):
        if request.url.path == '/free': frees.append(True)
        return await backend(request)
    with owner_env.client(backend=external, run_worker=True) as c:
        first = owner_env.submit(c).json()['id']
        owner_env.wait_task(c, first, 'A', lambda t: t['status'] == 'completed')
        backend.started.clear(); backend.finish.clear()
        reference = owner_env.upload(c)
        edit = owner_env.submit(c, kind='image_edit', image_ids=[reference], quality='fast').json()['id']
        assert backend.started.wait(2)
        c.post('/v1/tasks/' + edit + '/cancel', headers=owner_env.auth('A'))
        owner_env.wait_task(c, edit, 'A', lambda t: t['status'] == 'cancelled')
        backend.finish.set()
        last = owner_env.submit(c).json()['id']
        owner_env.wait_task(c, last, 'A', lambda t: t['status'] == 'completed')
        assert len(frees) == 3  # cancelled edit leaves residency unknown


def test_tb07_unload_request_is_a_stage_not_a_release_claim(owner_env):
    import asyncio
    import threading
    backend = owner_env.new_backend()
    entered = threading.Event(); release = threading.Event()
    async def external(request):
        if request.url.path == '/free':
            entered.set()
            assert await asyncio.to_thread(release.wait, 3)
        return await backend(request)
    with owner_env.client(backend=external, run_worker=True) as c:
        tid = owner_env.submit(c).json()['id']
        assert entered.wait(2)
        try:
            task = c.get('/v1/tasks/' + tid, headers=owner_env.auth('A')).json()
            assert task['status'] == 'running' and task['stage'] == 'unloading'
            assert task['step'] is None
        finally:
            release.set()
        owner_env.wait_task(c, tid, 'A', lambda t: t['status'] == 'completed')


def test_tb07_late_internal_update_cannot_overwrite_terminal(owner_env):
    with owner_env.client() as c:
        tid = owner_env.submit(c).json()['id']
        cancelled = c.post('/v1/tasks/' + tid + '/cancel', headers=owner_env.auth('A')).json()
        c.app.state.store.update(tid, status='completed', result={'file_id': 'unverified'})
        # update() is used by older worker callers; it must honor all terminal states.
        c.app.state.store.event(tid, {'type': 'failed', 'error': 'late'})
        assert c.get('/v1/tasks/' + tid, headers=owner_env.auth('A')).json() == cancelled
        # A failed terminal must have the same protection as cancellation.
        other = owner_env.submit(c).json()['id']
        store = c.app.state.store
        failed = store.event(other, {'type': 'failed', 'error': 'fixture'})
        store.update(other, status='running')
        assert c.get('/v1/tasks/' + other, headers=owner_env.auth('A')).json() == failed


def test_tb07_owned_execution_error_fails_after_cleanup_without_leaking_payload(owner_env):
    backend = owner_env.new_backend(hold=True)
    with owner_env.client(backend=backend, run_worker=True, event_stream_factory=backend.event_stream) as c:
        tid = owner_env.submit(c).json()['id']
        assert backend.started.wait(2)
        try:
            backend.events_to_emit.put({'type': 'execution_error', 'data': {'prompt_id': backend.jobs[0]['prompt_id'],
                'node_id': '7', 'exception_message': 'private-prompt-key-fixture', 'current_inputs': {'prompt': 'private-prompt-key-fixture'}}})
            failed = owner_env.wait_task(c, tid, 'A', lambda t: t['status'] == 'failed')
            assert failed['blocked_reason'] == 'backend_execution_error'
            assert 'private-prompt-key-fixture' not in str(failed)
            assert not backend.running
        finally:
            backend.finish.set()


@pytest.mark.parametrize('status,cancelled,event,stopped,saved,expected', [
    ('cancelled', True, {'type':'save_complete','seq':2,'result':{}}, True, True, 'cancelled'),
    ('running', True, {'type':'backend_stopped','seq':2}, False, False, 'running'),
    ('running', True, {'type':'backend_stopped','seq':2}, True, False, 'cancelled'),
    ('running', False, {'type':'save_complete','seq':2,'result':{}}, False, False, 'running'),
    ('running', False, {'type':'stage','seq':0,'stage':'loading'}, False, False, 'running'),
])
def test_tb07_state_counterexamples(status, cancelled, event, stopped, saved, expected):
    from services.task_lifecycle import apply_event
    task = {'status':status,'stage':'saving','stage_seq':1,'cancel_requested':cancelled}
    out = apply_event(task,event,backend_stopped=stopped,result_saved=saved)
    assert out['status'] == expected
    if event['seq'] <= task['stage_seq']: assert out == task


def test_tb07_cas_rejects_stale_writer_and_preserves_phase_start(owner_env):
    with owner_env.client() as c:
        tid = owner_env.submit(c).json()['id']; store = c.app.state.store
        loading = store.transition(tid,status='running',stage='loading',expected_seq=0)
        assert store.transition(tid,status='running',stage='generating',expected_seq=0) == loading
        sampling = store.transition(tid,status='running',stage='generating',expected_seq=loading['stage_seq'])
        stepped = store.event(tid,{'type':'progress','step':1,'steps':8})
        assert stepped['stage_started_at'] == sampling['stage_started_at']
        assert stepped['stage_updated_at'] >= sampling['stage_updated_at']
        assert store.event(tid,{'type':'progress','step':True,'steps':8}) == stepped
        assert store.event(tid,{'type':'progress','step':2,'steps':40}) == stepped
        assert store.event(tid,{'type':'progress','step':1,'steps':8}) == stepped


def test_tb07_result_reclamation_failure_halts_worker(owner_env, monkeypatch):
    import os
    import threading
    from pathlib import Path
    backend = owner_env.new_backend()
    entered = threading.Event(); release = threading.Event(); saved = []
    fsync, unlink = os.fsync, Path.unlink
    fault = [True]
    def gate(fd):
        path = Path('/proc/self/fd/' + str(fd)).resolve()
        if path.parent == owner_env.root/'files' and not saved:
            saved.append(path); entered.set(); assert release.wait(3)
        return fsync(fd)
    def deny_reclamation(path, *args, **kwargs):
        if fault[0] and path.parent == owner_env.root/'files' and path.name.startswith('file-'):
            raise PermissionError('synthetic result reclamation failure')
        return unlink(path, *args, **kwargs)
    monkeypatch.setattr(os, 'fsync', gate)
    monkeypatch.setattr(Path, 'unlink', deny_reclamation)
    with owner_env.client(backend=backend, run_worker=True) as c:
        tid = owner_env.submit(c).json()['id']; assert entered.wait(2)
        try:
            c.post('/v1/tasks/' + tid + '/cancel', headers=owner_env.auth('A'))
            second = owner_env.submit(c, 'B').json()['id']
        finally:
            release.set()
        try:
            failed = owner_env.wait_task(c, tid, 'A', lambda t: t['status'] == 'failed')
            assert failed['blocked_reason'] == 'cleanup_unconfirmed'
            assert c.get('/health', headers=owner_env.auth('A')).status_code == 503
            assert owner_env.submit(c).status_code == 503
            assert c.get('/v1/tasks/' + second, headers=owner_env.auth('B')).json()['status'] == 'queued'
            assert len(backend.jobs) == 1
        finally:
            fault[0] = False  # let pre-fix teardown finish after the failing assertion


def test_tb07_cancel_waits_for_accepted_free_request(owner_env):
    import asyncio
    import threading
    import httpx
    backend = owner_env.new_backend()
    started = threading.Event(); release = threading.Event(); settled = threading.Event()
    overlapped = threading.Event(); calls = 0
    async def unload_request():
        assert await asyncio.to_thread(release.wait, 5)
        settled.set()
    async def external(request):
        nonlocal calls
        if request.url.path == '/free':
            calls += 1
            if calls == 1:
                operation = asyncio.create_task(unload_request())
                started.set()
                await asyncio.shield(operation)  # server operation survives client cancellation
            return httpx.Response(200, json={})
        if request.url.path == '/prompt' and not settled.is_set(): overlapped.set()
        return await backend(request)
    with owner_env.client(backend=external, run_worker=True) as c:
        try:
            tid = owner_env.submit(c).json()['id']; assert started.wait(2)
            c.post('/v1/tasks/' + tid + '/cancel', headers=owner_env.auth('A'))
            second = owner_env.submit(c, 'B').json()['id']
            assert not overlapped.wait(.5), 'next prompt preceded pending /free response'
            assert c.get('/v1/tasks/' + tid, headers=owner_env.auth('A')).json()['stage'] == 'cancelling'
            assert c.get('/v1/tasks/' + second, headers=owner_env.auth('B')).json()['status'] == 'queued'
        finally:
            release.set()
        owner_env.wait_task(c, tid, 'A', lambda t: t['status'] == 'cancelled')
        owner_env.wait_task(c, second, 'B', lambda t: t['status'] == 'completed')
        assert settled.is_set() and not overlapped.is_set()
