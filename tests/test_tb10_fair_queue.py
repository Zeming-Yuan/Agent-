"""Approved scheduler, HTTP/worker and MCP public seams; synthetic backend only."""
import pytest
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


@pytest.mark.parametrize('prior_residents', [frozenset({'high'}), None])
def test_tb10_idle_backend_gets_release_turn_before_cold_capacity_is_known(owner_env,prior_residents):
    backend = owner_env.new_backend()
    freed = threading.Event()
    config = synthetic_resources(wait_timeout=.3)
    original = config['resource_sampler']
    config['resource_sampler'] = lambda tid: dataclasses.replace(original(tid),
        available_bytes=(60 if freed.is_set() else 25)*1024**3,
        resident_profiles=frozenset() if freed.is_set() else prior_residents)
    calls = []
    async def external(request):
        if request.url.path == '/free':calls.append('free');freed.set()
        return await backend(request)
    with TestClient(create_app(owner_env.root, owner_env.keys['legacy'], key_registry=owner_env.registry,
            identity_mode='staging', transport=httpx.MockTransport(external), images_enabled=True,
            audio_enabled=False, event_stream_factory=backend.event_stream, **config)) as c:
        tid = owner_env.submit(c).json()['id']
        done = owner_env.wait_task(c, tid, 'A', lambda t: t['status'] in ('completed','failed'))
        assert done['status'] == 'completed', done
        assert calls == ['free'] and len(backend.jobs) == 1


def blocked_config():
    config = synthetic_resources(wait_timeout=.25)
    config['memory_budgets']['generate'] = dataclasses.replace(config['memory_budgets']['generate'], peak_increment_bytes=2*1024**3)
    return config


def seed_blocked_pair(env, backend, config):
    with configured_client(env, backend, config, run_worker=False) as c:
        ref = env.upload(c)
        a = env.submit(c, 'A', kind='image_edit', image_ids=[ref], quality='high').json()['id']
        b = env.submit(c, 'B').json()['id']
    return a, b


def test_tb10_unclaimed_wait_deadline_is_visible_while_other_owner_runs(owner_env):
    backend = owner_env.new_backend(hold=True)
    config = blocked_config()
    original = config['resource_sampler']
    config['resource_sampler'] = lambda tid: dataclasses.replace(original(tid), available_bytes=25*1024**3)
    a, b = seed_blocked_pair(owner_env, backend, config)
    with configured_client(owner_env, backend, config) as c:
        try:
            assert backend.started.wait(1)
            failed = owner_env.wait_task(c, a, 'A', lambda t: t['status'] == 'failed', timeout=1)
            assert failed['blocked_reason'] == 'resource_wait_expired'
            assert c.get('/v1/tasks/'+b, headers=owner_env.auth('B')).json()['status'] == 'running'
        finally:backend.finish.set()


def test_tb10_recovered_head_waits_for_occupied_turn_without_expiring(owner_env):
    backend = owner_env.new_backend(hold=True)
    config = blocked_config()
    recovered = threading.Event()
    original = config['resource_sampler']
    config['resource_sampler'] = lambda tid: dataclasses.replace(original(tid), available_bytes=(60 if recovered.is_set() else 25)*1024**3)
    a, b = seed_blocked_pair(owner_env, backend, config)
    with configured_client(owner_env, backend, config) as c:
        try:
            assert backend.started.wait(1)
            recovered.set()
            # The resource condition recovers before its own deadline; a longer
            # unrelated inference must not count as continued resource waiting.
            threading.Event().wait(.4)
            state = c.get('/v1/tasks/'+a, headers=owner_env.auth('A')).json()
            assert state['status'] == 'queued', state
            assert state['queue_ahead'] == 1 and state['queue_reason'] is None
        finally:backend.finish.set()
        owner_env.wait_task(c, a, 'A', lambda t: t['status'] == 'completed')
        assert [job['client_id'] for job in backend.jobs] == [b, a]


def test_tb10_follower_explains_owner_head_resource_block(owner_env):
    backend = owner_env.new_backend()
    config = blocked_config()
    original = config['resource_sampler']
    config['resource_sampler'] = lambda tid: dataclasses.replace(original(tid),available_bytes=25*1024**3)
    with configured_client(owner_env, backend, config, run_worker=False) as c:
        ref = owner_env.upload(c)
        owner_env.submit(c, 'A', kind='image_edit', image_ids=[ref], quality='high')
        follower = owner_env.submit(c, 'A').json()
        assert follower['queue_ahead'] is None
        assert follower['queue_reason'] == 'system_memory'


def test_tb10_proven_release_with_low_memory_yields_without_repeated_free(owner_env):
    backend = owner_env.new_backend(hold=True)
    config = blocked_config()
    config['resource_settings']['wait_timeout'] = 3.
    freed = threading.Event(); recovered = threading.Event()
    original = config['resource_sampler']; calls = []
    config['resource_sampler'] = lambda tid: dataclasses.replace(original(tid),
        resident_profiles=frozenset() if freed.is_set() else frozenset({'high'}),
        available_bytes=(60 if recovered.is_set() else 25)*1024**3)
    async def external(request):
        if request.url.path == '/free':calls.append('free');freed.set()
        return await backend(request)
    # Retain the event stream while wrapping the external HTTP boundary.
    external.event_stream = backend.event_stream
    a, b = seed_blocked_pair(owner_env, external, config)
    with configured_client(owner_env, external, config) as c:
        try:
            assert backend.started.wait(1), 'released but memory-blocked A held B control turn'
            assert backend.jobs[0]['client_id'] == b
            count = len(calls)
            threading.Event().wait(.25)
            assert len(calls) == count == 2  # one A release, one B release; no retry loop
            state = c.get('/v1/tasks/'+a, headers=owner_env.auth('A')).json()
            assert state['status'] == 'queued' and state['queue_ahead'] is None
        finally:recovered.set();backend.finish.set()
        owner_env.wait_task(c, a, 'A', lambda t: t['status'] == 'completed')


def test_tb10_running_resource_sample_still_counts_the_owned_slot(owner_env):
    backend = owner_env.new_backend(hold=True)
    config = blocked_config()
    original = config['resource_sampler']
    config['resource_sampler'] = lambda tid: dataclasses.replace(original(tid),
        running_prompts=tuple(sorted(backend.running)), resident_profiles=frozenset({'generate'}) if backend.running else frozenset())
    with configured_client(owner_env, backend, config) as c:
        a = owner_env.submit(c, 'A').json()['id']
        try:
            assert backend.started.wait(1)
            b = owner_env.submit(c, 'B').json()['id']
            state = c.get('/v1/tasks/'+b,headers=owner_env.auth('B')).json()
            assert state['queue_ahead'] == 1, state
            threading.Event().wait(.4)
            assert c.get('/health',headers=owner_env.auth('A')).status_code == 200
            assert c.get('/v1/tasks/'+b,headers=owner_env.auth('B')).json()['status'] == 'queued'
        finally:backend.finish.set()
        owner_env.wait_task(c,b,'B',lambda t:t['status']=='completed')
        assert [job['client_id'] for job in backend.jobs] == [a,b]


from services.image_queue import choose_next, queue_ahead


@pytest.mark.parametrize('last,a_ok,b_ok,expected', [
    ('A',True,True,'B1'),('B',True,True,'A1'),('A',True,False,'A1'),
    ('B',False,True,'B1'),('A',False,False,None),('removed',True,True,'A1')])
def test_tb10_round_robin_counterexamples(last,a_ok,b_ok,expected):
    assert choose_next([{'id':'A1','owner':'A','eligible':a_ok},
                        {'id':'B1','owner':'B','eligible':b_ok}],last) == expected


def test_tb10_queue_policy_is_immutable_and_never_overtakes_blocked_owner_head():
    rows = [{'id':'A1','owner':'A','eligible':False,'enqueue_seq':1},
            {'id':'A2','owner':'A','eligible':True,'enqueue_seq':2},
            {'id':'B1','owner':'B','eligible':True,'enqueue_seq':3}]
    before = [dict(row) for row in rows]
    assert queue_ahead(rows,'A1',None) is None
    assert queue_ahead(rows,'A2',None) is None
    assert queue_ahead(rows,'B1',None,'occupied') == 1
    assert rows == before


def test_tb10_global_capacity_is_not_personal_quota(owner_env):
    with owner_env.client() as c:
        accepted = [owner_env.submit(c,'A',request_key=str(n)) for n in range(4)]
        assert [r.status_code for r in accepted] == [202]*4
        full = owner_env.submit(c,'B')
        assert full.status_code == 429 and full.headers['retry-after'] == '10'
        replay = owner_env.submit(c,'A',request_key='0')
        assert replay.status_code == 202 and replay.json()['id'] == accepted[0].json()['id']
        assert len(c.get('/v1/tasks',headers=owner_env.auth('A')).json()['data']) == 4


def test_tb10_concurrent_same_time_acceptance_keeps_owner_fifo(owner_env,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    monkeypatch.setattr('services.store.time.time',lambda:1_790_000_000.)
    gate = threading.Barrier(4)
    with owner_env.client() as c:
        def submit(n):
            gate.wait(timeout=2)
            return owner_env.submit(c,'A',request_key=str(n))
        with ThreadPoolExecutor(max_workers=4) as pool:
            replies = list(pool.map(submit,range(4)))
        assert all(r.status_code == 202 for r in replies)
        listing = c.get('/v1/tasks',headers=owner_env.auth('A')).json()['data']
        assert len({t['created'] for t in listing}) == 1
        order = [t['id'] for t in listing]
    backend = owner_env.new_backend()
    with owner_env.client(backend=backend,run_worker=True) as c:
        owner_env.wait_task(c,order[-1],'A',lambda t:t['status']=='completed')
        assert [job['client_id'] for job in backend.jobs] == order


def test_tb10_restart_cancel_and_backup_restore_preserve_owner_turn(owner_env,tmp_path):
    import shutil
    backend = owner_env.new_backend()
    with owner_env.client(backend=backend,run_worker=True) as c:
        first = owner_env.submit(c,'A').json()['id']
        owner_env.wait_task(c,first,'A',lambda t:t['status']=='completed')
    with owner_env.client() as c:
        removed = owner_env.submit(c,'A').json()['id']
        a = owner_env.submit(c,'A').json()['id']
        b = owner_env.submit(c,'B').json()['id']
        assert c.post('/v1/tasks/'+removed+'/cancel',headers=owner_env.auth('A')).json()['status']=='cancelled'
        assert c.post('/v1/tasks/'+removed+'/cancel',headers=owner_env.auth('A')).json()['status']=='cancelled'
    backup = tmp_path/'restored'
    shutil.copytree(owner_env.root,backup)
    owner_env.root = backup
    backend = owner_env.new_backend()
    with owner_env.client(backend=backend,run_worker=True) as c:
        owner_env.wait_task(c,a,'A',lambda t:t['status']=='completed')
        assert [job['client_id'] for job in backend.jobs] == [b,a]
        assert c.get('/v1/tasks/'+first,headers=owner_env.auth('A')).json()['status']=='completed'
        assert c.get('/v1/tasks/'+a,headers=owner_env.auth('B')).status_code==404


def test_tb10_all_blocked_waits_without_free_or_prompt_and_wakes_on_resource_change(owner_env):
    backend = owner_env.new_backend()
    config = synthetic_resources(wait_timeout=3.)
    recovered = threading.Event(); original = config['resource_sampler']; calls=[]
    config['resource_sampler'] = lambda tid: dataclasses.replace(original(tid),available_bytes=(60 if recovered.is_set() else 25)*1024**3)
    async def external(request):
        if request.url.path in ('/free','/prompt'):calls.append(request.url.path)
        return await backend(request)
    external.event_stream = backend.event_stream
    with configured_client(owner_env,external,config) as c:
        a=owner_env.submit(c,'A').json()['id']; b=owner_env.submit(c,'B').json()['id']
        owner_env.wait_task(c,b,'B',lambda t:t['stage']=='waiting_resources')
        threading.Event().wait(.25)
        assert calls == [] and backend.jobs == []
        recovered.set()
        owner_env.wait_task(c,b,'B',lambda t:t['status']=='completed')
        assert [job['client_id'] for job in backend.jobs] == [a,b]


def test_tb10_queued_cancel_keeps_owned_control_count_until_release_settles(owner_env):
    import asyncio
    backend=owner_env.new_backend(); entered=threading.Event(); release=threading.Event()
    config=synthetic_resources(wait_timeout=3.)
    async def external(request):
        if request.url.path=='/free':
            entered.set()
            assert await asyncio.to_thread(release.wait,2)
        return await backend(request)
    external.event_stream=backend.event_stream
    with configured_client(owner_env,external,config) as c:
        a=owner_env.submit(c,'A').json()['id']
        try:
            assert entered.wait(1)
            b=owner_env.submit(c,'B').json()['id']
            cancelled=c.post('/v1/tasks/'+a+'/cancel',headers=owner_env.auth('A')).json()
            assert cancelled['status']=='cancelled'
            assert c.get('/v1/tasks/'+b,headers=owner_env.auth('B')).json()['queue_ahead']==1
            assert backend.jobs==[]
        finally:release.set()
        owner_env.wait_task(c,b,'B',lambda t:t['status']=='completed')
        assert [job['client_id'] for job in backend.jobs]==[b]


def test_tb10_nonimage_media_does_not_add_to_image_snapshot(owner_env):
    with owner_env.client() as c:
        fid=owner_env.upload(c)
        media=c.post('/v1/tasks',headers=owner_env.auth('A'),json={'kind':'pdf','file_id':fid})
        assert media.status_code==202
        a=owner_env.submit(c,'A').json(); b=owner_env.submit(c,'B').json()
        assert a['queue_ahead']==0 and b['queue_ahead']==1
        assert 'queue_ahead' not in c.get('/v1/tasks/'+media.json()['id'],headers=owner_env.auth('A')).json()


def test_tb10_real_stdio_tls_exposes_dynamic_counts_and_downloads_same_result(owner_env,tmp_path):
    import asyncio
    import json
    import os
    import sys
    import ssl
    from pathlib import Path
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from image_test_harness import image_app, https_server
    backend=owner_env.new_backend(hold=True)
    app=image_app(owner_env.root,owner_env.keys['legacy'],key_registry=owner_env.registry,
        identity_mode='staging',transport=httpx.MockTransport(backend),run_worker=True,
        audio_enabled=False,images_enabled=True,event_stream_factory=backend.event_stream)
    with https_server(app,tmp_path) as (port,cert):
        with httpx.Client(base_url=f'https://127.0.0.1:{port}',verify=ssl.create_default_context(cafile=str(cert)),trust_env=False) as c:
            a1=owner_env.submit(c,'A',request_key='stdio-a1').json()['id']
            assert backend.started.wait(2)
            a2=owner_env.submit(c,'A',request_key='stdio-a2').json()['id']
            b1=owner_env.submit(c,'B',request_key='stdio-b1').json()['id']
            key=tmp_path/'personal.key';key.write_text(owner_env.keys['A']);key.chmod(0o600)
            config=tmp_path/'client.json'
            config.write_text(json.dumps({'base_url':f'https://127.0.0.1:{port}/v1','api_key_file':str(key),
                'ca_file':str(cert),'output_dir':str(tmp_path/'图片 output'),'journal_path':str(tmp_path/'journal.sqlite3')}))
            script=Path(__file__).resolve().parents[1]/'client/spark_image_tools.py'
            async def run():
                params=StdioServerParameters(command=sys.executable,args=[str(script),'--config',str(config)],
                    env={k:v for k,v in os.environ.items() if k!='PYTHONPATH'},cwd=tmp_path)
                with open(os.devnull,'w') as errors:
                    async with stdio_client(params,errlog=errors) as (read,write):
                        async with ClientSession(read,write) as session:
                            await session.initialize()
                            async def call(name,args):
                                result=await session.call_tool(name,args)
                                assert not result.isError,result
                                return result
                            def state(result):return json.loads(next(block.text for block in result.content if block.type=='text'))
                            shown=state(await call('get_image_task',{'task_id':a2,'wait_seconds':0}))
                            assert shown['queue_ahead']==2 and '前方 2 单' in shown['queue_text']
                            listed=state(await call('list_image_tasks',{}))['data']
                            assert [t['id'] for t in listed]==[a1,a2]
                            assert [t['queue_ahead'] for t in listed]==[0,2]
                            await call('cancel_image_task',{'task_id':a2})
                            assert c.get('/v1/tasks/'+b1,headers=owner_env.auth('B')).json()['queue_ahead']==1
                            backend.finish.set()
                            result=await call('get_image_task',{'task_id':a1,'wait_seconds':20})
                            assert any(block.type=='image' for block in result.content)
                            assert next((tmp_path/'图片 output').glob('*.png')).read_bytes()==backend.png
            try:asyncio.run(run())
            finally:backend.finish.set()
            owner_env.wait_task(c,b1,'B',lambda t:t['status']=='completed')
            assert [job['client_id'] for job in backend.jobs]==[a1,b1]


def test_tb10_snapshot_counts_the_same_pending_release_turn_as_claim(owner_env):
    backend=owner_env.new_backend()
    config=blocked_config()
    original=config['resource_sampler']
    config['resource_sampler']=lambda tid:dataclasses.replace(original(tid),available_bytes=25*1024**3,resident_profiles=frozenset({'high'}))
    with configured_client(owner_env,backend,config,run_worker=False) as c:
        ref=owner_env.upload(c)
        a=owner_env.submit(c,'A',kind='image_edit',image_ids=[ref],quality='high').json()
        b=owner_env.submit(c,'B').json()
        assert a['queue_ahead'] is None and a['queue_reason']=='release_required'
        assert b['queue_ahead']==1  # A must first own the controlled release turn


def test_tb10_expired_profile_wait_does_not_disable_other_valid_profiles(owner_env):
    import time
    backend=owner_env.new_backend(hold=True)
    config=synthetic_resources(wait_timeout=.15)
    a,b=seed_blocked_pair(owner_env,backend,config)
    config['memory_budgets']['high']=dataclasses.replace(config['memory_budgets']['high'],valid_until=time.monotonic()-1)
    with configured_client(owner_env,backend,config) as c:
        try:
            assert backend.started.wait(1)
            failed=owner_env.wait_task(c,a,'A',lambda t:t['status']=='failed',timeout=1)
            assert failed['blocked_reason']=='resource_wait_expired',failed
            assert 'invalid_budget' in failed['error']
            assert c.get('/health',headers=owner_env.auth('B')).status_code==200
            second=owner_env.submit(c,'B').json()['id']
        finally:backend.finish.set()
        owner_env.wait_task(c,second,'B',lambda t:t['status']=='completed')
        assert [job['client_id'] for job in backend.jobs]==[b,second]
