"""Offline encrypted VPN-settings backup. Never starts services or changes routes.

Restore creates a NEW private installation and a NEW administrator. It does not
restore login sessions, operational logs, old binaries or the whole Linux server.
Requires the distribution-maintained python3-cryptography package on the host.
"""
import argparse
import getpass
import hashlib
import json
import os
import pathlib
import stat
import sys
import tempfile
from bootstrap import ROOT, OWNER, directory, prepare
from broker import PrepareBroker
from driver import ApplicationProbe
from drafts import Drafts, MAX_BYTES
from journal import Journal

HEADER = b'VPN-SETTINGS-AES256GCM-SCRYPT-v1\x00'
MAX_ENCRYPTED = MAX_BYTES + 16384


def key(password, salt):
    if not isinstance(password, str) or not 15 <= len(password) <= 128 or len(password.encode('utf8')) > 512:
        raise ValueError('Use a backup passphrase of 15–128 characters.')
    return hashlib.scrypt(password.encode('utf8'), salt=salt, n=32768, r=8, p=1,
                          dklen=32, maxmem=64*1024*1024)


def encrypt(payload, password):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    plain = json.dumps(payload, separators=(',', ':'), ensure_ascii=False).encode('utf8')
    if len(plain) > MAX_ENCRYPTED - 128:
        raise ValueError('Backup exceeds the supported configuration bound.')
    salt, nonce = os.urandom(16), os.urandom(12)
    prefix = HEADER+salt+nonce
    return prefix+AESGCM(key(password, salt)).encrypt(nonce, plain, prefix)


def decrypt(content, password):
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    if (not isinstance(content, bytes) or not len(HEADER)+44 <= len(content) <= MAX_ENCRYPTED
        or not content.startswith(HEADER)):
        raise ValueError('Unsupported or oversized encrypted backup.')
    offset = len(HEADER)
    salt, nonce = content[offset:offset+16], content[offset+16:offset+28]
    try:
        plain = AESGCM(key(password, salt)).decrypt(nonce, content[offset+28:], content[:offset+28])
        payload = json.loads(plain.decode('utf8'))
    except (InvalidTag, UnicodeError, json.JSONDecodeError):
        raise ValueError('Backup authentication failed. Check passphrase and file integrity.') from None
    validate(payload)
    return payload


def validate(payload):
    if not isinstance(payload, dict) or set(payload) != {'schema', 'files', 'application'} or payload['schema'] != 1:
        raise ValueError('Unsupported backup schema.')
    config, names = Drafts.check_bundle(payload['files'])
    if set(payload['files']) != names:
        raise ValueError('Backup contains unsupported files.')
    ApplicationProbe(payload['application'], config['subnet'])


def private_file(path, limit):
    path = directory(path)
    attributes = path.lstat()
    if (not stat.S_ISREG(attributes.st_mode) or attributes.st_nlink != 1
        or attributes.st_uid != 0 or attributes.st_mode & 0o077 or attributes.st_size > limit):
        raise ValueError('Use a bounded root-owned private file with mode 0600.')
    return path.read_bytes()


def snapshot(installation):
    installation = directory(installation)
    if installation.stat().st_uid != 0 or installation.stat().st_mode & 0o077:
        raise ValueError('Use an owned private installation directory.')
    manifest = json.loads(private_file(installation/'installation.json', 32768))
    if manifest.get('owner') != OWNER or manifest.get('managed') is not True:
        raise ValueError('Only a managed installation can be backed up by this tool.')
    private = installation/'data/management'
    store = PrepareBroker(private, ROOT/'build/doctor.py')
    journal = Journal(private, pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip())
    try:
        with journal.read_only_snapshot() as state:
            if state['change'] and state['change']['phase'] in ('pending', 'rollback-requested'):
                raise ValueError('Finish or recover the pending change before creating a backup.')
            active = state['state']['active']
            if store.generations.active() != active:
                raise ValueError('Confirmed and selected settings disagree.')
            payload = {'schema': 1, 'files': store.load(active),
                       'application': json.loads(private_file(private/'readiness.json', 4096))}
            validate(payload)
            return payload
    finally: journal.close()


def write_backup(output, content):
    output = directory(output)
    if output == ROOT or ROOT in output.parents:
        raise ValueError('Backups belong outside the source repository.')
    parent = output.parent
    if parent.stat().st_uid != 0 or parent.stat().st_mode & 0o077:
        raise ValueError('Create a dedicated root-owned backup directory with mode 0700.')
    if not isinstance(content, bytes) or len(content) > MAX_ENCRYPTED or not content.startswith(HEADER):
        raise ValueError('Only bounded encrypted content may be saved.')
    fd = os.open(output, os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(content); stream.flush(); os.fsync(stream.fileno())
    fd = os.open(parent, os.O_RDONLY|os.O_DIRECTORY)
    try: os.fsync(fd)
    finally: os.close(fd)


def restore(payload, destination, username, password):
    validate(payload)
    destination = directory(destination)
    if destination.exists():
        raise ValueError('Restore requires a NEW directory; existing installations are never overwritten.')
    with tempfile.TemporaryDirectory(prefix='vpn-private-restore-') as temp:
        source = pathlib.Path(temp)
        source.chmod(0o700)
        for name, value in payload['files'].items():
            fd = os.open(source/name, os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, 'w', encoding='utf8') as stream: stream.write(value)
        return prepare(destination, source, username, password, managed=True, application=payload['application'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='action', required=True)
    export = commands.add_parser('export'); export.add_argument('--installation', required=True); export.add_argument('--output', required=True)
    import_ = commands.add_parser('restore'); import_.add_argument('--input', required=True); import_.add_argument('--destination', required=True)
    args = parser.parse_args()
    if sys.platform != 'linux' or os.geteuid() != 0:
        parser.error('Use root on the installation host; no remote automation is performed.')
    try:
        password = getpass.getpass('Backup encryption passphrase (at least 15 characters): ')
        if args.action == 'export':
            if password != getpass.getpass('Repeat backup passphrase: '): raise ValueError('Passphrases differ.')
            write_backup(args.output, encrypt(snapshot(args.installation), password))
            print('Encrypted confirmed VPN settings saved. Keep the passphrase separately.')
        else:
            payload = decrypt(private_file(args.input, MAX_ENCRYPTED), password)
            username = input('New administrator username: ').strip()
            account_password = getpass.getpass('New administrator passphrase: ')
            if account_password != getpass.getpass('Repeat administrator passphrase: '): raise ValueError('Passphrases differ.')
            restore(payload, args.destination, username, account_password)
            print('Restored into a new private installation. No services started or routes changed. Previous sessions were not restored.')
    except ImportError:
        parser.exit(1, 'Install the distribution-maintained python3-cryptography dependency before using backups.\n')
    except (ValueError, OSError, KeyError, TypeError):
        parser.exit(1, 'Backup/restore rejected. Check private permissions, state, passphrase and configuration validation.\n')


if __name__ == '__main__': main()
