"""T05 recovery through authenticated HTTP, real persistence and image workers."""
import io

import pytest
from PIL import Image


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
