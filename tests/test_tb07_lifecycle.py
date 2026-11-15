def test_tb07_cancel_waits_until_backend_stopped(owner_env):
    backend = owner_env.new_backend(hold=True, hold_stop=True)
    with owner_env.client(backend=backend, run_worker=True) as c:
        tid = owner_env.submit(c, 'A').json()['id']
        assert backend.started.wait(2)
        try:
            response = c.post('/v1/tasks/' + tid + '/cancel', headers=owner_env.auth('A'))
            assert response.json()['status'] == 'running'
            assert response.json()['stage'] == 'cancelling'
            # Repeated cancellation must not interrupt the cleanup itself.
            again = c.post('/v1/tasks/' + tid + '/cancel', headers=owner_env.auth('A'))
            assert again.json()['stage_seq'] == response.json()['stage_seq']
            second = owner_env.submit(c, 'B').json()['id']
            assert len(backend.jobs) == 1
            assert c.get('/v1/tasks/' + second, headers=owner_env.auth('B')).json()['status'] == 'queued'
        finally:
            backend.release_stop.set()
        done = owner_env.wait_task(c, tid, 'A', lambda t: t['status'] == 'cancelled')
        assert done['stage'] == 'cancelled'
        backend.finish.set()
        owner_env.wait_task(c, second, 'B', lambda t: t['status'] == 'completed')
