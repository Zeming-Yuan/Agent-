"""Pure task lifecycle rules; persistence assigns a sequence in one transaction."""

TERMINAL = frozenset({'completed', 'failed', 'cancelled'})
STAGE_ORDER = {name: index for index, name in enumerate(
    ('queued', 'waiting_resources', 'unloading', 'loading', 'generating', 'saving', 'cancelling'))}


def apply_event(task: dict, event: dict, *, backend_stopped=False, result_saved=False) -> dict:
    out = dict(task)
    if task['status'] in TERMINAL or event['seq'] <= task.get('stage_seq', 0):
        return out
    kind = event['type']
    if kind == 'cancel_requested':
        if task.get('cancel_requested'):
            return out
        out['cancel_requested'] = True
        out.update(status='cancelled' if task['status'] == 'queued' else 'running',
                   stage='cancelled' if task['status'] == 'queued' else 'cancelling')
    elif kind == 'backend_stopped':
        if not backend_stopped or not task.get('cancel_requested'):
            return out
        out.update(status='cancelled', stage='cancelled')
    elif kind == 'save_complete':
        if not result_saved or task.get('cancel_requested'):
            return out
        out.update(status='completed', stage='completed', result=event['result'], progress=1)
    elif kind == 'failed':
        out.update(status='failed', stage='failed', error=event.get('error'),
                   blocked_reason=event.get('blocked_reason'))
    elif kind == 'resource_wait':
        if task['status'] != 'queued' or task.get('cancel_requested'):
            return out
        if task.get('stage') == 'waiting_resources' and task.get('blocked_reason') == event['reason']:
            return out
        out.update(stage='waiting_resources', blocked_reason=event['reason'])
    elif kind == 'resource_ready':
        if task['status'] != 'queued' or task.get('cancel_requested') or task.get('stage') != 'waiting_resources':
            return out
        out.update(stage='queued', blocked_reason=None)
    elif kind == 'stage':
        stage = event['stage']
        if task.get('cancel_requested') or stage not in STAGE_ORDER:
            return out
        if STAGE_ORDER[stage] <= STAGE_ORDER.get(task.get('stage'), -1):
            return out
        out.update(status=event.get('status', task['status']), stage=stage, blocked_reason=None)
    elif kind == 'progress':
        if task.get('cancel_requested') or task.get('stage') != 'generating':
            return out
        step, steps = event.get('step'), event.get('steps')
        if (type(step) is not int or type(steps) is not int or not 0 <= step <= steps or steps <= 0
                or (task.get('steps') is not None and steps != task['steps'])
                or (task.get('step') is not None and step <= task['step'])):
            return out
        out.update(step=step, steps=steps)
    elif kind == 'observation_lost':
        if task.get('blocked_reason') == 'events_unavailable':
            return out
        out.update(step=None, steps=None, blocked_reason='events_unavailable')
    else:
        return out
    out['stage_seq'] = event['seq']
    if out.get('stage') != 'generating':
        out.update(step=None, steps=None)
    return out
