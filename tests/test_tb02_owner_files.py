"""T02 file isolation through the authenticated public HTTP boundary."""


def test_tb02_other_owner_cannot_download(owner_env):
    with owner_env.client() as c:
        fid = owner_env.upload(c, 'A')
        assert c.get(f'/v1/files/{fid}/content', headers=owner_env.auth('A')).status_code == 200
        foreign = c.get(f'/v1/files/{fid}/content', headers=owner_env.auth('B'))
        absent = c.get('/v1/files/file-' + 'f' * 32 + '/content', headers=owner_env.auth('B'))
        assert foreign.status_code == absent.status_code == 404
        assert foreign.json() == absent.json() == {'detail': 'Object not found'}


def test_tb02_same_bytes_are_independent_objects(owner_env):
    with owner_env.client() as c:
        a = owner_env.upload(c, 'A')
        b = owner_env.upload(c, 'B')
        assert a != b
        original = c.get(f'/v1/files/{a}/content', headers=owner_env.auth('A')).content
        foreign = c.delete(f'/v1/files/{a}', headers=owner_env.auth('B'))
        absent = c.delete('/v1/files/file-' + 'f' * 32, headers=owner_env.auth('B'))
        assert foreign.status_code == absent.status_code == 404
        assert foreign.json() == absent.json() == {'detail': 'Object not found'}
        assert c.delete(f'/v1/files/{b}', headers=owner_env.auth('B')).status_code == 200
        assert c.get(f'/v1/files/{a}/content', headers=owner_env.auth('A')).content == original
        assert c.delete(f'/v1/files/{a}', headers=owner_env.auth('A')).status_code == 200


def test_tb02_owner_upload_reference_result(owner_env):
    backend = owner_env.new_backend()
    with owner_env.client(backend=backend, run_worker=True) as c:
        fid = owner_env.upload(c, 'A')
        accepted = owner_env.submit(c, 'A', kind='image_edit', image_ids=[fid])
        assert accepted.status_code == 202, accepted.text
        task = owner_env.wait_task(c, accepted.json()['id'], 'A',
                                  lambda t: t['status'] in ('completed', 'failed'))
        assert task['status'] == 'completed', task
        result_id = task['result']['file_id']
        own = c.get(f'/v1/files/{result_id}/content', headers=owner_env.auth('A'))
        assert own.status_code == 200
        from PIL import Image
        import io
        assert Image.open(io.BytesIO(own.content)).format == 'PNG'
        assert c.get(f'/v1/files/{result_id}/content', headers=owner_env.auth('B')).json() == {'detail': 'Object not found'}
        assert len(backend.jobs) == 1


import pytest


@pytest.mark.parametrize('kind,field', [('image_edit', 'image_ids'), ('image_generate', 'foreground_file_id'),
                                      ('pdf', 'file_id'), ('video', 'file_id')])
def test_tb02_foreign_reference_rejected_before_enqueue(owner_env, kind, field):
    backend = owner_env.new_backend()
    with owner_env.client(backend=backend, run_worker=True) as c:
        fid = owner_env.upload(c, 'A')
        def submit(reference):
            if field == 'file_id':
                return c.post('/v1/tasks', headers=owner_env.auth('B'),
                              json={'kind': kind, 'file_id': reference})
            value = [reference] if field == 'image_ids' else reference
            return owner_env.submit(c, 'B', kind=kind, **{field: value})
        backend.offline.set()
        foreign = submit(fid)
        absent = submit('file-' + 'f' * 32)
        assert foreign.status_code == absent.status_code == 404
        assert foreign.json() == absent.json() == {'detail': 'Object not found'}
        assert fid not in foreign.text and 'fixture.png' not in foreign.text
        backend.offline.clear()
        accepted = owner_env.submit(c, 'B')
        assert accepted.status_code == 202
        task = owner_env.wait_task(c, accepted.json()['id'], 'B', lambda t: t['status'] in ('completed', 'failed'))
        assert task['status'] == 'completed'
        assert len(backend.jobs) == 1  # only the subsequent valid request reached inference


def test_tb02_sync_edit_deduplicates_only_within_owner(owner_env):
    backend = owner_env.new_backend()
    data = backend.png
    def edit(c, owner, key):
        return c.post('/v1/images/edits', headers={**owner_env.auth(owner), 'Idempotency-Key': key},
                      data={'prompt': 'edit'}, files={'image': ('private-name.png', data, 'image/png')})
    with owner_env.client(backend=backend, run_worker=True) as c:
        references = {}
        for owner, key in [('A', 'a-edit'), ('A', 'a-edit'), ('B', 'b-edit')]:
            response = edit(c, owner, key)
            assert response.status_code == 200, response.text
            task = c.get('/v1/tasks/' + response.json()['task_id'], headers=owner_env.auth(owner)).json()
            source_id = task['options']['image_ids'][0]
            if owner in references:
                assert references[owner] == source_id
            references[owner] = source_id
            result_id = response.json()['data'][0]['file_id']
            assert c.get(f'/v1/files/{result_id}/content', headers=owner_env.auth(owner)).status_code == 200
            assert c.get(f'/v1/files/{source_id}/content', headers=owner_env.auth(owner)).content == data
        assert references['A'] != references['B']
        import hashlib
        guessed = 'file-' + hashlib.sha256(data).hexdigest()[:32]
        assert guessed not in references.values()
        assert c.get(f'/v1/files/{guessed}/content', headers=owner_env.auth('B')).status_code == 404
        assert c.delete('/v1/files/' + references['B'], headers=owner_env.auth('B')).status_code == 200
        assert c.get('/v1/files/' + references['A'] + '/content', headers=owner_env.auth('A')).content == data
        assert len(backend.jobs) == 2


def test_tb02_sync_foreign_foreground_checked_before_backend(owner_env):
    backend = owner_env.new_backend()
    with owner_env.client(backend=backend) as c:
        fid = owner_env.upload(c, 'A')
        backend.offline.set()
        responses = [c.post('/v1/images/generations', headers=owner_env.auth('B'),
                            json={'prompt': 'fixture', 'foreground_file_id': ref})
                     for ref in (fid, 'file-' + 'f' * 32)]
        assert [r.status_code for r in responses] == [404, 404]
        assert responses[0].json() == responses[1].json() == {'detail': 'Object not found'}
        assert backend.jobs == []


@pytest.mark.parametrize('kind,field', [('image_edit', 'image_ids'), ('image_generate', 'foreground_file_id'),
                                      ('pdf', 'file_id'), ('video', 'file_id')])
def test_tb02_own_pending_reference_is_protected(owner_env, kind, field):
    with owner_env.client() as c:
        fid = owner_env.upload(c, 'A')
        if field == 'file_id':
            accepted = c.post('/v1/tasks', headers=owner_env.auth('A'), json={'kind': kind, 'file_id': fid})
        else:
            accepted = owner_env.submit(c, 'A', kind=kind, **{field: [fid] if field == 'image_ids' else fid})
        assert accepted.status_code == 202, accepted.text
        assert c.delete(f'/v1/files/{fid}', headers=owner_env.auth('A')).status_code == 409
        assert c.delete(f'/v1/files/{fid}', headers=owner_env.auth('B')).status_code == 404
        assert c.post('/v1/tasks/' + accepted.json()['id'] + '/cancel', headers=owner_env.auth('A')).status_code == 200
        assert c.delete(f'/v1/files/{fid}', headers=owner_env.auth('A')).status_code == 200


def test_tb02_failed_edit_keeps_other_owners_file(owner_env):
    with owner_env.client() as c:
        fid = owner_env.upload(c, 'A')
        original = c.get(f'/v1/files/{fid}/content', headers=owner_env.auth('A')).content
        before = set((owner_env.root / 'files').iterdir())
        for n in range(4):
            assert owner_env.submit(c, 'A', request_key=f'full-{n}').status_code == 202
        failed = c.post('/v1/images/edits', headers=owner_env.auth('B'), data={'prompt': 'edit'},
                        files={'image': ('x.png', original, 'image/png')})
        assert failed.status_code == 429
        assert failed.headers['retry-after'] == '10'
        assert c.get(f'/v1/files/{fid}/content', headers=owner_env.auth('A')).content == original
        assert set((owner_env.root / 'files').iterdir()) == before


@pytest.mark.parametrize('second_owner', ['A', 'B'])
def test_tb02_concurrent_edit_uploads_have_owner_scoped_dedup(owner_env, second_owner):
    from concurrent.futures import ThreadPoolExecutor
    backend = owner_env.new_backend()
    with owner_env.client(backend=backend, run_worker=True) as first, owner_env.client(backend=backend) as second:
        def edit(c, owner, key):
            return c.post('/v1/images/edits', headers={**owner_env.auth(owner), 'Idempotency-Key': key},
                          data={'prompt': 'edit'}, files={'image': ('x.png', backend.png, 'image/png')})
        with ThreadPoolExecutor(max_workers=2) as pool:
            a = pool.submit(edit, first, 'A', 'first')
            b = pool.submit(edit, second, second_owner, 'second')
            responses = [a.result(timeout=8), b.result(timeout=8)]
        refs = []
        for c, owner, r in [(first, 'A', responses[0]), (second, second_owner, responses[1])]:
            assert r.status_code == 200, r.text
            task = c.get('/v1/tasks/' + r.json()['task_id'], headers=owner_env.auth(owner)).json()
            ref = task['options']['image_ids'][0]
            refs.append(ref)
            assert c.get(f'/v1/files/{ref}/content', headers=owner_env.auth(owner)).content == backend.png
        assert (refs[0] == refs[1]) == (second_owner == 'A')
        assert len(backend.jobs) == 2


def test_tb02_own_transparent_foreground_result_is_private(owner_env):
    import io
    from PIL import Image
    backend = owner_env.new_backend()
    buf = io.BytesIO()
    foreground = Image.new('RGBA', (4, 4), (0, 0, 0, 0))
    for x in range(1, 3):
        for y in range(1, 3):
            foreground.putpixel((x, y), (255, 0, 0, 255))
    foreground.save(buf, format='PNG')
    with owner_env.client(backend=backend, run_worker=True) as c:
        uploaded = c.post('/v1/files', headers=owner_env.auth('A'),
                          files={'file': ('foreground.png', buf.getvalue(), 'image/png')})
        response = c.post('/v1/images/generations', headers=owner_env.auth('A'),
                          json={'prompt': 'fixture', 'foreground_file_id': uploaded.json()['id']})
        assert response.status_code == 200, response.text
        result = response.json()['data'][0]['file_id']
        downloaded = c.get(f'/v1/files/{result}/content', headers=owner_env.auth('A'))
        assert downloaded.status_code == 200
        assert Image.open(io.BytesIO(downloaded.content)).convert('RGB').getpixel((4, 4)) == (255, 0, 0)
        assert c.get(f'/v1/files/{result}/content', headers=owner_env.auth('B')).status_code == 404


def test_tb02_failed_exclusive_upload_does_not_unlink_existing_file(owner_env, monkeypatch):
    """A storage/name collision must never clean up a file this upload did not create."""
    import asyncio
    from types import SimpleNamespace
    import httpx
    import uuid
    with owner_env.client() as c:
        fid = owner_env.upload(c, 'A')
        before = c.get(f'/v1/files/{fid}/content', headers=owner_env.auth('A')).content
        async def collide():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=c.app, raise_app_exceptions=False),
                                         base_url='http://test') as other:
                return await other.post('/v1/files', headers=owner_env.auth('B'),
                                        files={'file': ('collision.png', b'other bytes')})
        with monkeypatch.context() as patch:
            patch.setattr(uuid, 'uuid4', lambda: SimpleNamespace(hex=fid[5:]))
            failed = asyncio.run(collide())
        assert failed.status_code == 500
        async def download():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=c.app, raise_app_exceptions=False),
                                         base_url='http://test') as other:
                return await other.get(f'/v1/files/{fid}/content', headers=owner_env.auth('A'))
        after = asyncio.run(download())
        assert after.status_code == 200
        assert after.content == before


def test_tb02_reference_deleted_during_backend_probe_is_not_enqueued(owner_env):
    import asyncio
    import threading
    from concurrent.futures import ThreadPoolExecutor
    backend = owner_env.new_backend()
    entered, release = threading.Event(), threading.Event()
    async def controlled(req):
        if req.url.path == '/system_stats':
            entered.set()
            assert await asyncio.to_thread(release.wait, 3)
        return await backend(req)
    with owner_env.client(backend=controlled) as c, owner_env.client() as other:
        fid = owner_env.upload(c, 'A')
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(owner_env.submit, c, 'A', kind='image_edit', image_ids=[fid])
            try:
                assert entered.wait(3)
                assert other.delete(f'/v1/files/{fid}', headers=owner_env.auth('A')).status_code == 200
            finally:
                release.set()
            rejected = pending.result(timeout=4)
        assert rejected.status_code == 404
        assert rejected.json() == {'detail': 'Object not found'}
        for _ in range(4):
            assert owner_env.submit(c, 'A').status_code == 202
        assert owner_env.submit(c, 'A').status_code == 429
        assert backend.jobs == []


def test_tb02_global_upload_quota_is_atomic_between_app_instances(owner_env):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    with owner_env.client() as first, owner_env.client() as second:
        # Sparse logical occupancy is test setup; real HTTP uploads race the remaining capacity.
        first.app.state.store.add_file('file-' + 'e'*32, 'quota-fixture', 2*1024**3 - 3*1024**2)
        barrier = threading.Barrier(2)
        def upload(c, owner):
            barrier.wait(timeout=3)
            return c.post('/v1/files', headers=owner_env.auth(owner),
                          files={'file': ('x.bin', b'x' * (2*1024**2))})
        with ThreadPoolExecutor(max_workers=2) as pool:
            a = pool.submit(upload, first, 'A')
            b = pool.submit(upload, second, 'B')
            results = [a.result(timeout=5), b.result(timeout=5)]
        assert sorted(r.status_code for r in results) == [200, 413]
        for owner, response in zip(['A', 'B'], results):
            if response.status_code == 200:
                fid = response.json()['id']
                assert first.get(f'/v1/files/{fid}/content', headers=owner_env.auth(owner)).content == b'x' * (2*1024**2)
                stranger = 'B' if owner == 'A' else 'A'
                assert second.delete(f'/v1/files/{fid}', headers=owner_env.auth(stranger)).status_code == 404


def test_tb02_restart_and_restored_copy_preserve_private_files(owner_env, tmp_path):
    import shutil
    import sqlite3
    backend = owner_env.new_backend()
    files = {}
    with owner_env.client(backend=backend, run_worker=True) as c:
        for owner in ['A', 'B']:
            response = c.post('/v1/images/edits', headers={**owner_env.auth(owner), 'Idempotency-Key': owner},
                              data={'prompt': 'edit'}, files={'image': ('x.png', backend.png, 'image/png')})
            assert response.status_code == 200
            files[owner] = response.json()['data'][0]['file_id']
    # Quiescent synthetic runtime; SQLite backup plus files restores to a NEW directory.
    original_root = owner_env.root
    restored = tmp_path / 'restored'
    restored.mkdir()
    with sqlite3.connect(original_root / 'state.sqlite3') as source, sqlite3.connect(restored / 'state.sqlite3') as target:
        source.backup(target)
    shutil.copytree(original_root / 'files', restored / 'files')
    for root in [original_root, restored]:
        owner_env.root = root
        with owner_env.client(backend=backend, run_worker=True) as c:
            for owner, fid in files.items():
                assert c.get(f'/v1/files/{fid}/content', headers=owner_env.auth(owner)).status_code == 200
                stranger = 'B' if owner == 'A' else 'A'
                assert c.get(f'/v1/files/{fid}/content', headers=owner_env.auth(stranger)).status_code == 404
                replay = c.post('/v1/images/edits', headers={**owner_env.auth(owner), 'Idempotency-Key': owner},
                                data={'prompt': 'edit'}, files={'image': ('x.png', backend.png, 'image/png')})
                assert replay.status_code == 200
                assert replay.json()['data'][0]['file_id'] == fid
    assert len(backend.jobs) == 2
