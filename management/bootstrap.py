"""Prepare an owned private VPN installation; never starts Docker or changes routes."""
import argparse
import getpass
import hashlib
import json
import os
import pathlib
import re
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'build'))
sys.path.insert(0, str(ROOT/'dashboard'))
from accounts import Accounts
from configuration import normalize

OWNER = 'vpn-management-bootstrap-v1'


def directory(value):
    p = pathlib.Path(value)
    if not p.is_absolute() or '..' in p.parts or not re.fullmatch(r'[/A-Za-z0-9_.-]+', str(p)):
        raise ValueError('Use a dedicated absolute Linux path without spaces.')
    if len(p.parts) < 3 or any(x.is_symlink() for x in (p, *p.parents)):
        raise ValueError('Use a dedicated directory without symlinks.')
    return p


def validate_config(source):
    """Reuse the engine's validator in a child process, without shared globals."""
    import subprocess
    source = directory(source)
    if not source.is_dir():
        raise ValueError('Configuration directory is missing.')
    # Generated mode has structured identities/proposals; arbitrary strongSwan
    # include directives and private filesystem paths are outside this installer.
    first = source/'controller.json'
    if first.is_symlink() or not first.is_file() or first.stat().st_size > 32768:
        raise ValueError('Controller file is missing, unsafe or too large.')
    c = normalize(json.loads(first.read_text()))
    if c['ipsec_mode'] != 'generated':
        raise ValueError('Guided installation requires generated IPsec mode.')
    names = {'controller.json', 'peers.json', 'deployment.json'}
    names |= {'wg-client-'+p['peer']+'.key' for p in c['paths'] if p['kind'] == 'wireguard'}
    names |= {'ipsec-'+p['peer']+'.key' for p in c['paths'] if p['kind'] == 'ipsec'}
    for name in names:
        p = source/name
        if p.is_symlink() or not p.is_file() or p.stat().st_size > 32768:
            raise ValueError('A required configuration file is missing, unsafe or too large.')
    result = subprocess.run([sys.executable, str(ROOT/'build/doctor.py'),
        '--config-dir', str(source), '--files-only', '--json'], capture_output=True, timeout=15)
    if result.returncode:
        raise ValueError('Engine validation failed. Check file formats and credential permissions with doctor.py.')
    return c, names


def compose():
    return '''# vpn-management-bootstrap-v1; engine is the only network administrator.
services:
  vpn-router:
    build: ./engine
    network_mode: host
    restart: unless-stopped
    read_only: true
    cap_drop: [ALL]
    cap_add: [NET_ADMIN, NET_RAW, NET_BIND_SERVICE]
    security_opt: [no-new-privileges:true]
    pids_limit: 128
    mem_limit: 256m
    stop_grace_period: 20s
    tmpfs: [/tmp:rw,noexec,nosuid,size=16m, /run:rw,nosuid,size=16m]
    volumes: [./config:/etc/vpn:ro, ./data/runtime:/run/vpn-router:rw]
    logging: {driver: json-file, options: {max-size: 10m, max-file: "3"}}
  vpn-mirror:
    build: ./web
    network_mode: none
    user: "0:0"
    restart: unless-stopped
    read_only: true
    cap_drop: [ALL]
    security_opt: [no-new-privileges:true]
    pids_limit: 32
    mem_limit: 64m
    command: [python3, mirror.py, --source, /runtime, --destination, /telemetry]
    volumes: [./data/runtime:/runtime:ro, ./data/telemetry:/telemetry:rw]
    logging: {driver: json-file, options: {max-size: 5m, max-file: "2"}}
  vpn-dashboard:
    build: ./web
    network_mode: host
    user: "65532:65532"
    restart: unless-stopped
    read_only: true
    cap_drop: [ALL]
    security_opt: [no-new-privileges:true]
    pids_limit: 64
    mem_limit: 128m
    command: [python3, server.py, --bind, 127.0.0.1, --port, "8787", --auth-dir, /auth, --origin, http://127.0.0.1:8787, --history, /history, --draft-dir, /drafts]
    volumes: [./data/telemetry:/telemetry:ro, ./data/accounts:/auth:rw, ./data/history:/history:rw, ./data/drafts:/drafts:rw]
    logging: {driver: json-file, options: {max-size: 5m, max-file: "2"}}
'''


def prepare(destination, source, username, password):
    if sys.platform != 'linux' or os.geteuid() != 0:
        raise ValueError('Preparation requires root on the separate Linux test host.')
    dest = directory(destination)
    if dest == ROOT or ROOT in dest.parents:
        raise ValueError('Private installations must be outside the source repository.')
    c, names = validate_config(source)
    if dest.exists():
        raise ValueError('Destination exists. This command does not overwrite or upgrade installations.')
    # Stage beside the destination and publish once complete. A failure leaves
    # no half-installed public directory and never changes the existing system.
    stage = dest.parent/('.'+dest.name+'-'+os.urandom(8).hex())
    stage.mkdir(mode=0o700)
    try:
        for d in ('engine', 'web', 'config', 'data', 'data/runtime', 'data/telemetry',
                  'data/accounts', 'data/history', 'data/drafts', 'web/validators'):
            (stage/d).mkdir(mode=0o700)
        for name in names:
            shutil.copyfile(pathlib.Path(source)/name, stage/'config'/name)
            (stage/'config'/name).chmod(0o600)
        for name in ('Dockerfile', *[p.name for p in (ROOT/'build').glob('*.py')], 'strongswan.conf'):
            shutil.copyfile(ROOT/'build'/name, stage/'engine'/name)
            (stage/'engine'/name).chmod(0o644)
        for name in ('Dockerfile', 'accounts.py', 'drafts.py', 'history.py', 'server.py', 'mirror.py',
                     'index.html', 'app.js', 'profiles.js', 'login.js', 'drafts.js', 'style.css'):
            shutil.copyfile(ROOT/'dashboard'/name, stage/'web'/name)
            (stage/'web'/name).chmod(0o644)
        for name in ('doctor.py', 'guard.py', 'configuration.py'):
            shutil.copyfile(ROOT/'build'/name, stage/'web/validators'/name)
            (stage/'web/validators'/name).chmod(0o644)
        (stage/'web/validators').chmod(0o755)
        with (stage/'web/Dockerfile').open('a') as f:
            f.write('\nCOPY validators /validators/\n')
        for d in ('data/accounts', 'data/history', 'data/drafts'):
            os.chown(stage/d, 65532, 65532)
        (stage/'data/runtime').chmod(0o700)
        (stage/'data/telemetry').chmod(0o755)
        a = Accounts(stage/'data/accounts', initialize=True)
        try:
            a.put_user(username, password)
        finally:
            a.close()
        os.chown(stage/'data/accounts/accounts.sqlite3', 65532, 65532)
        (stage/'compose.yaml').write_text(compose())
        (stage/'compose.yaml').chmod(0o600)
        manifest = {'owner': OWNER, 'paths': len(c['paths']),
            'source_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                              for folder in ('build', 'dashboard')
                              for p in (ROOT/folder).iterdir() if p.is_file()}}
        (stage/'installation.json').write_text(json.dumps(manifest, indent=2)+'\n')
        (stage/'installation.json').chmod(0o600)
        # No credential values are included in this receipt.
        stage.rename(dest)
    finally:
        if stage.exists():
            assert stage.parent == dest.parent and stage.name.startswith('.'+dest.name+'-')
            shutil.rmtree(stage)
    return {'owner': OWNER, 'paths': len(c['paths']), 'prepared': True, 'started': False}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config-dir', required=True)
    p.add_argument('--destination', default='/opt/vpn-system')
    p.add_argument('--prepare', action='store_true')
    args = p.parse_args()
    try:
        destination = directory(args.destination)
        c, _ = validate_config(args.config_dir)
        if not args.prepare:
            print('Validated '+str(len(c['paths']))+' tunnels. Destination: '+str(destination))
            print('Preview only. Repeat with sudo and --prepare to create private files and the administrator account.')
            return
        username = input('Administrator username (lowercase, at least 3 characters): ').strip()
        password = getpass.getpass('Administrator passphrase (at least 15 characters): ')
        if password != getpass.getpass('Repeat passphrase: '):
            raise ValueError('Passphrases differ.')
        print(json.dumps(prepare(destination, args.config_dir, username, password)))
        print('Prepared, not running. Review Compose and perform network preflight before startup. No routes or firewall rules changed.')
    except (ValueError, OSError, KeyError, TypeError):
        p.exit(1, 'Preparation failed. Check paths, credentials and doctor.py results; no networking was changed.\n')


if __name__ == '__main__':
    main()
