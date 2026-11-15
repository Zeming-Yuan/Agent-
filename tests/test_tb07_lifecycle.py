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
