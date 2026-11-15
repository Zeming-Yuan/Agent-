"""Approved public resource policy and HTTP/serial-worker boundaries."""
from services.image_telemetry import ResourceSample


def test_tb09_low_memory_does_not_start_work():
    from services.image_resources import MemoryBudget, admit
    gib = 1024**3
    sample = ResourceSample(25*gib, 50*gib, 10.0, frozenset(), (), 2)
    budget = MemoryBudget(10*gib, 2*gib, 20*gib, 100.0, 'runtime')
    decision = admit(sample, budget, now=10.0, runtime_hash='runtime', released=True, max_age=1.0)
    assert not decision.allowed
    assert decision.reason == 'system_memory'


import dataclasses
import pytest


@pytest.mark.parametrize('fault, reason', [
    ('missing_sample','missing_evidence'), ('missing_budget','missing_evidence'),
    ('release','release_unconfirmed'), ('stale','stale_sample'), ('future','stale_sample'),
    ('container','container_memory'), ('runtime','invalid_budget'), ('expired','invalid_budget'),
    ('reserve','invalid_budget'), ('negative','invalid_budget'), ('nan_budget','invalid_budget'),
    ('nan_clock','stale_sample'), ('nan_age','stale_sample'), ('zero_age','stale_sample'),
    ('missing_memory','missing_evidence'), ('errors','missing_evidence'),
    ('running','release_unconfirmed'), ('unknown_residents','release_unconfirmed'),
])
def test_tb09_invalid_evidence_never_admits(fault, reason):
    from services.image_resources import MemoryBudget, admit
    gib = 1024**3
    sample = ResourceSample(60*gib, 50*gib, 10.0, frozenset(), (), 2)
    budget = MemoryBudget(10*gib, 2*gib, 20*gib, 100.0, 'runtime')
    now, age, released = 10., 1., True
    if fault == 'missing_sample': sample = None
    if fault == 'missing_budget': budget = None
    if fault == 'release': released = False
    if fault == 'stale': now = 20.
    if fault == 'future': now = 9.
    if fault == 'container': sample = dataclasses.replace(sample, cgroup_headroom_bytes=gib)
    if fault == 'runtime': budget = dataclasses.replace(budget, runtime_hash='different')
    if fault == 'expired': budget = dataclasses.replace(budget, valid_until=10.)
    if fault == 'reserve': budget = dataclasses.replace(budget, reserve_bytes=19*gib)
    if fault == 'negative': budget = dataclasses.replace(budget, peak_increment_bytes=-1)
    if fault == 'nan_budget': budget = dataclasses.replace(budget, valid_until=float('nan'))
    if fault == 'nan_clock': now = float('nan')
    if fault == 'nan_age': age = float('nan')
    if fault == 'zero_age': age = 0.
    if fault == 'missing_memory': sample = dataclasses.replace(sample, available_bytes=None)
    if fault == 'errors': sample = dataclasses.replace(sample, errors=('sampler_failed',))
    if fault == 'running': sample = dataclasses.replace(sample, running_prompts=('old-prompt',))
    if fault == 'unknown_residents': sample = dataclasses.replace(sample, resident_profiles=None)
    decision = admit(sample, budget, now=now, runtime_hash='runtime', released=released, max_age=age)
    assert (decision.allowed, decision.reason) == (False, reason)


def test_tb09_exact_budget_boundary_allows_without_summing_unified_scopes():
    from services.image_resources import MemoryBudget, admit
    gib = 1024**3
    decision = admit(ResourceSample(32*gib, 12*gib, 10., frozenset(), (), 2),
        MemoryBudget(10*gib, 2*gib, 20*gib, 100., 'runtime'),
        now=10., runtime_hash='runtime', released=True, max_age=1.)
    assert (decision.allowed, decision.reason) == (True, 'ready')


def release_sample(at=10., **changes):
    return ResourceSample(60*1024**3, 50*1024**3, at, frozenset(), (), 2,
        release_proven=True, release_task_id='task-one', host_id='host',
        runtime_hash='runtime', session_id='session', **changes)


@pytest.mark.parametrize('fault', ['valid','epoch_only','resident','running','sparse','duplicate',
    'different_session','different_task','different_host','different_runtime','old_epoch','errors','short'])
def test_tb09_release_requires_correlated_continuous_proof(fault):
    from services.image_resources import released
    rows = [release_sample(at) for at in (10., 10.1, 10.2, 10.3)]
    change = {'epoch_only': {'release_proven': None}, 'resident': {'resident_profiles': frozenset({'fast'})},
        'running': {'running_prompts': ('orphan',)}, 'different_session': {'session_id': 'other'},
        'different_task': {'release_task_id': 'other'}, 'different_host': {'host_id': 'other'},
        'different_runtime': {'runtime_hash': 'other'}, 'old_epoch': {'release_epoch': 1},
        'errors': {'errors': ('missing_signal',)}}.get(fault, {})
    rows[1] = dataclasses.replace(rows[1], **change)
    if fault == 'sparse': rows = [rows[0], dataclasses.replace(rows[-1], observed_at=11.)]
    if fault == 'duplicate': rows[1] = rows[0]
    if fault == 'short': rows = rows[:2]
    assert released(rows, after_epoch=1, stable_window=.25) is (fault == 'valid')


from image_test_harness import synthetic_resources as resources


def client_with_resources(env, backend, **config):
    import httpx
    from fastapi.testclient import TestClient
    from services.gateway import create_app
    return TestClient(create_app(env.root, env.keys['legacy'], key_registry=env.registry,
        identity_mode='staging', transport=httpx.MockTransport(backend), run_worker=True,
        audio_enabled=False, images_enabled=True, event_stream_factory=backend.event_stream, **config))


def test_tb09_low_memory_remains_queued_until_resources_recover(owner_env):
    import dataclasses
    backend = owner_env.new_backend()
    config = resources(available=25*1024**3)
    original = config['resource_sampler']
    import threading
    recovered = threading.Event()
    config['resource_sampler'] = lambda tid: dataclasses.replace(original(tid),
        available_bytes=(60 if recovered.is_set() else 25)*1024**3)
    with client_with_resources(owner_env, backend, **config) as c:
        response = owner_env.submit(c, request_key='low-memory')
        assert response.status_code == 202, response.text
        tid = response.json()['id']
        waiting = owner_env.wait_task(c, tid, 'A', lambda t: t.get('blocked_reason') == 'system_memory')
        assert (waiting['status'], waiting['stage']) == ('queued','waiting_resources')
        assert backend.jobs == []
        recovered.set()
        done = owner_env.wait_task(c, tid, 'A', lambda t: t['status'] == 'completed')
        assert done['id'] == tid and len(backend.jobs) == 1
        assert c.get(done['result']['content_url'], headers=owner_env.auth('A')).status_code == 200


def test_tb09_unconfigured_production_is_degraded_and_replay_still_works(owner_env):
    from fastapi.testclient import TestClient
    from services.gateway import create_app
    import httpx
    backend = owner_env.new_backend()
    with client_with_resources(owner_env, backend, **resources()) as c:
        first = owner_env.submit(c, request_key='recoverable').json()
        done = owner_env.wait_task(c, first['id'], 'A', lambda t: t['status'] == 'completed')
    with TestClient(create_app(owner_env.root, owner_env.keys['legacy'], key_registry=owner_env.registry,
        identity_mode='staging', transport=httpx.MockTransport(backend), run_worker=False,
        audio_enabled=False, images_enabled=True)) as c:
        assert c.get('/health', headers=owner_env.auth('A')).status_code == 503
        assert owner_env.submit(c, request_key='new').status_code == 503
        assert owner_env.submit(c, request_key='recoverable').json()['id'] == first['id']
        assert c.get(done['result']['content_url'], headers=owner_env.auth('A')).status_code == 200
        assert c.get('/v1/tasks/'+first['id'], headers=owner_env.auth('B')).status_code == 404


def test_tb09_initial_sampler_outage_recovers_same_queued_task(owner_env):
    import threading
    ready = threading.Event(); attempted = threading.Event()
    config = resources(wait_timeout=.5)
    original = config['resource_sampler']
    def sample(tid):
        attempted.set()
        return original(tid) if ready.is_set() else None
    config['resource_sampler'] = sample
    backend = owner_env.new_backend()
    with client_with_resources(owner_env, backend, **config) as c:
        tid = owner_env.submit(c).json()['id']
        assert attempted.wait(1)
        assert backend.jobs == []
        ready.set()
        done = owner_env.wait_task(c, tid, 'A', lambda t: t['status'] in ('failed','completed'))
        assert done['status'] == 'completed', done
        assert len(backend.jobs) == 1


def test_tb09_slow_external_setup_cannot_bridge_an_observation_gap(owner_env):
    import asyncio
    import time
    config = resources()
    reads = []
    original = config['resource_sampler']
    def sample(tid):
        row = original(tid); reads.append(row.observed_at); return row
    config['resource_sampler'] = sample
    backend = owner_env.new_backend()
    proof_at_submit = []
    async def external(request):
        if request.url.path == '/prompt':
            recent = [t for t in reads if time.monotonic()-t < .15]
            proof_at_submit.append(len(recent) >= 2 and recent[-1]-recent[0] >= .02)
        return await backend(request)
    class SlowEvents:
        async def __aenter__(self):
            await asyncio.sleep(.3)
            return self
        async def __aexit__(self, *exc):return False
        async def events(self):
            await asyncio.Event().wait()
            yield
    # Event connection is an external boundary, not a mocked internal controller.
    import httpx
    from fastapi.testclient import TestClient
    from services.gateway import create_app
    app = create_app(owner_env.root, owner_env.keys['legacy'], key_registry=owner_env.registry,
        identity_mode='staging',transport=httpx.MockTransport(external),run_worker=True,
        audio_enabled=False,images_enabled=True,event_stream_factory=lambda *_:SlowEvents(),**config)
    with TestClient(app) as c:
        tid = owner_env.submit(c).json()['id']
        done = owner_env.wait_task(c, tid, 'A', lambda t:t['status'] in ('failed','completed'))
        assert done['status'] == 'completed', done
        assert proof_at_submit == [True]


def test_tb09_lost_release_at_final_resource_read_stops_new_admission(owner_env):
    config = resources(wait_timeout=.1)
    config['resource_settings']['stable_window'] = .00001
    original = config['resource_sampler']
    reads = 0
    def sample(tid):
        nonlocal reads
        reads += 1
        row = original(tid)
        return dataclasses.replace(row, release_proven=False) if reads >= 4 else row
    config['resource_sampler'] = sample
    backend = owner_env.new_backend()
    with client_with_resources(owner_env, backend, **config) as c:
        tid = owner_env.submit(c).json()['id']
        owner_env.wait_task(c,tid,'A',lambda t:t['status']=='failed')
        assert backend.jobs == []
        assert c.get('/health',headers=owner_env.auth('A')).status_code == 503
        assert owner_env.submit(c).status_code == 503
