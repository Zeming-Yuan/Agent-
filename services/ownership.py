"""Expand-only ownership metadata, compatible with legacy positional writes."""
import sqlite3
from contextlib import closing
from pathlib import Path
from fastapi import HTTPException


def expand_ownership(db_path: Path, legacy_owner: str) -> None:
    if not isinstance(legacy_owner, str) or not legacy_owner.strip():
        raise ValueError('explicit legacy owner required')
    with closing(sqlite3.connect(db_path, timeout=10)) as db, db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('''CREATE TABLE IF NOT EXISTS object_owners(
            kind TEXT NOT NULL, object_id TEXT NOT NULL, owner TEXT NOT NULL,
            PRIMARY KEY(kind, object_id))''')
        for kind, table in (('file', 'files'), ('task', 'tasks')):
            db.execute(f'''INSERT OR IGNORE INTO object_owners
                SELECT ?, id, ? FROM {table}''', (kind, legacy_owner))


def preflight_ownership(db_path: Path) -> dict:
    report = {}
    uri = Path(db_path).resolve().as_uri() + '?mode=ro'
    with closing(sqlite3.connect(uri, uri=True, timeout=10)) as db:
        db.execute('BEGIN')
        has_owners = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='object_owners'").fetchone()
        for kind, table in (('file', 'files'), ('task', 'tasks')):
            report['unowned_' + table] = db.execute(f'''
                SELECT count(*) FROM {table} x LEFT JOIN object_owners o
                ON o.kind=? AND o.object_id=x.id WHERE o.object_id IS NULL
                ''', (kind,)).fetchone()[0] if has_owners else db.execute(
                    f'SELECT count(*) FROM {table}').fetchone()[0]
        report['unowned_idempotency_records'] = db.execute('''
            SELECT count(*) FROM tasks t LEFT JOIN object_owners o
            ON o.kind='task' AND o.object_id=t.id
            WHERE t.idem IS NOT NULL AND o.object_id IS NULL
            ''').fetchone()[0] if has_owners else db.execute(
                'SELECT count(*) FROM tasks WHERE idem IS NOT NULL').fetchone()[0]
        report['running_tasks'] = db.execute(
            "SELECT count(*) FROM tasks WHERE status='running'").fetchone()[0]
    return report


def require_owner(db, kind: str, object_id: str, owner: str) -> None:
    found = db.execute('''SELECT 1 FROM object_owners
        WHERE kind=? AND object_id=? AND owner=?''', (kind, object_id, owner)).fetchone()
    if not found:
        raise HTTPException(404, 'Object not found')


def validate_ownership(db, files: Path, *, legacy_owner: str | None = None) -> dict:
    """Validate one SQLite snapshot; optional legacy identity is only for offline contract."""
    import json
    tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    owners = {(row['kind'], row['object_id']): row['owner']
              for row in db.execute('SELECT * FROM object_owners')} if 'object_owners' in tables else {}
    file_rows = {row['id']: row for row in db.execute('SELECT * FROM files')}
    tasks = {row['id']: row for row in db.execute('SELECT * FROM tasks')}

    def owner(kind, oid):
        value = owners.get((kind, oid), legacy_owner)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f'unowned {kind} {oid}')
        return value

    for (kind, oid), value in owners.items():
        if kind not in ('file', 'task') or oid not in (file_rows if kind == 'file' else tasks):
            raise ValueError(f'dangling ownership {kind} {oid}')
        owner(kind, oid)
    for fid, row in file_rows.items():
        owner('file', fid)
        path = files / fid
        if Path(fid).name != fid or path.is_symlink() or not path.is_file():
            raise ValueError(f'dangling or unsafe file bytes {fid}')
        if path.stat().st_size != row['bytes']:
            raise ValueError(f'file size mismatch {fid}')
    for tid, task in tasks.items():
        task_owner = owner('task', tid)
        try:
            options = json.loads(task['options']) if task['options'] else {}
            result = json.loads(task['result']) if task['result'] else {}
            if not isinstance(options, dict) or not isinstance(result, (dict, list)):
                raise ValueError
            images = options.get('image_ids', [])
            if not isinstance(images, list):
                raise ValueError
            refs = [task['file_id'], options.get('foreground_file_id'), *images]
            if isinstance(result, dict):
                refs.extend([result.get('file_id'), result.get('source_file_id')])
            if any(ref is not None and (not isinstance(ref, str) or not ref) for ref in refs):
                raise ValueError
        except (ValueError, TypeError):
            raise ValueError(f'invalid references in task {tid}') from None
        for fid in filter(None, refs):
            if fid not in file_rows:
                raise ValueError(f'dangling file reference in task {tid}: {fid}')
            if owner('file', fid) != task_owner:
                raise ValueError(f'cross-owner file reference in task {tid}: {fid}')
    if 'task_requests' in tables:
        requests = {(r['owner'], r['request_key']): r['task_id'] for r in db.execute('SELECT * FROM task_requests')}
        for tid, task in tasks.items():
            mapped = requests.get((owner('task', tid), task['idem'])) if task['idem'] else None
            if mapped is not None and mapped != tid:
                raise ValueError(f'conflicting request task {tid}')
        for row in db.execute('SELECT * FROM task_requests'):
            if row['task_id'] not in tasks:
                raise ValueError(f'dangling request task {row["task_id"]}')
            if owner('task', row['task_id']) != row['owner']:
                raise ValueError(f'cross-owner request task {row["task_id"]}')
    if 'file_digests' in tables:
        for row in db.execute('SELECT * FROM file_digests'):
            if row['file_id'] not in file_rows:
                raise ValueError(f'dangling digest file {row["file_id"]}')
            if owner('file', row['file_id']) != row['owner']:
                raise ValueError(f'cross-owner digest file {row["file_id"]}')
    return {'files': len(file_rows), 'tasks': len(tasks)}


def validate_contract(db, files: Path, *, legacy_owner: str | None = None) -> dict:
    if legacy_owner is not None and legacy_owner != 'legacy':
        raise ValueError('legacy owner must match the existing stable legacy identity')
    if db.execute("SELECT 1 FROM tasks WHERE status='running' LIMIT 1").fetchone():
        raise ValueError('running tasks must be reconciled before owner migration')
    counts = validate_ownership(db, files, legacy_owner=legacy_owner)
    return {'ready': True, 'legacy_owner': legacy_owner, **counts}


def inspect_contract(db_path: Path, *, legacy_owner: str | None = None) -> dict:
    uri = Path(db_path).resolve().as_uri() + '?mode=ro'
    with closing(sqlite3.connect(uri, uri=True, timeout=10)) as db:
        db.row_factory = sqlite3.Row
        db.execute('BEGIN')
        return validate_contract(db, Path(db_path).parent / 'files', legacy_owner=legacy_owner)
