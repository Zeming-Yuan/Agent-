"""Owner-scoped files and durable job state; explicit ownership and owner-scoped request identity."""
from contextlib import contextmanager
import hashlib
import json
import sqlite3
import time
import uuid
from pathlib import Path
from fastapi import HTTPException
from .ownership import require_owner


def task_fingerprint(files: Path, kind, fid, options):
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
        with (files / reference).open('rb') as stream:
            material_digests.append((role, hashlib.file_digest(stream, 'sha256').hexdigest()))
    return hashlib.sha256(json.dumps([kind, canonical, material_digests],
        sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


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
            CREATE TABLE IF NOT EXISTS file_tombstones(file_id TEXT PRIMARY KEY, owner TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS task_requests(owner TEXT NOT NULL, request_key TEXT NOT NULL,
                fingerprint TEXT NOT NULL, task_id TEXT NOT NULL, PRIMARY KEY(owner, request_key));
            CREATE TABLE IF NOT EXISTS files(id TEXT PRIMARY KEY, name TEXT, bytes INTEGER, created INTEGER);
            CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY, kind TEXT, file_id TEXT,
              options TEXT, status TEXT, progress REAL, result TEXT, error TEXT,
              idem TEXT, fingerprint TEXT, created INTEGER, updated INTEGER);
            CREATE TABLE IF NOT EXISTS task_runtime(task_id TEXT PRIMARY KEY, stage TEXT NOT NULL,
              stage_seq INTEGER NOT NULL, stage_started_at REAL NOT NULL, stage_updated_at REAL NOT NULL,
              blocked_reason TEXT, cancel_requested INTEGER NOT NULL DEFAULT 0);
            INSERT OR IGNORE INTO task_runtime
              SELECT id,status,0,updated,updated,NULL,0 FROM tasks;
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

    def file(self, fid, *, owner):
        with self.connect() as db:
            require_owner(db, 'file', fid, owner)
            row = db.execute('SELECT * FROM files WHERE id=?', (fid,)).fetchone()
        if row is None:
            raise HTTPException(404, 'Object not found')
        return dict(row)

    def path(self, fid, *, owner):
        self.file(fid, owner=owner)
        # Only opaque IDs retrieved from SQLite can reach the filesystem.
        return self.files / fid

    def add_file(self, fid, name, size, *, owner):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            used=db.execute('SELECT coalesce(sum(bytes),0) FROM files').fetchone()[0]
            if used+size>2*1024**3: raise HTTPException(413,'File/storage limit exceeded')
            db.execute('INSERT INTO files VALUES(?,?,?,?)', (fid, Path(name).name[:200], size, int(time.time())))
            db.execute('INSERT INTO object_owners VALUES(?,?,?)', ('file', fid, owner))
        return self.file(fid, owner=owner)

    def save_generated(self, fid, data, name, *, owner):
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

    def delete_file(self, fid, *, owner):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            require_owner(db, 'file', fid, owner)
            if db.execute("""SELECT 1 FROM tasks WHERE status IN ('queued','running') AND
                          (file_id=? OR json_extract(options,'$.foreground_file_id')=? OR
                           EXISTS(SELECT 1 FROM json_each(tasks.options,'$.image_ids') WHERE value=?))""",
                          (fid,fid,fid)).fetchone():
                raise HTTPException(409, 'File has pending tasks')
            (self.files / fid).unlink(missing_ok=True)
            db.execute('INSERT INTO file_tombstones VALUES(?,?)', (fid, owner))
            db.execute('DELETE FROM file_digests WHERE file_id=?', (fid,))
            db.execute('DELETE FROM files WHERE id=?', (fid,))
            db.execute("DELETE FROM object_owners WHERE kind='file' AND object_id=?", (fid,))

    def task(self, tid, *, owner):
        with self.connect() as db:
            require_owner(db, 'task', tid, owner)
            return self._task(db, tid)

    def lookup_request(self, owner, request_key, fingerprint):
        """Read an existing owner request without requiring backend readiness."""
        if not request_key:
            return None
        with self.connect() as db:
            db.execute('BEGIN')
            row = db.execute('SELECT task_id,fingerprint FROM task_requests WHERE owner=? AND request_key=?',
                             (owner, request_key)).fetchone()
            if row is None:
                return None
            if row['fingerprint'] != fingerprint:
                raise HTTPException(409, 'Idempotency key reused with different request')
            require_owner(db, 'task', row['task_id'], owner)
            return self._task(db, row['task_id'])

    def list_tasks(self, owner, *, status=None, after=None, limit=20):
        if status is not None and status not in ('queued', 'running', 'completed', 'failed', 'cancelled'):
            raise HTTPException(422, 'Invalid task status')
        if type(limit) is not int or not 1 <= limit <= 100:
            raise HTTPException(422, 'limit must be between 1 and 100')
        with self.connect() as db:
            db.execute('BEGIN')
            clauses = ['o.owner=?']
            params = [owner]
            if after is not None:
                require_owner(db, 'task', after, owner)
                cursor = db.execute('SELECT created,rowid FROM tasks WHERE id=?', (after,)).fetchone()
                if cursor is None:
                    raise HTTPException(404, 'Object not found')
                clauses.append('(t.created,t.rowid) > (?,?)')
                params.extend((cursor['created'], cursor['rowid']))
            if status is not None:
                clauses.append('t.status=?')
                params.append(status)
            rows = db.execute("""SELECT t.id FROM tasks t JOIN object_owners o
                ON o.kind='task' AND o.object_id=t.id WHERE """ + ' AND '.join(clauses) +
                ' ORDER BY t.created,t.rowid LIMIT ?', (*params, limit + 1)).fetchall()
            page = rows[:limit]
            return {'object': 'list', 'data': [self._task(db, row['id']) for row in page],
                    'has_more': len(rows) > limit,
                    'next_cursor': page[-1]['id'] if len(rows) > limit else None}

    def _task(self, db, tid):
        row = db.execute('''SELECT t.*,r.stage,r.stage_seq,r.stage_started_at,r.stage_updated_at,
            r.blocked_reason,r.cancel_requested FROM tasks t LEFT JOIN task_runtime r ON r.task_id=t.id
            WHERE t.id=?''', (tid,)).fetchone()
        if row is None:
            raise HTTPException(404, 'Task not found')
        item = dict(row)
        for key in ('options', 'result'):
            item[key] = json.loads(item[key]) if item[key] else None
        for key in ('idem', 'fingerprint'):
            item.pop(key)
        item['cancel_requested'] = bool(item['cancel_requested'])
        return item

    def request_fingerprint(self, kind, fid, options, *, owner):
        """Validate and hash materials while excluding concurrent file deletion."""
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            return self._request_fingerprint(db, kind, fid, options, owner)

    def _request_fingerprint(self, db, kind, fid, options, owner):
        refs = ([fid] if fid else []) + options.get('image_ids', [])
        if options.get('foreground_file_id'):
            refs.append(options['foreground_file_id'])
        for reference in refs:
            require_owner(db, 'file', reference, owner)
        return task_fingerprint(self.files, kind, fid, options)

    def submit(self, kind, fid, options, idem, *, owner):
        tid = 'task-' + uuid.uuid4().hex
        now = int(time.time())
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            fingerprint = self._request_fingerprint(db, kind, fid, options, owner)
            if idem:
                row = db.execute('SELECT task_id AS id,fingerprint FROM task_requests WHERE owner=? AND request_key=?', (owner, idem)).fetchone()
                if row:
                    if row['fingerprint'] != fingerprint:
                        raise HTTPException(409, 'Idempotency key reused with different request')
                    return self.task(row['id'], owner=owner)
            count = db.execute("SELECT count(*) FROM tasks WHERE status IN ('queued','running')").fetchone()[0]
            if count >= self.max_pending:
                raise HTTPException(429, 'Media queue full', headers={'Retry-After':'10'})
            db.execute('INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                       (tid, kind, fid, json.dumps(options), 'queued', 0, None, None, None, fingerprint, now, now))
            db.execute('INSERT INTO object_owners VALUES(?,?,?)', ('task', tid, owner))
            db.execute('INSERT INTO task_runtime VALUES(?,?,?,?,?,?,?)', (tid, 'queued', 0, now, now, None, 0))
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

    def transition(self, tid: str, *, status: str, stage: str, expected_seq: int,
                   result: dict | None = None, error: str | None = None) -> dict:
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self._transition_tx(db, tid, status=status, stage=stage, expected_seq=expected_seq,
                                result=result, error=error)
            return self._task(db, tid)

    def _transition_tx(self, db, tid, *, status, stage, expected_seq, result=None, error=None):
        task = self._task(db, tid)
        if task['status'] in ('completed', 'failed', 'cancelled') or task['stage_seq'] != expected_seq:
            return
        if task['cancel_requested'] and status == 'completed':
            return
        now = time.time()
        started = task['stage_started_at'] if task['stage'] == stage else now
        db.execute('''UPDATE task_runtime SET stage=?,stage_seq=stage_seq+1,
            stage_started_at=?,stage_updated_at=? WHERE task_id=?''', (stage, started, now, tid))
        db.execute('UPDATE tasks SET status=?,progress=?,result=?,error=?,updated=? WHERE id=?',
                   (status, 1 if status == 'completed' else task['progress'],
                    json.dumps(result) if result is not None else None, error, int(now), tid))

    def request_cancel(self, tid, *, owner):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            require_owner(db, 'task', tid, owner)
            task = self._task(db, tid)
            if task['status'] not in ('queued', 'running') or task['cancel_requested']:
                return task, False
            db.execute('UPDATE task_runtime SET cancel_requested=1 WHERE task_id=?', (tid,))
            self._transition_tx(db, tid, status='cancelled' if task['status'] == 'queued' else 'running',
                                stage='cancelled' if task['status'] == 'queued' else 'cancelling',
                                expected_seq=task['stage_seq'])
            return self._task(db, tid), True

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
