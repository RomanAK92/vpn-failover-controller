"""Bounded private configuration drafts. No apply, Docker or networking access."""
import hashlib
import json
import os
import pathlib
import re
import secrets
import shutil
import subprocess
import sys
import threading

OWNER = 'vpn-private-draft-v1'
MAX_DRAFTS = 8
MAX_BYTES = 65536
IDENTIFIER = re.compile(r'[a-f0-9]{32}')
LOCK = threading.Lock()


class DraftError(ValueError):
    pass


class Drafts:
    def __init__(self, directory, validator):
        self.root = pathlib.Path(directory)
        self.validator = pathlib.Path(validator)
        if any(p.is_symlink() for p in (self.root, *self.root.parents)):
            raise DraftError('Draft paths must not be symlinks.')
        if not self.root.is_dir() or (os.name == 'posix' and self.root.stat().st_mode & 0o077):
            raise DraftError('Initialize a dedicated draft directory with mode 0700.')
        if self.validator.is_symlink() or not self.validator.is_file():
            raise DraftError('The reviewed engine validator is unavailable.')

    def entries(self):
        result = []
        for p in self.root.iterdir():
            if p.name.startswith('.pending-'):
                continue  # Interrupted staging is never an applicable generation.
            if not IDENTIFIER.fullmatch(p.name) or p.is_symlink() or not p.is_dir():
                raise DraftError('Unexpected data in the draft store; inspect privately.')
            result.append(self.inspect(p.name))
        return result

    def inspect(self, identifier):
        if not isinstance(identifier, str) or not IDENTIFIER.fullmatch(identifier):
            raise DraftError('Invalid draft identifier.')
        root = self.root/identifier
        receipt = root/'manifest.json'
        if root.is_symlink() or receipt.is_symlink() or not receipt.is_file() or receipt.stat().st_size > 16384:
            raise DraftError('Invalid draft receipt.')
        try:
            manifest = json.loads(receipt.read_text())
            if manifest['owner'] != OWNER or manifest['summary']['id'] != identifier:
                raise DraftError('Invalid draft ownership.')
            return manifest['summary']
        except (KeyError, TypeError, json.JSONDecodeError):
            raise DraftError('Draft receipt is unreadable.') from None

    @staticmethod
    def check_bundle(files):
        if not isinstance(files, dict) or not 3 <= len(files) <= 12:
            raise DraftError('Provide a bounded configuration package.')
        if any(not isinstance(k, str) or not isinstance(v, str) for k, v in files.items()):
            raise DraftError('Configuration files must be text.')
        if sum(len(v.encode('utf8')) for v in files.values()) > MAX_BYTES:
            raise DraftError('Configuration package exceeds 64 KiB.')
        try:
            c = json.loads(files['controller.json'])
            peers = json.loads(files['peers.json'])
            deployment = json.loads(files['deployment.json'])
            if not isinstance(c, dict) or c.get('schema_version') != 2 or c.get('ipsec_mode') != 'generated':
                raise DraftError('Use structured schema 2 generated settings.')
            allowed_controller = {'schema_version','subnet','targets','quorum','interval',
                                  'failure_rounds','recovery_rounds','ipsec_mode','paths'}
            if set(c) - allowed_controller:
                raise DraftError('Unsupported controller setting.')
            paths = c['paths']
            if not isinstance(paths, list) or not 1 <= len(paths) <= 4:
                raise DraftError('One to four tunnels are required.')
            names = {'controller.json', 'peers.json', 'deployment.json'}
            used = set()
            for p in paths:
                common = {'name','kind','peer','interface','address','source','table','priority',
                          'mark_priority','mark','mtu','mss'}
                kind = p['kind']
                extra = {'listen_port','keepalive'} if kind == 'wireguard' else {'if_id','connection'}
                if kind not in ('wireguard', 'ipsec') or set(p) - (common | extra):
                    raise DraftError('Unsupported tunnel setting.')
                peer = p['peer']
                if not isinstance(peer, str) or not re.fullmatch(r'[a-z][a-z0-9_-]{0,19}', peer):
                    raise DraftError('Invalid peer identifier.')
                used.add(peer)
                names.add(('wg-client-' if kind == 'wireguard' else 'ipsec-')+peer+'.key')
                allowed_peer = {'endpoint', 'port', 'public_key'} if kind == 'wireguard' else {
                    'endpoint','local_id','remote_id','ike_proposals','esp_proposals'}
                if not isinstance(peers[peer], dict) or set(peers[peer]) - allowed_peer:
                    raise DraftError('Unsupported peer setting.')
            if not isinstance(peers, dict) or set(peers) != used:
                raise DraftError('Peer list must match the selected tunnels.')
            if not isinstance(deployment, dict) or set(deployment) != {'app_subnet', 'publication'}:
                raise DraftError('Unsupported deployment setting.')
            if set(files) - (names | {'INSTALL.txt'}) or not names <= set(files):
                raise DraftError('Missing or unsupported configuration file. Scripts and raw IPsec imports are rejected.')
            return c, names
        except (KeyError, TypeError, json.JSONDecodeError, AttributeError):
            # Never echo parser text: it may contain credentials.
            raise DraftError('Invalid structured configuration package.') from None

    def save(self, files, label):
        if not isinstance(label, str) or not re.fullmatch(r'[A-Za-z0-9 _.-]{1,60}', label):
            raise DraftError('Use a short label containing letters, numbers, spaces, dots or dashes.')
        c, names = self.check_bundle(files)
        with LOCK:
            self.entries()
            if len(list(self.root.iterdir())) >= MAX_DRAFTS:
                raise DraftError('Eight drafts are retained. Private archival is required before adding more.')
            identifier = secrets.token_hex(16)
            stage = self.root/('.pending-'+identifier)
            stage.mkdir(mode=0o700)
            try:
                for name in sorted(names):
                    fd = os.open(stage/name, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
                    with os.fdopen(fd, 'w', encoding='utf8') as f:
                        f.write(files[name])
                        f.flush()
                        os.fsync(f.fileno())
                result = subprocess.run([sys.executable, str(self.validator), '--config-dir', str(stage),
                                         '--files-only', '--json'], capture_output=True, timeout=15)
                if result.returncode:
                    raise DraftError('The engine rejected this draft. Check its settings and credential formats.')
                summary = {'id': identifier, 'label': label, 'subnet': c['subnet'],
                    'probe_count': len(c['targets']), 'state': 'draft', 'applied': False,
                    'paths': [{'name': p['name'], 'kind': p['kind'], 'interface': p['interface']} for p in c['paths']]}
                receipt = {'owner': OWNER, 'summary': summary,
                    'sha256': {name: hashlib.sha256((stage/name).read_bytes()).hexdigest() for name in names}}
                fd = os.open(stage/'manifest.json', os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                with os.fdopen(fd, 'w', encoding='utf8') as f:
                    json.dump(receipt, f)
                    f.flush()
                    os.fsync(f.fileno())
                stage_fd = os.open(stage, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(stage_fd)
                finally:
                    os.close(stage_fd)
                stage.rename(self.root/identifier)
                directory_fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
                return summary
            finally:
                if stage.exists():
                    assert stage.parent == self.root and stage.name == '.pending-'+identifier
                    shutil.rmtree(stage)
