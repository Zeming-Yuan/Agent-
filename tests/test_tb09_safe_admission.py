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
        audio_enabled=False, images_enabled=True, event_stream_factory=getattr(backend,'event_stream',None), **config))


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


@pytest.mark.parametrize('fault',['expired','runtime','reserve','missing_envelope','size','references',
    'prompt','foreground','nan_setting'])
def test_tb09_unsigned_or_out_of_envelope_work_is_never_accepted(owner_env, fault):
    import time
    config = resources()
    if fault in ('expired','runtime','reserve'):
        field = {'expired':{'valid_until':time.monotonic()-1},'runtime':{'runtime_hash':'other'},
                 'reserve':{'reserve_bytes':19*1024**3}}[fault]
        config['memory_budgets']['generate'] = dataclasses.replace(config['memory_budgets']['generate'], **field)
    if fault == 'missing_envelope':config['resource_settings']['input_envelopes'] = {}
    if fault == 'size':config['resource_settings']['input_envelopes']['generate']['sizes'] = ['1280x768']
    if fault == 'references':config['resource_settings']['input_envelopes']['standard']['max_references'] = 0
    if fault == 'prompt':config['resource_settings']['input_envelopes']['generate']['max_prompt_chars'] = 2
    if fault == 'foreground':config['resource_settings']['input_envelopes']['generate']['foreground'] = False
    if fault == 'nan_setting':config['resource_settings']['max_age'] = float('nan')
    backend = owner_env.new_backend()
    with client_with_resources(owner_env, backend, **config) as c:
        options = {}
        if fault == 'references':options = {'kind':'image_edit','image_ids':[owner_env.upload(c)]}
        if fault == 'foreground':options = {'foreground_file_id':owner_env.upload(c)}
        response = owner_env.submit(c, **options)
        assert response.status_code == 503, response.text
        assert c.get('/v1/tasks',headers=owner_env.auth('A')).json()['data'] == []
        assert backend.jobs == []


def test_tb09_below_reserve_enters_wait_and_recovers_same_task(owner_env, monkeypatch):
    from pathlib import Path
    import threading
    recovered = threading.Event()
    read_text = Path.read_text
    def read(path, *args, **kwargs):
        if str(path) == '/proc/meminfo':
            return 'MemAvailable: '+str((60 if recovered.is_set() else 19)*1024**2)+' kB\n'
        return read_text(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'read_text', read)
    config = resources()
    original = config['resource_sampler']
    config['resource_sampler'] = lambda tid: dataclasses.replace(original(tid),
        available_bytes=(60 if recovered.is_set() else 19)*1024**3)
    backend = owner_env.new_backend()
    with client_with_resources(owner_env, backend, **config) as c:
        tid = owner_env.submit(c).json()['id']
        waiting = owner_env.wait_task(c,tid,'A',lambda t:t.get('blocked_reason')=='system_memory' or t['status']=='failed')
        assert waiting['status']=='queued', waiting
        assert backend.jobs == []
        recovered.set()
        owner_env.wait_task(c,tid,'A',lambda t:t['status']=='completed')


def test_tb09_reference_pixels_must_fit_approved_envelope_before_backend_work(owner_env):
    config = resources()
    config['resource_settings']['input_envelopes']['standard']['max_reference_pixels'] = 16
    backend = owner_env.new_backend()
    with client_with_resources(owner_env,backend,**config) as c:
        fid = owner_env.upload(c)
        response = owner_env.submit(c,kind='image_edit',image_ids=[fid])
        assert response.status_code == 202
        done = owner_env.wait_task(c,response.json()['id'],'A',lambda t:t['status'] in ('failed','completed'))
        assert done['status']=='failed' and 'envelope' in done['error']
        assert backend.jobs == []


def approved_config(tmp_path, monkeypatch):
    """Synthetic operator approval, never a usable production budget."""
    import json, hashlib, time
    from services.image_telemetry import host_identity
    config_dir = tmp_path/'approved'; config_dir.mkdir(mode=0o700)
    telemetry = tmp_path/'observations'; telemetry.mkdir(mode=0o700)
    monkeypatch.setenv('IMAGE_TELEMETRY_DIR',str(telemetry))
    cfg = resources()
    params = {'settings':cfg['resource_settings'], 'profiles':{name:{
        'budget': {'peak_increment_bytes':budget.peak_increment_bytes,'margin_bytes':budget.margin_bytes,
                   'reserve_bytes':budget.reserve_bytes},
        'input_envelope':cfg['resource_settings']['input_envelopes'][name]}
        for name,budget in cfg['memory_budgets'].items()}}
    params['settings'] = {k:v for k,v in params['settings'].items() if k != 'input_envelopes'}
    raw_rows = [dict(observed_at=t,available_bytes=60*1024**3,cgroup_headroom_bytes=50*1024**3,
        host_id=host_identity(),runtime_hash='runtime',session_id='session',errors=[])
        for t in (10.,10.1,10.2,10.3)]
    raw = config_dir/'baseline.jsonl';raw.write_text(''.join(json.dumps(row)+'\n' for row in raw_rows));raw.chmod(0o600)
    params_hash = hashlib.sha256(json.dumps(params,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    config = {'version':1,'mode':'controlled_calibration','approved_by':'test-operator',
        'host_id':host_identity(),'runtime_hash':'runtime','expires_at_utc':time.time()+3600,
        'guard_active':True,'backend_idle':True,'parameters_sha256':params_hash,
        'baseline':{'path':'baseline.jsonl','sha256':hashlib.sha256(raw.read_bytes()).hexdigest()},**params}
    path = config_dir/'admission.json';path.write_text(json.dumps(config));path.chmod(0o600)
    return path, config, telemetry


@pytest.mark.parametrize('fault',['valid','unsigned','hash','expired','runtime','guard','baseline_hash',
    'no_baseline','not_calibrated','permissions','nan','changed_parameters'])
def test_tb09_only_operator_approved_evidence_bound_calibration_config_loads(tmp_path, monkeypatch, fault):
    import json,hashlib,time
    from services.image_resource_config import load_resources
    path,cfg,_ = approved_config(tmp_path,monkeypatch)
    if fault=='expired':cfg['expires_at_utc']=time.time()-1
    if fault=='runtime':cfg['runtime_hash']='other'
    if fault=='guard':cfg['guard_active']=False
    if fault=='baseline_hash':cfg['baseline']['sha256']='0'*64
    if fault=='no_baseline':cfg.pop('baseline')
    if fault=='not_calibrated':cfg['mode']='not_calibrated'
    if fault=='nan':cfg['settings']['stable_window']=float('nan')
    if fault=='changed_parameters':cfg['profiles']['generate']['budget']['peak_increment_bytes']=1
    path.write_text(json.dumps(cfg))
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    if fault=='unsigned':digest=None
    if fault=='hash':digest='0'*64
    if fault=='permissions':path.chmod(0o644)
    loaded=load_resources(path,expected_sha256=digest,runtime_hash='runtime')
    assert bool(loaded) is (fault=='valid')
    if loaded:
        assert loaded['memory_budgets']['generate'].reserve_bytes==20*1024**3
        # No current sample and no old-profile proof are invented from approval.
        assert loaded['resource_sampler']('task-one') is None


@pytest.mark.parametrize('fault',['valid_unknown','missing_errors','partial','host','runtime','world_readable','symlink'])
def test_tb09_private_backend_samples_preserve_unknown_signals(tmp_path, monkeypatch, fault):
    import json,time
    from services.image_resource_config import read_resource_sample
    from services.image_telemetry import host_identity
    directory=tmp_path/'samples';directory.mkdir(mode=0o700)
    row={'available_bytes':60*1024**3,'cgroup_headroom_bytes':50*1024**3,'observed_at':time.monotonic(),
        'resident_profiles':None,'running_prompts':[],'release_epoch':1,'release_proven':None,
        'release_task_id':None,'host_id':host_identity(),'runtime_hash':'runtime','session_id':'session','errors':[]}
    if fault=='host':row['host_id']='other'
    if fault=='runtime':row['runtime_hash']='other'
    if fault=='missing_errors':row.pop('errors')
    path=directory/'memory.jsonl';path.write_text(json.dumps(row)+('' if fault=='partial' else '\n'));path.chmod(0o600)
    if fault=='world_readable':path.chmod(0o644)
    if fault=='symlink':
        target=directory/'old';path.rename(target);path.symlink_to(target)
    sample=read_resource_sample(directory,'runtime')
    if fault=='valid_unknown':
        assert sample is not None and sample.resident_profiles is None and sample.release_proven is None
    else:assert sample is None


def test_tb09_factory_loads_only_pinned_config_and_unknown_release_still_waits(owner_env,tmp_path,monkeypatch):
    import json,hashlib,time
    from services.gateway import create_app
    from services.image_telemetry import host_identity
    from fastapi.testclient import TestClient
    import httpx
    path,_,telemetry=approved_config(tmp_path,monkeypatch)
    monkeypatch.setenv('IMAGE_RESOURCE_CONFIG',str(path))
    monkeypatch.setenv('IMAGE_RESOURCE_CONFIG_SHA256',hashlib.sha256(path.read_bytes()).hexdigest())
    monkeypatch.setenv('IMAGE_RUNTIME_HASH','runtime')
    row={'available_bytes':60*1024**3,'cgroup_headroom_bytes':50*1024**3,'observed_at':time.monotonic(),
        'resident_profiles':None,'running_prompts':[],'release_epoch':2,'release_proven':None,
        'host_id':host_identity(),'runtime_hash':'runtime','session_id':'session','errors':[]}
    memory=telemetry/'memory.jsonl';memory.write_text(json.dumps(row)+'\n');memory.chmod(0o600)
    backend=owner_env.new_backend()
    app=create_app(owner_env.root,owner_env.keys['legacy'],key_registry=owner_env.registry,
        identity_mode='staging',transport=httpx.MockTransport(backend),images_enabled=True,
        audio_enabled=False,event_stream_factory=backend.event_stream)
    with TestClient(app) as c:
        response=owner_env.submit(c)
        assert response.status_code==202,response.text
        tid=response.json()['id']
        task=owner_env.wait_task(c,tid,'A',lambda t:t['stage']=='waiting_resources')
        assert task['status']=='queued' and backend.jobs==[]
        assert c.post('/v1/tasks/'+tid+'/cancel',headers=owner_env.auth('A')).json()['status']=='cancelled'
        assert backend.jobs==[]


def test_tb09_startup_cleanup_failure_stops_admission_without_retry_loop(owner_env):
    import httpx,time
    backend=owner_env.new_backend()
    attempts=[]
    async def external(request):
        if request.url.path=='/interrupt':
            attempts.append(True)
            return httpx.Response(503,json={'error':'unconfirmed'})
        return await backend(request)
    with client_with_resources(owner_env,external,**resources()) as c:
        deadline=time.monotonic()+.4
        while time.monotonic()<deadline:
            health=c.get('/health',headers=owner_env.auth('A'))
            if health.status_code==503:break
            time.sleep(.01)
        assert health.status_code==503,health.text
        assert owner_env.submit(c).status_code==503
        assert len(attempts)==1 and backend.jobs==[]


def test_tb09_cached_sampler_reads_do_not_invent_or_destroy_window(owner_env):
    import time
    config=resources(wait_timeout=.5)
    initial=True
    def sample(tid):
        nonlocal initial
        row=dataclasses.replace(release_sample(int(time.monotonic()*10)/10),release_task_id=tid,
                                release_epoch=1 if initial else 2)
        initial=False
        return row
    config['resource_sampler']=sample
    backend=owner_env.new_backend()
    with client_with_resources(owner_env,backend,**config) as c:
        tid=owner_env.submit(c).json()['id']
        done=owner_env.wait_task(c,tid,'A',lambda t:t['status'] in ('failed','completed'))
        assert done['status']=='completed',done
        assert len(backend.jobs)==1


def test_tb09_brief_headroom_spike_is_not_a_stable_safe_start(owner_env):
    config=resources(wait_timeout=.15)
    original=config['resource_sampler'];reads=0
    def sample(tid):
        nonlocal reads
        reads+=1
        return dataclasses.replace(original(tid),available_bytes=(60 if reads%8 in (6,7) else 25)*1024**3)
    config['resource_sampler']=sample
    backend=owner_env.new_backend()
    with client_with_resources(owner_env,backend,**config) as c:
        tid=owner_env.submit(c).json()['id']
        done=owner_env.wait_task(c,tid,'A',lambda t:t['status'] in ('failed','completed'))
        assert done['status']=='failed' and 'system_memory' in done['error'],done
        assert backend.jobs==[]


@pytest.mark.parametrize('fault,reason,degraded',[
    ('ack_only','release_unconfirmed',True),('unknown_proof','release_unconfirmed',True),
    ('old_running','release_unconfirmed',True),('unknown_residents','release_unconfirmed',True),
    ('container','resource_wait_expired',False),('stale','release_unconfirmed',True),
    ('wrong_session','release_unconfirmed',True),('free_error','release_unconfirmed',True)])
def test_tb09_faults_do_not_submit_inference_and_release_uncertainty_degrades(owner_env,fault,reason,degraded):
    import time,httpx
    config=resources(wait_timeout=.12)
    original=config['resource_sampler'];reads=0
    def sample(tid):
        nonlocal reads
        reads+=1;row=original(tid)
        change={
            'ack_only':{'release_epoch':2},'unknown_proof':{'release_proven':None},
            'old_running':{'running_prompts':('orphan',)},'unknown_residents':{'resident_profiles':None},
            'container':{'cgroup_headroom_bytes':1},'stale':{'observed_at':time.monotonic()-10},
            'wrong_session':{'session_id':'session' if reads==1 else 'restarted'},
        }.get(fault,{})
        return dataclasses.replace(row,**change)
    config['resource_sampler']=sample
    backend=owner_env.new_backend()
    async def external(request):
        if fault=='free_error' and request.url.path=='/free':return httpx.Response(503,json={})
        return await backend(request)
    with client_with_resources(owner_env,external,**config) as c:
        tid=owner_env.submit(c,request_key='fault').json()['id']
        done=owner_env.wait_task(c,tid,'A',lambda t:t['status']=='failed')
        assert done['blocked_reason']==reason,done
        assert backend.jobs==[]
        assert owner_env.submit(c,request_key='fault').json()['id']==tid
        assert c.get('/v1/tasks/'+tid,headers=owner_env.auth('B')).status_code==404
        assert c.get('/health',headers=owner_env.auth('A')).status_code==(503 if degraded else 200)
        if degraded:assert owner_env.submit(c).status_code==503


def test_tb09_waiting_cancel_permissions_and_idempotency_preserve_original_task(owner_env):
    backend=owner_env.new_backend()
    with client_with_resources(owner_env,backend,**resources(available=25*1024**3)) as c:
        tid=owner_env.submit(c,request_key='same-intent').json()['id']
        owner_env.wait_task(c,tid,'A',lambda t:t.get('blocked_reason')=='system_memory')
        assert owner_env.submit(c,request_key='same-intent').json()['id']==tid
        assert owner_env.submit(c,request_key='same-intent',prompt='changed').status_code==409
        assert c.post('/v1/tasks/'+tid+'/cancel',headers=owner_env.auth('B')).status_code==404
        assert c.post('/v1/tasks/'+tid+'/cancel',headers=owner_env.auth('A')).json()['status']=='cancelled'
        assert c.post('/v1/tasks/'+tid+'/cancel',headers=owner_env.auth('A')).json()['status']=='cancelled'
        assert backend.jobs==[]


def test_tb09_profile_graph_boundaries_remain_isolated_after_cancel(owner_env):
    backend=owner_env.new_backend(hold=True)
    with client_with_resources(owner_env,backend,**resources()) as c:
        fid=owner_env.upload(c)
        fast=owner_env.submit(c,kind='image_edit',image_ids=[fid],quality='fast').json()['id']
        assert backend.started.wait(2)
        c.post('/v1/tasks/'+fast+'/cancel',headers=owner_env.auth('A'))
        owner_env.wait_task(c,fast,'A',lambda t:t['status']=='cancelled')
        assert not backend.running
        backend.finish.set()
        for kind,quality in [('image_edit','standard'),('image_generate','standard'),('image_edit','high')]:
            tid=owner_env.submit(c,kind=kind,quality=quality,**({'image_ids':[fid]} if kind=='image_edit' else {})).json()['id']
            owner_env.wait_task(c,tid,'A',lambda t:t['status']=='completed')
        graphs=[job['prompt'] for job in backend.jobs]
        assert [g['7']['inputs']['steps'] for g in graphs]==[4,20,8,40]
        assert [('12' in g) for g in graphs]==[True,False,False,False]
        assert not backend.running


def test_tb09_config_cli_uses_approval_pin_and_reports_nonzero_without_it(tmp_path,monkeypatch):
    import os,subprocess,sys,hashlib
    path,_,_=approved_config(tmp_path,monkeypatch)
    env={**os.environ,'IMAGE_RUNTIME_HASH':'runtime','IMAGE_RESOURCE_CONFIG_SHA256':hashlib.sha256(path.read_bytes()).hexdigest()}
    command=[sys.executable,'-m','services.image_resource_config','--check-config',str(path)]
    valid=subprocess.run(command,env=env,capture_output=True,text=True,timeout=5)
    assert valid.returncode==0,valid.stdout+valid.stderr
    env.pop('IMAGE_RESOURCE_CONFIG_SHA256')
    invalid=subprocess.run(command,env=env,capture_output=True,text=True,timeout=5)
    assert invalid.returncode==1


def test_tb09_shutdown_preserves_queued_wait_for_safe_restart(owner_env):
    backend=owner_env.new_backend()
    with client_with_resources(owner_env,backend,**resources(available=25*1024**3)) as c:
        tid=owner_env.submit(c,request_key='resume-after-shutdown').json()['id']
        owner_env.wait_task(c,tid,'A',lambda t:t.get('blocked_reason')=='system_memory')
    assert backend.jobs==[]
    with client_with_resources(owner_env,backend,**resources()) as c:
        done=owner_env.wait_task(c,tid,'A',lambda t:t['status'] in ('failed','completed'))
        assert done['status']=='completed',done
        assert owner_env.submit(c,request_key='resume-after-shutdown').json()['id']==tid
        assert len(backend.jobs)==1


def test_tb09_operator_approval_cannot_make_unidentified_baseline_valid(tmp_path,monkeypatch):
    import json,hashlib
    from services.image_resource_config import load_resources
    path,cfg,_=approved_config(tmp_path,monkeypatch)
    raw=path.parent/'baseline.jsonl'
    rows=[json.loads(line) for line in raw.read_text().splitlines()]
    for row in rows:row['session_id']={'unknown':'session'}
    raw.write_text(''.join(json.dumps(row)+'\n' for row in rows))
    cfg['baseline']['sha256']=hashlib.sha256(raw.read_bytes()).hexdigest()
    path.write_text(json.dumps(cfg))
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    assert load_resources(path,expected_sha256=digest,runtime_hash='runtime')=={}
