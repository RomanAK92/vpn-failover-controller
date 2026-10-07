"""Isolated Compose account bootstrap/recreation acceptance; no live VPN writes."""
import json
import os
import pathlib
import secrets
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).parents[1]


def run(*args, input=None, check=True):
    result = subprocess.run(args, input=input, text=True, capture_output=True, timeout=180)
    if check and result.returncode:
        raise RuntimeError('Compose acceptance command failed: '+args[0])
    return result


def main():
    if os.name != 'posix' or os.geteuid() != 0:
        raise SystemExit('Use a disposable Linux Docker host as root.')
    project = 'vpn-account-compose-'+secrets.token_hex(4)
    private = pathlib.Path(tempfile.mkdtemp(prefix=project+'-'))
    os.chmod(private, 0o700)
    before = run('docker', 'ps', '-a', '--format', '{{.Names}} {{.State}}').stdout.splitlines()
    route = run('ip', 'route', 'show', 'default').stdout
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    origin = 'http://127.0.0.1:'+str(port)
    telemetry = private/'telemetry'
    telemetry.mkdir(mode=0o755)
    # UID65532 needs traverse access to this test-only directory. Credential
    # storage lives in Compose's private volume, never this fixture directory.
    os.chmod(private, 0o755)
    override = private/'override.json'
    override.write_text(json.dumps({'services': {'vpn-dashboard': {
        'image': project+':test',
        'restart': 'no',
        'command': ['python3', 'server.py', '--bind', '127.0.0.1', '--port', str(port),
                    '--auth-dir', '/auth', '--origin', origin, '--history', '/history'],
        'volumes': [str(telemetry)+':/telemetry:ro'],
        'healthcheck': {'test': ['CMD', 'python3', '-c',
            "import urllib.request; urllib.request.urlopen('"+origin+"/api/auth',timeout=2).close()"]}
    }}}))
    command = ['docker', 'compose', '--project-name', project, '-f',
               str(ROOT/'dashboard/compose.accounts.yaml'), '-f', str(override)]
    password = secrets.token_urlsafe(24)
    checks = 0

    def request(path, data=None, headers=None):
        h = {'Origin': origin, 'X-VPN-Request': '1', 'Content-Type': 'application/json'}
        h.update(headers or {})
        req = urllib.request.Request(origin+path, headers=h,
            data=json.dumps(data).encode() if data is not None else None)
        try:
            response = urllib.request.urlopen(req, timeout=5)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            return response.status, response.headers, json.load(response)

    def ready():
        for _ in range(100):
            try:
                if request('/api/auth')[0] == 200:
                    return
            except OSError:
                pass
            time.sleep(.1)
        raise RuntimeError('Account service did not become ready.')

    try:
        rendered = json.loads(run(*command, 'config', '--format', 'json').stdout)
        assert rendered['services']['vpn-dashboard']['read_only'] is True
        assert rendered['services']['vpn-dashboard']['cap_drop'] == ['ALL']
        assert rendered['services']['vpn-dashboard']['user'] == '65532:65532'
        checks += 1
        run(*command, 'build')
        # Empty storage must fail closed, rather than starting anonymous mode.
        empty = run(*command, 'run', '--rm', '--no-deps', 'vpn-dashboard', check=False)
        assert empty.returncode != 0
        checks += 1
        # Mimic the documented interactive bootstrap's storage permissions and
        # account API without placing a password in command arguments or logs.
        bootstrap = "from accounts import Accounts; import json,sys; a=Accounts('/auth',initialize=True); a.put_user('admin',json.load(sys.stdin)['password']); a.close()"
        run(*command, 'run', '--rm', '--no-deps', '-T', 'vpn-dashboard',
            'python3', '-c', bootstrap, input=json.dumps({'password': password}))
        run(*command, 'up', '-d', '--no-build')
        ready()
        assert request('/api/status')[0] == 401
        code, headers, session = request('/api/login', {'username': 'admin', 'password': password})
        assert code == 200
        cookie = headers['Set-Cookie'].split(';')[0]
        assert request('/api/status', headers={'Cookie': cookie})[0] == 200
        checks += 3
        run(*command, 'up', '-d', '--force-recreate', '--no-build')
        ready()
        assert request('/api/status', headers={'Cookie': cookie})[0] == 200
        checks += 1
        code, _, result = request('/api/accounts', {
            'username': 'admin', 'password': password+'-new', 'current_password': password,
            'role': 'admin', 'replace': True}, {'Cookie': cookie, 'X-CSRF-Token': session['csrf']})
        assert code == 200 and result['reauthenticate']
        assert request('/api/status', headers={'Cookie': cookie})[0] == 401
        run(*command, 'restart')
        ready()
        assert request('/api/login', {'username': 'admin', 'password': password+'-new'})[0] == 200
        checks += 3
        assert run('ip', 'route', 'show', 'default').stdout == route
        after = run('docker', 'ps', '-a', '--format', '{{.Names}} {{.State}}').stdout.splitlines()
        assert all(item in after for item in before)
        checks += 2
        print(json.dumps({'passed': True, 'checks': checks,
                         'scope': 'Compose bootstrap/recreation, not host reboot or version upgrade'}), flush=True)
    finally:
        # Compose project scopes every resource removal. No external volumes.
        run(*command, 'down', '-v', '--remove-orphans', check=False)
        run('docker', 'image', 'rm', project+':test', check=False)
        assert private.parent == pathlib.Path(tempfile.gettempdir()) and private.name.startswith(project+'-')
        shutil.rmtree(private)
        print('Owned account Compose resources cleaned', flush=True)


if __name__ == '__main__':
    main()
