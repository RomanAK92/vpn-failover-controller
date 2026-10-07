"""Durable transaction intent for a separate rollback watcher, not a VPN driver.

This module never changes networking. A driver must revalidate every generation,
observe desired/revision changes and prove recovery before acknowledging rollback.
"""
import contextlib
import os
import pathlib
import re
import secrets
import sqlite3
import time
import threading
import stat
if os.name == 'posix':
    import fcntl

GENERATION = re.compile(r'[a-f0-9]{32}')


class TransactionError(ValueError):
    pass


def storage_full(error):
    """Python 3.10 lacks sqlite_errorcode; accept only SQLite's exact FULL error."""
    code = getattr(error, 'sqlite_errorcode', None)
    return code == 13 if code is not None else str(error) == 'database or disk is full'


class Journal:
    def __init__(self, directory, boot_id, clock=time.monotonic):
        if not isinstance(boot_id, str) or not re.fullmatch(r'[A-Za-z0-9-]{1,64}', boot_id):
            raise TransactionError('Invalid boot identity.')
        self.clock = clock
        self.boot_id = boot_id
        self.thread_lock = threading.RLock()
        root = pathlib.Path(directory)
        if any(p.is_symlink() for p in (root, *root.parents)) or not root.is_dir():
            raise TransactionError('Initialize a private transaction directory.')
        if os.name == 'posix' and (root.stat().st_mode & 0o077 or root.stat().st_uid != os.geteuid()):
            raise TransactionError('Transaction storage requires mode 0700.')
        p = root/'transactions.sqlite3'
        if p.is_symlink() or (p.exists() and not p.is_file()):
            raise TransactionError('Invalid transaction database.')
        if not p.exists():
            fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            os.close(fd)
        if os.name == 'posix' and (p.stat().st_mode & 0o077 or p.stat().st_uid != os.geteuid()
                                   or p.stat().st_nlink != 1):
            raise TransactionError('Transaction database requires mode 0600.')
        self.path = p.resolve()
        self.lock_fd = os.open(root/'transactions.lock', os.O_RDWR | os.O_CREAT |
                               getattr(os, 'O_NOFOLLOW', 0), 0o600)
        attributes = os.fstat(self.lock_fd)
        if (not stat.S_ISREG(attributes.st_mode) or attributes.st_nlink != 1
            or (os.name == 'posix' and (attributes.st_uid != os.geteuid() or attributes.st_mode & 0o077))):
            os.close(self.lock_fd)
            raise TransactionError('Invalid private transaction lock.')
        self.db = None
        try:
            self.db = sqlite3.connect(p, timeout=5, isolation_level=None, check_same_thread=False)
            self.db.row_factory = sqlite3.Row
            self.db.execute('PRAGMA synchronous=FULL')
            with self.file_locked():
                version = self.db.execute('PRAGMA user_version').fetchone()[0]
                if version not in (0, 1):
                    raise TransactionError('Unsupported transaction database version.')
                if version == 0:
                    self.db.executescript('''
                CREATE TABLE IF NOT EXISTS state (
                  singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                  active TEXT NOT NULL, desired TEXT NOT NULL, revision INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS change (
                  singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                  id TEXT NOT NULL, previous TEXT NOT NULL, candidate TEXT NOT NULL,
                  phase TEXT NOT NULL, boot TEXT NOT NULL, started REAL NOT NULL,
                  deadline REAL NOT NULL, reason TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events (
                  id INTEGER PRIMARY KEY AUTOINCREMENT, event TEXT NOT NULL,
                  change_id TEXT NOT NULL, reason TEXT NOT NULL, created REAL NOT NULL);
                PRAGMA user_version=1;
            ''')
        except Exception:
            if self.db is not None:
                self.db.close()
            os.close(self.lock_fd)
            raise

    def close(self):
        self.db.close()
        os.close(self.lock_fd)

    @contextlib.contextmanager
    def file_locked(self):
        """Also usable during disk-full recovery: acquiring a lock writes no data."""
        with self.thread_lock:
            if os.name == 'posix':
                fcntl.flock(self.lock_fd, fcntl.LOCK_EX)
            try:
                yield
            finally:
                if os.name == 'posix':
                    fcntl.flock(self.lock_fd, fcntl.LOCK_UN)

    @contextlib.contextmanager
    def locked(self):
        with self.file_locked():
            self.db.execute('BEGIN IMMEDIATE')
            try:
                yield
                self.db.execute('COMMIT')
            except BaseException:
                if self.db.in_transaction:
                    self.db.execute('ROLLBACK')
                raise

    def event(self, event, identifier='', reason=''):
        self.db.execute('INSERT INTO events(event,change_id,reason,created) VALUES(?,?,?,?)',
                        (event, identifier, reason, time.time()))
        self.db.execute('DELETE FROM events WHERE id NOT IN (SELECT id FROM events ORDER BY id DESC LIMIT 1000)')

    @staticmethod
    def generation(value):
        if not isinstance(value, str) or not GENERATION.fullmatch(value):
            raise TransactionError('Invalid generation identifier.')
        return value

    def initialize(self, generation):
        generation = self.generation(generation)
        with self.locked():
            if self.db.execute('SELECT 1 FROM state').fetchone():
                raise TransactionError('The installation already has an active generation.')
            self.db.execute('INSERT INTO state VALUES(1,?,?,1)', (generation, generation))
            self.event('initialized')

    def read_state(self, database=None):
        database = database or self.db
        state = database.execute('SELECT active,desired,revision FROM state').fetchone()
        if not state:
            raise TransactionError('Initialize an active generation first.')
        change = database.execute('SELECT id,previous,candidate,phase,reason,deadline,boot,started FROM change').fetchone()
        return {'state': dict(state), 'change': dict(change) if change else None}

    @contextlib.contextmanager
    def read_only_snapshot(self):
        """Coherent read-only state, held against cooperating writers; no writes."""
        with self.file_locked():
            reader = sqlite3.connect(self.path.as_uri()+'?mode=ro', uri=True, timeout=5,
                                     isolation_level=None)
            reader.row_factory = sqlite3.Row
            try:
                reader.execute('BEGIN')
                if reader.execute('PRAGMA user_version').fetchone()[0] != 1:
                    raise TransactionError('Unsupported recovery database version.')
                snapshot = self.read_state(reader)
                yield snapshot
            finally:
                reader.close()

    @contextlib.contextmanager
    def recovery_snapshot(self):
        """Read-only expiry check, never accepting a browser override or health flag."""
        with self.read_only_snapshot() as snapshot:
            c = snapshot['change']
            now = self.clock()
            if not c or (c['phase'] != 'rollback-requested' and not (
                c['phase'] == 'pending' and (c['boot'] != self.boot_id or
                now < c['started'] or now >= c['deadline']))):
                raise TransactionError('No independently verified recovery intent.')
            yield snapshot

    def snapshot(self):
        with self.locked():
            return self.read_state()

    def begin(self, candidate, timeout=180):
        candidate = self.generation(candidate)
        if type(timeout) is not int or not 60 <= timeout <= 600:
            raise TransactionError('Confirmation timeout must be 60 to 600 seconds.')
        now = self.clock()
        identifier = secrets.token_hex(16)
        with self.locked():
            state = self.db.execute('SELECT active,desired FROM state').fetchone()
            if not state or state['active'] != state['desired']:
                raise TransactionError('No confirmed active generation is available.')
            change = self.db.execute('SELECT phase FROM change').fetchone()
            if change and change['phase'] in ('pending', 'rollback-requested'):
                raise TransactionError('Finish the existing transaction first.')
            if state['active'] == candidate:
                raise TransactionError('The candidate is already active.')
            self.db.execute('INSERT OR REPLACE INTO change VALUES(1,?,?,?,?,?,?,?,?)',
                (identifier, state['active'], candidate, 'pending', self.boot_id, now, now+timeout, ''))
            self.db.execute('UPDATE state SET desired=?,revision=revision+1', (candidate,))
            self.event('rollback-armed', identifier)
        return identifier

    def watch(self, force=False):
        """Can run from an independent process. Request recovery, never claim it."""
        with self.locked():
            c = self.db.execute('SELECT * FROM change').fetchone()
            if not c or c['phase'] != 'pending':
                return False
            now = self.clock()
            reason = 'operator-revert' if force else (
                'boot-changed' if c['boot'] != self.boot_id else
                'clock-invalid' if now < c['started'] else
                'confirmation-expired' if now >= c['deadline'] else '')
            if not reason:
                return False
            self.db.execute("UPDATE change SET phase='rollback-requested',reason=?", (reason,))
            self.db.execute('UPDATE state SET desired=?,revision=revision+1', (c['previous'],))
            self.event('rollback-requested', c['id'], reason)
            return True

    def cancel(self, reason):
        if reason not in ('operator-revert', 'engine-failure', 'watcher-failure', 'apply-failed', 'service-restarted'):
            raise TransactionError('Invalid privileged cancellation reason.')
        with self.locked():
            c = self.db.execute('SELECT * FROM change').fetchone()
            if not c or c['phase'] != 'pending': return False
            self.db.execute("UPDATE change SET phase='rollback-requested',reason=?", (reason,))
            self.db.execute('UPDATE state SET desired=?,revision=revision+1', (c['previous'],))
            self.event('rollback-requested', c['id'], reason)
            return True

    def confirm(self, identifier, generation, revision, fresh_health=False):
        """Root driver must supply independently measured fresh health, never web input."""
        with self.locked():
            c = self.db.execute('SELECT * FROM change').fetchone()
            state = self.db.execute('SELECT * FROM state').fetchone()
            now = self.clock()
            if (not c or c['id'] != identifier or c['phase'] != 'pending'
                or c['boot'] != self.boot_id or not c['started'] <= now < c['deadline']
                or not state or state['desired'] != generation or c['candidate'] != generation
                or state['revision'] != revision or fresh_health is not True):
                raise TransactionError('Confirmation rejected; recovery intent remains armed.')
            self.db.execute("UPDATE change SET phase='confirmed'")
            self.db.execute('UPDATE state SET active=?', (generation,))
            self.event('confirmed', identifier)

    def restored(self, generation, revision, fresh_health=False):
        with self.locked():
            c = self.db.execute('SELECT * FROM change').fetchone()
            state = self.db.execute('SELECT * FROM state').fetchone()
            if (not c or c['phase'] != 'rollback-requested' or not state
                or c['previous'] != generation or state['desired'] != generation
                or state['revision'] != revision or fresh_health is not True):
                raise TransactionError('Recovery has not been proven.')
            self.db.execute("UPDATE change SET phase='rolled-back'")
            self.db.execute('UPDATE state SET active=?', (generation,))
            self.event('recovery-proven', c['id'])
