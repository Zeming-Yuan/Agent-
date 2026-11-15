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
    if files.is_symlink() or not files.is_dir():
        raise ValueError('unsafe files directory')
    tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    owners = {(row['kind'], row['object_id']): row['owner']
              for row in db.execute('SELECT * FROM object_owners')} if 'object_owners' in tables else {}
    file_rows = {row['id']: row for row in db.execute('SELECT * FROM files')}
    tasks = {row['id']: row for row in db.execute('SELECT * FROM tasks')}
    deleted = {row['file_id']: row['owner'] for row in db.execute('SELECT * FROM file_tombstones')} if 'file_tombstones' in tables else {}

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
                if (task['status'] in ('completed', 'failed', 'cancelled') and deleted.get(fid) == task_owner):
                    continue  # Proven owner deletion, not an unaccounted dangling association.
                raise ValueError(f'dangling file reference in task {tid}: {fid}')
            if owner('file', fid) != task_owner:
                raise ValueError(f'cross-owner file reference in task {tid}: {fid}')
    if legacy_owner is None:
        require_scoped_requests(db)
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


TASK_COLUMNS = 'id,kind,file_id,options,status,progress,result,error,idem,fingerprint,created,updated'


def global_idem_indexes(db) -> set[str]:
    return {index['name'] for index in db.execute('PRAGMA index_list(tasks)') if index['unique']
            and [row['name'] for row in db.execute('PRAGMA index_info("' + index['name'].replace('"', '""') + '")')] == ['idem']}


def validate_contract(db, files: Path, *, legacy_owner: str | None = None, allow_running=False) -> dict:
    if legacy_owner is not None and legacy_owner != 'legacy':
        raise ValueError('legacy owner must match the existing stable legacy identity')
    if [row['name'] for row in db.execute('PRAGMA table_info(tasks)')] != TASK_COLUMNS.split(','):
        raise ValueError('unsupported task schema; preserve data and use a matching migration version')
    allowed_auto = global_idem_indexes(db)
    for index in db.execute('PRAGMA index_list(tasks)'):
        if index['origin'] == 'u' and index['name'] not in allowed_auto:
            raise ValueError('unsupported task schema implicit unique constraint')
    marker = db.execute("SELECT 1 FROM sqlite_master WHERE name='ownership_migration' AND type='table'").fetchone()
    if marker:
        versions = db.execute('SELECT version,legacy_owner FROM ownership_migration').fetchall()
        if len(versions) != 1 or tuple(versions[0]) != (1, 'legacy'):
            raise ValueError('owner migration version or legacy identity mismatch')
    elif legacy_owner is None:
        raise ValueError('owner migration incomplete: contract required')
    if legacy_owner is None and allowed_auto:
        raise ValueError('owner migration retains global idempotency constraint')
    if not allow_running and db.execute("SELECT 1 FROM tasks WHERE status='running' LIMIT 1").fetchone():
        raise ValueError('running tasks must be reconciled before owner migration')
    counts = validate_ownership(db, files, legacy_owner=legacy_owner)
    return {'ready': True, 'legacy_owner': legacy_owner, **counts}


def inspect_contract(db_path: Path, *, legacy_owner: str | None = None, allow_running=False) -> dict:
    uri = Path(db_path).resolve().as_uri() + '?mode=ro'
    with closing(sqlite3.connect(uri, uri=True, timeout=10)) as db:
        db.row_factory = sqlite3.Row
        db.execute('BEGIN')
        return validate_contract(db, Path(db_path).parent / 'files', legacy_owner=legacy_owner,
                                 allow_running=allow_running)


def require_scoped_requests(db) -> None:
    """Old global records must be explicitly mapped before any modern writer starts."""
    mapped = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='task_requests'").fetchone()
    if mapped:
        missing = db.execute('''SELECT t.id FROM tasks t
            LEFT JOIN object_owners o ON o.kind='task' AND o.object_id=t.id
            LEFT JOIN task_requests r ON r.owner=o.owner AND r.request_key=t.idem
            WHERE t.idem IS NOT NULL AND (r.task_id IS NULL OR r.task_id!=t.id) LIMIT 1''').fetchone()
    else:
        missing = db.execute('SELECT id FROM tasks WHERE idem IS NOT NULL LIMIT 1').fetchone()
    if missing:
        raise ValueError(f'owner migration required: missing request mapping for task {missing[0]}')
