"""T05 recovery through authenticated HTTP, real persistence and image workers."""
import io
import asyncio
import json

import httpx
import pytest
from PIL import Image


def sync_request(owner_env, backend, kind, *, request_key='sync'):
    headers = {**owner_env.auth('A'), 'Idempotency-Key': request_key}
    if kind == 'image_generate':
        return httpx.Request('POST', 'http://testserver/v1/images/generations', headers=headers,
                             json={'model': 'spark-image', 'prompt': 'fixture'})
    return httpx.Request('POST', 'http://testserver/v1/images/edits', headers=headers,
                         data={'prompt': 'fixture'}, files={'image': ('source.png', backend.png, 'image/png')})


async def disconnecting_asgi_request(app, request, started):
    payload = request.read()
    first = True
    disconnected = False

    async def receive():
        nonlocal first, disconnected
        if first:
            first = False
            return {'type': 'http.request', 'body': payload, 'more_body': False}
        if not started.is_set():
            assert await asyncio.to_thread(started.wait, 2), 'backend never started'
        disconnected = True
        return {'type': 'http.disconnect'}

    async def send(message):
        pass  # The remote client is gone; only durable HTTP recovery matters.

    scope = {'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1',
             'method': request.method, 'scheme': 'http', 'path': request.url.path,
             'raw_path': request.url.raw_path, 'query_string': b'',
             'headers': [(k.lower(), v) for k, v in request.headers.raw], 'client': ('test', 1),
             'server': ('testserver', 80), 'root_path': ''}
    try:
        await asyncio.wait_for(app(scope, receive, send), 3)
    except (asyncio.CancelledError, TimeoutError):
        # The server task may remain in middleware after the client has gone.
        assert disconnected
    except RuntimeError as exc:
        # Starlette reports a cancelled endpoint as no response after disconnect.
        assert disconnected and str(exc) == 'No response returned.'
    assert disconnected


def test_tb05_replay_works_when_image_backend_offline(owner_env):
    backend = owner_env.new_backend()
    with owner_env.client(backend=backend, run_worker=True) as c:
        first = owner_env.submit(c, 'A', request_key='keep')
        assert first.status_code == 202
        tid = first.json()['id']
        owner_env.wait_task(c, tid, 'A', lambda t: t['status'] == 'completed')
        backend.offline.set()
        replay = owner_env.submit(c, 'A', request_key='keep')
        assert replay.status_code == 202, replay.text
        assert replay.json()['id'] == tid
        listing = c.get('/v1/tasks', headers=owner_env.auth('A'))
        assert listing.status_code == 200
        assert [t['id'] for t in listing.json()['data']] == [tid]
        fid = replay.json()['result']['file_id']
        image = c.get('/v1/files/' + fid + '/content', headers=owner_env.auth('A'))
        assert image.status_code == 200
        with Image.open(io.BytesIO(image.content)) as decoded:
            decoded.load()
            assert decoded.format == 'PNG'
        assert len(backend.jobs) == 1


def test_tb05_owner_pagination_and_status_filter_keep_admission_order(owner_env):
    with owner_env.client() as c:
        ids = []
        for owner in ['A', 'B', 'A', 'A']:
            response = owner_env.submit(c, owner)
            assert response.status_code == 202
            ids.append(response.json()['id'])
        assert c.post('/v1/tasks/' + ids[0] + '/cancel', headers=owner_env.auth('A')).status_code == 200
        first = c.get('/v1/tasks', params={'limit': 2}, headers=owner_env.auth('A'))
        assert first.status_code == 200
        assert first.json()['object'] == 'list'
        assert first.json()['has_more'] is True
        assert [t['id'] for t in first.json()['data']] == [ids[0], ids[2]]
        assert first.json()['next_cursor'] == ids[2]
        second = c.get('/v1/tasks', params={'limit': 2, 'after': first.json()['next_cursor']},
                       headers=owner_env.auth('A')).json()
        assert [t['id'] for t in second['data']] == [ids[3]]
        assert second['next_cursor'] is None
        assert second['object'] == 'list' and second['has_more'] is False
        queued = c.get('/v1/tasks', params={'status': 'queued'}, headers=owner_env.auth('A')).json()
        assert [t['id'] for t in queued['data']] == [ids[2], ids[3]]
        cancelled = c.get('/v1/tasks', params={'status': 'cancelled'}, headers=owner_env.auth('A')).json()
        assert [t['id'] for t in cancelled['data']] == [ids[0]]
        # A valid cursor can have a different current status from the filter.
        after_cancel = c.get('/v1/tasks', params={'status': 'queued', 'after': ids[0]},
                             headers=owner_env.auth('A')).json()
        assert [t['id'] for t in after_cancel['data']] == [ids[2], ids[3]]
        assert [t['id'] for t in c.get('/v1/tasks', headers=owner_env.auth('B')).json()['data']] == [ids[1]]
        assert all('owner' not in t and 'idem' not in t and 'fingerprint' not in t for t in first.json()['data'])


@pytest.mark.parametrize('params', [{'status': 'unknown'}, {'status': ''}, {'limit': 0},
                                   {'limit': 101}, {'limit': 'bad'}])
def test_tb05_invalid_listing_options_are_rejected(owner_env, params):
    with owner_env.client() as c:
        assert c.get('/v1/tasks', params=params, headers=owner_env.auth('A')).status_code == 422


def test_tb05_other_owner_cursor_is_not_visible(owner_env):
    with owner_env.client() as c:
        tid = owner_env.submit(c, 'A').json()['id']
        for cursor in [tid, 'task-missing', '']:
            response = c.get('/v1/tasks', params={'after': cursor}, headers=owner_env.auth('B'))
            assert response.status_code == 404
            assert response.json() == {'detail': 'Object not found'}
        for headers in [{}, {'Authorization': 'Bearer unknown'}]:
            assert c.get('/v1/tasks', headers=headers).status_code == 401


def test_tb05_delete_racing_request_fingerprint_never_returns_server_error(owner_env, monkeypatch):
    # Pause only the filesystem boundary; both deletion and submission use HTTP.
    from concurrent.futures import ThreadPoolExecutor
    from pathlib import Path
    import threading

    with owner_env.client() as a, owner_env.client() as b:
        fid = owner_env.upload(a, 'A')
        source = owner_env.root / 'files' / fid
        opening = threading.Event()
        deleting = threading.Event()
        deleted = threading.Event()
        original_open = Path.open

        def controlled_open(path, *args, **kwargs):
            if path == source and args and args[0] == 'rb':
                opening.set()
                assert deleting.wait(2)
                # Without the read transaction, deletion completes before open.
                # With it, deletion waits for hashing to release the SQLite lock.
                deleted.wait(.2)
            return original_open(path, *args, **kwargs)

        monkeypatch.setattr(Path, 'open', controlled_open)

        def remove():
            assert opening.wait(2)
            deleting.set()
            response = b.delete('/v1/files/' + fid, headers=owner_env.auth('A'))
            deleted.set()
            return response

        # TestClient surfaces unhandled500 as an exception; either is a failure.
        with ThreadPoolExecutor(max_workers=2) as pool:
            deletion = pool.submit(remove)
            submission = pool.submit(owner_env.submit, a, 'A', kind='image_edit',
                                     request_key='race-delete', image_ids=[fid])
            response = submission.result(timeout=5)
            removed = deletion.result(timeout=5)
        assert response.status_code in (202, 404), response.text
        assert removed.status_code in (200, 409)
        if response.status_code == 202:
            assert removed.status_code == 409


@pytest.mark.parametrize('kind', ['image_generate', 'image_edit'])
def test_tb05_sync_disconnect_does_not_cancel_work(owner_env, kind):
    backend = owner_env.new_backend(hold=True)
    with owner_env.client(backend=backend, run_worker=True) as c:
        c.portal.call(disconnecting_asgi_request, c.app, sync_request(owner_env, backend, kind), backend.started)
        rows = c.get('/v1/tasks', headers=owner_env.auth('A')).json()['data']
        assert len(rows) == 1
        assert rows[0]['status'] in ('queued', 'running')
        running = c.get('/v1/tasks', params={'status': 'running'}, headers=owner_env.auth('A')).json()['data']
        assert [t['id'] for t in running] == [rows[0]['id']]
        backend.finish.set()
        done = owner_env.wait_task(c, rows[0]['id'], 'A', lambda t: t['status'] in ('completed', 'failed', 'cancelled'))
        assert done['status'] == 'completed'
        image = c.get('/v1/files/' + done['result']['file_id'] + '/content', headers=owner_env.auth('A'))
        assert image.status_code == 200
        with Image.open(io.BytesIO(image.content)) as decoded:
            decoded.load()
        assert len(backend.jobs) == 1


@pytest.mark.parametrize('kind', ['image_generate', 'image_edit'])
def test_tb05_sync_replay_works_when_image_backend_offline(owner_env, kind):
    backend = owner_env.new_backend()
    with owner_env.client(backend=backend, run_worker=True) as c:
        first = c.send(sync_request(owner_env, backend, kind))
        assert first.status_code == 200, first.text
        backend.offline.set()
        replay = c.send(sync_request(owner_env, backend, kind))
        assert replay.status_code == 200, replay.text
        assert replay.json()['task_id'] == first.json()['task_id']
        assert replay.json()['data'] == first.json()['data']
        assert len(c.get('/v1/tasks', headers=owner_env.auth('A')).json()['data']) == 1
        assert len(backend.jobs) == 1


@pytest.mark.parametrize('kind', ['image_generate', 'image_edit'])
def test_tb05_sync_wait_timeout_keeps_task_id_and_can_resume(owner_env, monkeypatch, kind):
    from types import SimpleNamespace
    from services import image_routes

    backend = owner_env.new_backend()
    # Only the route's clock is substituted; the event loop/worker clocks are real.
    clock = iter([0, 571])
    with owner_env.client(backend=backend) as c:
        with monkeypatch.context() as patch:
            patch.setattr(image_routes, 'time', SimpleNamespace(monotonic=lambda: next(clock)))
            response = c.send(sync_request(owner_env, backend, kind, request_key='timeout'))
        assert response.status_code == 504
        tid = response.json()['detail']['task_id']
        assert c.get('/v1/tasks/' + tid, headers=owner_env.auth('A')).json()['status'] == 'queued'
        assert len(backend.jobs) == 0
    with owner_env.client(backend=backend, run_worker=True) as c:
        done = owner_env.wait_task(c, tid, 'A', lambda t: t['status'] == 'completed')
        assert c.get(done['result']['content_url'], headers=owner_env.auth('A')).status_code == 200
        replay = c.send(sync_request(owner_env, backend, kind, request_key='timeout'))
        assert replay.status_code == 200 and replay.json()['task_id'] == tid
        assert len(backend.jobs) == 1


async def lose_response(app, request):
    class LostResponseTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            response = await httpx.ASGITransport(app=app).handle_async_request(request)
            await response.aread()
            raise httpx.ReadTimeout('response lost', request=request)

    async with httpx.AsyncClient(transport=LostResponseTransport()) as client:
        with pytest.raises(httpx.ReadTimeout, match='response lost'):
            await client.send(request)


@pytest.mark.parametrize('kind', ['image_generate', 'image_edit'])
def test_tb05_async_lost_response_and_query_timeout_recover_original_work(owner_env, kind):
    backend = owner_env.new_backend(hold=True)
    with owner_env.client(backend=backend, run_worker=True) as c:
        options = {'prompt': 'fixture'}
        if kind == 'image_edit':
            options['image_ids'] = [owner_env.upload(c, 'A')]
        headers = {**owner_env.auth('A'), 'Idempotency-Key': 'lost-response'}
        request = httpx.Request('POST', 'http://testserver/v1/tasks', headers=headers,
                                json={'kind': kind, 'options': options})
        c.portal.call(lose_response, c.app, request)
        rows = c.get('/v1/tasks', headers=owner_env.auth('A')).json()['data']
        assert len(rows) == 1
        tid = rows[0]['id']
        assert backend.started.wait(3)
        query = httpx.Request('GET', 'http://testserver/v1/tasks/' + tid, headers=owner_env.auth('A'))
        c.portal.call(lose_response, c.app, query)
        assert c.get('/v1/tasks/' + tid, headers=owner_env.auth('A')).json()['status'] == 'running'
        replay = c.send(httpx.Request('POST', 'http://testserver/v1/tasks', headers=headers,
                                     json={'kind': kind, 'options': options}))
        assert replay.status_code == 202 and replay.json()['id'] == tid
        backend.finish.set()
        done = owner_env.wait_task(c, tid, 'A', lambda t: t['status'] == 'completed')
        assert c.get(done['result']['content_url'], headers=owner_env.auth('A')).status_code == 200
        assert len(backend.jobs) == 1


@pytest.mark.parametrize('entry', ['create_app', 'factory'])
def test_tb05_strict_restart_after_process_crash_preserves_queue_and_results(owner_env, monkeypatch, entry):
    import shutil
    import subprocess
    import sys
    from scripts.migrate_image_owners import contract_ownership

    with owner_env.client():
        pass  # Create an empty owned store before the explicit offline migration.
    contract_ownership(owner_env.root / 'state.sqlite3', 'legacy')
    backend = owner_env.new_backend()
    with owner_env.client(identity_mode='strict', backend=backend, run_worker=True) as c:
        completed = owner_env.submit(c, 'A', request_key='saved').json()['id']
        done = owner_env.wait_task(c, completed, 'A', lambda t: t['status'] == 'completed')
        result_url = done['result']['content_url']
        original = c.get(result_url, headers=owner_env.auth('A')).content
    child = subprocess.run([sys.executable, '-c', '''
import json,os,sys
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'tests'))
from conftest import ImageBackend
from fastapi.testclient import TestClient
import httpx
from services.gateway import create_app
from services.identity import KeyRegistry
cfg=json.load(sys.stdin)
backend=ImageBackend(hold=True)
app=create_app(Path(cfg['root']),'',key_registry=KeyRegistry(Path(cfg['registry'])),
    identity_mode='strict',images_enabled=True,audio_enabled=False,
    transport=httpx.MockTransport(backend))
c=TestClient(app);c.__enter__()
def submit(key):
    r=c.post('/v1/tasks',headers={**cfg['auth'],'Idempotency-Key':key},
        json={'kind':'image_generate','options':{'prompt':'fixture'}})
    assert r.status_code==202
    return r.json()['id']
running=submit('interrupted')
assert backend.started.wait(3)
queued=submit('queued')
print(json.dumps({'running':running,'queued':queued,'jobs':len(backend.jobs)}),flush=True)
os._exit(0)  # Deliberate process loss: no lifespan shutdown/recover fabrication.
'''], input=json.dumps({'root': str(owner_env.root),
                       'registry': str(owner_env.registry.db_path),
                       'auth': owner_env.auth('A')}), capture_output=True, text=True, timeout=10)
    assert child.returncode == 0, child.stderr
    interrupted = json.loads(child.stdout)
    assert interrupted['jobs'] == 1
    # A fresh process/app sees real persisted queued/running/completed states.
    offline = owner_env.new_backend()
    offline.offline.set()
    if entry == 'factory':
        from fastapi.testclient import TestClient
        from services import gateway
        # A restored isolated application directory, never the real .private.
        base = owner_env.root.parent / 'factory-source'
        restored = base / '.private' / 'runtime'
        shutil.copytree(owner_env.root, restored)
        shutil.copy2(owner_env.registry.db_path, restored / 'keys.sqlite3')
        monkeypatch.setattr(gateway, '__file__', str(base / 'services' / 'gateway.py'))
        monkeypatch.setenv('AGENT_IDENTITY_MODE', 'strict')
        monkeypatch.setenv('IMAGES_ENABLED', '1')
        monkeypatch.setenv('AUDIO_ENABLED', '0')
        monkeypatch.delenv('MAIN_TOKEN_FILE', raising=False)
        original_client = httpx.AsyncClient

        class OfflineClient(original_client):
            def __init__(self, *args, **kwargs):
                if kwargs.get('transport') is None:
                    kwargs['transport'] = httpx.MockTransport(lambda req: httpx.Response(503))
                super().__init__(*args, **kwargs)

        monkeypatch.setattr(httpx, 'AsyncClient', OfflineClient)
        recovering = TestClient(gateway.application())
    else:
        recovering = owner_env.client(identity_mode='strict', backend=offline)
    with recovering as c:
        expected = {completed: 'completed', interrupted['running']: 'failed', interrupted['queued']: 'queued'}
        rows = c.get('/v1/tasks', headers=owner_env.auth('A')).json()['data']
        assert {t['id']: t['status'] for t in rows} == expected
        for status, tid in [('completed', completed), ('failed', interrupted['running']), ('queued', interrupted['queued'])]:
            filtered = c.get('/v1/tasks', params={'status': status}, headers=owner_env.auth('A')).json()
            assert [t['id'] for t in filtered['data']] == [tid]
        assert c.get(result_url, headers=owner_env.auth('A')).content == original
        assert c.get('/v1/tasks', headers=owner_env.auth('B')).json()['data'] == []
        for key, tid in [('saved', completed), ('interrupted', interrupted['running']), ('queued', interrupted['queued'])]:
            replay = owner_env.submit(c, 'A', request_key=key)
            assert replay.status_code == 202 and replay.json()['id'] == tid
        assert 'restart' in c.get('/v1/tasks/' + interrupted['running'], headers=owner_env.auth('A')).json()['error'].lower()
        assert len(offline.jobs) == 0
    # Only the previously queued task is executed when workers resume.
    resumed = owner_env.new_backend()
    with owner_env.client(identity_mode='strict', backend=resumed, run_worker=True) as c:
        owner_env.wait_task(c, interrupted['queued'], 'A', lambda t: t['status'] == 'completed')
        assert c.get('/v1/tasks/' + interrupted['running'], headers=owner_env.auth('A')).json()['status'] == 'failed'
        assert len(resumed.jobs) == 1


@pytest.mark.parametrize('kind', ['image_generate', 'image_edit'])
def test_tb05_offline_replay_conflict_and_owner_scope(owner_env, kind):
    backend = owner_env.new_backend()
    with owner_env.client(backend=backend, run_worker=True) as c:
        options = {'image_ids': [owner_env.upload(c, 'A')]} if kind == 'image_edit' else {}
        tid = owner_env.submit(c, 'A', kind=kind, request_key='private', **options).json()['id']
        done = owner_env.wait_task(c, tid, 'A', lambda t: t['status'] == 'completed')
        backend.offline.set()
        if kind == 'image_edit':
            # A new upload with identical content still identifies the same request.
            options['image_ids'] = [owner_env.upload(c, 'A')]
        replay = owner_env.submit(c, 'A', kind=kind, request_key='private', **options)
        assert replay.status_code == 202 and replay.json()['id'] == tid
        assert owner_env.submit(c, 'A', kind=kind, request_key='private', prompt='changed', **options).status_code == 409
        b_options = {'image_ids': [owner_env.upload(c, 'B')]} if kind == 'image_edit' else {}
        assert owner_env.submit(c, 'B', kind=kind, request_key='private', **b_options).status_code == 503
        assert c.get('/v1/tasks', headers=owner_env.auth('B')).json()['data'] == []
        assert c.get(done['result']['content_url'], headers=owner_env.auth('B')).status_code == 404
        assert owner_env.submit(c, 'A', kind=kind, request_key='new', **options).status_code == 503
        assert len(backend.jobs) == 1


@pytest.mark.parametrize('entry', ['async_generate', 'async_edit', 'sync_generate', 'sync_edit'])
def test_tb05_new_work_offline_is_rejected_without_new_task(owner_env, entry):
    backend = owner_env.new_backend()
    backend.offline.set()
    with owner_env.client(backend=backend) as c:
        if entry.startswith('async'):
            kind = 'image_edit' if entry.endswith('edit') else 'image_generate'
            options = {'image_ids': [owner_env.upload(c, 'A')]} if kind == 'image_edit' else {}
            response = owner_env.submit(c, 'A', kind=kind, request_key='new', **options)
        else:
            kind = 'image_edit' if entry.endswith('edit') else 'image_generate'
            response = c.send(sync_request(owner_env, backend, kind, request_key='new'))
        assert response.status_code == 503
        assert c.get('/v1/tasks', headers=owner_env.auth('A')).json()['data'] == []
        assert len(backend.jobs) == 0
        if entry == 'sync_edit':
            # Failed admission rolls back this call's automatic reference upload.
            assert list((owner_env.root / 'files').iterdir()) == []


@pytest.mark.parametrize('entry', ['async', 'sync_generate', 'sync_edit'])
def test_tb05_deleted_result_is_unavailable_without_rerun(owner_env, entry):
    backend = owner_env.new_backend()
    with owner_env.client(backend=backend, run_worker=True) as c:
        if entry == 'async':
            response = owner_env.submit(c, 'A', request_key='delete')
            tid = response.json()['id']
            done = owner_env.wait_task(c, tid, 'A', lambda t: t['status'] == 'completed')
            fid = done['result']['file_id']
        else:
            kind = 'image_edit' if entry.endswith('edit') else 'image_generate'
            response = c.send(sync_request(owner_env, backend, kind, request_key='delete'))
            assert response.status_code == 200
            tid, fid = response.json()['task_id'], response.json()['data'][0]['file_id']
        assert c.delete('/v1/files/' + fid, headers=owner_env.auth('A')).status_code == 200
        backend.offline.set()
        if entry == 'async':
            replay = owner_env.submit(c, 'A', request_key='delete')
            assert replay.status_code == 202 and replay.json()['id'] == tid
        else:
            assert c.send(sync_request(owner_env, backend, kind, request_key='delete')).status_code == 404
        assert c.get('/v1/files/' + fid + '/content', headers=owner_env.auth('A')).status_code == 404
        assert c.get('/v1/tasks/' + tid, headers=owner_env.auth('A')).json()['status'] == 'completed'
        assert len(backend.jobs) == 1


def test_tb05_default_and_maximum_page_boundaries_with_equal_timestamps(owner_env, monkeypatch):
    from types import SimpleNamespace
    from services import store
    monkeypatch.setattr(store, 'time', SimpleNamespace(time=lambda: 1700000000))
    with owner_env.client() as c:
        ids = []
        for _ in range(25):
            response = owner_env.submit(c, 'A')
            assert response.status_code == 202
            tid = response.json()['id']
            ids.append(tid)
            assert c.post('/v1/tasks/' + tid + '/cancel', headers=owner_env.auth('A')).status_code == 200
        first = c.get('/v1/tasks', headers=owner_env.auth('A')).json()
        assert [t['id'] for t in first['data']] == ids[:20]
        assert first['has_more'] is True and first['next_cursor'] == ids[19]
        last = c.get('/v1/tasks', params={'after': first['next_cursor']}, headers=owner_env.auth('A')).json()
        assert [t['id'] for t in last['data']] == ids[20:]
        assert last['has_more'] is False and last['next_cursor'] is None
        all_rows = c.get('/v1/tasks', params={'limit': 100}, headers=owner_env.auth('A')).json()
        assert [t['id'] for t in all_rows['data']] == ids
        assert all_rows['has_more'] is False


def test_tb05_unowned_task_is_absent_from_list_and_cursor(owner_env):
    import sqlite3
    with owner_env.client() as c:
        tid = owner_env.submit(c, 'A').json()['id']
        # External corruption injection; never infer an owner for an orphan.
        with sqlite3.connect(owner_env.root / 'state.sqlite3') as db:
            db.execute("DELETE FROM object_owners WHERE kind='task' AND object_id=?", (tid,))
        for owner in ['A', 'B']:
            assert c.get('/v1/tasks', headers=owner_env.auth(owner)).json()['data'] == []
            missing = c.get('/v1/tasks', params={'after': tid}, headers=owner_env.auth(owner))
            assert missing.status_code == 404 and missing.json() == {'detail': 'Object not found'}


@pytest.mark.parametrize('kind', ['image_generate', 'image_edit'])
def test_tb05_concurrent_new_request_rechecks_mapping_after_readiness(owner_env, kind):
    from concurrent.futures import ThreadPoolExecutor
    import threading

    backend = owner_env.new_backend()
    barrier = threading.Barrier(2)

    async def controlled_backend(request):
        if request.url.path == '/system_stats':
            await asyncio.to_thread(barrier.wait, 3)
        return await backend(request)

    with owner_env.client(backend=controlled_backend, run_worker=True) as c:
        options = {'image_ids': [owner_env.upload(c, 'A')]} if kind == 'image_edit' else {}
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(owner_env.submit, c, 'A', kind=kind, request_key='race', **options) for _ in range(2)]
            responses = [future.result(timeout=5) for future in futures]
        assert [r.status_code for r in responses] == [202, 202]
        tid = responses[0].json()['id']
        assert responses[1].json()['id'] == tid
        owner_env.wait_task(c, tid, 'A', lambda t: t['status'] == 'completed')
        assert [t['id'] for t in c.get('/v1/tasks', headers=owner_env.auth('A')).json()['data']] == [tid]
        assert len(backend.jobs) == 1


def test_tb05_offline_key_rotation_keeps_owner_recovery_scope(owner_env):
    backend = owner_env.new_backend()
    with owner_env.client(backend=backend, run_worker=True) as c:
        tid = owner_env.submit(c, 'A', request_key='rotate').json()['id']
        done = owner_env.wait_task(c, tid, 'A', lambda t: t['status'] == 'completed')
        old_headers = owner_env.auth('A')
        old = owner_env.registry.resolve(owner_env.keys['A'])
        owner_env.keys['A'] = owner_env.registry.issue('A')
        owner_env.registry.revoke(old.key_id)
        backend.offline.set()
        assert c.get('/v1/tasks', headers=old_headers).status_code == 401
        listing = c.get('/v1/tasks', headers={**owner_env.auth('A'), 'X-Request-ID': 'recovery-audit'})
        assert listing.headers['x-request-id'] == 'recovery-audit'
        assert [t['id'] for t in listing.json()['data']] == [tid]
        assert owner_env.submit(c, 'A', request_key='rotate').json()['id'] == tid
        assert c.get(done['result']['content_url'], headers=owner_env.auth('A')).status_code == 200
        assert c.get('/v1/tasks', headers=owner_env.auth('B')).json()['data'] == []
        assert len(backend.jobs) == 1


def test_tb05_replay_is_readable_after_uncertain_submission_stops_worker(owner_env):
    backend = owner_env.new_backend()

    async def lose_backend_response(request):
        response = await backend(request)
        if request.url.path == '/prompt':
            raise httpx.ReadTimeout('backend accepted but response lost', request=request)
        return response

    with owner_env.client(backend=lose_backend_response, run_worker=True) as c:
        tid = owner_env.submit(c, 'A', request_key='uncertain').json()['id']
        done = owner_env.wait_task(c, tid, 'A', lambda t: t['status'] == 'failed')
        assert 'unknown' in done['error'].lower()
        assert c.get('/health', headers=owner_env.auth('A')).status_code == 503
        replay = owner_env.submit(c, 'A', request_key='uncertain')
        assert replay.status_code == 202 and replay.json()['id'] == tid
        assert replay.json()['status'] == 'failed'
        assert owner_env.submit(c, 'A', request_key='new').status_code == 503
        assert len(backend.jobs) == 1
