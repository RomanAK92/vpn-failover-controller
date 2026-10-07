"""Isolated engine-lifecycle acceptance entrypoint. No apply command listener.

This development entrypoint tests process-group ownership with real encrypted
traffic. The transactional coordinator/broker connection is not enabled here.
"""
import argparse
import json
import os
import pathlib
import signal
import sys
import time
from driver import EngineDriver


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--generation', required=True)
    application = parser.add_mutually_exclusive_group(required=True)
    application.add_argument('--application-json')
    application.add_argument('--application-file')
    args = parser.parse_args()
    if sys.platform != 'linux' or os.geteuid() != 0:
        parser.error('Use the isolated reviewed Linux engine container.')
    os.umask(0o077)
    if args.application_file:
        path = pathlib.Path(args.application_file)
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 4096 or path.stat().st_mode & 0o077:
            parser.error('Use a bounded private application readiness file.')
        settings = json.loads(path.read_text())
    else:
        settings = json.loads(args.application_json)
    driver = EngineDriver(application=settings)
    stop = False
    def stopping(*_):
        nonlocal stop
        stop = True
    signal.signal(signal.SIGTERM, stopping)
    signal.signal(signal.SIGINT, stopping)
    failures = 0
    try:
        while not stop:
            try:
                driver.start(args.generation)
                started = time.monotonic()
                readiness_reported = False
                while not stop and driver.running():
                    if not readiness_reported and driver.ready(args.generation):
                        print(json.dumps({'event': 'engine-generation-ready',
                            'generation': args.generation, 'all_paths': True,
                            'application_http': True, 'live_apply_enabled': False}), flush=True)
                        readiness_reported = True
                    if time.monotonic()-started >= 300: failures = 0
                    time.sleep(.5)
            finally:
                driver.stop()
            if not stop:
                failures = min(failures+1, 6)
                delay = min(60, 2**failures)
                print(json.dumps({'event': 'engine-group-stopped', 'restart_in_seconds': delay}), flush=True)
                deadline = time.monotonic()+delay
                while not stop and time.monotonic() < deadline: time.sleep(.2)
    finally:
        driver.stop()


if __name__ == '__main__':
    main()
