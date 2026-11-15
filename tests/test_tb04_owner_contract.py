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


@pytest.mark.parametrize('unsafe', ['orphan-symlink', 'files-symlink', 'nested-backup'])
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
