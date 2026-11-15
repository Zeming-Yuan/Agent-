"""Durable request identity, partitioned by service and server-authenticated owner."""
import json
import os
import re
import sqlite3
from contextlib import closing
from pathlib import Path


class RequestJournal:
    def __init__(self, path: Path, service: str, owner: str):
        self.path, self.service, self.owner = Path(path), service, owner
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(fd)
        self.path.chmod(0o600)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('''CREATE TABLE IF NOT EXISTS requests(
                service TEXT, owner TEXT, request_id TEXT, fingerprint TEXT,
                payload TEXT, task_id TEXT, PRIMARY KEY(service,owner,request_id))''')

    def prepare(self, request_id: str, fingerprint: str, payload: dict) -> dict:
        if not isinstance(request_id,str) or not re.fullmatch(r'[\x21-\x7e]{1,128}',request_id):
            raise ValueError('request_id must be 1..128 printable ASCII characters without spaces')
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('BEGIN IMMEDIATE')
            key = (self.service, self.owner, request_id)
            row = db.execute('SELECT fingerprint,payload,task_id FROM requests '
                             'WHERE service=? AND owner=? AND request_id=?', key).fetchone()
            if row and row[0] != fingerprint:
                raise ValueError('request id reused with different input')
            if not row:
                db.execute('INSERT INTO requests VALUES(?,?,?,?,?,NULL)',
                           key+(fingerprint,json.dumps(payload,ensure_ascii=False)))
            return {'request_id':request_id, 'task_id':row[2] if row else None,
                    'payload':json.loads(row[1]) if row else payload}

    def accepted(self, request_id: str, task_id: str) -> None:
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('UPDATE requests SET task_id=? WHERE service=? AND owner=? AND request_id=?',
                       (task_id,self.service,self.owner,request_id))

    def pending(self) -> list[dict]:
        with closing(sqlite3.connect(self.path)) as db:
            return [{'request_id':r[0],'task_id':r[1]} for r in db.execute(
                'SELECT request_id,task_id FROM requests WHERE service=? AND owner=? ORDER BY rowid',
                (self.service,self.owner))]
