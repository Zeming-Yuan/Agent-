"""T04 migration/CLI and HTTP acceptance on synthetic offline copies."""
import pytest
from services.store import Store


def test_tb04_owner_contract_running_task_blocks_contract(tmp_path):
    from scripts.migrate_image_owners import contract_ownership
    store = Store(tmp_path)
    task = store.submit('image_generate', None, {'prompt': 'x'}, None, owner='legacy')
    store.update(task['id'], status='running')
    before = store.db.read_bytes()
    with pytest.raises(ValueError, match='running'):
        contract_ownership(store.db, 'legacy')
    assert store.db.read_bytes() == before


def test_tb04_owner_contract_backup_is_private_complete_and_exclusive(tmp_path):
    import hashlib
    import json
    import sqlite3
    from scripts.migrate_image_owners import backup_state
    from services.identity import KeyRegistry
    store = Store(tmp_path / 'runtime')
    fid = 'file-' + 'd' * 32
    store.save_generated(fid, b'old', 'old.png', owner='legacy')
    keys = KeyRegistry(store.root / 'keys.sqlite3')
    raw = keys.issue('legacy')
    target = tmp_path / 'backup'
    hashes = backup_state(store.db, target)
    assert (target / 'files' / fid).read_bytes() == b'old'
    with sqlite3.connect(target / 'state.sqlite3') as db:
        assert db.execute('SELECT id FROM files').fetchall() == [(fid,)]
    assert KeyRegistry(target / 'keys.sqlite3').resolve(raw).owner == 'legacy'
    assert json.loads((target / 'manifest.json').read_text()) == hashes
    assert all(hashlib.sha256((target / path).read_bytes()).hexdigest() == digest
               for path, digest in hashes.items())
    assert target.stat().st_mode & 0o777 == 0o700
    assert all(p.stat().st_mode & 0o077 == 0 for p in target.rglob('*'))
    with pytest.raises(FileExistsError):
        backup_state(store.db, target)
    assert (target / 'files' / fid).read_bytes() == b'old'


def test_tb04_owner_contract_repeat_keeps_legacy_ids_requests_and_indexes(tmp_path, legacy_services):
    import sqlite3
    from scripts.migrate_image_owners import contract_ownership
    store = legacy_services.Store(tmp_path / 'runtime')
    fid = 'file-' + 'd' * 32
    store.save_generated(fid, b'old', 'old.png')
    task = store.submit('image_generate', None, {'prompt': 'x'}, 'request-one')
    with store.connect() as db:
        db.execute('CREATE INDEX tasks_created ON tasks(created)')
        before = tuple(db.execute('SELECT rowid,* FROM tasks').fetchone())
    first = contract_ownership(store.db, 'legacy')
    second = contract_ownership(store.db, 'legacy')
    assert first['version'] == second['version'] == 1
    assert first['legacy_owner'] == 'legacy'
    with store.connect() as db:
        assert tuple(db.execute('SELECT rowid,* FROM tasks').fetchone()) == before
        assert tuple(db.execute('SELECT kind,object_id,owner FROM object_owners WHERE kind=\'file\'').fetchone()) == ('file', fid, 'legacy')
        assert tuple(db.execute('SELECT owner,request_key,task_id FROM task_requests').fetchone()) == ('legacy', 'request-one', task['id'])
        assert db.execute("SELECT 1 FROM sqlite_master WHERE name='tasks_created'").fetchone()
        db.execute("INSERT INTO tasks(id,idem) VALUES('another-task','request-one')")
    assert (store.files / fid).read_bytes() == b'old'
    backup = __import__('pathlib').Path(first['backup_dir'])
    with sqlite3.connect(backup / 'state.sqlite3') as db:
        assert db.execute("SELECT 1 FROM sqlite_master WHERE name='ownership_migration'").fetchone() is None
    assert (backup / 'files' / fid).read_bytes() == b'old'


@pytest.mark.parametrize('field', ['file_id', 'image_ids', 'foreground_file_id', 'result', 'source_result'])
@pytest.mark.parametrize('problem', ['dangling', 'cross-owner'])
def test_tb04_owner_contract_invalid_reference_refuses_without_writes(tmp_path, field, problem):
    import json
    from scripts.migrate_image_owners import contract_ownership
    store = Store(tmp_path)
    task = store.submit('image_generate', None, {'prompt': 'private prompt'}, None, owner='legacy')
    fid = 'file-' + 'f' * 32
    if problem == 'cross-owner':
        store.save_generated(fid, b'other', 'other.png', owner='B')
    with store.connect() as db:
        if field == 'file_id':
            db.execute('UPDATE tasks SET file_id=?', (fid,))
        elif field in ('result', 'source_result'):
            db.execute('UPDATE tasks SET result=?', (json.dumps({'file_id' if field == 'result' else 'source_file_id': fid}),))
        else:
            db.execute('UPDATE tasks SET options=?', (json.dumps({field: [fid] if field == 'image_ids' else fid}),))
    before = store.db.read_bytes()
    with pytest.raises(ValueError, match=problem) as exc:
        contract_ownership(store.db, 'legacy')
    assert task['id'] in str(exc.value)
    assert 'private prompt' not in str(exc.value)
    assert store.db.read_bytes() == before


@pytest.mark.parametrize('problem', ['wrong-legacy', 'missing-bytes', 'symlink', 'bad-options', 'empty-owner',
                                      'orphan-owner', 'orphan-request', 'cross-request', 'orphan-digest', 'cross-digest', 'conflicting-request'])
def test_tb04_owner_contract_preflight_rejects_invalid_state(tmp_path, problem):
    from scripts.migrate_image_owners import contract_ownership
    store = Store(tmp_path / 'runtime')
    fid = 'file-' + 'd' * 32
    store.save_generated(fid, b'old', 'old.png', owner='legacy')
    task = store.submit('image_generate', None, {'prompt': 'x'}, 'old-key', owner='legacy')
    legacy = 'another' if problem == 'wrong-legacy' else 'legacy'
    with store.connect() as db:
        if problem == 'missing-bytes':
            (store.files / fid).unlink()
        elif problem == 'symlink':
            secret = tmp_path / 'outside'; secret.write_bytes(b'old')
            (store.files / fid).unlink(); (store.files / fid).symlink_to(secret)
        elif problem == 'bad-options':
            db.execute("UPDATE tasks SET options='[]'")
        elif problem == 'empty-owner':
            db.execute("UPDATE object_owners SET owner=' '")
        elif problem == 'orphan-owner':
            db.execute("INSERT INTO object_owners VALUES('file','missing','legacy')")
        elif problem == 'orphan-request':
            db.execute("UPDATE task_requests SET task_id='missing'")
        elif problem == 'cross-request':
            db.execute("UPDATE task_requests SET owner='B'")
        elif problem == 'conflicting-request':
            db.execute("UPDATE tasks SET idem='old-key'")  # frozen old representation
            other = 'task-' + 'f' * 32
            db.execute('INSERT INTO tasks(id,options,status) VALUES(?,?,?)', (other, '{}', 'failed'))
            db.execute("INSERT INTO object_owners VALUES('task',?,'legacy')", (other,))
            db.execute('UPDATE task_requests SET task_id=?', (other,))
        elif problem == 'orphan-digest':
            db.execute("INSERT INTO file_digests VALUES('legacy','digest','missing')")
        elif problem == 'cross-digest':
            db.execute("INSERT INTO file_digests VALUES('B','digest',?)", (fid,))
    before = store.db.read_bytes()
    with pytest.raises(ValueError):
        contract_ownership(store.db, legacy)
    assert store.db.read_bytes() == before
    assert not (store.root / 'ownership-backups').exists()


def test_tb04_owner_contract_cli_dry_run_and_missing_identity_are_read_only(tmp_path):
    import json
    import subprocess
    import sys
    store = Store(tmp_path / 'runtime')
    before = store.db.read_bytes()
    command = [sys.executable, '-m', 'scripts.migrate_image_owners', '--db', str(store.db)]
    missing = subprocess.run(command + ['--dry-run'], capture_output=True, text=True)
    assert missing.returncode != 0
    dry = subprocess.run(command + ['--legacy-owner', 'legacy', '--dry-run'], capture_output=True, text=True)
    assert dry.returncode == 0, dry.stderr
    assert json.loads(dry.stdout)['ready'] is True
    assert store.db.read_bytes() == before
    assert not (store.root / 'ownership-backups').exists()
    target = tmp_path / 'backup'
    migrated = subprocess.run(command + ['--legacy-owner', 'legacy', '--backup-dir', str(target)], capture_output=True, text=True)
    assert migrated.returncode == 0, migrated.stderr
    assert json.loads(migrated.stdout)['version'] == 1
    assert (target / 'manifest.json').exists()
    absent = tmp_path / 'absent' / 'state.sqlite3'
    bad = subprocess.run([sys.executable, '-m', 'scripts.migrate_image_owners', '--db', str(absent), '--legacy-owner', 'legacy', '--dry-run'], capture_output=True, text=True)
    assert bad.returncode != 0
    assert not absent.parent.exists()


@pytest.mark.parametrize('stage', ['create', 'copy', 'rename'])
def test_tb04_owner_contract_sqlite_interruption_rolls_back_and_can_retry(tmp_path, legacy_services, monkeypatch, stage):
    import sqlite3
    from pathlib import Path
    from scripts.migrate_image_owners import contract_ownership
    store = legacy_services.Store(tmp_path / 'runtime')
    fid = 'file-' + 'd' * 32
    store.save_generated(fid, b'old', 'old.png')
    task = store.submit('image_generate', None, {'prompt': 'x'}, 'one')
    before = store.db.read_bytes()
    connect = sqlite3.connect
    def connection(*args, **kwargs):
        db = connect(*args, **kwargs)
        if str(args[0]).startswith(store.db.resolve().as_uri()) and 'mode=rw' in str(args[0]):
            def authorize(action, a, b, database, source):
                refused = ((stage == 'create' and action == sqlite3.SQLITE_CREATE_TABLE and a == 'tasks_next') or
                           (stage == 'copy' and action == sqlite3.SQLITE_INSERT and a == 'tasks_next') or
                           (stage == 'rename' and action == sqlite3.SQLITE_ALTER_TABLE and b == 'tasks_next'))
                return sqlite3.SQLITE_DENY if refused else sqlite3.SQLITE_OK
            db.set_authorizer(authorize)
        return db
    with monkeypatch.context() as fault:
        fault.setattr(sqlite3, 'connect', connection)
        with pytest.raises(sqlite3.DatabaseError, match='authorized'):
            contract_ownership(store.db, 'legacy')
    assert store.db.read_bytes() == before
    assert store.task(task['id'])['status'] == 'queued'
    assert store.path(fid).read_bytes() == b'old'
    report = contract_ownership(store.db, 'legacy')
    assert Path(report['backup_dir']).is_dir()


@pytest.mark.parametrize('owner', ['', ' ', None, 'A'])
def test_tb04_owner_contract_requires_stable_explicit_identity(tmp_path, owner):
    from scripts.migrate_image_owners import contract_ownership
    store = Store(tmp_path)
    before = store.db.read_bytes()
    with pytest.raises(ValueError, match='legacy'):
        contract_ownership(store.db, owner)
    assert store.db.read_bytes() == before


@pytest.mark.parametrize('unsafe', ['orphan-symlink', 'files-symlink', 'keys-symlink', 'nested-backup'])
def test_tb04_owner_contract_backup_refuses_unsafe_filesystem(tmp_path, unsafe):
    from scripts.migrate_image_owners import backup_state
    store = Store(tmp_path / 'runtime')
    outside = tmp_path / 'outside'; outside.mkdir()
    (outside / 'private').write_bytes(b'private')
    target = tmp_path / 'backup'
    if unsafe == 'orphan-symlink':
        (store.files / 'orphan').symlink_to(outside / 'private')
    elif unsafe == 'files-symlink':
        store.files.rmdir(); store.files.symlink_to(outside, target_is_directory=True)
    elif unsafe == 'keys-symlink':
        from services.identity import KeyRegistry
        KeyRegistry(outside / 'keys.sqlite3').issue('B')
        (store.root / 'keys.sqlite3').symlink_to(outside / 'keys.sqlite3')
    else:
        target = store.files / 'backup'
    with pytest.raises(ValueError, match='unsafe'):
        backup_state(store.db, target)
    assert not target.exists()


def test_tb04_owner_contract_preserves_explicit_triggers(tmp_path):
    from scripts.migrate_image_owners import contract_ownership
    store = Store(tmp_path)
    with store.connect() as db:
        db.execute('CREATE TABLE task_audit(task_id TEXT)')
        db.execute('CREATE TRIGGER audit_task AFTER INSERT ON tasks BEGIN INSERT INTO task_audit VALUES(new.id); END')
    contract_ownership(store.db, 'legacy')
    created = store.submit('image_generate', None, {'prompt': 'x'}, None, owner='legacy')
    with store.connect() as db:
        assert [row[0] for row in db.execute('SELECT task_id FROM task_audit')] == [created['id']]


def test_tb04_owner_contract_preview_refuses_linked_files_root(tmp_path):
    from scripts.migrate_image_owners import contract_ownership
    from services.ownership import inspect_contract
    store = Store(tmp_path / 'runtime')
    outside = tmp_path / 'outside'; outside.mkdir()
    store.files.rmdir(); store.files.symlink_to(outside, target_is_directory=True)
    before = store.db.read_bytes()
    with pytest.raises(ValueError, match='unsafe'):
        inspect_contract(store.db, legacy_owner='legacy')
    assert store.db.read_bytes() == before


@pytest.mark.parametrize('method,args', [
    ('file', ('file-missing',)), ('path', ('file-missing',)),
    ('add_file', ('file-missing', 'x', 0)), ('save_generated', ('file-missing', b'x', 'x')),
    ('delete_file', ('file-missing',)), ('task', ('task-missing',)),
    ('submit', ('image_generate', None, {'prompt': 'x'}, None)),
])
def test_tb04_owner_contract_user_store_methods_require_explicit_owner(tmp_path, method, args):
    store = Store(tmp_path)
    with pytest.raises(TypeError, match='owner'):
        getattr(store, method)(*args)


def test_tb04_owner_contract_strict_accepts_only_contracted_explicit_registry(owner_env):
    from scripts.migrate_image_owners import contract_ownership
    from image_test_harness import image_app as create_app
    store = Store(owner_env.root)
    with pytest.raises(ValueError, match='owner migration'):
        owner_env.client(identity_mode='strict')
    contract_ownership(store.db, 'legacy')
    with pytest.raises(ValueError, match='explicit key registry'):
        create_app(owner_env.root, owner_env.keys['legacy'], identity_mode='strict', run_worker=False)
    with owner_env.client(identity_mode='strict') as c:
        fid = owner_env.upload(c, 'legacy')
        assert c.get('/v1/files/' + fid + '/content', headers=owner_env.auth('A')).status_code == 404
        task = owner_env.submit(c, 'legacy', request_key='same')
        other = owner_env.submit(c, 'A', request_key='same')
        assert task.status_code == other.status_code == 202
        assert task.json()['id'] != other.json()['id']
        assert c.get('/v1/tasks/' + task.json()['id'], headers=owner_env.auth('A')).status_code == 404


def test_tb04_owner_contract_new_requests_only_use_owner_scoped_mapping(owner_env):
    from scripts.migrate_image_owners import contract_ownership
    store = Store(owner_env.root)
    contract_ownership(store.db, 'legacy')
    with owner_env.client(identity_mode='strict') as c:
        created = owner_env.submit(c, 'legacy', request_key='private-key')
        assert created.status_code == 202
        replay = owner_env.submit(c, 'legacy', request_key='private-key')
        assert replay.json()['id'] == created.json()['id']
        with store.connect() as db:
            assert db.execute('SELECT idem FROM tasks WHERE id=?', (created.json()['id'],)).fetchone()[0] is None
            assert tuple(db.execute('SELECT owner,request_key,task_id FROM task_requests').fetchone()) == ('legacy', 'private-key', created.json()['id'])


@pytest.mark.parametrize('problem', ['unowned', 'missing-request', 'wrong-version', 'global-index', 'dangling'])
@pytest.mark.parametrize('state', ['queued', 'running'])
def test_tb04_owner_contract_strict_preflight_rejects_corruption_without_mutating(owner_env, problem, state):
    from scripts.migrate_image_owners import contract_ownership
    store = Store(owner_env.root)
    task = store.submit('image_generate', None, {'prompt': 'x'}, 'one', owner='legacy')
    with store.connect() as db:
        db.execute("UPDATE tasks SET idem='one'")  # historical global record
    contract_ownership(store.db, 'legacy')
    with store.connect() as db:
        db.execute('UPDATE tasks SET status=?', (state,))
        if problem == 'unowned':
            db.execute('DELETE FROM object_owners')
        elif problem == 'missing-request':
            db.execute('DELETE FROM task_requests')
        elif problem == 'wrong-version':
            db.execute('UPDATE ownership_migration SET version=2')
        elif problem == 'global-index':
            db.execute('CREATE UNIQUE INDEX global_idem ON tasks(idem)')
        else:
            db.execute("UPDATE tasks SET file_id='file-missing'")
    before = store.db.read_bytes()
    with pytest.raises(ValueError):
        owner_env.client(identity_mode='strict')
    assert store.db.read_bytes() == before


@pytest.mark.parametrize('mode', ['legacy', 'staging'])
@pytest.mark.parametrize('state', ['unowned', 'owned-unmapped'])
def test_tb04_owner_contract_startup_never_silently_claims_unowned_data(tmp_path, legacy_services, mode, state):
    from image_test_harness import image_app as create_app
    store = legacy_services.Store(tmp_path)
    store.save_generated('file-' + 'd' * 32, b'old', 'old.png')
    store.submit('image_generate', None, {'prompt': 'x'}, 'historical-key')
    if state == 'owned-unmapped':
        from services.ownership import expand_ownership
        expand_ownership(store.db, 'legacy')
    before = store.db.read_bytes()
    with pytest.raises(ValueError, match='owner migration'):
        create_app(tmp_path, 'test-secret-token', run_worker=False, identity_mode=mode)
    assert store.db.read_bytes() == before
    assert not (tmp_path / 'keys.sqlite3').exists()


def test_tb04_owner_contract_factory_requires_identity_config_and_never_reads_shared_key(tmp_path, monkeypatch):
    import services.gateway as gateway
    from services.identity import KeyRegistry
    from scripts.migrate_image_owners import contract_ownership
    from fastapi.testclient import TestClient
    base = tmp_path / 'source'
    monkeypatch.setattr(gateway, '__file__', str(base / 'services' / 'gateway.py'))
    monkeypatch.delenv('AGENT_IDENTITY_MODE', raising=False)
    with pytest.raises(ValueError, match='explicit.*identity'):
        gateway.application()
    assert not base.exists()
    store = Store(base / '.private' / 'runtime')
    registry = KeyRegistry(store.root / 'keys.sqlite3')
    key = registry.issue('A')
    contract_ownership(store.db, 'legacy')
    monkeypatch.setenv('AGENT_IDENTITY_MODE', 'strict')
    monkeypatch.setenv('IMAGES_ENABLED', '0')
    monkeypatch.delenv('MAIN_TOKEN_FILE', raising=False)
    with TestClient(gateway.application()) as c:
        response = c.get('/v1/me', headers={'Authorization': 'Bearer ' + key})
        assert response.status_code == 200
        assert response.json() == {'owner': 'A'}
    assert not (base / '.private' / 'agent-api.key').exists()


def test_tb04_owner_contract_real_legacy_worker_cutover_and_restore_preserves_new_writes(owner_env, legacy_services, tmp_path):
    import httpx
    import shutil
    from pathlib import Path
    from fastapi.testclient import TestClient
    from image_test_harness import image_app as create_app
    from services.identity import KeyRegistry
    from scripts.migrate_image_owners import contract_ownership, backup_state
    root = owner_env.root
    root.mkdir()
    registry = KeyRegistry(root / 'keys.sqlite3')
    owner_env.keys.update({owner: registry.issue(owner) for owner in ('legacy', 'A', 'B')})
    original_key = owner_env.keys['legacy']
    backend = owner_env.new_backend()
    def old_client(work):
        return TestClient(legacy_services.create_app(root, original_key, run_worker=work,
            transport=httpx.MockTransport(backend), images_enabled=True, audio_enabled=False))
    with old_client(True) as c:
        source = owner_env.upload(c, 'legacy')
        task = owner_env.submit(c, 'legacy', request_key='completed').json()['id']
        done = owner_env.wait_task(c, task, 'legacy', lambda t: t['status'] == 'completed')
        result = done['result']['file_id']
        old_bytes = c.get(done['result']['content_url'], headers=owner_env.auth('legacy')).content
        assert old_bytes == backend.png
    with old_client(False) as c:
        queued = owner_env.submit(c, 'legacy', kind='image_edit', request_key='queued', image_ids=[source]).json()['id']
        cancelled = owner_env.submit(c, 'legacy', request_key='cancelled').json()['id']
        assert c.post('/v1/tasks/' + cancelled + '/cancel', headers=owner_env.auth('legacy')).json()['status'] == 'cancelled'
        interrupted = owner_env.submit(c, 'legacy', request_key='interrupted').json()['id']
    old_store = legacy_services.Store(root)
    old_store.update(interrupted, status='running')  # interrupted historical processing, never fabricated completed.
    with pytest.raises(ValueError, match='running'):
        contract_ownership(old_store.db, 'legacy')
    old_store.recover()  # explicit conservative reconciliation after confirming synthetic backend idle.
    migration = contract_ownership(old_store.db, 'legacy')
    def current(path, keys=registry, work=False):
        return TestClient(create_app(path, '', key_registry=keys, identity_mode='strict',
            run_worker=work, transport=httpx.MockTransport(backend), images_enabled=True, audio_enabled=False))
    with current(root) as c:
        for tid, expected in ((task, 'completed'), (queued, 'queued'), (cancelled, 'cancelled'), (interrupted, 'failed')):
            assert c.get('/v1/tasks/' + tid, headers=owner_env.auth('legacy')).json()['status'] == expected
            assert c.get('/v1/tasks/' + tid, headers=owner_env.auth('A')).status_code == 404
            assert c.post('/v1/tasks/' + tid + '/cancel', headers=owner_env.auth('A')).status_code == 404
        assert c.get('/v1/files/' + result + '/content', headers=owner_env.auth('legacy')).content == old_bytes
        assert c.get('/v1/files/' + result + '/content', headers=owner_env.auth('A')).status_code == 404
        assert owner_env.submit(c, 'legacy', request_key='completed').json()['id'] == task
        new_file = owner_env.upload(c, 'A')
        new_task = owner_env.submit(c, 'A', request_key='new-after-cutover').json()['id']
        new_b = owner_env.submit(c, 'B', request_key='new-after-cutover').json()['id']
        assert new_task != new_b
        old_principal = registry.resolve(original_key)
        owner_env.keys['legacy'] = registry.issue('legacy')
        registry.revoke(old_principal.key_id)
        assert c.get('/v1/tasks/' + task, headers={'Authorization': 'Bearer ' + original_key}).status_code == 401
        assert c.get('/v1/tasks/' + task, headers=owner_env.auth('legacy')).status_code == 200
    assert len(backend.jobs) == 1
    archive = tmp_path / 'post-cutover-archive'
    backup_state(root / 'state.sqlite3', archive)
    # Recover into separate directories. Never overwrite the live post-cutover writes.
    recovered_old = tmp_path / 'pre-cutover-restored'
    shutil.copytree(Path(migration['backup_dir']), recovered_old)
    contract_ownership(recovered_old / 'state.sqlite3', 'legacy')
    with current(recovered_old) as c:
        assert c.get('/v1/files/' + result + '/content', headers=owner_env.auth('legacy')).content == old_bytes
    recovered = tmp_path / 'latest-restored'
    shutil.copytree(archive, recovered)
    restored_registry = KeyRegistry(recovered / 'keys.sqlite3')
    with current(recovered, restored_registry) as c:
        assert c.get('/v1/tasks/' + task, headers={'Authorization': 'Bearer ' + original_key}).status_code == 401
        assert c.get('/v1/files/' + result + '/content', headers=owner_env.auth('legacy')).content == old_bytes
        assert c.get('/v1/files/' + new_file + '/content', headers=owner_env.auth('A')).content == backend.png
        assert c.get('/v1/files/' + new_file + '/content', headers=owner_env.auth('B')).status_code == 404
        assert owner_env.submit(c, 'A', request_key='new-after-cutover').json()['id'] == new_task
        assert c.get('/v1/tasks/' + new_b, headers=owner_env.auth('B')).status_code == 200
    assert len(backend.jobs) == 1


@pytest.mark.parametrize('owner,kind', [('A', 'image_generate'), ('B', 'image_generate'), ('A', 'image_edit'), ('B', 'image_edit')])
def test_tb04_owner_contract_strict_worker_results_remain_private(owner_env, owner, kind):
    from scripts.migrate_image_owners import contract_ownership
    store = Store(owner_env.root)
    contract_ownership(store.db, 'legacy')
    backend = owner_env.new_backend()
    with owner_env.client(identity_mode='strict', backend=backend, run_worker=True) as c:
        image_ids = [owner_env.upload(c, owner)] if kind == 'image_edit' else []
        response = owner_env.submit(c, owner, kind=kind, request_key='strict-work', image_ids=image_ids)
        assert response.status_code == 202
        tid = response.json()['id']
        done = owner_env.wait_task(c, tid, owner, lambda t: t['status'] == 'completed')
        assert c.get(done['result']['content_url'], headers=owner_env.auth(owner)).content == backend.png
        other = 'B' if owner == 'A' else 'A'
        assert c.get(done['result']['content_url'], headers=owner_env.auth(other)).status_code == 404
        assert c.post('/v1/tasks/' + tid + '/cancel', headers=owner_env.auth(other)).status_code == 404
        assert owner_env.submit(c, owner, kind=kind, request_key='strict-work', image_ids=image_ids).json()['id'] == tid
    assert len(backend.jobs) == 1


def test_tb04_owner_contract_concurrent_retries_serialize_one_ownership_snapshot(tmp_path, legacy_services):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    from scripts.migrate_image_owners import contract_ownership
    from services.ownership import inspect_contract
    store = legacy_services.Store(tmp_path)
    task = store.submit('image_generate', None, {'prompt': 'x'}, 'one')
    barrier = threading.Barrier(2)
    def contract(_):
        barrier.wait(timeout=3)
        return contract_ownership(store.db, 'legacy')
    with ThreadPoolExecutor(max_workers=2) as pool:
        reports = list(pool.map(contract, range(2)))
    assert len({r['backup_dir'] for r in reports}) == 2
    assert inspect_contract(store.db)['tasks'] == 1
    current = Store(tmp_path)
    assert current.submit('image_generate', None, {'prompt': 'x'}, 'one', owner='legacy')['id'] == task['id']


@pytest.mark.parametrize('problem', ['new-column', 'unknown-version', 'implicit-unique'])
def test_tb04_owner_contract_unknown_schema_or_version_is_never_discarded(tmp_path, problem):
    from scripts.migrate_image_owners import contract_ownership
    store = Store(tmp_path)
    with store.connect() as db:
        if problem == 'new-column':
            db.execute('ALTER TABLE tasks ADD COLUMN future_state TEXT')
        elif problem == 'implicit-unique':
            db.execute('DROP TABLE tasks')
            db.execute('CREATE TABLE tasks(id TEXT PRIMARY KEY,kind TEXT UNIQUE,file_id TEXT,options TEXT,status TEXT,progress REAL,result TEXT,error TEXT,idem TEXT,fingerprint TEXT,created INTEGER,updated INTEGER)')
        else:
            db.execute('CREATE TABLE ownership_migration(version INTEGER PRIMARY KEY,legacy_owner TEXT,backup_dir TEXT)')
            db.execute("INSERT INTO ownership_migration VALUES(2,'legacy','old-backup')")
    before = store.db.read_bytes()
    with pytest.raises(ValueError, match='schema|version'):
        contract_ownership(store.db, 'legacy')
    assert store.db.read_bytes() == before
    assert not (store.root / 'ownership-backups').exists()


def test_tb04_owner_contract_removes_explicit_global_idem_index(tmp_path):
    from scripts.migrate_image_owners import contract_ownership
    from services.ownership import inspect_contract
    store = Store(tmp_path)
    with store.connect() as db:
        db.execute('CREATE UNIQUE INDEX old_global_key ON tasks(idem)')
    contract_ownership(store.db, 'legacy')
    assert inspect_contract(store.db)['ready'] is True


def test_tb04_owner_contract_strict_restart_preserves_intentional_file_deletion(owner_env):
    from scripts.migrate_image_owners import contract_ownership
    store = Store(owner_env.root)
    contract_ownership(store.db, 'legacy')
    backend = owner_env.new_backend()
    with owner_env.client(identity_mode='strict', backend=backend, run_worker=True) as c:
        source = owner_env.upload(c, 'A')
        tid = owner_env.submit(c, 'A', kind='image_edit', request_key='deleted-source', image_ids=[source]).json()['id']
        done = owner_env.wait_task(c, tid, 'A', lambda t: t['status'] == 'completed')
        result = done['result']['file_id']
        assert c.delete('/v1/files/' + source, headers=owner_env.auth('A')).status_code == 200
        assert c.delete('/v1/files/' + result, headers=owner_env.auth('B')).status_code == 404
        assert c.delete('/v1/files/' + result, headers=owner_env.auth('A')).status_code == 200
    with owner_env.client(identity_mode='strict', backend=backend) as c:
        state = c.get('/v1/tasks/' + tid, headers=owner_env.auth('A'))
        assert state.status_code == 200 and state.json()['status'] == 'completed'
        assert c.get(done['result']['content_url'], headers=owner_env.auth('A')).status_code == 404
        replacement = owner_env.upload(c, 'A')
        replay = owner_env.submit(c, 'A', kind='image_edit', request_key='deleted-source', image_ids=[replacement])
        assert replay.json()['id'] == tid
    assert len(backend.jobs) == 1
