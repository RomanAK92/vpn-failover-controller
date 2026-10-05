"""Bounded, atomic persistence of dashboard observations; never raw telemetry."""
import json
import os
import pathlib
import re
import time

LIMIT = 200
MAX_AGE = 30 * 86400
UNAVAILABLE = 'Monitoring unavailable: status is stale or the supervisor is not healthy.'


def valid_event(event):
    if not isinstance(event, dict) or set(event) != {'time', 'path', 'message'}:
        return False
    if type(event['time']) not in (int, float) or not 0 < event['time'] <= time.time() + 60:
        return False
    path = event['path']
    name = r'[a-z][a-z0-9_-]{0,39}'
    if path is not None and (not isinstance(path, str) or not re.fullmatch(name, path)):
        return False
    message = event['message']
    if not isinstance(message, str):
        return False
    if message == UNAVAILABLE:
        return path is None
    if path and message in (path + ': private-network probes are passing.',
                            path + ': probe threshold is not met. This alone does not mean a switch.'):
        return True
    route = re.fullmatch('Route changed: (' + name + r'|none) → (' + name + r'|none)\. (.+)\.', message)
    reasons = ('all paths unavailable', 'initial path selection', 'current path failure threshold reached',
               'preferred path recovered for stability threshold', 'Route selection changed')
    return bool(route and route[3] in reasons and path == (None if route[2] == 'none' else route[2]))


class History:
    def __init__(self, directory):
        self.directory = pathlib.Path(directory)
        self.path = self.directory / 'history.json'

    def load(self):
        if not self.path.exists():
            return [], None
        if self.path.is_symlink() or self.path.stat().st_size > 262144:
            raise ValueError('Invalid history file')
        data = json.loads(self.path.read_text())
        if not isinstance(data, dict) or data.get('version') != 1:
            raise ValueError('Invalid history version')
        events = data['events']
        if not isinstance(events, list) or len(events) > LIMIT or not all(valid_event(e) for e in events):
            raise ValueError('Invalid history events')
        switch = data.get('switch_time')
        if switch is not None and (type(switch) not in (int, float) or not 0 < switch <= time.time() + 60):
            raise ValueError('Invalid history switch')
        return [e for e in events if e['time'] >= time.time() - MAX_AGE], switch

    def save(self, events, switch_time):
        if self.directory.is_symlink() or self.path.is_symlink():
            raise ValueError('History symlinks are not allowed')
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        temporary = self.directory / 'history.tmp'
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, 'O_NOFOLLOW', 0)
        fd = os.open(temporary, flags, 0o600)
        with os.fdopen(fd, 'w') as handle:
            json.dump({'version': 1, 'events': list(events)[-LIMIT:], 'switch_time': switch_time}, handle)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(self.path)
