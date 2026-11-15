"""Approved scheduler, HTTP/worker and MCP public seams; synthetic backend only."""
def test_tb10_owner_gets_turn_before_repeat_submitter():
    from services.image_queue import choose_next
    heads = [{'id':'A1','owner':'A','eligible':True},
             {'id':'B1','owner':'B','eligible':True}]
    assert choose_next(heads, None) == 'A1'
    heads[0]['id'] = 'A2'
    assert choose_next(heads, 'A') == 'B1'


def test_tb10_http_worker_serves_other_owner_before_second_task(owner_env):
    backend = owner_env.new_backend(hold=True)
    with owner_env.client(backend=backend, run_worker=True) as c:
        a1 = owner_env.submit(c, 'A', request_key='a1').json()['id']
        assert backend.started.wait(2)
        a2 = owner_env.submit(c, 'A', request_key='a2').json()['id']
        b1 = owner_env.submit(c, 'B', request_key='b1').json()['id']
        backend.finish.set()
        owner_env.wait_task(c, a2, 'A', lambda t: t['status'] == 'completed')
        owner_env.wait_task(c, b1, 'B', lambda t: t['status'] == 'completed')
        assert [job['client_id'] for job in backend.jobs] == [a1, b1, a2]


def test_tb10_http_queue_ahead_tracks_fair_order_without_other_owner_details(owner_env):
    backend = owner_env.new_backend(hold=True)
    with owner_env.client(backend=backend, run_worker=True) as c:
        a1 = owner_env.submit(c, 'A').json()['id']
        assert backend.started.wait(2)
        a2 = owner_env.submit(c, 'A').json()['id']
        b1 = owner_env.submit(c, 'B').json()['id']
        assert c.get('/v1/tasks/'+a1, headers=owner_env.auth('A')).json()['queue_ahead'] == 0
        assert c.get('/v1/tasks/'+a2, headers=owner_env.auth('A')).json()['queue_ahead'] == 2
        b = c.get('/v1/tasks/'+b1, headers=owner_env.auth('B')).json()
        assert b['queue_ahead'] == 1
        assert all(key not in b for key in ('owner','last_owner','enqueue_seq','claimed_task'))
        listing = c.get('/v1/tasks', headers=owner_env.auth('A')).json()['data']
        assert [t['queue_ahead'] for t in listing] == [0, 2]
        assert c.get('/v1/tasks/'+a1, headers=owner_env.auth('B')).status_code == 404
        backend.finish.set()
        done = owner_env.wait_task(c, b1, 'B', lambda t: t['status'] == 'completed')
        assert done['queue_ahead'] is None


def test_tb10_mcp_explains_dynamic_queue_snapshot_without_eta():
    from client.spark_image_tools import present_task
    task = {'id':'task-fixture','kind':'image_generate','status':'queued','stage':'queued',
            'queue_ahead':2, 'queue_reason':None}
    shown = present_task(task)
    assert shown['queue_text'] == '当前前方 2 单，排位随资源与队列变化'
    assert not any(key in shown for key in ('eta','estimated_seconds'))
    waiting = present_task({**task,'queue_ahead':None,'queue_reason':'system_memory'})
    assert waiting['queue_text'] == '等待资源，当前无法确定前方单数'
    assert waiting['queue_reason'] == 'system_memory'


from contextlib import contextmanager
import dataclasses
import threading
import httpx
from fastapi.testclient import TestClient
from image_test_harness import synthetic_resources
from services.gateway import create_app


@contextmanager
def configured_client(env, backend, config, *, run_worker=True):
    with TestClient(create_app(env.root, env.keys['legacy'], key_registry=env.registry,
            identity_mode='staging', transport=httpx.MockTransport(backend), run_worker=run_worker,
            audio_enabled=False, images_enabled=True, event_stream_factory=backend.event_stream, **config)) as c:
        yield c


def test_tb10_blocked_owner_head_does_not_block_others_or_allow_own_overtake(owner_env):
    backend = owner_env.new_backend(hold=True)
    recovered = threading.Event()
    config = synthetic_resources(wait_timeout=5.)
    sample = config['resource_sampler']
    config['resource_sampler'] = lambda tid: dataclasses.replace(sample(tid),
        available_bytes=(60 if recovered.is_set() else 25)*1024**3)
    config['memory_budgets']['generate'] = dataclasses.replace(config['memory_budgets']['generate'], peak_increment_bytes=2*1024**3)
    with configured_client(owner_env, backend, config, run_worker=False) as c:
        ref = owner_env.upload(c)
        a1 = owner_env.submit(c, 'A', kind='image_edit', image_ids=[ref], quality='high').json()['id']
        a2 = owner_env.submit(c, 'A').json()['id']
        b1 = owner_env.submit(c, 'B').json()['id']
    with configured_client(owner_env, backend, config) as c:
        try:
            assert backend.started.wait(1), 'eligible B did not start while A head was memory blocked'
            assert backend.jobs[0]['client_id'] == b1
            blocked = c.get('/v1/tasks/'+a1, headers=owner_env.auth('A')).json()
            assert blocked['queue_ahead'] is None and blocked['queue_reason'] == 'system_memory'
            assert c.get('/v1/tasks/'+a2, headers=owner_env.auth('A')).json()['queue_ahead'] is None
        finally:
            recovered.set()
            backend.finish.set()
        owner_env.wait_task(c, a2, 'A', lambda t: t['status'] == 'completed')
        assert [job['client_id'] for job in backend.jobs] == [b1, a1, a2]
