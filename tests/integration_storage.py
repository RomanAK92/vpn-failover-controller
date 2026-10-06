"""Real ENOSPC filesystem-selection acceptance, not VPN traffic recovery.

Uses a bounded tmpfs in an owned, no-network, capability-free Docker container.
Does not mount a host filesystem, change networking or write real credentials.
"""
import argparse
import errno
import json
import os
import pathlib
import secrets
import sqlite3
import subprocess
import sys

ROOT = pathlib.Path(__file__).parents[1]
sys.path.insert(0, str(ROOT/'management'))


def inside():
    from journal import Journal, TransactionError
    from generations import Generations
    root = pathlib.Path('/private/store')
    root.mkdir(mode=0o700)
    (root/'generations').mkdir(mode=0o700)
    previous, candidate = 'a'*32, 'b'*32
    for name in (previous, candidate):
        (root/'generations'/name).mkdir(mode=0o700)
    now = [1000]
    journal = Journal(root, 'isolated-storage-boot', lambda: now[0])
    journal.initialize(previous)
    pointers = Generations(root); pointers.initialize(previous)
    change = journal.begin(candidate, 60)
    pointers.pointers(change, previous, candidate)
    pointers.select(change, candidate, journal)
    assert pointers.active() == candidate
    print(json.dumps({'check': 'candidate-and-preallocated-recovery-pointer', 'passed': True}), flush=True)
    filler = root/'owned-filler'
    fd = os.open(filler, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        while True:
            os.write(fd, b'x'*4096)
    except OSError as exc:
        if exc.errno != errno.ENOSPC: raise
    finally:
        os.close(fd)
    assert os.statvfs(root).f_bavail == 0
    now[0] += 61
    try:
        journal.watch()
    except sqlite3.OperationalError as exc:
        assert exc.sqlite_errorcode == sqlite3.SQLITE_FULL
    else:
        raise AssertionError('Full-filesystem journal write unexpectedly succeeded.')
    print(json.dumps({'check': 'actual-enospc-refuses-journal-update', 'passed': True}), flush=True)
    journal.close()
    journal = Journal(root, 'isolated-storage-boot', lambda: now[0])
    print(json.dumps({'check': 'independent-journal-reopen-on-full-filesystem', 'passed': True}), flush=True)
    assert pointers.recover(journal)
    assert pointers.active() == previous
    with journal.recovery_snapshot() as snapshot:
        assert snapshot['change']['phase'] == 'pending'  # No writable acknowledgement or traffic proof.
    try:
        journal.confirm(change, candidate, 2, True)
    except (TransactionError, sqlite3.OperationalError):
        pass
    else:
        raise AssertionError('Expired candidate was confirmed after emergency selection.')
    print(json.dumps({'check': 'read-only-expiry-restores-existing-pointer-without-false-confirmation',
                      'passed': True, 'traffic_recovery_proven': False}), flush=True)
    filler.unlink()
    assert journal.watch()
    assert journal.snapshot()['change']['phase'] == 'rollback-requested'
    assert not pointers.recover(journal)
    journal.close()
    print(json.dumps({'result': 'PASS', 'checks': 5, 'network_changes': False,
                      'traffic_recovery_proven': False}), flush=True)


def main():
    if sys.platform != 'linux' or os.geteuid() != 0:
        raise SystemExit('Run only on the isolated Linux Docker host.')
    name = 'vpn-storage-'+secrets.token_hex(4)
    route = subprocess.check_output(['ip', 'route', 'show', 'default'])
    try:
        result = subprocess.run(['docker', 'run', '--rm', '--name', name, '--network', 'none',
            '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true', '--read-only',
            '--memory', '64m', '--pids-limit', '32', '--tmpfs', '/private:rw,noexec,nosuid,size=1m',
            '-v', str(ROOT)+':/source:ro', '--entrypoint', 'python3', 'python:3.12-alpine',
            '/source/tests/integration_storage.py', '--inside'], capture_output=True, text=True, timeout=30)
        print(result.stdout, end='', flush=True)
        if result.returncode:
            # Fixture contains identifiers only, but still avoid printing arbitrary process output.
            raise RuntimeError('Isolated full-filesystem acceptance failed; inspect its retained private diagnostics.')
        if subprocess.check_output(['ip', 'route', 'show', 'default']) != route:
            raise RuntimeError('Host default changed during storage acceptance.')
    finally:
        subprocess.run(['docker', 'rm', '-f', name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inside', action='store_true')
    args = parser.parse_args()
    inside() if args.inside else main()
