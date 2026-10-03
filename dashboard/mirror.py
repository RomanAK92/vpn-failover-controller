"""Optional host-side allowlisted telemetry copy. No Docker or networking commands."""
import argparse
import json
import os
import pathlib
import time
from server import project, read_json


def copy_once(source, destination):
    source, destination = pathlib.Path(source), pathlib.Path(destination)
    # Separate directory avoids exporting credentials or the IPsec control socket.
    if destination.resolve() == source.resolve() or source.resolve() in destination.resolve().parents:
        raise ValueError('Telemetry destination must be outside VPN runtime')
    data = project(read_json(source / 'status.json'), read_json(source / 'watchdog.json'))
    destination.mkdir(mode=0o755, parents=True, exist_ok=True)
    temporary = destination / 'telemetry.tmp'
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o644)
    with os.fdopen(fd, 'w') as handle:
        json.dump(data, handle)
    temporary.replace(destination / 'telemetry.json')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', default='/run/vpn-router')
    parser.add_argument('--destination', default='/run/vpn-dashboard')
    args = parser.parse_args()
    while True:
        try:
            copy_once(args.source, args.destination)
        except (OSError, ValueError, KeyError, TypeError, IndexError):
            pass  # Old telemetry will become stale; never display it as current.
        time.sleep(2)
