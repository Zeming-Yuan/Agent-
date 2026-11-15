"""T03 public task/identity behavior with real gateway, store and workers."""


def test_tb03_same_request_key_does_not_cross_owners(owner_env):
    with owner_env.client() as c:
        a = owner_env.submit(c, 'A', request_key='same')
        b = owner_env.submit(c, 'B', request_key='same')
        assert a.status_code == b.status_code == 202
        assert a.json()['id'] != b.json()['id']
        assert c.get('/v1/tasks/' + a.json()['id'], headers=owner_env.auth('B')).status_code == 404
        again = owner_env.submit(c, 'A', request_key='same')
        assert again.status_code == 202
        assert again.json()['id'] == a.json()['id']


def test_tb03_different_upload_ids_same_material_replay(owner_env):
    with owner_env.client() as c:
        first = owner_env.upload(c, 'A')
        second = owner_env.upload(c, 'A')
        assert first != second
        one = owner_env.submit(c, 'A', kind='image_edit', request_key='edit', image_ids=[first])
        two = owner_env.submit(c, 'A', kind='image_edit', request_key='edit', image_ids=[second])
        assert one.status_code == two.status_code == 202
        assert one.json()['id'] == two.json()['id']


def test_tb03_expand_preserves_legacy_request_replay(owner_env, legacy_services):
    import httpx
    from fastapi.testclient import TestClient
    backend = owner_env.new_backend()
    def old_client():
        return TestClient(legacy_services.create_app(owner_env.root, owner_env.keys['legacy'],
            run_worker=False, images_enabled=True, audio_enabled=False,
            transport=httpx.MockTransport(backend)))
    with old_client() as c:
        original = owner_env.submit(c, 'legacy', request_key='old').json()['id']
    with owner_env.client() as c:
        replay = owner_env.submit(c, 'legacy', request_key='old')
        assert replay.status_code == 202, replay.text
        assert replay.json()['id'] == original
        new = owner_env.submit(c, 'legacy', request_key='new').json()['id']
    with old_client() as c:
        replay = owner_env.submit(c, 'legacy', request_key='new')
        assert replay.status_code == 202, replay.text
        assert replay.json()['id'] == new


import io
import pytest
from PIL import Image


def test_tb03_changed_payload_conflicts_and_queue_replay_does_not_take_slot(owner_env):
    with owner_env.client() as c:
        original = owner_env.submit(c, 'A', request_key='one', prompt='red')
        assert original.status_code == 202
        for n in range(3):
            assert owner_env.submit(c, 'B', request_key=str(n)).status_code == 202
        replay = owner_env.submit(c, 'A', request_key='one', prompt='red')
        assert replay.status_code == 202 and replay.json()['id'] == original.json()['id']
        assert owner_env.submit(c, 'A', request_key='one', prompt='blue').status_code == 409
        full = owner_env.submit(c, 'A')
        assert full.status_code == 429 and full.headers['retry-after'] == '10'
        cancelled = c.post('/v1/tasks/' + original.json()['id'] + '/cancel', headers=owner_env.auth('A'))
        assert cancelled.status_code == 200 and cancelled.json()['status'] == 'cancelled'
        assert owner_env.submit(c, 'A').status_code == 202
        assert owner_env.submit(c, 'B').status_code == 429


@pytest.mark.parametrize('owner', ['A', 'B'])
@pytest.mark.parametrize('kind', ['image_generate', 'image_edit'])
def test_tb03_worker_result_stays_private(owner_env, owner, kind):
    backend = owner_env.new_backend()
    stranger = 'B' if owner == 'A' else 'A'
    with owner_env.client(backend=backend, run_worker=True) as c:
        options = {'image_ids': [owner_env.upload(c, owner)]} if kind == 'image_edit' else {}
        response = owner_env.submit(c, owner, kind=kind, **options)
        assert response.status_code == 202
        tid = response.json()['id']
        done = owner_env.wait_task(c, tid, owner, lambda t: t['status'] in ('completed', 'failed'))
        assert done['status'] == 'completed', done
        result_id = done['result']['file_id']
        image = c.get('/v1/files/' + result_id + '/content', headers=owner_env.auth(owner))
        assert image.status_code == 200
        with Image.open(io.BytesIO(image.content)) as decoded:
            decoded.load()
            assert decoded.format == 'PNG'
        for path, method in [('/v1/tasks/' + tid, c.get),
                             ('/v1/tasks/' + tid + '/cancel', c.post),
                             ('/v1/files/' + result_id + '/content', c.get)]:
            denied = method(path, headers=owner_env.auth(stranger))
            assert denied.status_code == 404 and denied.json() == {'detail': 'Object not found'}
        assert 'owner' not in done and 'idem' not in done and 'fingerprint' not in done
        assert len(backend.jobs) == 1


def test_tb03_running_task_foreign_cancel_cannot_interrupt(owner_env):
    backend = owner_env.new_backend(hold=True)
    with owner_env.client(backend=backend, run_worker=True) as c:
        tid = owner_env.submit(c, 'A').json()['id']
        assert backend.started.wait(3)
        missing = 'task-' + 'f' * 32
        for method, suffix in [(c.get, ''), (c.post, '/cancel')]:
            foreign = method('/v1/tasks/' + tid + suffix, headers=owner_env.auth('B'))
            absent = method('/v1/tasks/' + missing + suffix, headers=owner_env.auth('B'))
            assert foreign.status_code == absent.status_code == 404
            assert foreign.json() == absent.json() == {'detail': 'Object not found'}
        assert c.get('/v1/tasks/' + tid, headers=owner_env.auth('A')).json()['status'] == 'running'
        backend.finish.set()
        assert owner_env.wait_task(c, tid, 'A', lambda t: t['status'] == 'completed')['result']['file_id']


@pytest.mark.parametrize('field', ['owner', 'key_id'])
def test_tb03_client_cannot_forge_owner(owner_env, field):
    with owner_env.client() as c:
        forged = c.post('/v1/tasks', headers=owner_env.auth('B'),
                        json={'kind': 'image_generate', field: 'A', 'options': {'prompt': 'fixture'}})
        assert forged.status_code == 422
        forged_options = c.post('/v1/tasks', headers=owner_env.auth('B'),
                                json={'kind': 'image_generate', 'options': {'prompt': 'fixture', field: 'A'}})
        assert forged_options.status_code == 422


def test_tb03_concurrent_same_owner_replays_and_cross_owner_keys_are_atomic(owner_env):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    with owner_env.client() as a, owner_env.client() as b:
        barrier = threading.Barrier(4)
        def submit(c, owner):
            barrier.wait(3)
            return owner_env.submit(c, owner, request_key='race')
        with ThreadPoolExecutor(max_workers=4) as pool:
            jobs = [pool.submit(submit, c, o) for c, o in [(a, 'A'), (b, 'A'), (a, 'B'), (b, 'B')]]
            responses = [job.result(timeout=5) for job in jobs]
        assert [r.status_code for r in responses] == [202] * 4
        ids = [r.json()['id'] for r in responses]
        assert ids[0] == ids[1] and ids[2] == ids[3] and ids[0] != ids[2]
        assert owner_env.submit(a, 'A').status_code == 202
        assert owner_env.submit(b, 'B').status_code == 202
        assert owner_env.submit(a, 'A').status_code == 429


@pytest.mark.parametrize('kind', ['transcribe', 'audio_understand', 'pdf', 'video'])
def test_tb03_existing_media_task_access_is_scoped(owner_env, kind):
    from fastapi.testclient import TestClient
    from services.gateway import create_app
    import httpx
    app = create_app(owner_env.root, owner_env.keys['legacy'], key_registry=owner_env.registry,
                     identity_mode='staging', run_worker=False,
                     transport=httpx.MockTransport(owner_env.new_backend()))
    with TestClient(app) as c:
        ids = {}
        for owner in ['A', 'B']:
            fid = owner_env.upload(c, owner)
            response = c.post('/v1/tasks', headers={**owner_env.auth(owner), 'Idempotency-Key': 'media'},
                              json={'kind': kind, 'file_id': fid})
            assert response.status_code == 202
            ids[owner] = response.json()['id']
            other = 'B' if owner == 'A' else 'A'
            assert c.get('/v1/tasks/' + ids[owner], headers=owner_env.auth(owner)).json()['file_id'] == fid
            for method, suffix in [(c.get, ''), (c.post, '/cancel')]:
                foreign = method('/v1/tasks/' + ids[owner] + suffix, headers=owner_env.auth(other))
                absent = method('/v1/tasks/task-missing' + suffix, headers=owner_env.auth(other))
                assert foreign.status_code == absent.status_code == 404
                assert foreign.json() == absent.json() == {'detail': 'Object not found'}
            cancelled = c.post('/v1/tasks/' + ids[owner] + '/cancel', headers=owner_env.auth(owner))
            assert cancelled.json()['status'] == 'cancelled'
        assert ids['A'] != ids['B']


def test_tb03_material_content_and_reference_order_are_business_input(owner_env):
    with owner_env.client() as c:
        green = owner_env.upload(c, 'A')
        buf = io.BytesIO()
        Image.new('RGB', (8, 8), 'red').save(buf, format='PNG')
        red = c.post('/v1/files', headers=owner_env.auth('A'),
                     files={'file': ('red.png', buf.getvalue(), 'image/png')}).json()['id']
        one = owner_env.submit(c, 'A', kind='image_edit', request_key='order', image_ids=[green, red])
        assert one.status_code == 202
        assert owner_env.submit(c, 'A', kind='image_edit', request_key='order', image_ids=[red, green]).status_code == 409
        assert owner_env.submit(c, 'A', kind='image_edit', request_key='order', image_ids=[green, green]).status_code == 409
        assert owner_env.submit(c, 'A', kind='image_edit', request_key='order', image_ids=[green, red], quality='fast').status_code == 409
        # Identical business input with a fresh request key is an intentional new creation.
        fresh = owner_env.submit(c, 'A', kind='image_edit', request_key='new', image_ids=[green, red])
        assert fresh.status_code == 202 and fresh.json()['id'] != one.json()['id']


def test_tb03_media_worker_reads_owner_source_and_keeps_result_private(owner_env):
    # A small real text PDF exercises poppler and the real media worker, without a model.
    text = 'Private fixture document with enough selectable text for local extraction only.'
    stream = f'BT /F1 12 Tf 30 100 Td ({text}) Tj ET'.encode()
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>',
               b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
               b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 200] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
               b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
               b'<< /Length ' + str(len(stream)).encode() + b' >>\nstream\n' + stream + b'\nendstream']
    pdf = b'%PDF-1.4\n'
    offsets = []
    for n, obj in enumerate(objects, 1):
        offsets.append(len(pdf))
        pdf += str(n).encode() + b' 0 obj\n' + obj + b'\nendobj\n'
    xref = len(pdf)
    pdf += b'xref\n0 6\n0000000000 65535 f \n'
    pdf += b''.join(f'{offset:010d} 00000 n \n'.encode() for offset in offsets)
    pdf += f'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode()
    with owner_env.client(run_worker=True) as c:
        for owner, stranger in [('A', 'B'), ('B', 'A')]:
            uploaded = c.post('/v1/files', headers=owner_env.auth(owner),
                              files={'file': ('fixture.pdf', pdf, 'application/pdf')})
            assert uploaded.status_code == 200
            accepted = c.post('/v1/tasks', headers=owner_env.auth(owner),
                              json={'kind': 'pdf', 'file_id': uploaded.json()['id']})
            assert accepted.status_code == 202
            tid = accepted.json()['id']
            done = owner_env.wait_task(c, tid, owner, lambda t: t['status'] in ('completed', 'failed'))
            assert done['status'] == 'completed', done
            assert done['result']['pages'][0]['text'] == text
            assert c.get('/v1/tasks/' + tid, headers=owner_env.auth(stranger)).status_code == 404


def test_tb03_legacy_missing_material_conflicts_with_recoverable_task(owner_env, legacy_services):
    import httpx
    from fastapi.testclient import TestClient
    backend = owner_env.new_backend()
    with TestClient(legacy_services.create_app(owner_env.root, owner_env.keys['legacy'],
                    images_enabled=True, audio_enabled=False,
                    transport=httpx.MockTransport(backend))) as c:
        fid = owner_env.upload(c, 'legacy')
        response = owner_env.submit(c, 'legacy', kind='image_edit', request_key='deleted', image_ids=[fid])
        tid = response.json()['id']
        done = owner_env.wait_task(c, tid, 'legacy', lambda t: t['status'] == 'completed')
        result_id = done['result']['file_id']
        assert c.delete('/v1/files/' + fid, headers=owner_env.auth('legacy')).status_code == 200
    with owner_env.client(backend=backend, run_worker=True) as c:
        new_fid = owner_env.upload(c, 'legacy')
        replay = owner_env.submit(c, 'legacy', kind='image_edit', request_key='deleted', image_ids=[new_fid])
        assert replay.status_code == 409
        assert replay.json()['detail']['task_id'] == tid
        assert c.get('/v1/tasks/' + tid, headers=owner_env.auth('legacy')).json()['status'] == 'completed'
        assert c.get('/v1/files/' + result_id + '/content', headers=owner_env.auth('legacy')).status_code == 200
        assert len(backend.jobs) == 1


def test_tb03_new_request_replays_after_original_material_deleted(owner_env):
    backend = owner_env.new_backend()
    with owner_env.client(backend=backend, run_worker=True) as c:
        fid = owner_env.upload(c, 'A')
        tid = owner_env.submit(c, 'A', kind='image_edit', request_key='deleted', image_ids=[fid]).json()['id']
        done = owner_env.wait_task(c, tid, 'A', lambda t: t['status'] == 'completed')
        assert c.delete('/v1/files/' + fid, headers=owner_env.auth('A')).status_code == 200
        new_fid = owner_env.upload(c, 'A')
        replay = owner_env.submit(c, 'A', kind='image_edit', request_key='deleted', image_ids=[new_fid])
        assert replay.status_code == 202 and replay.json()['id'] == tid
        assert replay.json()['result'] == done['result']
        assert len(backend.jobs) == 1


def test_tb03_me_and_rotated_key_retain_owner_and_existing_result(owner_env, caplog):
    import logging
    backend = owner_env.new_backend()
    with caplog.at_level(logging.INFO, logger='agent-mm'), owner_env.client(backend=backend, run_worker=True) as c:
        assert c.get('/v1/me', headers=owner_env.auth('A')).json() == {'owner': 'A'}
        tid = owner_env.submit(c, 'A').json()['id']
        done = owner_env.wait_task(c, tid, 'A', lambda t: t['status'] == 'completed')
        old = owner_env.registry.resolve(owner_env.keys['A'])
        new_key = owner_env.registry.issue('A')
        new_auth = {'Authorization': 'Bearer ' + new_key}
        owner_env.registry.revoke(old.key_id)
        assert c.get('/v1/me', headers=new_auth).json() == {'owner': 'A'}
        assert c.get('/v1/tasks/' + tid, headers=new_auth).json()['result'] == done['result']
        assert c.get('/v1/files/' + done['result']['file_id'] + '/content', headers=new_auth).status_code == 200
        for auth in [owner_env.auth('A'), {'Authorization': 'Bearer unknown-revoked-key'}]:
            rejected = c.get('/v1/tasks/' + tid, headers=auth)
            assert rejected.status_code == 401 and rejected.headers['www-authenticate'] == 'Bearer'
            assert rejected.headers['x-request-id']
        assert c.get('/v1/tasks/' + tid, headers=owner_env.auth('B')).status_code == 404
        assert new_key not in caplog.text and owner_env.keys['A'] not in caplog.text


def test_tb03_issue_to_private_file_persists_only_digest_and_owner(owner_env, tmp_path):
    import stat
    from services.identity import issue_to_file, KeyRegistry
    target = tmp_path / 'personal.key'
    key_id = issue_to_file(owner_env.registry, 'A', target)
    raw = target.read_text().strip()
    principal = KeyRegistry(owner_env.registry.db_path).resolve(raw)
    assert principal.owner == 'A' and principal.key_id == key_id
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert raw.encode() not in owner_env.registry.db_path.read_bytes()


@pytest.mark.parametrize('fault', ['open', 'write'])
def test_tb03_failed_key_delivery_revokes_and_preserves_existing_files(owner_env, tmp_path, monkeypatch, fault):
    import os
    import secrets
    from services.identity import issue_to_file
    raw = 'ephemeral-test-credential-never-delivered'
    monkeypatch.setattr(secrets, 'token_urlsafe', lambda _: raw)
    target = tmp_path / 'key-output'
    if fault == 'open':
        target.write_text('existing key must survive')
    else:
        fdopen = os.fdopen
        class BrokenOutput:
            def __init__(self, stream):
                self.stream = stream
            def __enter__(self):
                return self
            def __exit__(self, *args):
                self.stream.close()
            def write(self, value):
                self.stream.write(value[:4])
                raise OSError('synthetic disk full')
        monkeypatch.setattr(os, 'fdopen', lambda *a, **kw: BrokenOutput(fdopen(*a, **kw)))
    with pytest.raises(OSError):
        issue_to_file(owner_env.registry, 'A', target)
    assert owner_env.registry.resolve(raw) is None
    if fault == 'open':
        assert target.read_text() == 'existing key must survive'
    else:
        assert not target.exists()


def test_tb03_key_cli_issue_rotate_revoke_and_http_access(owner_env, tmp_path):
    import subprocess
    import sys
    from services.identity import KeyRegistry
    def cli(*args):
        return subprocess.run([sys.executable, '-m', 'services.identity', '--db', str(owner_env.registry.db_path),
                               *map(str, args)], capture_output=True, text=True, timeout=5)
    first_path, second_path = tmp_path / 'first.key', tmp_path / 'second.key'
    first = cli('issue', '--owner', 'A', '--out', first_path)
    assert first.returncode == 0, first.stderr
    assert first_path.exists()
    first_key = first_path.read_text().strip()
    first_id = first.stdout.strip()
    assert owner_env.registry.resolve(first_key).key_id == first_id
    backend = owner_env.new_backend()
    with owner_env.client(backend=backend, run_worker=True) as c:
        submitted = c.post('/v1/tasks', headers={'Authorization': 'Bearer ' + first_key},
                           json={'kind': 'image_generate', 'options': {'prompt': 'fixture'}})
        assert submitted.status_code == 202
        tid = submitted.json()['id']
        done = owner_env.wait_task(c, tid, 'A', lambda t: t['status'] == 'completed')
        second = cli('issue', '--owner', 'A', '--out', second_path)
        assert second.returncode == 0, second.stderr
        second_key = second_path.read_text().strip()
        assert second.stdout.strip() != first_id
        assert cli('revoke', '--key-id', first_id).returncode == 0
        assert cli('revoke', '--key-id', first_id).returncode == 0  # revocation is idempotent
        assert KeyRegistry(owner_env.registry.db_path).resolve(first_key) is None
        assert c.get('/v1/tasks/' + tid, headers={'Authorization': 'Bearer ' + first_key}).status_code == 401
        rotated = {'Authorization': 'Bearer ' + second_key}
        assert c.get('/v1/me', headers=rotated).json() == {'owner': 'A'}
        assert c.get('/v1/files/' + done['result']['file_id'] + '/content', headers=rotated).status_code == 200
        assert c.get('/v1/tasks/' + tid, headers=owner_env.auth('B')).status_code == 404
    collision = cli('issue', '--owner', 'A', '--out', second_path)
    assert collision.returncode != 0
    assert second_path.read_text().strip() == second_key
    for result in [first, second, collision]:
        assert first_key not in result.stdout + result.stderr
        assert second_key not in result.stdout + result.stderr


@pytest.mark.parametrize('kind', ['image_generate', 'image_edit'])
def test_tb03_sync_and_async_share_owner_request_identity(owner_env, kind):
    backend = owner_env.new_backend()
    with owner_env.client(backend=backend, run_worker=True) as c:
        task_ids = []
        for owner in ['A', 'B']:
            opts = {'image_ids': [owner_env.upload(c, owner)]} if kind == 'image_edit' else {}
            response = owner_env.submit(c, owner, kind=kind, request_key='shared', **opts)
            assert response.status_code == 202
            tid = response.json()['id']
            done = owner_env.wait_task(c, tid, owner, lambda t: t['status'] == 'completed')
            headers = {**owner_env.auth(owner), 'Idempotency-Key': 'shared'}
            if kind == 'image_edit':
                replay = c.post('/v1/images/edits', headers=headers, data={'prompt': 'fixture'},
                                files={'image': ('renamed.png', backend.png, 'image/png')})
            else:
                replay = c.post('/v1/images/generations', headers=headers, json={'prompt': 'fixture'})
            assert replay.status_code == 200, replay.text
            assert replay.json()['task_id'] == tid
            assert replay.json()['data'][0]['file_id'] == done['result']['file_id']
            task_ids.append(tid)
        assert task_ids[0] != task_ids[1]
        assert len(backend.jobs) == 2


def test_tb03_restart_and_restored_copy_keep_task_identity_and_revocation(owner_env, tmp_path):
    import shutil
    import sqlite3
    from contextlib import closing
    from fastapi.testclient import TestClient
    from services.gateway import create_app
    from services.identity import KeyRegistry
    import httpx
    backend = owner_env.new_backend()
    tasks = {}
    with owner_env.client(backend=backend, run_worker=True) as c:
        for owner in ['A', 'B']:
            fid = owner_env.upload(c, owner)
            tid = owner_env.submit(c, owner, kind='image_edit', request_key='persisted', image_ids=[fid]).json()['id']
            tasks[owner] = owner_env.wait_task(c, tid, owner, lambda t: t['status'] == 'completed')
    old = owner_env.registry.resolve(owner_env.keys['A'])
    rotated_key = owner_env.registry.issue('A')
    owner_env.registry.revoke(old.key_id)
    restored = tmp_path / 'restored'
    restored.mkdir()
    for source, target in [(owner_env.root / 'state.sqlite3', restored / 'state.sqlite3'),
                           (owner_env.registry.db_path, restored / 'keys.sqlite3')]:
        with closing(sqlite3.connect(source)) as src, closing(sqlite3.connect(target)) as dst:
            src.backup(dst)
    shutil.copytree(owner_env.root / 'files', restored / 'files')
    for root, registry in [(owner_env.root, KeyRegistry(owner_env.registry.db_path)),
                           (restored, KeyRegistry(restored / 'keys.sqlite3'))]:
        app = create_app(root, owner_env.keys['legacy'], key_registry=registry, identity_mode='staging',
                         images_enabled=True, audio_enabled=False, transport=httpx.MockTransport(backend))
        with TestClient(app) as c:
            assert c.get('/v1/me', headers=owner_env.auth('A')).status_code == 401
            for owner in ['A', 'B']:
                headers = {'Authorization': 'Bearer ' + rotated_key} if owner == 'A' else owner_env.auth(owner)
                tid = tasks[owner]['id']
                assert c.get('/v1/tasks/' + tid, headers=headers).json()['result'] == tasks[owner]['result']
                assert c.get('/v1/files/' + tasks[owner]['result']['file_id'] + '/content', headers=headers).status_code == 200
                other_headers = owner_env.auth('B') if owner == 'A' else {'Authorization': 'Bearer ' + rotated_key}
                assert c.get('/v1/tasks/' + tid, headers=other_headers).status_code == 404
                fid = c.post('/v1/files', headers=headers, files={'file': ('new.png', backend.png, 'image/png')}).json()['id']
                replay = c.post('/v1/tasks', headers={**headers, 'Idempotency-Key': 'persisted'},
                                json={'kind': 'image_edit', 'options': {'prompt': 'fixture', 'image_ids': [fid]}})
                assert replay.status_code == 202 and replay.json()['id'] == tid
    assert len(backend.jobs) == 2


@pytest.mark.parametrize('existing', [False, True])
def test_tb03_delivery_cleanup_and_recovery_id_survive_registry_revoke_failure(owner_env, tmp_path, monkeypatch, existing):
    import os
    import secrets
    import sqlite3
    from services.identity import issue_to_file, KeyDeliveryError
    raw = 'ephemeral-test-rollback-credential'
    target = tmp_path / 'failed-output'
    if existing:
        target.write_text('existing output stays untouched')
    connect, fdopen = sqlite3.connect, os.fdopen
    def rejecting_connection(*args, **kwargs):
        db = connect(*args, **kwargs)
        # The real SQLite boundary permits issuance/reads but rejects revocation UPDATE.
        db.set_authorizer(lambda action, table, *rest:
                          sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_UPDATE and table == 'api_keys'
                          else sqlite3.SQLITE_OK)
        return db
    class FailedOutput:
        def __init__(self, stream):
            self.stream = stream
        def __enter__(self):
            return self
        def __exit__(self, *args):
            self.stream.close()
        def write(self, value):
            self.stream.write(value)
            self.stream.flush()
            raise OSError('synthetic output failure')
    with monkeypatch.context() as patch:
        patch.setattr(secrets, 'token_urlsafe', lambda _: raw)
        patch.setattr(sqlite3, 'connect', rejecting_connection)
        patch.setattr(os, 'fdopen', lambda *a, **kw: FailedOutput(fdopen(*a, **kw)))
        with pytest.raises(KeyDeliveryError) as failure:
            issue_to_file(owner_env.registry, 'A', target)
        if existing:
            assert target.read_text() == 'existing output stays untouched'
        else:
            assert not target.exists()
        principal = owner_env.registry.resolve(raw)
        assert failure.value.key_id == principal.key_id
        assert principal.key_id in str(failure.value) and raw not in str(failure.value)
    # Recovery is possible using only the safe ID after registry writes recover.
    owner_env.registry.revoke(failure.value.key_id)
    assert owner_env.registry.resolve(raw) is None


@pytest.mark.parametrize('output', ['existing', 'removed', 'cleanup_pending'])
def test_tb03_cli_recovery_message_respects_output_ownership(owner_env, tmp_path, monkeypatch, capsys, output):
    import os
    import secrets
    import sqlite3
    import sys
    from pathlib import Path
    from services.identity import main
    raw = 'ephemeral-test-cli-recovery-credential'
    target = tmp_path / 'output.key'
    if output == 'existing':
        target.write_text('previous credential must survive')
    connect, unlink = sqlite3.connect, Path.unlink
    def rejecting_connection(*args, **kwargs):
        db = connect(*args, **kwargs)
        db.set_authorizer(lambda action, table, *rest:
                          sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_UPDATE and table == 'api_keys'
                          else sqlite3.SQLITE_OK)
        return db
    def fail_stream(*args, **kwargs):
        raise OSError('synthetic stream failure')
    def fail_owned_unlink(path, *args, **kwargs):
        if path == target:
            raise PermissionError('synthetic cleanup failure')
        return unlink(path, *args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(secrets, 'token_urlsafe', lambda _: raw)
        patch.setattr(sqlite3, 'connect', rejecting_connection)
        patch.setattr(os, 'fdopen', fail_stream)
        patch.setattr(sys, 'argv', ['identity', '--db', str(owner_env.registry.db_path),
                                  'issue', '--owner', 'A', '--out', str(target)])
        if output == 'cleanup_pending':
            patch.setattr(Path, 'unlink', fail_owned_unlink)
        with pytest.raises(SystemExit) as failure:
            main()
        assert failure.value.code == 1
        captured = capsys.readouterr()
        principal = owner_env.registry.resolve(raw)
        assert captured.out == '' and principal.key_id in captured.err
        assert raw not in captured.err
        if output == 'cleanup_pending':
            assert target.exists()
            assert 'cleanup pending for newly created output' in captured.err
        else:
            assert 'preserve existing files' in captured.err
            assert 'cleanup pending' not in captured.err
            if output == 'existing':
                assert target.read_text() == 'previous credential must survive'
            else:
                assert not target.exists()
    owner_env.registry.revoke(principal.key_id)
    if output == 'cleanup_pending':
        target.unlink()
