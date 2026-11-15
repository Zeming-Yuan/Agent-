"""One explicit image attempt with private, correlated resource evidence.

Import is inert. No built-in credential, endpoint, workload or output directory.
"""
import argparse
import asyncio
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import ssl
import time
import uuid

import httpx
from PIL import Image
from scripts.image_measurement import summarize_run, validate_run, write_curve, baseline_summary


def read_rows(directory, name):
    try:
        lines = (directory/name).read_text().splitlines()
    except FileNotFoundError:
        return []
    return [json.loads(line) for line in lines if line.strip()]


def save_private(path, data):
    with path.open('xb') as stream:
        os.chmod(path, 0o600)
        stream.write(data); stream.flush(); os.fsync(stream.fileno())
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try: os.fsync(fd)
    finally: os.close(fd)


def write_json(path, value):
    save_private(path, (json.dumps(value, indent=2, sort_keys=True, allow_nan=False)+'\n').encode())


async def observe(config, report_root, *, transport=None):
    run_id = uuid.uuid4().hex
    directory = Path(report_root)/run_id
    directory.mkdir(mode=0o700, parents=True)
    source = Path(config['telemetry_source'])
    timeout = float(config['timeout_seconds'])
    baseline_seconds = float(config['baseline_seconds'])
    tolerance = int(config['baseline_tolerance_bytes'])
    if not math.isfinite(timeout) or not math.isfinite(baseline_seconds) or timeout <= 0 or baseline_seconds <= 0 or tolerance < 0: raise ValueError('Invalid observation bounds')
    if not config['base_url'].startswith('https://'): raise ValueError('HTTPS is required')
    context = ssl.create_default_context(cafile=config['ca_file'])
    key = Path(config['api_key_file']).read_text().strip()
    options = config.get('options', {})
    profile = options.get('quality', 'standard') if config.get('kind') == 'image_edit' else 'generate'
    row = {'evidence_version': 1, 'expected_host_id': config['expected_host_id'], 'run_id': run_id, 'request_id': run_id+'-0', 'task_id': None, 'profile': profile,
           'runtime_hash': config['runtime_hash'], 'host_match': False, 'backend_executions': 0,
           'status': 'not_started', 'output_verified': False, 'memory_samples': [], 'guard_events': [],
           'total_attempts': 1, 'retries': 0, 'capture_start_utc_ns': time.time_ns()}
    capture_start = row['capture_start_utc_ns']
    await asyncio.sleep(baseline_seconds)
    row['submitted_utc_ns'] = time.time_ns()
    row['submitted_ns'] = time.monotonic_ns()
    deadline = time.monotonic()+timeout
    try:
        async with asyncio.timeout(timeout), httpx.AsyncClient(base_url=config['base_url'].rstrip('/'), verify=context,
                headers={'Authorization': 'Bearer '+key}, timeout=min(timeout, 30), trust_env=False, transport=transport) as client:
            reply = await client.post('/v1/tasks', json={'kind': config.get('kind','image_generate'), 'options': options},
                                      headers={'Idempotency-Key': row['request_id']})
            row['http_status'] = reply.status_code
            reply.raise_for_status()
            state = reply.json(); row['task_id'] = state['id']
            if not re.fullmatch(r'task-[0-9a-f]{32}', row['task_id']): raise ValueError('Invalid task identity')
            while state['status'] not in ('completed','failed','cancelled'):
                if time.monotonic() >= deadline: raise TimeoutError('Observation deadline')
                await asyncio.sleep(.05)
                reply = await client.get('/v1/tasks/'+row['task_id']); reply.raise_for_status(); state = reply.json()
            row['status'] = state['status']; row['completed_ns'] = time.monotonic_ns()
            if row['status'] == 'completed':
                fid = state['result']['file_id']
                if not re.fullmatch(r'file-[0-9a-f]{32}', fid): raise ValueError('Invalid result identity')
                chunks = []; size = 0
                async with client.stream('GET', '/v1/files/'+fid+'/content') as image:
                    image.raise_for_status()
                    async for chunk in image.aiter_bytes():
                        size += len(chunk)
                        if size > 32*1024**2: raise ValueError('Oversized PNG')
                        chunks.append(chunk)
                data = b''.join(chunks); row['downloaded_ns'] = time.monotonic_ns()
                expected = tuple(map(int, options.get('size','1024x1024').split('x')))
                with Image.open(io.BytesIO(data)) as png:
                    if png.format != 'PNG' or png.size != expected: raise ValueError('Invalid PNG size/format')
                    png.verify()
                with Image.open(io.BytesIO(data)) as png: png.load()
                save_private(directory/'output.png', data)
                row['saved_ns'] = time.monotonic_ns()
                row['output_verified'] = True
                row['output_sha256'] = hashlib.sha256(data).hexdigest()
    except httpx.HTTPStatusError as exc:
        row.update(status='rejected' if exc.response.status_code == 429 else 'http_error',
                   http_status=exc.response.status_code, failure='HTTPStatusError')
    except (httpx.HTTPError, TimeoutError, OSError, ValueError, KeyError) as exc:
        row.update(status='timeout' if isinstance(exc,(TimeoutError,httpx.TimeoutException)) else 'error',
                   failure=type(exc).__name__)
    row['work_end_utc_ns'] = time.time_ns()
    await asyncio.sleep(baseline_seconds)
    capture_end = time.time_ns(); row['capture_end_utc_ns'] = capture_end
    source_errors = []
    def captured(name):
        try:
            return [r for r in read_rows(source, name) if capture_start <= r['utc_ns'] <= capture_end]
        except (OSError, ValueError, KeyError, TypeError):
            source_errors.append(name+'_unavailable'); return []
    memory = captured('memory.jsonl')
    events = captured('lifecycle.jsonl')
    tasks = [r for r in captured('tasks.jsonl') if r.get('task_id') == row['task_id']]
    executions = [r for r in events if r.get('event') == 'execution_started' and r.get('task_id') == row['task_id']]
    lifecycle = [r for r in events if r.get('task_id') == row['task_id'] or r.get('event','').startswith('release_')]
    expected_host = config['expected_host_id']
    row.update(memory_samples=memory, backend_executions=len(executions), source_errors=source_errors,
               host_match=bool(memory and tasks and executions and expected_host and
                   all(r.get('host_id') == expected_host for r in memory+tasks+executions)),
               task_events=tasks, execution_events=executions,
               guard_events=[r for r in memory if r.get('available_bytes') is not None and r['available_bytes'] < 20*1024**3])
    row['baseline'] = baseline_summary(memory, capture_start, row['submitted_utc_ns'],
                                      row['work_end_utc_ns'], capture_end, tolerance)
    try:
        environment = next(r for r in reversed(read_rows(source, 'environment.jsonl'))
            if r.get('host_id') == expected_host and r.get('runtime_hash') == config['runtime_hash'])
    except (OSError, ValueError, StopIteration):
        environment = None; source_errors.append('environment_unavailable')
    errors = validate_run(row)
    summary = {'run_id': run_id, 'task_id': row['task_id'], 'profile': profile, 'total_attempts': 1,
               'valid_samples': 0 if errors else 1, 'status': row['status'], 'errors': errors,
               'baseline': row['baseline'], 'release_proven': None, 'baseline_status': 'not_calibrated'}
    values = [r['available_bytes'] for r in memory if r.get('available_bytes') is not None]
    summary['min_available_bytes'] = min(values) if values else None
    for field in ('cgroup_current_bytes','cgroup_peak_bytes','gpu_allocated_bytes','gpu_reserved_bytes'):
        values = [r[field] for r in memory if r.get(field) is not None]
        summary['max_'+field] = max(values) if values else None
    summary['timings'] = summarize_run(row) if not errors else None
    summary['release_operations_seconds'] = [e['duration_seconds'] for e in lifecycle
        if e.get('event') == 'release_operations_returned']
    summary['stage_durations_seconds'] = {}
    ordered = sorted(tasks, key=lambda t:t['utc_ns'])
    for current, following in zip(ordered, ordered[1:]):
        stage = current['stage']
        summary['stage_durations_seconds'][stage] = summary['stage_durations_seconds'].get(stage,0)+(following['utc_ns']-current['utc_ns'])/1e9
    write_json(directory/'environment.json', {'host_id': expected_host, 'runtime_hash': config['runtime_hash'],
        'capture_start_utc_ns': capture_start, 'capture_end_utc_ns': capture_end, 'clock': 'client monotonic_ns; backend UTC+host',
        'concurrency': 1, 'backend': environment, 'input_size': {'size': options.get('size','1024x1024'), 'reference_count': len(options.get('image_ids',[]))}})
    for name, records in [('attempts.jsonl',[row]),('memory.jsonl',memory),('lifecycle.jsonl',tasks+lifecycle)]:
        save_private(directory/name, ''.join(json.dumps(r,sort_keys=True)+'\n' for r in records).encode())
    write_json(directory/'summary.json', summary)
    write_json(directory/'profile-report.json', {'profile': profile, 'runtime_hash': config['runtime_hash'],
        'baseline_status': 'not_calibrated', 'enabled': False, 'raw_runs': [run_id], 'release_proof': None})
    save_private(directory/'memory.svg', write_curve(memory, tasks, capture_start, capture_end).encode())
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenario', choices=['observe'], required=True)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--report-dir', type=Path, required=True)
    args = parser.parse_args()
    try:
        summary = asyncio.run(observe(json.loads(args.config.read_text()), args.report_dir))
    except (OSError, ValueError, KeyError) as exc:
        print(json.dumps({'status': 'configuration_error', 'error_type': type(exc).__name__})); return 2
    print(json.dumps(summary, sort_keys=True))
    return 0 if summary['valid_samples'] == 1 else 1


if __name__ == '__main__':
    raise SystemExit(main())
