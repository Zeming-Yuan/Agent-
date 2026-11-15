"""Read-only observations of fixed ComfyUI 0.33.2 worker operations.

An operation epoch proves those calls returned, never that all old graph/CPU
weight references were released. No API or custom node is installed.
"""
from dataclasses import asdict
import uuid
import weakref
from services.image_telemetry import sample_resources, write_private_jsonl
import threading
import time


class LifecycleProbe:
    def __init__(self, queue, manager, executor_type, torch, directory, host_id, runtime_hash):
        self.queue, self.manager, self.executor_type, self.torch = queue, manager, executor_type, torch
        self.directory, self.host_id, self.runtime_hash = directory, host_id, runtime_hash
        self.lock = threading.RLock()
        self.session_id = uuid.uuid4().hex
        self.release_epoch = 0
        self.observation_errors = set()
        self.pending = None
        self.worker_thread = None
        self.executor_ref = lambda: None

    def emit(self, event, **fields):
        try:
            write_private_jsonl(self.directory, 'lifecycle.jsonl', {
                'event': event, 'utc_ns': time.time_ns(), 'observed_at': time.monotonic(),
                'session_id': self.session_id, 'host_id': self.host_id, 'runtime_hash': self.runtime_hash, **fields})
        except (OSError, ValueError):
            self.observation_errors.add('observation_write_failed')

    def read_sample(self):
        row = asdict(sample_resources())
        signals = self.snapshot()
        row['errors'] = list(row['errors'])+signals.pop('errors')
        row.update(signals, utc_ns=time.time_ns(), host_id=self.host_id,
                   runtime_hash=self.runtime_hash, session_id=self.session_id)
        return row

    def sample_once(self):
        row = self.read_sample()
        write_private_jsonl(self.directory, 'memory.jsonl', row)
        return row

    def snapshot(self):
        with self.lock:
            row = {'release_epoch': self.release_epoch, 'resident_profiles': None,
                   'release_proven': None, 'loaded_model_count': None, 'loaded_model_bytes': None,
                   'cached_output_nodes': None, 'cached_object_nodes': None,
                   'gpu_allocated_bytes': None, 'gpu_reserved_bytes': None,
                   'running_prompts': None, 'errors': sorted(self.observation_errors)}
            try:
                row['loaded_model_count'] = len(self.manager.current_loaded_models)
                running, _ = self.queue.get_current_queue_volatile()
                row['running_prompts'] = [item[1] for item in running]
                if self.torch.cuda.is_available():
                    row['gpu_allocated_bytes'] = self.torch.cuda.memory_allocated()
                    row['gpu_reserved_bytes'] = self.torch.cuda.memory_reserved()
            except Exception:
                row['errors'].append('lifecycle_signal_unavailable')
            try:
                row['loaded_model_bytes'] = sum(model.model_loaded_memory() for model in self.manager.current_loaded_models)
            except Exception:
                pass
            executor = self.executor_ref()
            if executor is not None:
                for signal, cache in [('cached_output_nodes','outputs'), ('cached_object_nodes','objects')]:
                    try:
                        row[signal] = len(getattr(executor.caches, cache).all_node_ids())
                    except Exception:
                        pass
            row['missing_signals'] = [key for key,value in row.items() if value is None]
            return row

    def install(self):
        get = self.queue.get
        def observed_get(*args, **kwargs):
            result = get(*args, **kwargs)
            if result is not None:
                item, _ = result
                self.emit('execution_started', prompt_id=item[1], task_id=item[3].get('client_id'))
            return result
        self.queue.get = observed_get
        get_flags = self.queue.get_flags
        def flags(reset=True):
            result = get_flags(reset)
            if reset and (result.get('free_memory') or result.get('unload_models')):
                with self.lock:
                    self.worker_thread = threading.get_ident()
                    self.emit('release_worker_started', release_epoch=self.release_epoch)
                    self.pending = {'unloaded': False, 'reset': not result.get('free_memory'),
                                    'started_at': time.monotonic()}
            return result
        self.queue.get_flags = flags
        def wrap(original, field):
            def observed(*args, **kwargs):
                result = original(*args, **kwargs)
                if field == 'reset': self.executor_ref = weakref.ref(args[0])
                with self.lock:
                    if self.pending is not None and threading.get_ident() == self.worker_thread:
                        self.pending[field] = True
                        if field == 'cache' and self.pending['unloaded'] and self.pending['reset']:
                            self.release_epoch += 1
                            self.emit('release_operations_returned', release_epoch=self.release_epoch,
                                      duration_seconds=time.monotonic()-self.pending['started_at'], release_proven=None)
                            self.pending = None
                return result
            return observed
        self.manager.unload_all_models = wrap(self.manager.unload_all_models, 'unloaded')
        self.executor_type.reset = wrap(self.executor_type.reset, 'reset')
        self.manager.soft_empty_cache = wrap(self.manager.soft_empty_cache, 'cache')


def install_on_worker_start(directory, *, host_id, runtime_hash):
    """Intercept only the fixed worker's thread start, before its first operation."""
    from pathlib import Path
    from services.image_telemetry import collect_samples
    original = threading.Thread.start
    stop = threading.Event()
    sampler = None
    def start(thread, *args, **kwargs):
        nonlocal sampler
        target = getattr(thread, '_target', None)
        if getattr(target, '__name__', '') == 'prompt_worker':
            threading.Thread.start = original
            namespace = target.__globals__
            if namespace['comfyui_version'].__version__ != '0.33.2':
                raise RuntimeError('Lifecycle observation supports ComfyUI 0.33.2 only')
            probe = LifecycleProbe(thread._args[0], namespace['comfy'].model_management,
                                   namespace['execution'].PromptExecutor, namespace['comfy'].model_management.torch,
                                   Path(directory), host_id, runtime_hash)
            probe.install()
            # Capture immediately before worker start, then every 100ms deadline.
            probe.sample_once()
            def sample():
                try:
                    collect_samples(probe.read_sample,
                        lambda row: write_private_jsonl(directory, 'memory.jsonl', row), wait=stop.wait)
                except (OSError, ValueError):
                    probe.emit('sampler_failed')
            sampler = threading.Thread(target=sample, daemon=True, name='image-observer')
            sampler.start()
        return original(thread, *args, **kwargs)
    threading.Thread.start = start
    def restore():
        if threading.Thread.start is start: threading.Thread.start = original
        stop.set()
        if sampler is not None: sampler.join(2)
    return restore


SUPPORTED_SOURCE_HASHES = {
    'main.py': '1ae7e09238355bcc2b415662e2baf2becdccb148ec27a46d053fabbd9a6b0e08',
    'execution.py': 'dcac4074826ac9121624ad113f6027684650579da626e24a4011617aae5f3fc0',
    'server.py': '74573b10465505b88b618da86059878e3a56418f84c7dae4073c8824aee35a6c',
    'comfy/model_management.py': 'ddf5fe6399398d9101850d42604dce20eec0a6b6cba18135ea4ad5d3da3de99e',
}


def runtime_identity(root, *, image_id, argv):
    import hashlib
    import json
    import platform
    from pathlib import Path
    root = Path(root)
    for name, expected in SUPPORTED_SOURCE_HASHES.items():
        path = root/name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('Unsupported ComfyUI source; observer requires revalidation')
    if not image_id: raise ValueError('Immutable runtime image identity required')
    from services import image_telemetry
    descriptor = {'comfy_version': '0.33.2', 'source_hashes': SUPPORTED_SOURCE_HASHES,
        'image_id': image_id, 'flags': list(argv), 'python': platform.python_version(),
        'kernel': platform.release(),
        'worker_sha256': hashlib.sha256(Path(image_telemetry.__file__).with_name('images.py').read_bytes()).hexdigest(),
        'launcher_sha256': hashlib.sha256(Path(__file__).with_name('start-comfy.py').read_bytes()).hexdigest(),
        'nvidia_driver': Path('/proc/driver/nvidia/version').read_text().splitlines()[0]
            if Path('/proc/driver/nvidia/version').is_file() else None,
        'probe_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'sampler_sha256': hashlib.sha256(Path(image_telemetry.__file__).read_bytes()).hexdigest(),
        'model_manifests': {name: hashlib.sha256((root/'models'/name).read_bytes()).hexdigest()
            if (root/'models'/name).is_file() else None for name in ('.verified.json','.editor-verified.json')}}
    return hashlib.sha256(json.dumps(descriptor, sort_keys=True).encode()).hexdigest(), descriptor
