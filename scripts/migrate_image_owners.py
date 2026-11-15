"""Contract ownership on an offline data copy; never infer a takeover identity."""
import hashlib
import json
import os
import shutil
import sqlite3
import uuid
from contextlib import closing
from pathlib import Path
from services.store import task_fingerprint
from services.ownership import TASK_COLUMNS, global_idem_indexes, validate_contract, inspect_contract



def remove_global_idem_constraint(db):
    removed = global_idem_indexes(db)
    schema = [row['sql'] for row in db.execute("SELECT name,sql FROM sqlite_master WHERE type IN ('index','trigger') AND tbl_name='tasks' AND sql IS NOT NULL") if row['name'] not in removed]
    db.execute("""CREATE TABLE tasks_next(id TEXT PRIMARY KEY, kind TEXT, file_id TEXT,
        options TEXT, status TEXT, progress REAL, result TEXT, error TEXT,
        idem TEXT, fingerprint TEXT, created INTEGER, updated INTEGER)""")
    db.execute('INSERT INTO tasks_next(rowid,' + TASK_COLUMNS + ') SELECT rowid,' + TASK_COLUMNS + ' FROM tasks ORDER BY rowid')
    db.execute('DROP TABLE tasks')
    db.execute('ALTER TABLE tasks_next RENAME TO tasks')
    for sql in schema:
        db.execute(sql)


def contract_ownership(db_path: Path, legacy_owner: str, *, backup_dir: Path | None = None) -> dict:
    if not isinstance(legacy_owner, str) or not legacy_owner.strip():
        raise ValueError('explicit legacy owner required')
    if legacy_owner != 'legacy':
        raise ValueError('legacy owner must match the existing stable legacy identity')
    db_path = Path(db_path).resolve(strict=True)
    uri = db_path.as_uri() + '?mode=rw'
    with closing(sqlite3.connect(uri, uri=True, timeout=10)) as db, db:
        db.row_factory = sqlite3.Row
        db.execute('BEGIN IMMEDIATE')
        validate_contract(db, db_path.parent / 'files', legacy_owner=legacy_owner)
        target = Path(backup_dir) if backup_dir is not None else db_path.parent / 'ownership-backups' / uuid.uuid4().hex
        backup_state(db_path, target)
        db.execute("""CREATE TABLE IF NOT EXISTS object_owners(kind TEXT NOT NULL,
            object_id TEXT NOT NULL, owner TEXT NOT NULL, PRIMARY KEY(kind,object_id))""")
        db.execute("""CREATE TABLE IF NOT EXISTS task_requests(owner TEXT NOT NULL,
            request_key TEXT NOT NULL, fingerprint TEXT NOT NULL, task_id TEXT NOT NULL,
            PRIMARY KEY(owner,request_key))""")
        for kind, table in (('file', 'files'), ('task', 'tasks')):
            db.execute('INSERT OR IGNORE INTO object_owners SELECT ?,id,? FROM ' + table, (kind, legacy_owner))
        for task in db.execute('SELECT t.*,o.owner FROM tasks t JOIN object_owners o ON o.kind=\'task\' AND o.object_id=t.id WHERE t.idem IS NOT NULL').fetchall():
            mapped = db.execute('SELECT 1 FROM task_requests WHERE owner=? AND request_key=?', (task['owner'], task['idem'])).fetchone()
            if not mapped:
                fingerprint = task_fingerprint(db_path.parent / 'files', task['kind'], task['file_id'], json.loads(task['options'] or '{}'))
                db.execute('INSERT INTO task_requests VALUES(?,?,?,?)', (task['owner'], task['idem'], fingerprint, task['id']))
        remove_global_idem_constraint(db)
        db.execute('CREATE TABLE IF NOT EXISTS ownership_migration(version INTEGER PRIMARY KEY, legacy_owner TEXT NOT NULL, backup_dir TEXT NOT NULL)')
        db.execute('INSERT OR IGNORE INTO ownership_migration VALUES(1,?,?)', (legacy_owner, str(target.resolve())))
    return {'version': 1, 'legacy_owner': legacy_owner, 'backup_dir': str(target.resolve())}


def backup_state(db_path: Path, backup_dir: Path) -> dict:
    """Caller must stop all writers, including registry and filesystem writers."""
    db_path = Path(db_path).resolve(strict=True)
    target = Path(backup_dir).resolve()
    source_files = db_path.parent / 'files'
    if ((db_path.parent / 'keys.sqlite3').is_symlink() or source_files.is_symlink() or not source_files.is_dir() or
            target.is_relative_to(source_files.resolve()) or
            any(p.is_symlink() or not (p.is_file() or p.is_dir()) for p in source_files.rglob('*'))):
        raise ValueError('unsafe backup filesystem')
    target.mkdir(mode=0o700, parents=True, exist_ok=False)
    for name, source_path in (('state.sqlite3', db_path),
                              ('keys.sqlite3', db_path.parent / 'keys.sqlite3')):
        if name == 'keys.sqlite3' and not source_path.exists():
            continue
        uri = source_path.as_uri() + '?mode=ro'
        with closing(sqlite3.connect(uri, uri=True)) as source, closing(sqlite3.connect(target / name)) as copy:
            os.chmod(target / name, 0o600)
            source.backup(copy)
    shutil.copytree(source_files, target / 'files')
    hashes = {}
    for path in target.rglob('*'):
        os.chmod(path, 0o700 if path.is_dir() else 0o600)
        if path.is_file():
            with path.open('rb') as stream:
                hashes[str(path.relative_to(target))] = hashlib.file_digest(stream, 'sha256').hexdigest()
    with (target / 'manifest.json').open('x', encoding='utf-8') as stream:
        os.chmod(target / 'manifest.json', 0o600)
        json.dump(hashes, stream, sort_keys=True)
        stream.write('\n')
    return hashes


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Offline ownership contract. Stop ALL writers and reconcile backend work first.')
    parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('--legacy-owner', required=True)
    parser.add_argument('--backup-dir', type=Path)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    if not args.dry_run and args.backup_dir is None:
        parser.error('--backup-dir is required for mutation')
    try:
        report = inspect_contract(args.db, legacy_owner=args.legacy_owner) if args.dry_run else contract_ownership(
            args.db, args.legacy_owner, backup_dir=args.backup_dir)
    except (ValueError, OSError, sqlite3.Error) as exc:
        parser.exit(1, f'owner contract refused: {type(exc).__name__}: {exc}\n')
    print(json.dumps(report, sort_keys=True))


if __name__ == '__main__':
    main()
