"""Independent transaction expiry watcher; requests recovery, never applies VPNs."""
import argparse
import json
import pathlib
import signal
import time
from journal import Journal


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--state-dir', required=True)
    p.add_argument('--once', action='store_true')
    args = p.parse_args()
    root = pathlib.Path(args.state_dir)
    if not (root/'transactions.sqlite3').is_file():
        p.error('Initialize transaction storage before starting its watcher.')
    boot = pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    store = Journal(root, boot)
    stop = False

    def stopping(*_):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGTERM, stopping)
    signal.signal(signal.SIGINT, stopping)
    try:
        store.snapshot()  # Never silently monitor an uninitialized installation.
        while not stop:
            changed = store.watch()
            if changed:
                state = store.snapshot()
                print(json.dumps({'event': 'rollback-requested',
                    'change_id': state['change']['id'], 'reason': state['change']['reason'],
                    'recovery_proven': False}), flush=True)
            if args.once:
                return
            time.sleep(.5)
    finally:
        store.close()


if __name__ == '__main__':
    main()
