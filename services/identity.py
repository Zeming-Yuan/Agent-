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


class KeyDeliveryError(RuntimeError):
    """Delivery rollback needs operator recovery, identified without the credential."""
    def __init__(self, key_id: str, *, cleanup_pending: bool):
        self.key_id = key_id
        self.cleanup_pending = cleanup_pending
        guidance = ('cleanup pending for newly created output' if cleanup_pending
                    else 'no owned output remains; preserve existing files')
        super().__init__(f'Key delivery rollback incomplete; revoke key ID {key_id}; {guidance}')


def issue_to_file(registry: KeyRegistry, owner: str, target: Path) -> str:
    """Issue once to an exclusive private file; return only the public key ID."""
    import os
    target = Path(target)
    raw = registry.issue(owner)
    principal = registry.resolve(raw)
    fd = None
    created = False
    try:
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        created = True
        stream = os.fdopen(fd, 'w', encoding='utf-8')
        fd = None  # stream now owns the descriptor
        with stream:
            stream.write(raw + '\n')
    except BaseException:
        incomplete = False
        cleanup_pending = False
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                incomplete = True
        try:
            registry.revoke(principal.key_id)
        except Exception:
            incomplete = True
        # Cleanup is independent of registry availability and never owns prior files.
        if created:
            try:
                target.unlink(missing_ok=True)
            except OSError:
                incomplete = True
                cleanup_pending = True
        if incomplete:
            raise KeyDeliveryError(principal.key_id, cleanup_pending=cleanup_pending) from None
        raise
    return principal.key_id


def main():
    """Local operator entry point; credentials never appear on stdout/stderr."""
    import argparse
    parser = argparse.ArgumentParser(description='Manage personal API keys in a controlled registry')
    parser.add_argument('--db', type=Path, required=True)
    commands = parser.add_subparsers(dest='command', required=True)
    issue = commands.add_parser('issue', help='Write a new credential to a new private file')
    issue.add_argument('--owner', required=True)
    issue.add_argument('--out', type=Path, required=True)
    revoke = commands.add_parser('revoke', help='Idempotently revoke a public key ID')
    revoke.add_argument('--key-id', required=True)
    args = parser.parse_args()
    try:
        registry = KeyRegistry(args.db)
        if args.command == 'issue':
            key_id = issue_to_file(registry, args.owner, args.out)
        else:
            registry.revoke(args.key_id)
            key_id = args.key_id
    except KeyDeliveryError as exc:
        parser.exit(1, str(exc) + '\n')
    except (OSError, ValueError, sqlite3.Error) as exc:
        parser.exit(1, f'Key operation failed ({type(exc).__name__})\n')
    print(key_id)


if __name__ == '__main__':
    main()
