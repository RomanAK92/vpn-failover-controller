"""Private prepare/preview broker. No live apply or networking operations.

Only a future reviewed driver may turn a prepared generation into a running VPN.
This service never accepts a shell command, path, health assertion or apply verb.
"""
import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import pathlib
import re
import socket
import socketserver
import stat
import sqlite3
import struct
import subprocess
import sys
import threading

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'dashboard'))
from drafts import Drafts, DraftError, IDENTIFIER, MAX_BYTES
from generations import Generations
from journal import TransactionError
from plan import preview

MAX_REQUEST = MAX_BYTES + 8192  # JSON escaping overhead is bounded too.
MAX_RESPONSE = 32768
SOCKET_OWNER = 'vpn-prepare-broker-v1'


def receive(connection, limit):
    def exact(n):
        result = bytearray()
        while len(result) < n:
            chunk = connection.recv(n-len(result))
            if not chunk:
                raise ValueError('Incomplete private request.')
            result.extend(chunk)
        return bytes(result)
    size = struct.unpack('!I', exact(4))[0]
    if not 1 <= size <= limit:
        raise ValueError('Private request size is outside the permitted bound.')
    return json.loads(exact(size).decode('utf8'))


def send(connection, value, limit):
    data = json.dumps(value, separators=(',', ':')).encode('utf8')
    if len(data) > limit:
        raise ValueError('Private response exceeded its bound.')
    connection.sendall(struct.pack('!I', len(data))+data)


class PrepareBroker:
    def __init__(self, directory, validator):
        self.generations = Generations(directory)
        for private in (self.generations.root, self.generations.generations):
            if private.stat().st_uid != os.geteuid() or private.stat().st_mode & 0o077:
                raise ValueError('The broker must own its dedicated private generation directories.')
        self.store = Drafts(self.generations.generations, validator)
        self.validator = pathlib.Path(validator)
        self.lock = threading.Lock()

    def load(self, identifier):
        """Read only validated root-owned private data, never a caller's path."""
        self.generations.target(identifier)
        directory = self.store.root/identifier
        self.store.inspect(identifier)
        receipt = json.loads((directory/'manifest.json').read_text())
        hashes = receipt.get('sha256')
        if not isinstance(hashes, dict) or not 3 <= len(hashes) <= 12:
            raise DraftError('Invalid generation receipt.')
        files = {}
        total = 0
        for name, digest in hashes.items():
            if (not isinstance(name, str) or '/' in name or '\\' in name or name in ('.', '..')
                or not isinstance(digest, str) or len(digest) != 64):
                raise DraftError('Invalid generation receipt.')
            path = directory/name
            attributes = path.lstat()
            if (not stat.S_ISREG(attributes.st_mode) or attributes.st_nlink != 1
                or attributes.st_mode & 0o077 or attributes.st_uid != os.geteuid()
                or attributes.st_size > MAX_BYTES):
                raise DraftError('Unsafe private generation file.')
            data = path.read_bytes()
            total += len(data)
            if total > MAX_BYTES or hashlib.sha256(data).hexdigest() != digest:
                raise DraftError('Private generation integrity failed.')
            files[name] = data.decode('utf8')
        _, required = Drafts.check_bundle(files)
        if set(files) != required:
            raise DraftError('Generation file set does not match its receipt.')
        result = subprocess.run([sys.executable, str(self.validator), '--config-dir', str(directory),
            '--files-only', '--json'], capture_output=True, timeout=15)
        if result.returncode:
            raise DraftError('The engine rejected the private generation.')
        return files

    def dispatch(self, request):
        if not isinstance(request, dict) or not isinstance(request.get('action'), str):
            raise ValueError('A structured private command is required.')
        action = request['action']
        with self.lock:
            if action == 'status' and set(request) == {'action'}:
                pointer = self.generations.root/'active'
                active = self.generations.active() if pointer.exists() or pointer.is_symlink() else None
                return {'active_generation': active,
                        'prepared': [{**item, 'state': 'prepared'} for item in self.store.entries()],
                        'archived': self.store.archived(),
                        'live_apply_enabled': False}
            if action in ('archive', 'restore') and set(request) == {'action', 'generation'}:
                generation=request['generation']
                if not isinstance(generation,str) or not IDENTIFIER.fullmatch(generation):
                    raise ValueError('Invalid generation identifier.')
                if action == 'archive':
                    if self.generations.active() == generation:
                        raise ValueError('Selected settings cannot be archived.')
                    for pointer in self.generations.root.iterdir():
                        if pointer.name.startswith(('candidate-','recovery-')):
                            if not pointer.is_symlink():raise ValueError('Unexpected recovery data; inspect privately.')
                            target=os.readlink(pointer)
                            if not re.fullmatch(r'generations/[a-f0-9]{32}',target):
                                raise ValueError('Invalid recovery reference.')
                            if target == 'generations/'+generation:
                                raise ValueError('Recovery settings cannot be archived.')
                return self.store.move_archive(generation,restore=action=='restore')
            if action == 'prepare' and set(request) == {'action', 'files', 'label'}:
                result = self.store.save(request['files'], request['label'])
                return {**result, 'state': 'prepared', 'applied': False}
            if action == 'preview' and set(request) == {'action', 'generation'}:
                candidate = request['generation']
                if not isinstance(candidate, str) or not IDENTIFIER.fullmatch(candidate):
                    raise ValueError('Invalid generation identifier.')
                old = self.load(self.generations.active())
                new = self.load(candidate)
                result = preview(json.loads(old['controller.json']), json.loads(old['deployment.json']),
                                 json.loads(new['controller.json']), json.loads(new['deployment.json']))
                return {'generation': candidate, **result}
            raise ValueError('This private broker permits status, prepare and preview only.')


class BrokerServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True
    request_queue_size = 4

    def __init__(self, path, broker, allowed_uids=(0, 65532)):
        self.broker = broker
        self.allowed_uids = frozenset(allowed_uids)
        self.slots = threading.BoundedSemaphore(4)
        super().__init__(str(path), BrokerHandler)

    def process_request(self, request, address):
        if not self.slots.acquire(blocking=False):
            request.close()
            return
        try:
            super().process_request(request, address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            self.slots.release()

    def handle_error(self, *_):
        # No traceback or request content: the payload can contain private keys.
        print('Private broker request failed; no credential content logged.', flush=True)


class BrokerHandler(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.settimeout(5)
        _, uid, _ = struct.unpack('3i', self.request.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
        if uid not in self.server.allowed_uids:
            return
        try:
            request = receive(self.request, MAX_REQUEST)
            response = {'ok': True, 'result': self.server.broker.dispatch(request)}
        except (ValueError, OSError, UnicodeError, KeyError, TypeError, TransactionError,
                subprocess.TimeoutExpired, sqlite3.OperationalError):
            response = {'ok': False, 'error': 'Private preparation rejected. Review settings, storage and engine validation.'}
        send(self.request, response, MAX_RESPONSE)


@contextlib.contextmanager
def socket_directory(path):
    """Root-owned socket directory; web can connect but cannot replace its files."""
    path = pathlib.Path(path)
    if not path.is_absolute() or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('Use a dedicated absolute socket directory.')
    receipt = path/'owner.json'
    if not path.exists():
        path.mkdir(mode=0o750)
        os.chown(path, 0, 65532)
        os.chmod(path, 0o2750)  # Socket inherits web GID without CAP_CHOWN in a restricted service.
        fd = os.open(receipt, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w') as out:
            json.dump({'owner': SOCKET_OWNER}, out)
    if (not path.is_dir() or path.stat().st_uid != 0 or path.stat().st_gid != 65532
        or stat.S_IMODE(path.stat().st_mode) not in (0o750, 0o2750) or receipt.is_symlink()
        or not receipt.is_file() or receipt.stat().st_size > 1024
        or receipt.stat().st_uid != 0 or receipt.stat().st_mode & 0o077
        or json.loads(receipt.read_text()) != {'owner': SOCKET_OWNER}):
        raise ValueError('Socket directory ownership is not established.')
    descriptor = os.open(path/'broker.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        attributes = os.fstat(descriptor)
        if (not stat.S_ISREG(attributes.st_mode) or attributes.st_nlink != 1
            or attributes.st_uid != 0 or attributes.st_mode & 0o077):
            raise ValueError('Invalid private broker lock.')
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        target = path/'prepare.sock'
        if target.exists() or target.is_symlink():
            attributes = target.lstat()
            if not stat.S_ISSOCK(attributes.st_mode) or attributes.st_uid != 0:
                raise ValueError('Refusing to replace unrelated socket data.')
            target.unlink()  # A previous owned server exited; ownership lock is held.
        yield target
    finally:
        os.close(descriptor)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--generation-dir', required=True)
    parser.add_argument('--socket-dir', required=True)
    parser.add_argument('--validator', required=True)
    args = parser.parse_args()
    if sys.platform != 'linux' or os.geteuid() != 0:
        parser.error('This private service requires its reviewed Linux root deployment.')
    os.umask(0o077)
    broker = PrepareBroker(args.generation_dir, args.validator)
    with socket_directory(args.socket_dir) as target:
        with BrokerServer(target, broker) as server:
            if target.stat().st_uid != 0 or target.stat().st_gid != 65532:
                raise ValueError('Preinitialize the socket directory with root ownership, web GID and mode 2750.')
            os.chmod(target, 0o660)
            server.serve_forever(poll_interval=.2)


if __name__ == '__main__':
    main()
