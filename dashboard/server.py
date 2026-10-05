"""Read-only dashboard. Reads only sanitized telemetry, never VPN credentials."""
import argparse
import collections
import hmac
import ipaddress
import json
import math
import pathlib
import re
import threading
import time
import sys
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from history import History, MAX_AGE
from accounts import Accounts, AuthError, origin_policy, cookie_token, cookie_header
from urllib.parse import urlsplit
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = pathlib.Path(__file__).parent


def text(value, limit=160):
    return re.sub(r'[\x00-\x1f\x7f]', '', str(value))[:limit]


def number(value, default=0):
    return value if type(value) in (int, float) and math.isfinite(value) else default


def project(status, watchdog):
    """Explicit allowlist: unknown fields, diagnostics and secrets never leave here."""
    if not isinstance(status, dict) or not isinstance(watchdog, dict):
        raise ValueError('Invalid telemetry object')
    paths = status.get('paths', [])
    if not isinstance(paths, list) or not 1 <= len(paths) <= 4:
        raise ValueError('Invalid path count')
    if any(not isinstance(p, dict) for p in paths):
        raise ValueError('Invalid paths')
    names = [p['name'] for p in paths]
    if any(not isinstance(n, str) or not re.fullmatch(r'[a-z][a-z0-9_-]{0,39}', n) for n in names):
        raise ValueError('Invalid path name')
    if len(set(names)) != len(names):
        raise ValueError('Duplicate paths')
    settings = status['settings']
    if not isinstance(settings, dict):
        raise ValueError('Invalid settings')
    for key in ('probes', 'healthy'):
        if not isinstance(status.get(key, {}), dict):
            raise ValueError('Invalid telemetry mapping')
    for key in ('failure_rounds', 'recovery_rounds'):
        values = status.get(key, [0]*4)
        if not isinstance(values, list) or len(values) < len(paths):
            raise ValueError('Invalid telemetry counters')
    result = {
        'monotonic': number(status['monotonic']),
        'status_max_age': min(120, max(1, number(status.get('status_max_age'), 15))),
        'settings': {k: number(settings[k]) for k in ('interval', 'quorum', 'failure_rounds', 'recovery_rounds')},
        'active': status.get('active') if status.get('active') in names else None,
        'paths': [],
        'watchdog': {
            'monotonic': number(watchdog.get('monotonic')),
            **{k: watchdog.get(k) is True for k in ('controller', 'ike', 'integrity')},
        },
    }
    for index, path in enumerate(paths):
        if path.get('kind') not in ('wireguard', 'ipsec'):
            raise ValueError('Invalid protocol')
        probes = path.get('probes', status.get('probes', {}).get(path['name'], {}))
        if not isinstance(probes, dict):
            raise ValueError('Invalid probe results')
        filtered = {}
        for address, ok in list(probes.items())[:8]:
            if ipaddress.ip_address(address).version == 4:
                filtered[address] = ok is True
        result['paths'].append({
            'name': path['name'], 'kind': path['kind'],
            'interface': text(path.get('interface', ''), 15),
            'healthy': path.get('healthy', status.get('healthy', {}).get(path['name'])) is True,
            'probes': filtered,
            'failed_rounds': number(path.get('failed_rounds', status.get('failure_rounds', [0]*4)[index])),
            'recovery_rounds': number(path.get('recovery_rounds', status.get('recovery_rounds', [0]*4)[index])),
        })
    switch = status.get('last_switch')
    if isinstance(switch, dict):
        # Reason is selected by the controller, never arbitrary exception text.
        reasons = ('all paths unavailable', 'initial path selection',
                   'current path failure threshold reached',
                   'preferred path recovered for stability threshold')
        result['last_switch'] = {
            'time': number(switch.get('time')),
            **{k: switch.get(k) if switch.get(k) in names else None for k in ('old', 'new')},
            'reason': switch.get('reason') if switch.get('reason') in reasons else 'Route selection changed',
        }
    return result


def read_json(path):
    if path.is_symlink() or path.stat().st_size > 262144:
        raise ValueError('Invalid telemetry file')
    return json.loads(path.read_text())


class Monitor:
    def __init__(self, directory, history_directory=None):
        self.directory = pathlib.Path(directory)
        self.events = collections.deque(maxlen=200)
        self.previous = None
        self.switch_time = None
        self.lock = threading.Lock()
        self.history = History(history_directory) if history_directory else None
        self.history_warning = None
        if self.history:
            try:
                events, self.switch_time = self.history.load()
                self.events.extend(events)
            except (OSError, ValueError, KeyError, TypeError):
                self.history_warning = 'Saved history could not be loaded. Current monitoring is independent.'

    def persist(self, before):
        cutoff = time.time() - MAX_AGE
        self.events = collections.deque((e for e in self.events if e['time'] >= cutoff), maxlen=200)
        if self.history and (before != list(self.events) or self.history_warning):
            try:
                self.history.save(self.events, self.switch_time)
                self.history_warning = None
            except (OSError, ValueError, TypeError):
                self.history_warning = 'History could not be saved. Current monitoring still works.'

    def snapshot(self, now=None):
        now = time.monotonic() if now is None else now
        with self.lock:
            before = list(self.events)
            try:
                raw = read_json(self.directory / 'telemetry.json')
                state = project(raw, raw['watchdog'])
                age = now - state['monotonic']
                w = state['watchdog']
                available = (0 <= age < state['status_max_age']
                             and 0 <= now - w['monotonic'] < 25
                             and all(w[k] for k in ('controller', 'ike', 'integrity')))
                state['age_seconds'] = round(max(0, age), 1)
                state['available'] = available
                current = {p['name']: p['healthy'] for p in state['paths']} if available else None
                if current != self.previous:
                    if current is None:
                        self.events.append({'time': time.time(), 'path': None, 'message': 'Monitoring unavailable: status is stale or the supervisor is not healthy.'})
                    else:
                        for name, healthy in current.items():
                            if self.previous is None or self.previous.get(name) != healthy:
                                self.events.append({'time': time.time(), 'path': name, 'message': name + (': private-network probes are passing.' if healthy else ': probe threshold is not met. This alone does not mean a switch.')})
                    self.previous = current
                switch = state.get('last_switch')
                if switch and switch['time'] != self.switch_time:
                    self.events.append({'time': switch['time'], 'path': switch['new'], 'message': 'Route changed: ' + (switch['old'] or 'none') + ' → ' + (switch['new'] or 'none') + '. ' + switch['reason'] + '.'})
                    self.switch_time = switch['time']
                self.persist(before)
                state['history_warning'] = self.history_warning
                state['events'] = list(reversed(self.events))
                return state
            except (OSError, ValueError, KeyError, TypeError, IndexError):
                self.previous = None
                self.persist(before)
                return {'available': False, 'active': None, 'paths': [], 'events': list(reversed(self.events)), 'history_warning': self.history_warning, 'message': 'No valid telemetry available. Check the optional status mirror.'}


def check_binding(address, token):
    ip = ipaddress.ip_address(address)
    if ip.version != 4:
        raise ValueError('Use a specific IPv4 loopback/private address')
    private4 = ip.version == 4 and any(ip in ipaddress.ip_network(p) for p in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16'))
    if not (ip.is_loopback or private4):
        raise ValueError('Bind only to loopback or a specific private IPv4/VPN address')
    if not ip.is_loopback and len(token) < 32:
        raise ValueError('Private remote binding requires a token of at least 32 characters')


def serve(args):
    token = pathlib.Path(args.token_file).read_text().strip() if args.token_file else ''
    auth_dir = getattr(args, 'auth_dir', None)
    origin = getattr(args, 'origin', None)
    if auth_dir and (token or not origin):
        raise ValueError('Account mode requires an origin and cannot use a legacy token.')
    if origin and not auth_dir:
        raise ValueError('An origin requires initialized account storage.')
    secure = origin_policy(origin) if auth_dir else False
    if auth_dir and not secure and not ipaddress.ip_address(args.bind).is_loopback:
        raise ValueError('Plain HTTP account mode requires a loopback listener.')
    check_binding(args.bind, 'account-mode-requires-origin-check' if auth_dir else token)
    accounts = Accounts(auth_dir) if auth_dir else None
    if accounts and not accounts.db.execute("SELECT 1 FROM users WHERE role='admin'").fetchone():
        raise ValueError('Create an administrator before starting account mode.')
    monitor = Monitor(args.telemetry, getattr(args, 'history', None))
    def sample():
        while True:
            monitor.snapshot()
            time.sleep(2)
    threading.Thread(target=sample, daemon=True).start()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # Never record authorization headers or URLs.

        def sid(self):
            return cookie_token(self.headers.get('Cookie'), secure)

        def verify_host(self):
            if accounts and self.headers.get('Host', '') != urlsplit(origin).netloc:
                raise AuthError(403, 'Unexpected dashboard host.')

        def json_response(self, status, value, headers=None):
            self.respond(status, json.dumps(value).encode(), 'application/json', headers)

        def do_POST(self):
            if not accounts:
                self.respond(405, b'No live management endpoint', 'text/plain')
                return
            try:
                self.verify_host()
                if self.headers.get('Origin') != origin or self.headers.get('X-VPN-Request') != '1':
                    raise AuthError(403, 'Request verification failed.')
                if self.headers.get('Content-Type') != 'application/json' or self.headers.get('Transfer-Encoding'):
                    raise AuthError(400, 'Use a bounded JSON request.')
                length = int(self.headers.get('Content-Length', '0'))
                if not 1 <= length <= 4096:
                    raise AuthError(413, 'Request too large or empty.')
                data = json.loads(self.rfile.read(length))
                if not isinstance(data, dict):
                    raise ValueError()
                if self.path == '/api/login':
                    sid, user = accounts.login(data.get('username'), data.get('password'), self.client_address[0])
                    self.json_response(200, user, {'Set-Cookie': cookie_header(sid, secure)})
                elif self.path == '/api/activity':
                    self.json_response(200, accounts.session(self.sid(), self.headers.get('X-CSRF-Token', '')))
                elif self.path == '/api/logout':
                    accounts.logout(self.sid(), self.headers.get('X-CSRF-Token', ''))
                    self.json_response(200, {'logged_out': True}, {'Set-Cookie': cookie_header('', secure, clear=True)})
                else:
                    self.json_response(404, {'error': 'No such operation.'})
            except AuthError as exc:
                self.json_response(exc.status, {'error': exc.message})
            except (ValueError, TypeError, UnicodeError):
                self.json_response(400, {'error': 'Invalid request.'})
            except Exception:
                self.json_response(503, {'error': 'Authentication service unavailable.'})

        def do_GET(self):
            if self.path == '/api/auth':
                self.json_response(200, {'mode': 'accounts' if accounts else 'token' if token else 'local'})
                return
            if self.path.startswith('/api/') and accounts:
                try:
                    self.verify_host()
                    user = accounts.session(self.sid(), touch=False)
                    if self.path == '/api/session':
                        self.json_response(200, user)
                        return
                    if self.path == '/api/security-events':
                        self.json_response(200, {'events': accounts.events(self.sid())})
                        return
                    if self.path != '/api/status':
                        self.json_response(404, {'error': 'No such operation.'})
                        return
                except AuthError as exc:
                    self.json_response(exc.status, {'error': exc.message})
                    return
                except Exception:
                    self.json_response(503, {'error': 'Authentication service unavailable.'})
                    return
            if self.path == '/api/status':
                supplied = self.headers.get('Authorization', '')
                if token and not hmac.compare_digest(supplied.encode(), ('Bearer ' + token).encode()):
                    self.respond(401, b'{"error":"Unlock with the dashboard access token"}', 'application/json')
                    return
                self.respond(200, json.dumps(monitor.snapshot()).encode(), 'application/json')
                return
            assets = {'/': ('index.html', 'text/html'), '/app.js': ('app.js', 'text/javascript'),
                      '/profiles.js': ('profiles.js', 'text/javascript'), '/login.js': ('login.js', 'text/javascript'), '/style.css': ('style.css', 'text/css')}
            if self.path not in assets:
                self.respond(404, b'Not found', 'text/plain')
                return
            name, mime = assets[self.path]
            self.respond(200, (HERE / name).read_bytes(), mime)

        def respond(self, status, data, mime, headers=None):
            self.send_response(status)
            for name, value in (headers or {}).items():
                self.send_header(name, value)
            self.send_header('Content-Type', mime + '; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
            self.end_headers()
            self.wfile.write(data)

    class BoundedServer(ThreadingHTTPServer):
        daemon_threads = True
        slots = threading.BoundedSemaphore(32)

        def get_request(self):
            request, address = super().get_request()
            request.settimeout(5)
            return request, address

        def process_request(self, request, address):
            if not self.slots.acquire(blocking=False):
                self.shutdown_request(request)
                return
            try:
                super().process_request(request, address)
            except Exception:
                self.slots.release()
                raise

        def process_request_thread(self, request, address):
            try:
                super().process_request_thread(request, address)
            finally:
                self.slots.release()

    BoundedServer((args.bind, args.port), Handler).serve_forever()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--bind', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8787)
    parser.add_argument('--telemetry', default='/telemetry')
    parser.add_argument('--token-file')
    parser.add_argument('--auth-dir', help='Private initialized account directory; enables login sessions')
    parser.add_argument('--origin', help='Exact browser origin; HTTPS required except loopback SSH access')
    parser.add_argument('--history', help='Optional writable directory for up to 200 observations, retained 30 days')
    serve(parser.parse_args())
