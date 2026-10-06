"""Bounded ownership of an engine process group; not a live apply coordinator.

The caller must select a validated generation after stopping the previous engine.
No web-supplied commands, PID, health boolean or arbitrary probe URL are accepted.
"""
import hashlib
import http.client
import ipaddress
import json
import os
import pathlib
import re
import signal
import ssl
import socket
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'build') if (ROOT/'build/health.py').is_file() else '/app')
from health import healthy


class DriverError(RuntimeError):
    pass


class ApplicationProbe:
    def __init__(self, settings, subnet):
        if not isinstance(settings, dict) or set(settings) - {'address', 'port', 'path', 'scheme', 'status'}:
            raise ValueError('Use a structured private application probe.')
        address = ipaddress.ip_address(settings.get('address'))
        net = ipaddress.ip_network(subnet, strict=True)
        port = settings.get('port')
        path = settings.get('path', '/')
        scheme = settings.get('scheme', 'http')
        status = settings.get('status', 200)
        if (address.version != 4 or address not in net or address in (net.network_address, net.broadcast_address)
            or type(port) is not int or not 1 <= port <= 65535
            or not isinstance(path, str) or not re.fullmatch(r'/[A-Za-z0-9/_.~-]{0,199}', path)
            or scheme not in ('http', 'https', 'tcp') or type(status) is not int or not 200 <= status <= 299
            or (scheme == 'tcp' and (path != '/' or status != 200))):
            raise ValueError('Probe must use an office IPv4 address, bounded path and successful HTTP status.')
        self.address, self.port, self.path, self.scheme, self.status = str(address), port, path, scheme, status

    def check(self):
        connection = None
        try:
            if self.scheme == 'tcp':
                with socket.create_connection((self.address,self.port),timeout=2):return True
            if self.scheme == 'https':
                connection = http.client.HTTPSConnection(self.address, self.port, timeout=2,
                                                         context=ssl.create_default_context())
            else:
                connection = http.client.HTTPConnection(self.address, self.port, timeout=2)
            connection.request('GET', self.path)
            response = connection.getresponse()
            body = response.read(4097)
            return response.status == self.status and len(body) <= 4096
        except (OSError, ValueError, http.client.HTTPException):
            return False
        finally:
            if connection:
                connection.close()


class EngineDriver:
    def __init__(self, config='/etc/vpn', runtime='/run/vpn-router', app='/app', application=None):
        if sys.platform != 'linux':
            raise DriverError('Engine ownership requires Linux process groups.')
        self.config, self.runtime, self.app = pathlib.Path(config), pathlib.Path(runtime), pathlib.Path(app)
        self.application_settings = application
        self.application = None
        self.process = None
        self.generation = None
        self.started = None
        self.hashes = None
        self.expected_names = None
        self.baseline = self.defaults()

    @staticmethod
    def command(arguments, timeout=5):
        result = subprocess.run(arguments, capture_output=True, timeout=timeout)
        if result.returncode:
            raise DriverError('A bounded engine-control command failed; output is private.')
        return result.stdout

    def defaults(self):
        data = self.command(['ip', '-j', 'route', 'show', 'default'])
        if len(data) > 32768:
            raise DriverError('Default-route inspection exceeded its bound.')
        rows = json.loads(data)
        if not isinstance(rows, list):
            raise DriverError('Default-route inspection is invalid.')
        return json.dumps(rows, sort_keys=True, separators=(',', ':'))

    def configuration_hashes(self):
        controller = self.config/'controller.json'
        if controller.is_symlink() or not controller.is_file() or controller.stat().st_size > 32768:
            raise DriverError('Unsafe engine controller file.')
        c = json.loads(controller.read_text())
        if c.get('schema_version') != 2 or c.get('ipsec_mode') != 'generated':
            raise DriverError('The management driver requires structured generated configuration.')
        names = {'controller.json', 'peers.json', 'deployment.json'}
        names |= {('wg-client-' if p['kind'] == 'wireguard' else 'ipsec-')+p['peer']+'.key'
                  for p in c['paths']}
        result = {}
        for name in names:
            if not re.fullmatch(r'[A-Za-z0-9_.-]{1,80}', name):
                raise DriverError('Unsafe engine configuration filename.')
            path = self.config/name
            if path.is_symlink() or not path.is_file() or path.stat().st_size > 32768:
                raise DriverError('Unsafe or missing engine configuration file.')
            result[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        return c, result

    def running(self):
        if self.process is None:
            return False
        # Keep an exited leader unreaped until its group has been stopped. Its
        # reserved PID cannot be reused to target somebody else's process group.
        try:
            return os.waitid(os.P_PID, self.process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT) is None
        except ChildProcessError:
            return False

    def start(self, generation):
        if self.process is not None:
            raise DriverError('Stop the owned engine before another start.')
        if not isinstance(generation, str) or not re.fullmatch(r'[a-f0-9]{32}', generation):
            raise DriverError('Invalid selected generation identifier.')
        if self.defaults() != self.baseline:
            raise DriverError('Default route changed before engine startup.')
        self.command([sys.executable, str(self.app/'doctor.py'), '--config-dir', str(self.config),
                      '--files-only', '--json'], timeout=15)
        config, hashes = self.configuration_hashes()
        self.application = ApplicationProbe(self.application_settings, config['subnet']) if self.application_settings else None
        self.hashes = hashes
        self.expected_names = {p['name'] for p in config['paths']}
        self.started = time.monotonic()
        self.process = subprocess.Popen([sys.executable, '-u', str(self.app/'supervisor.py')],
                                        start_new_session=True)
        self.generation = generation

    def verified_status(self, generation):
        """Fresh owned engine telemetry; standby failures do not become fabricated health."""
        if self.generation != generation or not self.running() or self.application is None:
            return None
        try:
            if self.defaults() != self.baseline or self.configuration_hashes()[1] != self.hashes:
                return None
            state = json.loads((self.runtime/'status.json').read_text())
            watchdog = json.loads((self.runtime/'watchdog.json').read_text())
            if (state['monotonic'] < self.started or watchdog['monotonic'] < self.started
                or set(state['healthy']) != self.expected_names or any(type(v) is not bool for v in state['healthy'].values())
                or not healthy(self.runtime)):
                return None
            return state
        except (OSError, ValueError, KeyError, TypeError, DriverError, subprocess.TimeoutExpired):
            return None

    def ready(self, generation):
        """All candidate paths and the real private application must pass."""
        state = self.verified_status(generation)
        return bool(state and all(state['healthy'].values()) and self.application.check())

    def group_live(self):
        if self.process is None:
            return False
        for entry in pathlib.Path('/proc').iterdir():
            if not entry.name.isdigit(): continue
            try:
                pid = int(entry.name)
                # Each engine is placed in its own session. No unrelated sibling
                # can join that process group from a different session.
                if os.getpgid(pid) == self.process.pid and os.getsid(pid) == self.process.pid:
                    state = (entry/'stat').read_text().rsplit(')', 1)[1].split()[0]
                    if state != 'Z': return True
            except (OSError, ProcessLookupError, ValueError):
                continue
        return False

    def stop(self):
        if self.process is None: return
        pid = self.process.pid
        if pid <= 1 or pid == os.getpid() or pid == os.getpgrp():
            raise DriverError('Refusing an invalid owned process group.')
        for action, wait in ((signal.SIGTERM, 8), (signal.SIGKILL, 2)):
            try:
                os.killpg(pid, action)
            except ProcessLookupError:
                pass
            deadline = time.monotonic()+wait
            while self.group_live() and time.monotonic() < deadline:
                time.sleep(.05)
            if not self.group_live(): break
        if self.group_live():
            raise DriverError('The owned engine group did not stop; do not select another generation.')
        self.process.wait(timeout=2)
        self.process = None
        self.generation = None
        self.hashes = None
