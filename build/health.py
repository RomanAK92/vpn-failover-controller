"""Readiness requires current owners, not merely recently saved status files."""
import json
import pathlib
import sys
import time


def owner_running(path):
    # Both owners hold exclusive locks for their entire lifetime. A shared
    # nonblocking lock succeeds only when that owner is absent.
    import fcntl
    try:
        with path.open('r') as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_SH | fcntl.LOCK_NB)
            except BlockingIOError:
                return True
        return False
    except OSError:
        return False


def healthy(runtime=pathlib.Path('/run/vpn-router'), owners=owner_running):
    try:
        if not all(owners(runtime / name) for name in ('supervisor.lock', 'controller.lock')):
            return False
        d = json.loads((runtime / 'status.json').read_text())
        w = json.loads((runtime / 'watchdog.json').read_text())
        now = time.monotonic()
        return (0 <= now - d['monotonic'] < d.get('status_max_age', 15)
                and d['active'] is not None
                and 0 <= now - w['monotonic'] < 25
                and all(w[k] for k in ('controller', 'ike', 'integrity')))
    except (OSError, ValueError, KeyError, TypeError):
        return False


if __name__ == '__main__':
    sys.exit(0 if healthy() else 1)
