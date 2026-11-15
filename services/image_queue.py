"""Non-preemptive owner turns shared by image claims and queue snapshots."""


def choose_next(heads: list[dict], last_owner: str | None) -> str | None:
    by_owner = {head['owner']: head for head in heads}
    owners = sorted(by_owner)
    if last_owner is not None:
        owners = [owner for owner in owners if owner > last_owner] + [owner for owner in owners if owner <= last_owner]
    for owner in owners:
        if by_owner[owner]['eligible']:
            return by_owner[owner]['id']
    return None


def queue_ahead(snapshot: list[dict], target_id: str, last_owner: str | None,
                running_id: str | None = None) -> int | None:
    if running_id == target_id:
        return 0
    rows = [dict(row) for row in snapshot if row['id'] != running_id]
    target = next((row for row in rows if row['id'] == target_id), None)
    if target is None or not target['eligible']:
        return None
    ahead = int(running_id is not None)
    while rows:
        heads = {}
        for row in sorted(rows, key=lambda row: row['enqueue_seq']):
            heads.setdefault(row['owner'], row)
        chosen = choose_next(list(heads.values()), last_owner)
        if chosen is None:
            return None
        if chosen == target_id:
            return ahead
        row = next(row for row in rows if row['id'] == chosen)
        rows.remove(row)
        last_owner = row['owner']
        ahead += 1
    return None
