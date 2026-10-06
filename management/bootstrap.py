"""Prepare an owned private VPN installation; never starts Docker or changes routes."""
import argparse
import getpass
import hashlib
import json
import os
import pathlib
import re
import secrets
import shutil
import stat
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'build'))
sys.path.insert(0, str(ROOT/'dashboard'))
from accounts import Accounts
from configuration import normalize
from tls_proxy import render as render_tls
from urllib.parse import urlsplit

OWNER = 'vpn-management-bootstrap-v1'
NGINX_IMAGE = 'nginxinc/nginx-unprivileged@sha256:15c994d10d6d78658721c3bcafff14cb281fba2a4bdf9d5ba92c416a472516e3'


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


def compose(managed=False):
    result = '''# vpn-management-bootstrap-v1; engine is the only network administrator.
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
    tmpfs: ["/tmp:rw,noexec,nosuid,size=16m", "/run:rw,nosuid,size=16m"]
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
    if managed:
        result = result.replace('    volumes: [./config:/etc/vpn:ro, ./data/runtime:/run/vpn-router:rw]',
            '    entrypoint: [python3, -u, /app/management/manager.py]\n'
            '    command: [--management-dir, /management, --socket-dir, /control, --application-file, /management/readiness.json]\n'
            '    volumes: [./data/management:/management:rw, ./data/control:/control:rw, ./data/runtime:/run/vpn-router:rw]')
        result = result.replace('--draft-dir, /drafts]', '--draft-dir, /drafts, --control-dir, /control]')
        result = result.replace('./data/drafts:/drafts:rw]', './data/drafts:/drafts:rw, ./data/control:/control:ro]')
    return result


def management_stage(stage, config, application):
    """Persistent disk generations; prepare only, never touches host networking."""
    sys.path.insert(0, str(ROOT/'management'))
    from broker import PrepareBroker, SOCKET_OWNER
    from driver import ApplicationProbe
    from journal import Journal
    ApplicationProbe(application, config['subnet'])  # Validate without calling it.
    source = stage/'engine/management'
    source.mkdir(mode=0o755)
    for name in ('driver.py', 'manager.py', 'operational.py', 'broker.py', 'coordinator.py', 'journal.py',
                 'generations.py', 'plan.py', 'rollback_watch.py'):
        shutil.copyfile(ROOT/'management'/name, source/name)
        (source/name).chmod(0o644)
    support = stage/'engine/broker_support'; support.mkdir(mode=0o755)
    shutil.copyfile(ROOT/'dashboard/drafts.py', support/'drafts.py')
    (support/'drafts.py').chmod(0o644)
    with (stage/'engine/Dockerfile').open('a') as out:
        out.write('\nCOPY management /app/management/\nCOPY broker_support /app/dashboard/\n'
                  'RUN test ! -e /etc/vpn && ln -s /management/active /etc/vpn\n')
    private = stage/'data/management'; private.mkdir(mode=0o700)
    (private/'generations').mkdir(mode=0o700)
    store = PrepareBroker(private, ROOT/'build/doctor.py')
    files = {p.name: p.read_text() for p in (stage/'config').iterdir()}
    generation = store.store.save(files, 'Initial installation')['id']
    store.generations.initialize(generation)
    journal = Journal(private, pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip())
    try: journal.initialize(generation)
    finally: journal.close()
    readiness = private/'readiness.json'
    readiness.write_text(json.dumps(application)); readiness.chmod(0o600)
    control = stage/'data/control'; control.mkdir(mode=0o750)
    os.chown(control, 0, 65532); control.chmod(0o2750)
    (control/'owner.json').write_text(json.dumps({'owner': SOCKET_OWNER}))
    (control/'owner.json').chmod(0o600)
    return generation


def https_stage(stage, settings):
    if not isinstance(settings, dict) or set(settings) not in ({'origin', 'bind', 'directory'}, {'origin', 'bind', 'directory','allowed_cidrs'}):
        raise ValueError('Provide an exact HTTPS origin, private bind and certificate directory.')
    proof=secrets.token_hex(32)
    conf = render_tls(settings['origin'], settings['bind'], proxy_proof=proof,allowed_cidrs=settings.get('allowed_cidrs',[]))
    source = directory(settings['directory'])
    files = {}
    for name, limit in (('fullchain.pem', 65536), ('privkey.pem', 16384)):
        attributes = (source/name).lstat()
        if (not stat.S_ISREG(attributes.st_mode) or attributes.st_nlink != 1 or attributes.st_size > limit
            or (name == 'privkey.pem' and (attributes.st_uid != 0 or attributes.st_mode & 0o077))):
            raise ValueError('Use a bounded certificate and root-owned mode0600 private key without symlinks.')
        files[name] = (source/name).read_bytes()
    tls = stage/'data/tls'; tls.mkdir(mode=0o750)
    os.chown(tls, 0, 101)
    for name, data in files.items():
        (tls/name).write_bytes(data); os.chown(tls/name, 0, 101); (tls/name).chmod(0o640)
    def check(*args):
        result = subprocess.run(['openssl', *args], capture_output=True, stdin=subprocess.DEVNULL, timeout=5)
        if result.returncode: raise ValueError('Certificate validity, name or key check failed.')
        return result.stdout.strip()
    check('x509','-in',str(tls/'fullchain.pem'),'-noout','-checkend','3600')
    hostname = urlsplit(settings['origin']).hostname
    import ipaddress
    try: ipaddress.ip_address(hostname); flag = '-checkip'
    except ValueError: flag = '-checkhost'
    match = check('x509','-in',str(tls/'fullchain.pem'),'-noout',flag,hostname)
    # OpenSSL x509 reports name mismatches with exit0; require its explicit
    # positive verdict instead of treating successful command execution as a match.
    expected = ('IP ' if flag == '-checkip' else 'Hostname ')+hostname+' does match certificate'
    if match != expected.encode('ascii'):
        raise ValueError('Certificate does not match the requested private HTTPS name.')
    public_cert=check('x509','-in',str(tls/'fullchain.pem'),'-pubkey','-noout')
    public_key=check('pkey','-in',str(tls/'privkey.pem'),'-pubout')
    if public_cert != public_key: raise ValueError('Certificate and private key do not match.')
    conf_path=stage/'data/https.conf'; conf_path.write_text(conf)
    os.chown(conf_path,0,101); conf_path.chmod(0o640)
    proof_path=stage/'data/accounts/ingress.key';proof_path.write_text(proof+'\n')
    os.chown(proof_path,65532,65532);proof_path.chmod(0o600)
    return '''  vpn-dashboard-https:
    image: "'''+NGINX_IMAGE+'''"
    network_mode: host
    user: "101:101"
    restart: unless-stopped
    read_only: true
    cap_drop: [ALL]
    security_opt: [no-new-privileges:true]
    pids_limit: 64
    mem_limit: 64m
    entrypoint: [nginx]
    command: [-c, /etc/nginx/nginx.conf, -g, "daemon off;"]
    tmpfs: ["/tmp:rw,noexec,nosuid,size=16m,uid=101,gid=101,mode=0700"]
    volumes: [./data/https.conf:/etc/nginx/nginx.conf:ro, ./data/tls:/tls:ro]
    logging: {driver: json-file, options: {max-size: 5m, max-file: "2"}}
'''


def sync_stage(stage):
    """Persist owned complete files/directories before publishing the installation."""
    for current, dirs, files in os.walk(stage, followlinks=False):
        for name in files:
            path=pathlib.Path(current)/name
            fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
            try: os.fsync(fd)
            finally: os.close(fd)
    directories=[stage]+[p for p in stage.rglob('*') if p.is_dir() and not p.is_symlink()]
    for path in reversed(directories):
        fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try: os.fsync(fd)
        finally: os.close(fd)


def prepare(destination, source, username, password, managed=False, application=None, https=None):
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
        for name in ('Dockerfile', 'accounts.py', 'drafts.py', 'control.py', 'history.py', 'server.py', 'mirror.py',
                     'index.html', 'app.js', 'profiles.js', 'login.js', 'drafts.js', 'management.js', 'style.css'):
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
        generation = management_stage(stage, c, application) if managed else None
        distribution = compose(managed)
        if https is not None:
            proxy = https_stage(stage, https)
            distribution = distribution.replace('--origin, http://127.0.0.1:8787,',
                '--origin, '+json.dumps(https['origin'])+', --trusted-proxy-file, /auth/ingress.key,')+proxy
        (stage/'compose.yaml').write_text(distribution)
        (stage/'compose.yaml').chmod(0o600)
        manifest = {'owner': OWNER, 'paths': len(c['paths']), 'managed': managed,
            'initial_generation': generation, 'live_apply_enabled': False, 'https_enabled': https is not None,
            'source_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                              for folder in ('build', 'dashboard', 'management')
                              for p in (ROOT/folder).iterdir() if p.is_file()}}
        (stage/'installation.json').write_text(json.dumps(manifest, indent=2)+'\n')
        (stage/'installation.json').chmod(0o600)
        # No credential values are included in this receipt.
        sync_stage(stage)
        stage.rename(dest)
        fd=os.open(dest.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try: os.fsync(fd)
        finally: os.close(fd)
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
    p.add_argument('--managed', action='store_true', help='Development persistent manager, with live Apply disabled')
    p.add_argument('--application-address', help='Reliable office HTTP application readiness IPv4')
    p.add_argument('--application-port', type=int, default=80)
    p.add_argument('--application-path', default='/')
    p.add_argument('--application-scheme', choices=('http', 'https', 'tcp'), default='http')
    p.add_argument('--https-origin', help='Optional exact private HTTPS origin, e.g. https://vpn.example.org:8443')
    p.add_argument('--https-bind', help='Specific private/VPN IPv4 address; never 0.0.0.0')
    p.add_argument('--tls-dir', help='Private fullchain.pem and mode0600 privkey.pem directory')
    p.add_argument('--https-allow-cidr',action='append',default=[],help='Explicit permitted private/VPN client network, /16 or narrower')
    args = p.parse_args()
    try:
        destination = directory(args.destination)
        c, _ = validate_config(args.config_dir)
        https = None
        if any((args.https_origin,args.https_bind,args.tls_dir)):
            https = {'origin':args.https_origin,'bind':args.https_bind,'directory':args.tls_dir,'allowed_cidrs':args.https_allow_cidr}
            render_tls(args.https_origin,args.https_bind,allowed_cidrs=args.https_allow_cidr)
            directory(args.tls_dir)
        application = {'address': args.application_address, 'port': args.application_port,
                       'path': args.application_path, 'scheme': args.application_scheme}
        if args.managed:
            sys.path.insert(0, str(ROOT/'management'))
            from driver import ApplicationProbe
            ApplicationProbe(application, c['subnet'])
        if not args.prepare:
            print('Validated '+str(len(c['paths']))+' tunnels. Destination: '+str(destination))
            print('Preview only. Repeat with sudo and --prepare to create private files and the administrator account.')
            return
        username = input('Administrator username (lowercase, at least 3 characters): ').strip()
        password = getpass.getpass('Administrator passphrase (at least 15 characters): ')
        if password != getpass.getpass('Repeat passphrase: '):
            raise ValueError('Passphrases differ.')
        print(json.dumps(prepare(destination, args.config_dir, username, password, args.managed, application, https)))
        print('Prepared, not running. Review Compose and perform network preflight before startup. No routes or firewall rules changed.')
    except (ValueError, OSError, KeyError, TypeError, subprocess.TimeoutExpired):
        p.exit(1, 'Preparation failed. Check paths, credentials and doctor.py results; no networking was changed.\n')


if __name__ == '__main__':
    main()
