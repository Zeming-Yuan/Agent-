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
