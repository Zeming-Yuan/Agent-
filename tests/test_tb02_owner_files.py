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
