"""Private account/session storage for the management interface; no VPN access."""
import argparse
import getpass
import hashlib
import hmac
import ipaddress
import json
import os
import pathlib
import re
import secrets
import sqlite3
import threading
import time
from http.cookies import SimpleCookie
from urllib.parse import urlsplit

USERNAME = re.compile(r'[a-z][a-z0-9_.-]{2,31}')
TOKEN = re.compile(r'[A-Za-z0-9_-]{43}')
IDLE = 15 * 60
LIFETIME = 8 * 60 * 60
BLOCK = 15 * 60
PARAMETERS = {'n': 32768, 'r': 8, 'p': 3, 'maxmem': 64 * 1024 * 1024, 'dklen': 32}
HASH_GATE = threading.Lock()


class AuthError(Exception):
    def __init__(self, status=401, message='Login unsuccessful.'):
        self.status, self.message = status, message
        super().__init__(message)


def digest(password, salt):
    return hashlib.scrypt(password.encode('utf-8'), salt=bytes.fromhex(salt), **PARAMETERS).hex()


def password_policy(password):
    if not isinstance(password, str) or not 15 <= len(password) <= 128 or len(password.encode('utf-8')) > 512:
        raise ValueError('Use a password or passphrase of 15 to 128 characters.')


def origin_policy(origin):
    url = urlsplit(origin)
    if url.username or url.password or url.path or url.query or url.fragment or not url.hostname:
        raise ValueError('Use an exact origin such as https://vpn.example.org, without a path.')
    # Plain HTTP is permitted only for a loopback SSH-forwarded browser.
    local = url.hostname == 'localhost'
    try:
        local = local or ipaddress.ip_address(url.hostname).is_loopback
    except ValueError:
        pass
    if url.scheme != 'https' and not (url.scheme == 'http' and local):
        raise ValueError('Remote browser access requires HTTPS.')
    _ = url.port  # Validate the port syntax.
    return url.scheme == 'https'


class Accounts:
    def __init__(self, directory, initialize=False, clock=time.time):
        self.clock = clock
        self.lock = threading.RLock()
        root = pathlib.Path(directory)
        if any(p.is_symlink() for p in (root, *root.parents)):
            raise ValueError('Authentication paths must not be symlinks.')
        if not root.exists():
            if not initialize:
                raise ValueError('Initialize a private account directory before startup.')
            root.mkdir(mode=0o700, parents=True)
        if not root.is_dir():
            raise ValueError('Authentication storage must be a private directory.')
        if os.name == 'posix' and (root.stat().st_mode & 0o077):
            raise ValueError('Authentication directory requires mode 0700.')
        path = root / 'accounts.sqlite3'
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise ValueError('Invalid authentication database path.')
        if not path.exists():
            if not initialize:
                raise ValueError('No account database found. Refusing anonymous startup.')
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
        if os.name == 'posix' and (path.stat().st_mode & 0o077):
            raise ValueError('Authentication database requires mode 0600.')
        self.db = sqlite3.connect(path, timeout=5, check_same_thread=False)
        self.db.execute('PRAGMA foreign_keys=ON')
        if initialize:
            if self.db.execute('PRAGMA user_version').fetchone()[0] not in (0, 1):
                raise ValueError('Unsupported authentication database version.')
            with self.db:
                self.db.executescript('''
CREATE TABLE IF NOT EXISTS users(name TEXT PRIMARY KEY, role TEXT NOT NULL, salt TEXT NOT NULL, hash TEXT NOT NULL, revision INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, user TEXT NOT NULL REFERENCES users(name), csrf TEXT NOT NULL, created REAL NOT NULL, seen REAL NOT NULL, revision INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS attempts(bucket TEXT PRIMARY KEY, count INTEGER NOT NULL, started REAL NOT NULL, blocked REAL NOT NULL);
CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, time REAL NOT NULL, event TEXT NOT NULL, user TEXT);
PRAGMA user_version=1;
''')
        if self.db.execute('PRAGMA user_version').fetchone()[0] != 1:
            raise ValueError('Unsupported authentication database version.')
        # Equal work for an unknown account; never reveal whether the user exists.
        self.dummy_salt = secrets.token_hex(16)
        self.dummy_hash = '0' * 64

    def close(self):
        self.db.close()

    def audit(self, event, user=None):
        if event not in ('account-created', 'account-updated', 'login-rejected', 'login-blocked', 'login-success', 'logout'):
            raise ValueError('Unrecognized audit event.')
        self.db.execute('INSERT INTO audit(time,event,user) VALUES(?,?,?)', (self.clock(), event, user))
        self.db.execute('DELETE FROM audit WHERE id NOT IN (SELECT id FROM audit ORDER BY id DESC LIMIT 1000)')

    def put_user(self, name, password, role='admin', replace=False):
        if not isinstance(name, str) or not USERNAME.fullmatch(name) or role not in ('admin', 'viewer'):
            raise ValueError('Use a valid account name and admin/viewer role.')
        password_policy(password)
        with HASH_GATE:
            salt = secrets.token_hex(16)
            hashed = digest(password, salt)
        with self.lock, self.db:
            old = self.db.execute('SELECT revision FROM users WHERE name=?', (name,)).fetchone()
            if old and not replace:
                raise ValueError('Account exists. Use explicit replace to reset it.')
            if not old and self.db.execute('SELECT COUNT(*) FROM users').fetchone()[0] >= 32:
                raise ValueError('Maximum of 32 accounts.')
            self.db.execute('DELETE FROM sessions WHERE user=?', (name,))
            self.db.execute('INSERT INTO users VALUES(?,?,?,?,?) ON CONFLICT(name) DO UPDATE SET role=excluded.role,salt=excluded.salt,hash=excluded.hash,revision=excluded.revision', (name, role, salt, hashed, old[0]+1 if old else 1))
            self.audit('account-updated' if old else 'account-created', name)

    def login(self, name, password, address):
        if not isinstance(name, str) or not USERNAME.fullmatch(name) or not isinstance(password, str) or len(password) > 128:
            raise AuthError()
        try:
            address = str(ipaddress.ip_address(address))
        except ValueError:
            raise AuthError()
        if not HASH_GATE.acquire(blocking=False):
            raise AuthError(429, 'Login busy. Try again shortly.')
        try:
            with self.lock, self.db:
                now = self.clock()
                self.db.execute('DELETE FROM attempts WHERE blocked<=? AND started<?', (now, now-BLOCK))
                buckets = [('user:'+name, 5), ('ip:'+address, 30)]
                for bucket, limit in buckets:
                    row = self.db.execute('SELECT count,started,blocked FROM attempts WHERE bucket=?', (bucket,)).fetchone()
                    if row and (row[2] > now or now < row[1]):
                        self.audit('login-blocked')
                        self.db.commit()
                        raise AuthError(429, 'Too many attempts. Try again in 15 minutes.')
                # Bound the storage and reject new buckets rather than removing active blocks.
                count = self.db.execute('SELECT COUNT(*) FROM attempts').fetchone()[0]
                if count >= 1024:
                    raise AuthError(429, 'Login protection busy. Try again later.')
                for bucket, limit in buckets:
                    self.db.execute('INSERT INTO attempts VALUES(?,1,?,0) ON CONFLICT(bucket) DO UPDATE SET count=count+1', (bucket, now))
                    self.db.execute('UPDATE attempts SET blocked=? WHERE bucket=? AND count>=?', (now+BLOCK, bucket, limit))
                user = self.db.execute('SELECT role,salt,hash,revision FROM users WHERE name=?', (name,)).fetchone()
                salt, expected = (user[1], user[2]) if user else (self.dummy_salt, self.dummy_hash)
                verified = hmac.compare_digest(digest(password, salt), expected)
                if not user or not verified:
                    self.audit('login-rejected')
                    # Commit protection even though the request is rejected.
                    self.db.commit()
                    raise AuthError()
                self.db.execute('DELETE FROM attempts WHERE bucket=?', ('user:'+name,))
                self.db.execute('DELETE FROM sessions WHERE seen<? OR created<?', (now-IDLE, now-LIFETIME))
                sid, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
                self.db.execute('INSERT INTO sessions VALUES(?,?,?,?,?,?)', (hashlib.sha256(sid.encode()).hexdigest(), name, csrf, now, now, user[3]))
                self.db.execute('DELETE FROM sessions WHERE id NOT IN (SELECT id FROM sessions ORDER BY created DESC LIMIT 128)')
                self.audit('login-success', name)
                return sid, {'username': name, 'role': user[0], 'csrf': csrf}
        finally:
            HASH_GATE.release()

    def session(self, sid, csrf=None, admin=False, touch=True):
        if not isinstance(sid, str) or not TOKEN.fullmatch(sid):
            raise AuthError()
        hashed = hashlib.sha256(sid.encode()).hexdigest()
        with self.lock, self.db:
            row = self.db.execute('SELECT s.user,u.role,s.csrf,s.created,s.seen,s.revision,u.revision FROM sessions s JOIN users u ON u.name=s.user WHERE s.id=?', (hashed,)).fetchone()
            now = self.clock()
            if not row or not row[3] <= now < row[3]+LIFETIME or not row[4] <= now < row[4]+IDLE or row[5] != row[6]:
                self.db.execute('DELETE FROM sessions WHERE id=?', (hashed,))
                self.db.commit()
                raise AuthError()
            if csrf is not None and not hmac.compare_digest(str(csrf), row[2]):
                raise AuthError(403, 'Request verification failed.')
            if admin and row[1] != 'admin':
                raise AuthError(403, 'Administrator access required.')
            if touch:
                self.db.execute('UPDATE sessions SET seen=? WHERE id=?', (now, hashed))
            return {'username': row[0], 'role': row[1], 'csrf': row[2]}

    def logout(self, sid, csrf):
        with self.lock, self.db:
            user = self.session(sid, csrf)
            self.db.execute('DELETE FROM sessions WHERE id=?', (hashlib.sha256(sid.encode()).hexdigest(),))
            self.audit('logout', user['username'])

    def events(self, sid):
        self.session(sid, admin=True, touch=False)
        with self.lock:
            return [{'time': row[0], 'event': row[1], 'username': row[2]} for row in self.db.execute('SELECT time,event,user FROM audit ORDER BY id DESC LIMIT 200')]


def cookie_token(header, secure):
    cookies = SimpleCookie()
    try:
        cookies.load(header or '')
        value = cookies.get('__Host-vpn_session' if secure else 'vpn_local_session')
        return value.value if value else ''
    except Exception:
        return ''


def cookie_header(sid, secure, clear=False):
    name = '__Host-vpn_session' if secure else 'vpn_local_session'
    return name+'='+sid+'; Path=/; HttpOnly; SameSite=Strict'+('; Secure' if secure else '')+'; Max-Age='+('0' if clear else str(LIFETIME))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Create/reset a local account interactively; no default passwords.')
    parser.add_argument('--directory', required=True)
    parser.add_argument('--username', required=True)
    parser.add_argument('--role', choices=('admin', 'viewer'), default='admin')
    parser.add_argument('--replace', action='store_true')
    args = parser.parse_args()
    password = getpass.getpass('New passphrase (at least 15 characters): ')
    if password != getpass.getpass('Repeat passphrase: '):
        parser.error('Passphrases differ.')
    store = Accounts(args.directory, initialize=True)
    try:
        store.put_user(args.username, password, args.role, args.replace)
    finally:
        store.close()
    print('Account saved. No password was printed or stored in plaintext.')
