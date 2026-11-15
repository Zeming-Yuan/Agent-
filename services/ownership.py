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
