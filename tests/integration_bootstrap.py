"""Test guided preparation and its web/mirror only; never start its VPN engine."""
import json
import os
import pathlib
import secrets
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = pathlib.Path(__file__).parents[1]
sys.path.insert(0, str(ROOT/'tests'))
from test_bootstrap import BootstrapTests, bootstrap
from test_dashboard import fixture


def run(*args):
    p = subprocess.run(args, text=True, capture_output=True, timeout=180)
    if p.returncode:
        raise RuntimeError('Guided setup acceptance failed: '+args[0])
    return p.stdout


def main():
    if os.name != 'posix' or os.geteuid() != 0:
        raise SystemExit('Use a disposable Linux Docker host as root.')
    project = 'vpn-guided-'+secrets.token_hex(4)
    original = run('docker', 'ps', '-a', '--format', '{{.Names}} {{.State}}').splitlines()
    default = run('ip', 'route', 'show', 'default')
    setup = BootstrapTests()
    setup.setUp()
    destination = setup.root/'installation'
    command = ['docker', 'compose', '--project-name', project, '-f', str(destination/'compose.yaml')]
    password = secrets.token_urlsafe(24)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    origin = 'http://127.0.0.1:'+str(port)
    try:
        previous_umask = os.umask(0o077)
        try:
            result = bootstrap.prepare(destination, setup.config, 'admin', password)
        finally:
            os.umask(previous_umask)
        assert result['prepared'] and not result['started']
        assert (destination/'data/accounts').stat().st_uid == 65532
        assert (destination/'data/accounts/accounts.sqlite3').stat().st_uid == 65532
        assert (destination/'config/wg-client-peer-1.key').stat().st_mode & 0o777 == 0o600
        override = setup.root/'override.json'
        override.write_text(json.dumps({'services': {
            'vpn-router': {'image': project+'-engine:test', 'restart': 'no'},
            'vpn-mirror': {'image': project+'-web:test', 'restart': 'no'},
            'vpn-dashboard': {'image': project+'-web:test', 'restart': 'no',
                'command': ['python3', 'server.py', '--bind', '127.0.0.1', '--port', str(port),
                            '--auth-dir', '/auth', '--origin', origin, '--history', '/history', '--draft-dir', '/drafts']}}}))
        command += ['-f', str(override)]
        parsed = json.loads(run(*command, 'config', '--format', 'json'))
        assert parsed['services']['vpn-mirror']['network_mode'] == 'none'
        assert parsed['services']['vpn-dashboard']['cap_drop'] == ['ALL']
        assert all('/etc/vpn' not in v['target'] for v in parsed['services']['vpn-dashboard']['volumes'])
        run(*command, 'build', 'vpn-dashboard')
        # Synthetic telemetry proves sanitation and UID boundaries. No engine is
        # started and no claimed encrypted application acceptance is made here.
        status = fixture()
        status['monotonic'] = time.monotonic()
        watchdog = {'monotonic': time.monotonic(), 'controller': True, 'ike': True, 'integrity': True,
                    'secret': 'DO-NOT-EXPORT'}
        for name, data in [('status.json', status), ('watchdog.json', watchdog)]:
            (destination/'data/runtime'/name).write_text(json.dumps(data))
            (destination/'data/runtime'/name).chmod(0o600)
        run(*command, 'up', '-d', '--no-build', 'vpn-mirror', 'vpn-dashboard')
        for _ in range(100):
            try:
                with urllib.request.urlopen(origin+'/api/auth', timeout=.5) as p:
                    assert json.load(p)['mode'] == 'accounts'
                break
            except OSError:
                time.sleep(.1)
        else:
            raise RuntimeError('Prepared web service unavailable.')
        request = urllib.request.Request(origin+'/api/login',
            data=json.dumps({'username': 'admin', 'password': password}).encode(),
            headers={'Origin': origin, 'X-VPN-Request': '1', 'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout=5) as p:
            cookie = p.headers['Set-Cookie'].split(';')[0]
            session = json.load(p)
            assert session['role'] == 'admin'
        for _ in range(50):
            with urllib.request.urlopen(urllib.request.Request(origin+'/api/status', headers={'Cookie': cookie}), timeout=5) as p:
                data = p.read().decode()
            if json.loads(data)['available']:
                break
            time.sleep(.1)
        assert json.loads(data)['available']
        assert 'DO-NOT-EXPORT' not in data and password not in data
        files = {p.name: p.read_text() for p in setup.config.iterdir()}
        # Remove unused template peers for the strict guided draft format.
        peers = json.loads(files['peers.json'])
        files['peers.json'] = json.dumps({k: peers[k] for k in ('peer-1', 'peer-2')})
        request = urllib.request.Request(origin+'/api/drafts',
            data=json.dumps({'label': 'Prepared office draft', 'files': files}).encode(),
            headers={'Origin': origin, 'X-VPN-Request': '1', 'Content-Type': 'application/json',
                     'Cookie': cookie, 'X-CSRF-Token': session['csrf']})
        with urllib.request.urlopen(request, timeout=5) as p:
            assert p.status == 201
            draft = json.load(p)
            assert not draft['applied']
        assert (destination/'data/drafts'/draft['id']/'wg-client-peer-1.key').stat().st_uid == 65532
        assert run('ip', 'route', 'show', 'default') == default
        current = run('docker', 'ps', '-a', '--format', '{{.Names}} {{.State}}').splitlines()
        assert all(x in current for x in original)
        assert not any(x.startswith(project+'-vpn-router') for x in current)
        print(json.dumps({'passed': True, 'checks': 14,
            'scope': 'guided private preparation, mirror, accounts and validated drafts; VPN engine not started'}), flush=True)
    finally:
        subprocess.run(command+['down', '--remove-orphans'], capture_output=True, timeout=30)
        subprocess.run(['docker', 'image', 'rm', project+'-web:test'], capture_output=True, timeout=30)
        setup.tearDown()
        print('Owned guided setup resources cleaned', flush=True)


if __name__ == '__main__':
    main()
