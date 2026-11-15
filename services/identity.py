"""Persistent digest-only API keys with stable owner identities."""
import hashlib
import secrets
import sqlite3
import uuid
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Principal:
    owner: str
    key_id: str


class KeyRegistry:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        with closing(sqlite3.connect(self.db_path, timeout=10)) as db, db:
            db.execute('''CREATE TABLE IF NOT EXISTS api_keys(
                key_id TEXT PRIMARY KEY, owner TEXT NOT NULL,
                digest TEXT UNIQUE NOT NULL, revoked INTEGER NOT NULL)''')

    def register(self, owner: str, raw_key: str) -> Principal:
        if not isinstance(owner, str) or not owner.strip() or not isinstance(raw_key, str) or len(raw_key) < 16:
            raise ValueError('owner and strong key required')
        digest = hashlib.sha256(raw_key.encode()).hexdigest()
        with closing(sqlite3.connect(self.db_path, timeout=10)) as db, db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT OR IGNORE INTO api_keys VALUES(?,?,?,0)',
                       (uuid.uuid4().hex, owner, digest))
            row = db.execute('SELECT owner,key_id FROM api_keys WHERE digest=?',
                             (digest,)).fetchone()
            if row[0] != owner:
                raise ValueError('key already belongs to another owner')
        return Principal(*row)

    def issue(self, owner: str) -> str:
        raw = secrets.token_urlsafe(32)
        self.register(owner, raw)
        return raw

    def resolve(self, raw_key: str) -> Principal | None:
        digest = hashlib.sha256(raw_key.encode()).hexdigest()
        with closing(sqlite3.connect(self.db_path, timeout=10)) as db:
            row = db.execute('SELECT owner,key_id FROM api_keys WHERE digest=? AND revoked=0',
                             (digest,)).fetchone()
        return Principal(*row) if row else None

    def revoke(self, key_id: str) -> None:
        with closing(sqlite3.connect(self.db_path, timeout=10)) as db, db:
            db.execute('UPDATE api_keys SET revoked=1 WHERE key_id=?', (key_id,))
