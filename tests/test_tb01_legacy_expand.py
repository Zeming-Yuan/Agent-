"""T01 migration and single-owner compatibility at public boundaries."""
from services.store import Store
import pytest


def test_tb01_legacy_expand_preserves_positional_writes(tmp_path):
    from services.ownership import expand_ownership, preflight_ownership

    store = Store(tmp_path)
    fid = 'file-' + 'a' * 32
    with store.connect() as db:
        db.execute('INSERT INTO files VALUES(?,?,?,?)', (fid, '旧图.png', 3, 1))
    expand_ownership(store.db, 'legacy')
    with store.connect() as db:
        db.execute('INSERT INTO files VALUES(?,?,?,?)',
                   ('file-' + 'b' * 32, 'new.png', 4, 1))
    assert store.file(fid)['bytes'] == 3
    assert preflight_ownership(store.db)['unowned_files'] == 1
    expand_ownership(store.db, 'legacy')
    assert preflight_ownership(store.db)['unowned_files'] == 0


@pytest.mark.parametrize('expanded', [False, True])
def test_tb01_legacy_expand_preflight_is_read_only_and_counts_old_writes(tmp_path, expanded):
    from services.ownership import expand_ownership, preflight_ownership

    store = Store(tmp_path)
    if expanded:
        expand_ownership(store.db, 'legacy')
    with store.connect() as db:
        db.execute('INSERT INTO files VALUES(?,?,?,?)', ('old-file', 'x.png', 1, 1))
        for tid, status, idem in [('q', 'queued', 'retry'), ('r', 'running', None)]:
            db.execute('INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                       (tid, 'image_generate', None, '{}', status, 0,
                        None, None, idem, 'fingerprint', 1, 1))
    before = store.db.read_bytes()
    assert preflight_ownership(store.db) == {
        'unowned_files': 1, 'unowned_tasks': 2,
        'unowned_idempotency_records': 1, 'running_tasks': 1,
    }
    assert store.db.read_bytes() == before
    expand_ownership(store.db, 'legacy')
    assert preflight_ownership(store.db) == {
        'unowned_files': 0, 'unowned_tasks': 0,
        'unowned_idempotency_records': 0, 'running_tasks': 1,
    }


def test_tb01_legacy_expand_preserves_explicit_owner_on_retry(tmp_path):
    from fastapi import HTTPException
    from services.ownership import expand_ownership, require_owner

    store = Store(tmp_path)
    fid = 'file-' + 'c' * 32
    store.add_file(fid, 'owned.png', 1)
    expand_ownership(store.db, 'A')
    for _ in range(3):
        expand_ownership(store.db, 'legacy')
    with store.connect() as db:
        require_owner(db, 'file', fid, 'A')
        errors = []
        for object_id, owner in [(fid, 'legacy'), ('missing', 'A')]:
            with pytest.raises(HTTPException) as exc:
                require_owner(db, 'file', object_id, owner)
            errors.append((exc.value.status_code, exc.value.detail))
        assert errors == [(404, 'Object not found'), (404, 'Object not found')]


def test_tb01_legacy_expand_preflight_missing_database_does_not_create_it(tmp_path):
    import sqlite3
    from services.ownership import preflight_ownership

    missing = tmp_path / 'missing.sqlite3'
    with pytest.raises(sqlite3.OperationalError):
        preflight_ownership(missing)
    assert not missing.exists()


@pytest.mark.parametrize('owner', ['', '   ', None])
def test_tb01_legacy_expand_requires_explicit_owner(tmp_path, owner):
    from services.ownership import expand_ownership

    store = Store(tmp_path)
    before = store.db.read_bytes()
    with pytest.raises(ValueError, match='explicit legacy owner'):
        expand_ownership(store.db, owner)
    assert store.db.read_bytes() == before


def test_tb01_legacy_expand_gateway_initializes_compatibility_metadata(tmp_path, caplog):
    from fastapi.testclient import TestClient
    from services.gateway import create_app
    from services.ownership import preflight_ownership

    store = Store(tmp_path)
    fid = 'file-' + 'd' * 32
    store.save_generated(fid, b'old result', 'result.png')
    task = store.submit('image_generate', None, {}, 'old-request')
    store.update(task['id'], status='completed', result={'file_id': fid})
    import logging
    caplog.set_level(logging.INFO, logger='agent-mm')
    with TestClient(create_app(tmp_path, 'test-secret-token', run_worker=False)) as client:
        auth = {'Authorization': 'Bearer test-secret-token'}
        assert client.get('/v1/tasks/' + task['id'], headers=auth).json()['result'] == {'file_id': fid}
        assert client.get('/v1/files/' + fid + '/content', headers=auth).content == b'old result'
        assert preflight_ownership(store.db) == {
            'unowned_files': 0, 'unowned_tasks': 0,
            'unowned_idempotency_records': 0, 'running_tasks': 0,
        }

    assert 'ownership_preflight unowned_files=1 unowned_tasks=1 unowned_idempotency_records=1 running_tasks=0' in caplog.text
    assert 'old-request' not in caplog.text
    assert 'test-secret-token' not in caplog.text


def test_tb01_legacy_expand_registry_persists_identity_without_raw_keys(tmp_path):
    from services.identity import KeyRegistry

    path = tmp_path / 'keys.sqlite3'
    registry = KeyRegistry(path)
    raw = registry.issue('legacy')
    original = registry.resolve(raw)
    assert original.owner == 'legacy'
    assert len(raw) >= 32
    reopened = KeyRegistry(path)
    assert reopened.register('legacy', raw) == original
    assert reopened.resolve(raw) == original
    rotated = reopened.issue('legacy')
    assert reopened.resolve(rotated).owner == original.owner
    assert reopened.resolve(rotated).key_id != original.key_id
    assert reopened.resolve('unknown-key') is None
    reopened.revoke(original.key_id)
    assert KeyRegistry(path).resolve(raw) is None
    assert reopened.resolve(rotated).owner == 'legacy'
    reopened.register('legacy', raw)
    assert reopened.resolve(raw) is None, 'registration must not undo revocation'
    assert raw.encode() not in path.read_bytes()
    assert rotated.encode() not in path.read_bytes()


@pytest.mark.parametrize('owner,key', [('', 'x' * 32), ('  ', 'x' * 32), ('A', 'short')])
def test_tb01_legacy_expand_registry_rejects_ambiguous_or_weak_identity(tmp_path, owner, key):
    from services.identity import KeyRegistry

    registry = KeyRegistry(tmp_path / 'keys.sqlite3')
    with pytest.raises(ValueError):
        registry.register(owner, key)
    assert registry.resolve(key) is None


def test_tb01_legacy_expand_registry_cannot_reassign_a_key(tmp_path):
    from services.identity import KeyRegistry

    registry = KeyRegistry(tmp_path / 'keys.sqlite3')
    raw = registry.issue('A')
    principal = registry.resolve(raw)
    with pytest.raises(ValueError, match='another owner'):
        registry.register('B', raw)
    assert registry.resolve(raw) == principal


def test_tb01_legacy_expand_legacy_mode_blocks_other_owners(owner_env, caplog):
    import logging
    with caplog.at_level(logging.INFO, logger='agent-mm'), owner_env.client(identity_mode='legacy') as client:
        for owner in ('A', 'B'):
            denied = client.get('/v1/models', headers=owner_env.auth(owner))
            assert denied.status_code == 401
            assert denied.headers['www-authenticate'] == 'Bearer'
            assert denied.headers['x-request-id'] in caplog.text
        assert client.get('/v1/models', headers=owner_env.auth('legacy')).status_code == 200
        owner_env.registry.revoke(owner_env.registry.resolve(owner_env.keys['legacy']).key_id)
        assert client.get('/v1/models', headers=owner_env.auth('legacy')).status_code == 401
    for raw in owner_env.keys.values():
        assert raw not in caplog.text


@pytest.mark.parametrize('mode', ['typo', '', 'strict'])
def test_tb01_legacy_expand_modes_fail_closed_before_migration(tmp_path, mode):
    from services.gateway import create_app

    with pytest.raises(ValueError, match='identity_mode|owner migration'):
        create_app(tmp_path, 'test-secret-token', identity_mode=mode, run_worker=False)
    assert not (tmp_path / 'state.sqlite3').exists()


def test_tb01_legacy_expand_staging_resolves_principal_without_token_fallback(owner_env):
    from fastapi import Request

    client = owner_env.client()

    @client.app.get('/test-principal')
    async def principal(request: Request):
        return {'owner': request.state.principal.owner, 'key_id': request.state.principal.key_id}

    with client:
        for owner in ('legacy', 'A', 'B'):
            response = client.get('/test-principal', headers=owner_env.auth(owner))
            assert response.status_code == 200
            expected = owner_env.registry.resolve(owner_env.keys[owner])
            assert response.json() == {'owner': owner, 'key_id': expected.key_id}
        owner_env.registry.revoke(owner_env.registry.resolve(owner_env.keys['A']).key_id)
        assert client.get('/test-principal', headers=owner_env.auth('A')).status_code == 401
    # With an explicit registry, the positional token has no independent fallback authority.
    from fastapi.testclient import TestClient
    from services.gateway import create_app
    with TestClient(create_app(owner_env.root, 'unregistered-fallback-token',
                               key_registry=owner_env.registry, run_worker=False)) as other:
        assert other.get('/v1/models', headers={'Authorization': 'Bearer unregistered-fallback-token'}).status_code == 401


def test_tb01_legacy_expand_registry_concurrent_registration_keeps_one_identity(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    import secrets
    from services.identity import KeyRegistry

    registry = KeyRegistry(tmp_path / 'keys.sqlite3')
    key = secrets.token_urlsafe(32)
    barrier = threading.Barrier(4)

    def register(_):
        barrier.wait(timeout=3)
        return KeyRegistry(registry.db_path).register('A', key)

    with ThreadPoolExecutor(max_workers=4) as pool:
        principals = list(pool.map(register, range(4)))
    assert len(set(principals)) == 1
    assert registry.resolve(key) == principals[0]


def test_tb01_legacy_expand_old_and_new_complete_image_flow_on_same_copy(owner_env, legacy_services):
    import io
    from PIL import Image
    import httpx
    from fastapi.testclient import TestClient
    from services.ownership import expand_ownership, preflight_ownership

    backend = owner_env.new_backend()
    root = owner_env.root
    legacy = legacy_services.create_app
    auth = owner_env.auth('legacy')
    # Seed the old-format store through the old HTTP application.
    with TestClient(legacy(root, owner_env.keys['legacy'], run_worker=False,
                           transport=httpx.MockTransport(backend), audio_enabled=False,
                           images_enabled=True)) as client:
        reference = owner_env.upload(client, 'legacy')
        queued = owner_env.submit(client, 'legacy', kind='image_edit', request_key='queued-edit',
                                  image_ids=[reference]).json()
        foreground_png = io.BytesIO()
        foreground = Image.new('RGBA', (8, 8), (255, 0, 0, 255))
        foreground.putpixel((0, 0), (0, 0, 0, 0))
        foreground.save(foreground_png, format='PNG')
        uploaded_fg = client.post('/v1/files', headers=auth,
            files={'file': ('foreground.png', foreground_png.getvalue(), 'image/png')})
        assert uploaded_fg.status_code == 200
        foreground_id = uploaded_fg.json()['id']
        queued_fg = owner_env.submit(client, 'legacy', request_key='foreground',
            foreground_file_id=foreground_id).json()
        stopped = owner_env.submit(client, 'legacy', request_key='interrupted').json()
    # A genuinely running row at shutdown is seeded via the old public Store API.
    old_store = legacy_services.Store(root)
    old_store.update(stopped['id'], status='running')
    expand_ownership(old_store.db, 'legacy')
    assert preflight_ownership(old_store.db)['running_tasks'] == 1
    prior_results = []
    for version in ('old', 'new', 'old'):
        options = dict(transport=httpx.MockTransport(backend), audio_enabled=False, images_enabled=True)
        if version == 'old':
            application = legacy(root, owner_env.keys['legacy'], **options)
        else:
            from services.gateway import create_app
            application = create_app(root, owner_env.keys['legacy'], key_registry=owner_env.registry,
                                     identity_mode='legacy', **options)
        with TestClient(application) as client:
            interrupted = client.get('/v1/tasks/' + stopped['id'], headers=auth).json()
            assert interrupted['status'] == 'failed'
            assert interrupted['error'] == 'Service restarted during processing'
            queued_state = owner_env.wait_task(client, queued['id'], 'legacy',
                lambda t: t['status'] in ('completed', 'failed'))
            assert queued_state['status'] == 'completed', queued_state
            assert queued_state['options']['image_ids'] == [reference]
            fg_state = owner_env.wait_task(client, queued_fg['id'], 'legacy',
                lambda t: t['status'] in ('completed', 'failed'))
            assert fg_state['status'] == 'completed', fg_state
            assert fg_state['options']['foreground_file_id'] == foreground_id
            fg_output = client.get(fg_state['result']['content_url'], headers=auth)
            assert fg_output.status_code == 200
            with Image.open(io.BytesIO(fg_output.content)) as image:
                image.load()
                assert image.size == (8, 8)
            for task_id, file_id, data in prior_results:
                task = client.get('/v1/tasks/' + task_id, headers=auth).json()
                assert task['result']['file_id'] == file_id
                assert client.get('/v1/files/' + file_id + '/content', headers=auth).content == data
            uploaded = owner_env.upload(client, 'legacy')
            submitted = owner_env.submit(client, 'legacy', request_key='flow-' + str(len(prior_results)))
            assert submitted.status_code == 202, submitted.text
            task = owner_env.wait_task(client, submitted.json()['id'], 'legacy',
                lambda t: t['status'] in ('completed', 'failed'))
            assert task['status'] == 'completed', task
            repeated = owner_env.submit(client, 'legacy', request_key='flow-' + str(len(prior_results)))
            assert repeated.json()['id'] == task['id']
            output = client.get(task['result']['content_url'], headers=auth)
            assert output.status_code == 200
            with Image.open(io.BytesIO(output.content)) as image:
                image.load()
                assert image.size == (8, 8)
            assert client.get('/v1/files/' + uploaded + '/content', headers=auth).content == backend.png
            prior_results.append((task['id'], task['result']['file_id'], output.content))
    # Old workers also wrote new positional rows after expand; preflight must expose them.
    report = preflight_ownership(old_store.db)
    assert report['unowned_files'] > 0 and report['unowned_tasks'] > 0
    expand_ownership(old_store.db, 'legacy')
    assert preflight_ownership(old_store.db) == {
        'unowned_files': 0, 'unowned_tasks': 0, 'unowned_idempotency_records': 0, 'running_tasks': 0,
    }
    assert len(backend.jobs) == 5  # queued edit/foreground plus one generation per application version


@pytest.mark.parametrize('case', ['test_upload_limit_paths_and_delete', 'test_task_idempotency_cancel_and_persistence'])
@pytest.mark.parametrize('version', ['old', 'new'])
def test_tb01_legacy_expand_original_cases_on_expanded_copy(tmp_path, legacy_services, case, version):
    import runpy
    from pathlib import Path
    from services.gateway import create_app
    from services.ownership import expand_ownership

    store = legacy_services.Store(tmp_path)
    expand_ownership(store.db, 'legacy')
    # Run the unchanged original case using the selected real application factory.
    original = runpy.run_path(str(Path(__file__).with_name('test_gateway.py')))[case]
    original.__globals__['create_app'] = legacy_services.create_app if version == 'old' else create_app
    original(tmp_path)


def test_tb01_legacy_expand_interrupted_transaction_can_retry_without_owner_loss(tmp_path):
    import sqlite3
    from services.ownership import expand_ownership, preflight_ownership, require_owner

    store = Store(tmp_path)
    store.add_file('existing', 'existing.png', 1)
    expand_ownership(store.db, 'A')
    store.add_file('new-file', 'new.png', 1)
    task = store.submit('image_generate', None, {}, 'new-request')
    with store.connect() as db:
        db.execute("""CREATE TRIGGER fail_task_owner BEFORE INSERT ON object_owners
                      WHEN NEW.kind='task' BEGIN SELECT RAISE(ABORT, 'injected interruption'); END""")
    before = preflight_ownership(store.db)
    with pytest.raises(sqlite3.IntegrityError, match='injected interruption'):
        expand_ownership(store.db, 'legacy')
    assert preflight_ownership(store.db) == before
    with store.connect() as db:
        require_owner(db, 'file', 'existing', 'A')
        db.execute('DROP TRIGGER fail_task_owner')
    expand_ownership(store.db, 'legacy')
    with store.connect() as db:
        require_owner(db, 'file', 'existing', 'A')
        require_owner(db, 'file', 'new-file', 'legacy')
        require_owner(db, 'task', task['id'], 'legacy')
    assert preflight_ownership(store.db)['unowned_files'] == 0


def test_tb01_legacy_expand_serializes_with_old_positional_writer(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    from services.ownership import expand_ownership, preflight_ownership

    store = Store(tmp_path)
    started = threading.Event()

    def expand():
        started.set()
        expand_ownership(store.db, 'legacy')

    with ThreadPoolExecutor(max_workers=1) as pool:
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT INTO files VALUES(?,?,?,?)', ('old-writer', 'x.png', 1, 1))
            job = pool.submit(expand)
            assert started.wait(timeout=3)
        job.result(timeout=3)
    assert store.file('old-writer')['bytes'] == 1
    assert preflight_ownership(store.db)['unowned_files'] == 0


def test_tb01_legacy_expand_backup_restores_image_and_task_identity(owner_env, tmp_path):
    import shutil
    import sqlite3
    from fastapi.testclient import TestClient
    from services.gateway import create_app
    from services.ownership import expand_ownership, preflight_ownership

    backend = owner_env.new_backend()
    with owner_env.client(backend=backend, run_worker=True, identity_mode='legacy') as client:
        source = owner_env.upload(client, 'legacy')
        response = owner_env.submit(client, 'legacy', request_key='backup-request')
        assert response.status_code == 202
        task = owner_env.wait_task(client, response.json()['id'], 'legacy',
            lambda t: t['status'] in ('completed', 'failed'))
        assert task['status'] == 'completed', task
        result = client.get(task['result']['content_url'], headers=owner_env.auth('legacy')).content
    expand_ownership(owner_env.root / 'state.sqlite3', 'legacy')
    backup = tmp_path / 'backup'
    backup.mkdir()
    shutil.copytree(owner_env.root / 'files', backup / 'files')
    with sqlite3.connect(owner_env.root / 'state.sqlite3') as old, sqlite3.connect(backup / 'state.sqlite3') as new:
        old.backup(new)
    with sqlite3.connect(owner_env.registry.db_path) as old, sqlite3.connect(backup / 'keys.sqlite3') as new:
        old.backup(new)
    # Restore to a separate root, never overwrite newer data in the original root.
    restored = tmp_path / 'restored'
    shutil.copytree(backup, restored)
    from services.identity import KeyRegistry
    restored_registry = KeyRegistry(restored / 'keys.sqlite3')
    assert restored_registry.resolve(owner_env.keys['legacy']) == owner_env.registry.resolve(owner_env.keys['legacy'])
    restored_app = create_app(restored, owner_env.keys['legacy'], run_worker=False,
                              key_registry=restored_registry)
    with TestClient(restored_app) as client:
        state = client.get('/v1/tasks/' + task['id'], headers=owner_env.auth('legacy')).json()
        assert state['result'] == task['result'] and state['status'] == 'completed'
        assert client.get(task['result']['content_url'], headers=owner_env.auth('legacy')).content == result
        assert client.get('/v1/files/' + source + '/content', headers=owner_env.auth('legacy')).content == backend.png
    assert preflight_ownership(restored / 'state.sqlite3')['unowned_tasks'] == 0
    assert len(backend.jobs) == 1


def test_tb01_legacy_expand_default_key_revocation_survives_app_restart(tmp_path):
    import secrets
    from fastapi.testclient import TestClient
    from services.gateway import create_app
    from services.identity import KeyRegistry

    token = secrets.token_urlsafe(32)
    auth = {'Authorization': 'Bearer ' + token}
    with TestClient(create_app(tmp_path, token, run_worker=False)) as client:
        assert client.get('/v1/models', headers=auth).status_code == 200
        registry = KeyRegistry(tmp_path / 'keys.sqlite3')
        registry.revoke(registry.resolve(token).key_id)
        assert client.get('/v1/models', headers=auth).status_code == 401
    with TestClient(create_app(tmp_path, token, run_worker=False)) as client:
        assert client.get('/v1/models', headers=auth).status_code == 401
