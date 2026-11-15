"""T08 public measurement boundaries; inference is never contacted on import."""
import asyncio
import runpy
import pytest
from pathlib import Path


def test_tb08_memory_evidence_import_does_not_start_image_work(monkeypatch):
    def reject_run(coro):
        coro.close()
        raise AssertionError('import invoked benchmark main')
    def reject_write(*args, **kwargs):
        raise AssertionError('import attempted filesystem write')
    monkeypatch.setattr(Path, 'mkdir', reject_write)
    monkeypatch.setattr(asyncio, 'run', reject_run)
    runpy.run_module('scripts.benchmark_images', run_name='benchmark_import_probe')


def test_tb08_memory_evidence_resource_sample_reports_separate_scopes_and_missing(tmp_path):
    from services.image_telemetry import sample_resources
    mem = tmp_path/'meminfo'; mem.write_text('MemTotal: 1000 kB\nMemAvailable: 123 kB\n')
    cg = tmp_path/'cg'; cg.mkdir()
    for name, value in [('current','20'),('peak','30'),('max','100')]:
        (cg/('memory.'+name)).write_text(value)
    row = sample_resources(meminfo=mem, cgroup=cg, now=lambda: 4.2)
    assert row.available_bytes == 125952
    assert row.cgroup_headroom_bytes == 80
    assert (row.cgroup_current_bytes, row.cgroup_peak_bytes) == (20, 30)
    assert row.observed_at == 4.2
    assert row.resident_profiles is None and row.running_prompts is None
    (cg/'memory.current').unlink(); mem.write_text('unavailable')
    bad = sample_resources(meminfo=mem, cgroup=cg)
    assert bad.available_bytes is None and bad.cgroup_headroom_bytes is None
    assert set(bad.errors) == {'meminfo_unavailable', 'cgroup_unavailable'}


def test_tb08_memory_evidence_sampler_deadlines_and_holes():
    from services.image_telemetry import collect_samples
    clock = [0.0]; rows = []
    def wait(seconds):
        clock[0] += seconds
        if len(rows) == 2: clock[0] += .35
        return len(rows) >= 4
    collect_samples(lambda: {'observed_at': clock[0]}, rows.append,
                    wait=wait, clock=lambda: clock[0])
    assert [round(r['observed_at'], 2) for r in rows] == [0, .1, .55, .6]
    assert rows[2]['sampling_gap_seconds'] == .45
    assert rows[0]['sampling_gap_seconds'] is None


def test_tb08_memory_evidence_release_epoch_waits_for_worker_gc(tmp_path):
    from types import SimpleNamespace
    from deploy.comfy_lifecycle_probe import LifecycleProbe
    class Queue:
        def __init__(self): self.flags = {}
        def get_flags(self, reset=True):
            result = self.flags.copy()
            if reset: self.flags.clear()
            return result
        def get(self, timeout=None): return None
        def get_current_queue_volatile(self): return [], []
    class Executor:
        def reset(self): pass
    manager = SimpleNamespace(current_loaded_models=[], unload_all_models=lambda: None, soft_empty_cache=lambda: None)
    cuda = SimpleNamespace(is_available=lambda: True, memory_allocated=lambda: 11, memory_reserved=lambda: 17)
    queue = Queue()
    probe = LifecycleProbe(queue, manager, Executor, SimpleNamespace(cuda=cuda), tmp_path, 'host', 'hash')
    probe.install()
    queue.flags = {'unload_models': True, 'free_memory': True}  # accepted only
    assert probe.snapshot()['release_epoch'] == 0
    queue.get_flags()
    manager.unload_all_models()
    assert probe.snapshot()['release_epoch'] == 0
    Executor().reset()
    assert probe.snapshot()['release_epoch'] == 0
    manager.soft_empty_cache()
    row = probe.snapshot()
    assert row['release_epoch'] == 1
    assert row['resident_profiles'] is None
    assert row['loaded_model_count'] == 0 and row['gpu_allocated_bytes'] == 11
    assert row['release_proven'] is None  # graph/CPU weight ownership remains unknown
    manager.soft_empty_cache()
    assert probe.snapshot()['release_epoch'] == 1


@pytest.mark.parametrize('profile', ['generate','fast','standard','high'])
def test_tb08_memory_evidence_private_task_trace_is_correlated_and_sanitized(owner_env, monkeypatch, tmp_path, profile):
    import json
    directory = tmp_path/'observations'
    monkeypatch.setenv('IMAGE_TELEMETRY_DIR', str(directory))
    backend = owner_env.new_backend()
    with owner_env.client(backend=backend, run_worker=True, event_stream_factory=backend.event_stream) as c:
        options = {} if profile == 'generate' else {'kind':'image_edit','image_ids':[owner_env.upload(c)],'quality':profile}
        tid = owner_env.submit(c, prompt='PRIVATE-PROMPT-SENTINEL', **options).json()['id']
        owner_env.wait_task(c, tid, 'A', lambda t: t['status'] == 'completed')
    rows = [json.loads(line) for line in (directory/'tasks.jsonl').read_text().splitlines()]
    task_rows = [r for r in rows if r['task_id'] == tid]
    assert {'unloading', 'loading', 'saving', 'completed'} <= {r.get('stage') for r in task_rows}
    assert any(r.get('prompt_id') == backend.jobs[0]['prompt_id'] for r in task_rows)
    assert all(r['profile'] == profile and r['input_size']['reference_count'] == (0 if profile == 'generate' else 1) for r in task_rows)
    assert all(r['owner_tag'] != 'A' for r in task_rows)
    raw = (directory/'tasks.jsonl').read_text()
    assert 'PRIVATE-PROMPT-SENTINEL' not in raw and owner_env.keys['A'] not in raw
    assert (directory.stat().st_mode & 0o777) == 0o700
    assert ((directory/'tasks.jsonl').stat().st_mode & 0o777) == 0o600


def test_tb08_memory_evidence_probe_records_actual_execution_and_sampling(tmp_path):
    import json
    from types import SimpleNamespace
    from deploy.comfy_lifecycle_probe import LifecycleProbe
    class Queue:
        def get_flags(self, reset=True): return {}
        def get_current_queue_volatile(self): return [], []
        def get(self, timeout=None):
            return ((0, '5d2fdf20-90f7-48a7-b4b4-373aaeb96638', {'secret': 'PROMPT'},
                     {'client_id': 'task-123'}, [], {'key': 'SECRET'}), 1)
    class Executor:
        def reset(self): pass
    manager = SimpleNamespace(current_loaded_models=[], unload_all_models=lambda: None, soft_empty_cache=lambda: None)
    probe = LifecycleProbe(Queue(), manager, Executor, SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False)),
                           tmp_path/'obs', 'host', 'runtime')
    probe.install()
    probe.queue.get()
    probe.sample_once()
    rows = [json.loads(line) for line in (tmp_path/'obs'/'lifecycle.jsonl').read_text().splitlines()]
    assert rows[0]['event'] == 'execution_started' and rows[0]['task_id'] == 'task-123'
    assert rows[0]['prompt_id'] == '5d2fdf20-90f7-48a7-b4b4-373aaeb96638'
    memory = json.loads((tmp_path/'obs'/'memory.jsonl').read_text().splitlines()[0])
    assert memory['host_id'] == 'host' and memory['runtime_hash'] == 'runtime'
    assert memory['available_bytes'] > 0 and memory['resident_profiles'] is None
    assert 'PROMPT' not in str(rows) and 'SECRET' not in str(rows)


def test_tb08_memory_evidence_probe_write_fault_does_not_change_backend_return(tmp_path):
    from types import SimpleNamespace
    from deploy.comfy_lifecycle_probe import LifecycleProbe
    class Queue:
        def get_flags(self, reset=True): return {'unload_models': True, 'free_memory': True}
        def get(self, timeout=None): return ((0, 'pid', {}, {'client_id': 'task'}, [], {}), 1)
        def get_current_queue_volatile(self): return [], []
    class Executor:
        def reset(self): return 'reset'
    directory = tmp_path/'not-a-directory'; directory.write_text('block')
    manager = SimpleNamespace(current_loaded_models=[], unload_all_models=lambda: 'unload', soft_empty_cache=lambda: 'cache')
    probe = LifecycleProbe(Queue(), manager, Executor, SimpleNamespace(), directory, 'host', 'hash')
    probe.install()
    assert probe.queue.get()[1] == 1
    probe.queue.get_flags()
    assert manager.unload_all_models() == 'unload'
    assert Executor().reset() == 'reset'
    assert manager.soft_empty_cache() == 'cache'
    assert 'observation_write_failed' in probe.snapshot()['errors']


def test_tb08_memory_evidence_launcher_observes_worker_without_custom_nodes(tmp_path):
    import json
    import threading
    from types import SimpleNamespace
    from deploy.comfy_lifecycle_probe import install_on_worker_start
    class Queue:
        def get_flags(self, reset=True): return {}
        def get_current_queue_volatile(self): return [], []
        def get(self, timeout=None): return None
    class Executor:
        def reset(self): pass
    manager = SimpleNamespace(current_loaded_models=[], unload_all_models=lambda: None, soft_empty_cache=lambda: None)
    manager.torch = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False))
    namespace = {'__file__': str(tmp_path/'main.py'), 'comfyui_version': SimpleNamespace(__version__='0.33.2'),
                 'execution': SimpleNamespace(PromptExecutor=Executor),
                 'comfy': SimpleNamespace(model_management=manager)}
    exec('def prompt_worker(q, server):\n    q.get()\n', namespace)
    restore = install_on_worker_start(tmp_path/'obs', host_id='host', runtime_hash='hash')
    try:
        worker = threading.Thread(target=namespace['prompt_worker'], args=(Queue(), None))
        worker.start(); worker.join(2)
        assert not worker.is_alive()
        restore()
        rows = [json.loads(x) for x in (tmp_path/'obs'/'memory.jsonl').read_text().splitlines()]
        assert rows[0]['runtime_hash'] == 'hash' and rows[0]['host_id'] == 'host'
    finally:
        restore()


def good_run():
    return {'run_id': 'run-1', 'request_id': 'run-1-0', 'task_id': 'task-a', 'profile': 'generate',
            'runtime_hash': 'hash', 'host_match': True, 'backend_executions': 1, 'status': 'completed',
            'output_verified': True, 'submitted_ns': 0, 'completed_ns': 10_000_000,
            'downloaded_ns': 15_000_000, 'saved_ns': 20_000_000,
            'memory_samples': [{'available_bytes': 40*1024**3}], 'guard_events': []}


@pytest.mark.parametrize('field,value', [('backend_executions', 0), ('host_match', False),
    ('status', 'failed'), ('output_verified', False), ('memory_samples', []),
    ('guard_events', ['guard_stop']), ('saved_ns', -1)])
def test_tb08_memory_evidence_invalid_work_is_not_a_perf_sample(field, value):
    from scripts.image_measurement import validate_run
    row = good_run(); row[field] = value
    assert validate_run(row)


def test_tb08_memory_evidence_e2e_includes_download_and_save():
    from scripts.image_measurement import validate_run, summarize_run
    row = good_run()
    assert validate_run(row) == []
    assert summarize_run(row)['e2e_ms'] == 20
    assert summarize_run(row)['inference_wait_ms'] == 10


def test_tb08_memory_evidence_observe_cli_downloads_decodes_saves_and_keeps_raw_evidence(owner_env, monkeypatch, tmp_path):
    import io
    import json
    import subprocess
    import sys
    import threading
    import time
    import httpx
    from PIL import Image
    from services.gateway import create_app
    from services.image_telemetry import host_identity, write_private_jsonl
    from image_test_harness import https_server
    directory = tmp_path/'obs'
    monkeypatch.setenv('IMAGE_TELEMETRY_DIR', str(directory))
    host = host_identity()
    backend = owner_env.new_backend()
    png = io.BytesIO(); Image.new('RGB', (1024, 1024), 'green').save(png, format='PNG'); backend.png = png.getvalue()
    stop = threading.Event()
    def samples():
        while not stop.is_set():
            write_private_jsonl(directory, 'memory.jsonl', {
                'utc_ns': time.time_ns(), 'observed_at': time.monotonic(), 'host_id': host,
                'runtime_hash': 'fixture-runtime', 'session_id': 'fixture-session',
                'available_bytes': 40*1024**3, 'cgroup_current_bytes': 2*1024**3,
                'cgroup_peak_bytes': 3*1024**3, 'cgroup_headroom_bytes': 73*1024**3,
                'cgroup_limit_bytes': 75*1024**3, 'resident_profiles': None,
                'gpu_allocated_bytes': 1024, 'gpu_reserved_bytes': 2048, 'release_epoch': 0,
                'running_prompts': [], 'errors': [], 'sampling_gap_seconds': None})
            stop.wait(.05)
    async def external(request):
        result = await backend(request)
        if request.url.path == '/prompt':
            body = json.loads(request.content)
            write_private_jsonl(directory, 'lifecycle.jsonl', {
                'event': 'execution_started', 'task_id': body['client_id'], 'prompt_id': body['prompt_id'],
                'utc_ns': time.time_ns(), 'observed_at': time.monotonic(), 'host_id': host,
                'runtime_hash': 'fixture-runtime', 'session_id': 'fixture-session'})
        return result
    app = create_app(owner_env.root, owner_env.keys['legacy'], key_registry=owner_env.registry,
        identity_mode='staging', transport=httpx.MockTransport(external), run_worker=True,
        audio_enabled=False, images_enabled=True, event_stream_factory=backend.event_stream)
    write_private_jsonl(directory, 'environment.jsonl', {'host_id':host, 'runtime_hash':'fixture-runtime',
        'descriptor': {'comfy_version':'0.33.2','image_id':'fixture-image','model_manifests':{}}})
    sampler = threading.Thread(target=samples); sampler.start()
    try:
        with https_server(app, tmp_path) as (port, cert):
            key = tmp_path/'personal.key'; key.write_text(owner_env.keys['A']); key.chmod(0o600)
            config = tmp_path/'observe.json'
            config.write_text(json.dumps({'base_url': f'https://127.0.0.1:{port}', 'api_key_file': str(key),
                'ca_file': str(cert), 'telemetry_source': str(directory), 'expected_host_id': host,
                'runtime_hash': 'fixture-runtime', 'timeout_seconds': 5, 'baseline_seconds': .25,
                'baseline_tolerance_bytes': 1024, 'options': {'prompt': 'PRIVATE-CLI-PROMPT', 'seed': 17}}))
            cmd = [sys.executable, '-m', 'scripts.benchmark_images', '--scenario', 'observe',
                   '--config', str(config), '--report-dir', str(tmp_path/'reports')]
            outcomes = [subprocess.run(cmd, capture_output=True, text=True, timeout=15) for _ in range(2)]
            for result in outcomes: assert result.returncode == 0, result.stdout+result.stderr
    finally:
        stop.set(); sampler.join(3)
    runs = sorted((tmp_path/'reports').iterdir())
    assert len(runs) == 2 and len(backend.jobs) == 2
    for run in runs:
        summary = json.loads((run/'summary.json').read_text())
        environment = json.loads((run/'environment.json').read_text())
        assert environment['backend']['descriptor']['comfy_version'] == '0.33.2'
        assert summary['valid_samples'] == 1 and summary['total_attempts'] == 1
        assert summary['timings']['e2e_ms'] >= summary['timings']['inference_wait_ms']
        assert summary['min_available_bytes'] == 40*1024**3
        assert summary['baseline']['status'] == 'stable'
        assert (run/'memory.svg').read_text().startswith('<svg')
        with Image.open(run/'output.png') as image: assert image.size == (1024, 1024)
        for name in ('environment.json','attempts.jsonl','memory.jsonl','lifecycle.jsonl','profile-report.json'):
            raw = (run/name).read_text()
            assert owner_env.keys['A'] not in raw and 'PRIVATE-CLI-PROMPT' not in raw
        assert run.stat().st_mode & 0o777 == 0o700


def measured_run():
    row = good_run()
    row.update(evidence_version=1, expected_host_id='host', capture_start_utc_ns=0,
        submitted_utc_ns=200_000_000, work_end_utc_ns=800_000_000, capture_end_utc_ns=1_000_000_000,
        source_errors=[], task_events=[{'task_id':'task-a','stage':'loading','stage_seq':2,'host_id':'host','utc_ns':250_000_000,'event':'submit_started','prompt_id':'pid'},
                                     {'task_id':'task-a','stage':'completed','stage_seq':4,'host_id':'host','utc_ns':800_000_000}],
        execution_events=[{'event':'execution_started','task_id':'task-a','prompt_id':'pid','host_id':'host',
                           'runtime_hash':'hash','session_id':'s','utc_ns':300_000_000}],
        memory_samples=[{'utc_ns': i*100_000_000, 'observed_at': i*.1, 'available_bytes':40*1024**3,
            'cgroup_current_bytes':2*1024**3,'cgroup_peak_bytes':3*1024**3,'cgroup_headroom_bytes':73*1024**3,
            'host_id':'host','runtime_hash':'hash','session_id':'s','errors':[], 'sampling_gap_seconds':None}
            for i in range(11)])
    return row


@pytest.mark.parametrize('fault', ['read_error','runtime','host','gap','memory_missing','cgroup_missing',
    'duplicate_execution','canonical_prompt','prompt_mismatch','session','missing_terminal','nonfinite','partial_capture'])
def test_tb08_memory_evidence_bad_observations_cannot_be_valid(fault):
    from scripts.image_measurement import validate_run
    row = measured_run()
    if fault == 'read_error': row['source_errors'] = ['memory.jsonl_unavailable']
    if fault == 'runtime': row['memory_samples'][0]['runtime_hash'] = 'different'
    if fault == 'host': row['memory_samples'][0]['host_id'] = 'other'
    if fault == 'gap': row['memory_samples'].pop(4); row['memory_samples'].pop(4)
    if fault == 'memory_missing': row['memory_samples'][0]['available_bytes'] = None
    if fault == 'cgroup_missing': row['memory_samples'][0]['cgroup_headroom_bytes'] = None
    if fault == 'duplicate_execution': row['execution_events'] *= 2
    if fault == 'canonical_prompt': row['execution_events'][0]['prompt_id'] = 'other-prompt'
    if fault == 'prompt_mismatch': row['execution_events'][0]['task_id'] = 'other-task'
    if fault == 'session': row['memory_samples'][0]['session_id'] = 'old-process'
    if fault == 'missing_terminal': row['task_events'] = []
    if fault == 'nonfinite': row['memory_samples'][0]['observed_at'] = float('nan')
    if fault == 'partial_capture': row['memory_samples'] = row['memory_samples'][5:]
    assert validate_run(row)


def test_tb08_memory_evidence_unknown_comfy_source_is_not_observed(tmp_path):
    from deploy.comfy_lifecycle_probe import runtime_identity
    (tmp_path/'main.py').write_text('unknown source')
    with pytest.raises(ValueError, match='Unsupported ComfyUI source'):
        runtime_identity(tmp_path, image_id='immutable-test-image', argv=['--disable-all-custom-nodes'])


@pytest.mark.parametrize('outcome,expected', [('429','rejected'), ('failed','failed'),
    ('timeout','timeout'), ('bad_png','error'), ('download_500','http_error'), ('save_fault','error')])
def test_tb08_memory_evidence_cli_counts_failed_attempts_without_leaking(tmp_path, monkeypatch, outcome, expected):
    import httpx
    import io
    import json
    from PIL import Image
    from scripts.benchmark_images import observe
    key = tmp_path/'key'; key.write_text('PRIVATE-KEY-SENTINEL')
    png = io.BytesIO(); Image.new('RGB',(1024,1024)).save(png,format='PNG')
    requests = []
    async def server(request):
        requests.append(request)
        if outcome == 'timeout': raise httpx.ReadTimeout('PRIVATE-KEY-SENTINEL', request=request)
        if request.url.path == '/v1/tasks':
            if outcome == '429': return httpx.Response(429, json={'detail':'SECRET'})
            return httpx.Response(200, json={'id':'task-'+'a'*32,'status':'failed' if outcome == 'failed' else 'completed',
                'result':{'file_id':'file-'+'b'*32}})
        if request.url.path.endswith('/content'):
            return httpx.Response(500 if outcome == 'download_500' else 200,
                content=b'not a PNG' if outcome == 'bad_png' else png.getvalue())
        return httpx.Response(404)
    if outcome == 'save_fault':
        import os
        fsync = os.fsync
        def fail_output(fd):
            if Path('/proc/self/fd/'+str(fd)).resolve().name == 'output.png': raise OSError('PRIVATE-KEY-SENTINEL')
            return fsync(fd)
        monkeypatch.setattr(os,'fsync',fail_output)
    config = {'base_url':'https://fixture.invalid','api_key_file':str(key),
        'ca_file':str(Path(__file__).resolve().parents[1]/'certificates/agent-root-ca.crt'),
        'telemetry_source':str(tmp_path/'obs'),'expected_host_id':'host','runtime_hash':'runtime',
        'timeout_seconds':1,'baseline_seconds':.001,'baseline_tolerance_bytes':1,
        'options':{'prompt':'PRIVATE-PROMPT-SENTINEL'}}
    summary = asyncio.run(observe(config,tmp_path/'reports',transport=httpx.MockTransport(server)))
    assert summary['total_attempts'] == 1 and summary['valid_samples'] == 0 and summary['status'] == expected
    assert len([r for r in requests if r.method == 'POST']) == 1
    for path in (tmp_path/'reports').rglob('*'):
        if path.is_file() and path.suffix != '.png':
            assert 'PRIVATE-KEY-SENTINEL' not in path.read_text()
            assert 'PRIVATE-PROMPT-SENTINEL' not in path.read_text()


def test_tb08_memory_evidence_probe_exposes_cache_counts_without_retaining_executor(tmp_path):
    import gc
    import weakref
    from types import SimpleNamespace
    from deploy.comfy_lifecycle_probe import LifecycleProbe
    class Queue:
        def get_flags(self, reset=True): return {}
        def get(self, timeout=None): return None
        def get_current_queue_volatile(self): return [], []
    class Executor:
        def reset(self):
            self.caches = SimpleNamespace(outputs=SimpleNamespace(all_node_ids=lambda: {'7','9'}),
                                          objects=SimpleNamespace(all_node_ids=lambda: {'1'}))
    manager = SimpleNamespace(current_loaded_models=[SimpleNamespace(model_loaded_memory=lambda: 1234)],
                              unload_all_models=lambda: None, soft_empty_cache=lambda: None)
    probe = LifecycleProbe(Queue(), manager, Executor, SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False)),
                           tmp_path/'obs','host','hash')
    probe.install(); executor = Executor(); executor.reset()
    row = probe.snapshot()
    assert row['loaded_model_bytes'] == 1234 and row['cached_output_nodes'] == 2 and row['cached_object_nodes'] == 1
    ref = weakref.ref(executor); del executor; gc.collect()
    assert ref() is None
    assert probe.snapshot()['cached_output_nodes'] is None


def test_tb08_memory_evidence_timeout_covers_download_not_just_polling(tmp_path):
    import httpx
    import io
    from PIL import Image
    from scripts.benchmark_images import observe
    class SlowPNG(httpx.AsyncByteStream):
        async def __aiter__(self):
            png = io.BytesIO(); Image.new('RGB',(1024,1024)).save(png,format='PNG')
            await asyncio.sleep(.08)
            yield png.getvalue()
    async def server(request):
        if request.method == 'POST':
            return httpx.Response(200,json={'id':'task-'+'a'*32,'status':'completed','result':{'file_id':'file-'+'b'*32}})
        return httpx.Response(200,stream=SlowPNG())
    key = tmp_path/'key'; key.write_text('fixture')
    config = {'base_url':'https://fixture.invalid','api_key_file':str(key),
        'ca_file':str(Path(__file__).resolve().parents[1]/'certificates/agent-root-ca.crt'),
        'telemetry_source':str(tmp_path/'obs'),'expected_host_id':'host','runtime_hash':'hash',
        'timeout_seconds':.02,'baseline_seconds':.001,'baseline_tolerance_bytes':1, 'options':{'prompt':'fixture'}}
    summary = asyncio.run(observe(config,tmp_path/'reports',transport=httpx.MockTransport(server)))
    assert summary['status'] == 'timeout' and summary['total_attempts'] == 1


def test_tb08_memory_evidence_cancel_trace_records_cleanup_boundary(owner_env, monkeypatch, tmp_path):
    import json
    directory = tmp_path/'obs'; monkeypatch.setenv('IMAGE_TELEMETRY_DIR',str(directory))
    backend = owner_env.new_backend(hold=True, hold_stop=True)
    with owner_env.client(backend=backend, run_worker=True) as c:
        tid = owner_env.submit(c).json()['id']; assert backend.started.wait(2)
        try:
            c.post('/v1/tasks/'+tid+'/cancel',headers=owner_env.auth('A'))
        finally:
            backend.release_stop.set(); backend.finish.set()
        owner_env.wait_task(c,tid,'A',lambda t:t['status']=='cancelled')
    rows = [json.loads(x) for x in (directory/'tasks.jsonl').read_text().splitlines()]
    assert {'cancelling','cancelled'} <= {r['stage'] for r in rows}
