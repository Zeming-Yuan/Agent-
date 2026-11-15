"""Owner-scoped files and durable job state; owner-scoped task access with expand compatibility."""
from contextlib import contextmanager
import hashlib
import json
import sqlite3
import time
import uuid
from pathlib import Path
from fastapi import HTTPException
from .ownership import require_owner


class Store:
    def __init__(self, root: Path, max_pending=4):
        self.root = Path(root)
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.files = self.root / 'files'
        self.files.mkdir(mode=0o700, exist_ok=True)
        self.db = self.root / 'state.sqlite3'
        self.max_pending = max_pending
        with self.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS object_owners(kind TEXT NOT NULL, object_id TEXT NOT NULL,
                owner TEXT NOT NULL, PRIMARY KEY(kind, object_id));
            CREATE TABLE IF NOT EXISTS file_digests(owner TEXT NOT NULL, digest TEXT NOT NULL,
                file_id TEXT UNIQUE NOT NULL, PRIMARY KEY(owner, digest));
            CREATE TABLE IF NOT EXISTS task_requests(owner TEXT NOT NULL, request_key TEXT NOT NULL,
                fingerprint TEXT NOT NULL, task_id TEXT NOT NULL, PRIMARY KEY(owner, request_key));
            CREATE TABLE IF NOT EXISTS files(id TEXT PRIMARY KEY, name TEXT, bytes INTEGER, created INTEGER);
            CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY, kind TEXT, file_id TEXT,
              options TEXT, status TEXT, progress REAL, result TEXT, error TEXT,
              idem TEXT UNIQUE, fingerprint TEXT, created INTEGER, updated INTEGER);
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.db, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def file(self, fid, *, owner="legacy"):
        with self.connect() as db:
            require_owner(db, 'file', fid, owner)
            row = db.execute('SELECT * FROM files WHERE id=?', (fid,)).fetchone()
        if row is None:
            raise HTTPException(404, 'Object not found')
        return dict(row)

    def path(self, fid, *, owner="legacy"):
        self.file(fid, owner=owner)
        # Only opaque IDs retrieved from SQLite can reach the filesystem.
        return self.files / fid

    def add_file(self, fid, name, size, *, owner="legacy"):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            used=db.execute('SELECT coalesce(sum(bytes),0) FROM files').fetchone()[0]
            if used+size>2*1024**3: raise HTTPException(413,'File/storage limit exceeded')
            db.execute('INSERT INTO files VALUES(?,?,?,?)', (fid, Path(name).name[:200], size, int(time.time())))
            db.execute('INSERT INTO object_owners VALUES(?,?,?)', ('file', fid, owner))
        return self.file(fid, owner=owner)

    def save_generated(self, fid, data, name, *, owner="legacy"):
        return self._save_generated(fid, data, name, owner=owner)[0]

    def save_reference(self, data, *, owner):
        """Return (file, created); reuse content only within this owner."""
        return self._save_generated('file-' + uuid.uuid4().hex, data, 'reference.png',
                                    owner=owner, digest=hashlib.sha256(data).hexdigest())

    def _save_generated(self, fid, data, name, *, owner, digest=None):
        path = self.files / fid
        created = False
        try:
            with self.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                if digest is not None:
                    reference = db.execute('SELECT file_id FROM file_digests WHERE owner=? AND digest=?',
                                           (owner, digest)).fetchone()
                    if reference:
                        return self.file(reference['file_id'], owner=owner), False
                existing = db.execute('SELECT bytes FROM files WHERE id=?', (fid,)).fetchone()
                if existing:
                    require_owner(db, 'file', fid, owner)
                    if existing['bytes'] == len(data) and path.is_file() and path.read_bytes() == data:
                        return self.file(fid, owner=owner), False
                    raise HTTPException(409, 'File ID conflicts with different content')
                used = db.execute('SELECT coalesce(sum(bytes),0) FROM files').fetchone()[0]
                if used + len(data) > 2*1024**3:
                    raise HTTPException(413, 'File/storage limit exceeded')
                with path.open('xb') as out:
                    created = True
                    out.write(data)
                db.execute('INSERT INTO files VALUES(?,?,?,?)', (fid, name, len(data), int(time.time())))
                db.execute('INSERT INTO object_owners VALUES(?,?,?)', ('file', fid, owner))
                if digest is not None:
                    db.execute('INSERT INTO file_digests VALUES(?,?,?)', (owner, digest, fid))
        except BaseException:
            if created:
                path.unlink(missing_ok=True)
            raise
        return self.file(fid, owner=owner), True

    def delete_file(self, fid, *, owner="legacy"):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            require_owner(db, 'file', fid, owner)
            if db.execute("""SELECT 1 FROM tasks WHERE status IN ('queued','running') AND
                          (file_id=? OR json_extract(options,'$.foreground_file_id')=? OR
                           EXISTS(SELECT 1 FROM json_each(tasks.options,'$.image_ids') WHERE value=?))""",
                          (fid,fid,fid)).fetchone():
                raise HTTPException(409, 'File has pending tasks')
            (self.files / fid).unlink(missing_ok=True)
            db.execute('DELETE FROM file_digests WHERE file_id=?', (fid,))
            db.execute('DELETE FROM files WHERE id=?', (fid,))
            db.execute("DELETE FROM object_owners WHERE kind='file' AND object_id=?", (fid,))

    def task(self, tid, *, owner="legacy"):
        with self.connect() as db:
            require_owner(db, 'task', tid, owner)
            return self._task(db, tid)

    def _task(self, db, tid):
        row = db.execute('SELECT * FROM tasks WHERE id=?', (tid,)).fetchone()
        if row is None:
            raise HTTPException(404, 'Task not found')
        item = dict(row)
        for key in ('options', 'result'):
            item[key] = json.loads(item[key]) if item[key] else None
        for key in ('idem', 'fingerprint'):
            item.pop(key)
        return item

    def _business_fingerprint(self, kind, fid, options):
        canonical = dict(options)
        material_digests = []
        material_refs = []
        if kind not in ('image_generate', 'image_edit') and fid:
            material_refs.append(('source', fid))
        material_refs.extend(('image', ref) for ref in canonical.pop('image_ids', []))
        foreground = canonical.pop('foreground_file_id', None)
        if foreground:
            material_refs.append(('foreground', foreground))
        for role, reference in material_refs:
            with (self.files / reference).open('rb') as stream:
                material_digests.append((role, hashlib.file_digest(stream, 'sha256').hexdigest()))
        return hashlib.sha256(json.dumps([kind, canonical, material_digests],
            sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()

    def submit(self, kind, fid, options, idem, *, owner="legacy"):
        tid = 'task-' + uuid.uuid4().hex
        now = int(time.time())
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            refs = ([fid] if fid else []) + options.get('image_ids', [])
            if options.get('foreground_file_id'):
                refs.append(options['foreground_file_id'])
            for reference in refs:
                require_owner(db, 'file', reference, owner)
            fingerprint = self._business_fingerprint(kind, fid, options)
            if idem:
                row = db.execute('SELECT task_id AS id,fingerprint FROM task_requests WHERE owner=? AND request_key=?', (owner, idem)).fetchone()
                if row is None and owner == 'legacy':
                    # Old writers retain their original positional schema and global key.
                    old = db.execute('SELECT * FROM tasks WHERE idem=?', (idem,)).fetchone()
                    if old:
                        require_owner(db, 'task', old['id'], owner)
                        try:
                            previous = self._business_fingerprint(old['kind'], old['file_id'], json.loads(old['options']))
                        except FileNotFoundError:
                            # Old ID-only fingerprints cannot prove equivalence after source deletion.
                            raise HTTPException(409, {'message': 'Legacy request material unavailable; retrieve existing task',
                                                      'task_id': old['id']}) from None
                        if previous != fingerprint:
                            raise HTTPException(409, 'Idempotency key reused with different request')
                        db.execute('INSERT INTO task_requests VALUES(?,?,?,?)', (owner, idem, fingerprint, old['id']))
                        return self.task(old['id'], owner=owner)
                if row:
                    if row['fingerprint'] != fingerprint:
                        raise HTTPException(409, 'Idempotency key reused with different request')
                    return self.task(row['id'], owner=owner)
            count = db.execute("SELECT count(*) FROM tasks WHERE status IN ('queued','running')").fetchone()[0]
            if count >= self.max_pending:
                raise HTTPException(429, 'Media queue full', headers={'Retry-After':'10'})
            db.execute('INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                       (tid, kind, fid, json.dumps(options), 'queued', 0, None, None, idem if owner == 'legacy' else None,
                        hashlib.sha256(json.dumps([kind, fid, options], sort_keys=True).encode()).hexdigest()
                        if owner == 'legacy' else fingerprint, now, now))
            db.execute('INSERT INTO object_owners VALUES(?,?,?)', ('task', tid, owner))
            if idem:
                db.execute('INSERT INTO task_requests VALUES(?,?,?,?)', (owner, idem, fingerprint, tid))
        return self.task(tid, owner=owner)

    def worker_task(self, tid):
        """Internal identity lookup; never exposed as an HTTP access method."""
        with self.connect() as db:
            item = self._task(db, tid)
            row = db.execute("SELECT owner FROM object_owners WHERE kind='task' AND object_id=?", (tid,)).fetchone()
        if row is None:
            raise RuntimeError('Task ownership missing')
        item['owner'] = row['owner']
        return item

    def update(self, tid, **fields):
        assert fields.keys() <= {'status', 'progress', 'result', 'error'}
        if 'result' in fields:
            fields['result'] = json.dumps(fields['result'], ensure_ascii=False)
        fields['updated'] = int(time.time())
        with self.connect() as db:
            # Cancellation is terminal, even if an upstream request completes at the same instant.
            db.execute('UPDATE tasks SET ' + ','.join(f'{k}=?' for k in fields) + " WHERE id=? AND status!='cancelled'",
                       (*fields.values(), tid))
        with self.connect() as db:
            return self._task(db, tid)

    def recover(self):
        with self.connect() as db:
            db.execute("UPDATE tasks SET status='failed',error='Service restarted during processing',updated=? WHERE status='running'", (int(time.time()),))

    def next_task(self, image=False):
        with self.connect() as db:
            op = 'IN' if image else 'NOT IN'
            row = db.execute(f"SELECT id FROM tasks WHERE status='queued' AND kind {op} ('image_generate','image_edit') ORDER BY created,rowid LIMIT 1").fetchone()
        return self.worker_task(row['id']) if row else None
