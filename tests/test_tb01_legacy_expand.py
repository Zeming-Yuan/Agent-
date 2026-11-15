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
