"""Opt-in private resource evidence. Host and GPU scopes must never be summed."""
from dataclasses import dataclass
from pathlib import Path
import time


@dataclass(frozen=True)
class ResourceSample:
    available_bytes: int | None
    cgroup_headroom_bytes: int | None
    observed_at: float
    resident_profiles: frozenset[str] | None = None
    running_prompts: tuple[str, ...] | None = None
    release_epoch: int = 0
    cgroup_current_bytes: int | None = None
    cgroup_peak_bytes: int | None = None
    cgroup_limit_bytes: int | None = None
    errors: tuple[str, ...] = ()


def sample_resources(*, meminfo=Path('/proc/meminfo'), cgroup=Path('/sys/fs/cgroup'), now=time.monotonic):
    available = current = peak = limit = headroom = None
    errors = []
    try:
        available = int(next(line.split()[1] for line in meminfo.read_text().splitlines()
                             if line.startswith('MemAvailable:')))*1024
    except (OSError, ValueError, StopIteration, IndexError):
        errors.append('meminfo_unavailable')
    try:
        current = int((cgroup/'memory.current').read_text())
        peak = int((cgroup/'memory.peak').read_text())
        raw_limit = (cgroup/'memory.max').read_text().strip()
        limit = None if raw_limit == 'max' else int(raw_limit)
        headroom = None if limit is None else limit-current
        if limit is None: errors.append('cgroup_unbounded')
    except (OSError, ValueError):
        errors.append('cgroup_unavailable')
    return ResourceSample(available, headroom, now(), cgroup_current_bytes=current,
                          cgroup_peak_bytes=peak, cgroup_limit_bytes=limit, errors=tuple(errors))


def collect_samples(read, emit, *, wait, clock=time.monotonic):
    """100ms absolute deadlines (10Hz target, at least 5Hz evidence required); missed intervals remain visible, never backfilled."""
    deadline = clock()
    previous = None
    while True:
        row = read()
        observed = row['observed_at']
        gap = None if previous is None else observed-previous
        row['sampling_gap_seconds'] = round(gap, 6) if gap is not None and gap > .2 else None
        emit(row)
        previous = observed
        deadline += .1
        now = clock()
        if deadline < now: deadline += (int((now-deadline)/.1)+1)*.1
        if wait(max(0, deadline-clock())): break


# Only the operator opts in; no public HTTP observation route exists.
import hashlib
import json
import logging
import os
import stat
import threading

_OWNER_SALT = os.urandom(32)
_WRITE_LOCK = threading.Lock()
# Latch on the existing Store instance, not a separate task lifecycle table.
_OBSERVATION_ERROR_ATTRIBUTE = '_image_observation_write_failed'


def host_identity(path=None):
    try:
        return hashlib.sha256(Path(path or os.getenv('IMAGE_HOST_ID_FILE', '/etc/machine-id')).read_bytes().strip()).hexdigest()
    except OSError:
        return None


def write_private_jsonl(directory, name, row):
    directory = Path(directory)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise PermissionError('Observation directory must be private and owned by operator')
    with _WRITE_LOCK:
        fd = os.open(directory/name, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise PermissionError('Observation file must be private and owned by operator')
            data = (json.dumps(row, sort_keys=True, allow_nan=False)+'\n').encode()
            while data:
                data = data[os.write(fd, data):]
        finally:
            os.close(fd)


def record_task(store, task, **evidence):
    directory = os.getenv('IMAGE_TELEMETRY_DIR')
    if not directory: return task
    try:
        task_with_owner = store.worker_task(task['id'])
        opts = task['options']
        row = {'task_id': task['id'], 'owner_tag': hashlib.sha256(_OWNER_SALT+task_with_owner['owner'].encode()).hexdigest(),
               'profile': opts['quality'] if task['kind'] == 'image_edit' else 'generate',
               'input_size': {'size': opts['size'], 'reference_count': len(opts['image_ids']),
                              'foreground': bool(opts['foreground_file_id'])},
               'stage': task['stage'], 'stage_seq': task['stage_seq'], 'status': task['status'],
               'blocked_reason': task.get('blocked_reason'),
               'observed_at': time.monotonic(), 'utc_ns': time.time_ns(), 'host_id': host_identity(),
               'observation_errors': ['task_observation_write_failed'] if getattr(store,_OBSERVATION_ERROR_ATTRIBUTE,False) else [], **evidence}
        write_private_jsonl(directory, 'tasks.jsonl', row)
    except Exception:
        setattr(store,_OBSERVATION_ERROR_ATTRIBUTE,True)
        logging.getLogger(__name__).warning('Image task observation unavailable')
    return task


NODE_OPERATIONS = {
    '1': 'model_load', '2': 'text_encoder_load', '3': 'vae_load', '4': 'text_encode',
    '5': 'conditioning', '6': 'latent_allocate', '7': 'sampling', '8': 'vae_decode',
    '9': 'backend_save', '10': 'sampling_setup', '11': 'cfg_norm', '12': 'lora_load',
    '20': 'reference_load', '21': 'reference_load', '22': 'reference_load',
}


def task_event(store, tid, event):
    task = store.event(tid, event)
    metadata = {}
    node = event.get('node')
    if node in NODE_OPERATIONS and task['stage'] == event.get('stage'):
        operation = NODE_OPERATIONS[node]
        if task['kind'] == 'image_edit':
            if node == '4': operation = 'text_vision_encode'
            elif node == '5': operation = 'negative_text_vision_encode'
        metadata = {'node': node, 'operation': operation, 'event': 'backend_node'}
    return record_task(store, task, **metadata)


def task_transition(store, tid, **transition):
    return record_task(store, store.transition(tid, **transition))


def record_current_task(store, tid, **evidence):
    if not os.getenv('IMAGE_TELEMETRY_DIR'): return
    try:
        record_task(store, store.worker_task(tid), **evidence)
    except Exception:
        setattr(store,_OBSERVATION_ERROR_ATTRIBUTE,True)
        logging.getLogger(__name__).warning('Image task observation unavailable')


def record_cached_nodes(store, tid, prompt_id, raw):
    if not os.getenv('IMAGE_TELEMETRY_DIR') or not isinstance(raw,dict) or raw.get('type') != 'execution_cached': return
    data = raw.get('data')
    if not isinstance(data,dict) or data.get('prompt_id') != prompt_id: return
    nodes = data.get('nodes')
    if not isinstance(nodes,list) or any(not isinstance(node,str) or node not in NODE_OPERATIONS for node in nodes): return
    try:
        task = store.worker_task(tid)
        if task['status'] != 'running': return
        operation = 'text_vision_encode_cached' if task['kind'] == 'image_edit' else 'text_encode_cached'
        record_task(store,task,event='backend_cached',cached_nodes=sorted(set(nodes)),
                    operation=operation if '4' in nodes else 'cached_nodes')
    except Exception:
        setattr(store,_OBSERVATION_ERROR_ATTRIBUTE,True)
        logging.getLogger(__name__).warning('Image cache observation unavailable')
