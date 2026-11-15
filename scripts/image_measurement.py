"""Validate evidence before reporting latency; missing observations are not zeros."""

def validate_run(record: dict) -> list[str]:
    errors = []
    for name in ('run_id', 'request_id', 'task_id', 'profile', 'runtime_hash'):
        if not record.get(name): errors.append(name)
    for name in ('host_match', 'output_verified'):
        if record.get(name) is not True: errors.append(name)
    if record.get('backend_executions') != 1: errors.append('backend_executions')
    if record.get('status') != 'completed': errors.append('status')
    if not record.get('memory_samples'): errors.append('memory_samples')
    if record.get('guard_events'): errors.append('guard_events')
    times = [record.get(k) for k in ('submitted_ns', 'completed_ns', 'downloaded_ns', 'saved_ns')]
    if not all(type(v) is int for v in times) or times != sorted(times): errors.append('timeline')
    if record.get('evidence_version') == 1:
        errors.extend(validate_observations(record))
    return errors


def summarize_run(record: dict) -> dict:
    errors = validate_run(record)
    if errors: raise ValueError(','.join(errors))
    return {'e2e_ms': (record['saved_ns']-record['submitted_ns'])/1e6,
            'inference_wait_ms': (record['completed_ns']-record['submitted_ns'])/1e6,
            'download_ms': (record['downloaded_ns']-record['completed_ns'])/1e6,
            'save_ms': (record['saved_ns']-record['downloaded_ns'])/1e6}


def baseline_summary(samples, start, submitted, finished, end, tolerance):
    def window(low, high):
        values = [r['available_bytes'] for r in samples if low <= r['utc_ns'] <= high and r.get('available_bytes') is not None]
        return {'samples': len(values), 'min_available_bytes': min(values) if values else None,
                'max_available_bytes': max(values) if values else None,
                'stable': len(values) >= 2 and max(values)-min(values) <= tolerance}
    before, after = window(start, submitted), window(finished, end)
    return {'status': 'stable' if before['stable'] and after['stable'] else 'inconclusive',
            'before': before, 'after': after, 'tolerance_bytes': tolerance}


def write_curve(samples, tasks, start, end):
    """Standalone SVG with independent system/cgroup/GPU panels, no summed total."""
    from html import escape
    fields = [('available_bytes','System MemAvailable'), ('cgroup_current_bytes','Container current'),
              ('cgroup_peak_bytes','Container lifetime peak'), ('gpu_allocated_bytes','GPU allocated'),
              ('gpu_reserved_bytes','GPU reserved')]
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="1100" height="720" viewBox="0 0 1100 720">',
             '<rect width="1100" height="720" fill="white"/>']
    for index, (field,label) in enumerate(fields):
        top = 35+index*135
        points = [(r['utc_ns'],r[field]/1024**3) for r in samples if r.get(field) is not None]
        maximum = max((v for _,v in points), default=1) or 1
        parts.append(f'<text x="20" y="{top}" font-size="16">{label} (GiB), max {maximum:.3f}</text>')
        coords = ' '.join(f'{100+950*(t-start)/max(1,end-start):.2f},{top+100-85*v/maximum:.2f}' for t,v in points)
        parts.append(f'<polyline fill="none" stroke="#2463a5" stroke-width="2" points="{coords}"/>')
        if not points: parts.append(f'<text x="100" y="{top+55}">signal unavailable</text>')
        for event in tasks:
            x = 100+950*(event['utc_ns']-start)/max(1,end-start)
            parts.append(f'<line x1="{x:.2f}" x2="{x:.2f}" y1="{top+10}" y2="{top+100}" stroke="#bbb"/>')
            if index == 0: parts.append(f'<text x="{x:.2f}" y="{top+115}" font-size="9">{escape(event.get("operation", event["stage"]))}</text>')
    return ''.join(parts)+ '</svg>\n'


def validate_observations(record):
    import math
    errors = []
    if record.get('source_errors'): errors.append('source_errors')
    samples = record['memory_samples']
    executions = record.get('execution_events', [])
    tasks = record.get('task_events', [])
    if len(executions) != 1 or any(e.get('task_id') != record['task_id'] for e in executions):
        errors.append('execution_identity')
    submissions = [t for t in tasks if t.get('event') == 'submit_started']
    if len(submissions) != 1 or len(executions) != 1 or submissions[0].get('prompt_id') != executions[0].get('prompt_id'):
        errors.append('canonical_prompt')
    if not any(t.get('status', 'completed') == 'completed' and t.get('stage') == 'completed' for t in tasks):
        errors.append('terminal_event')
    operations = {t.get('operation') for t in tasks}
    encoding = 'text_encode' if record['profile'] == 'generate' else 'text_vision_encode'
    encoding_known = encoding in operations or any('4' in t.get('cached_nodes', []) for t in tasks)
    if not encoding_known or not {'sampling','vae_decode','backend_save','cleanup'} <= operations:
        errors.append('operation_coverage')
    if any(t.get('blocked_reason') == 'events_unavailable' for t in tasks): errors.append('backend_events_unavailable')
    if any(t.get('observation_errors') for t in tasks): errors.append('task_observation_errors')
    seqs = [t.get('stage_seq') for t in tasks]
    if not seqs or any(type(seq) is not int for seq in seqs):
        errors.append('task_stage_gap')
    else:
        unique = sorted(set(seqs))
        if seqs != sorted(seqs) or unique[0] != 1 or any(b != a+1 for a,b in zip(unique,unique[1:])):
            errors.append('task_stage_gap')
    expected_host = record.get('expected_host_id')
    if not expected_host or any(r.get('host_id') != expected_host for r in samples+executions+tasks):
        errors.append('host_identity')
    if any(r.get('runtime_hash') != record['runtime_hash'] for r in samples+executions):
        errors.append('runtime_identity')
    sessions = {r.get('session_id') for r in samples+executions}
    if len(sessions) != 1 or None in sessions: errors.append('runtime_session')
    for sample in samples:
        if sample.get('errors') or sample.get('sampling_gap_seconds'): errors.append('sample_signal'); break
        if any(type(sample.get(k)) is not int or sample[k] < 0 for k in (
                'available_bytes','cgroup_current_bytes','cgroup_peak_bytes','cgroup_headroom_bytes')):
            errors.append('sample_signal'); break
        if not isinstance(sample.get('observed_at'), (int,float)) or not math.isfinite(sample['observed_at']):
            errors.append('sample_clock'); break
    stamps = [s.get('utc_ns') for s in samples]
    if not stamps or any(type(t) is not int for t in stamps):
        errors.append('sample_timeline')
    elif stamps != sorted(stamps) or any(b-a > 200_000_000 for a,b in zip(stamps, stamps[1:])):
        errors.append('sample_gap')
    elif stamps[0]-record['capture_start_utc_ns'] > 200_000_000 or record['capture_end_utc_ns']-stamps[-1] > 200_000_000:
        errors.append('sample_coverage')
    return errors
