"""Isolated management-engine acceptance service. Not a released distribution.

Default socket permits preparation/preview only. --enable-managed-changes is an
explicit operator opt-in retaining all readiness and rollback checks. This
development candidate still requires isolated acceptance before promotion.
--enable-test-apply is for
owned disposable acceptance topology, never a critical/shared production host.
Full crash/storage/browser/upgrade/recovery gates remain before promotion.
"""
import argparse
import json
import os
import pathlib
import signal
import sqlite3
import subprocess
import sys
import threading
import time
from broker import PrepareBroker, BrokerServer, socket_directory
from coordinator import ApplyCoordinator
from driver import EngineDriver
from journal import Journal, TransactionError, storage_full
from operational import OperationalControls


class ManagedBroker(PrepareBroker):
    def __init__(self, directory, validator, coordinator=None, enable_test_apply=False):
        super().__init__(directory, validator)
        self.coordinator = coordinator
        self.enable_test_apply = enable_test_apply
        self.storage_fault = False
        self.operational = None

    def dispatch(self, request):
        if not isinstance(request, dict): raise ValueError('Use a structured command.')
        action = request.get('action')
        if action == 'status' and set(request) == {'action'} and self.coordinator:
            with self.coordinator.lock:
                with self.coordinator.journal.read_only_snapshot() as snapshot:
                    pass
                running = self.coordinator.driver.generation
                return {'transaction': snapshot, 'selected_generation': self.generations.active(),
                        'running_generation': running,
                        'prepared': self.store.entries(),
                        'archived': self.store.archived(),
                        'ready': bool(running and self.coordinator.driver.ready(running)),
                        'confirmation_seconds_remaining': max(0, round(snapshot['change']['deadline']-time.monotonic()))
                            if snapshot['change'] and snapshot['change']['phase'] == 'pending' else 0,
                        'storage_fault': self.storage_fault,
                        'operations': self.operational.status() if self.operational else None,
                        'path_names': sorted(self.coordinator.driver.expected_names) if self.operational and running else [],
                        'database_recovery_acknowledged': bool(not self.storage_fault and snapshot['change']
                            and snapshot['change']['phase'] == 'rolled-back'),
                        'live_apply_enabled': self.enable_test_apply}
        if self.coordinator and self.operational and action in ('operate', 'automatic'):
            with self.coordinator.lock:
                if self.enable_test_apply and not self.storage_fault:
                    if action == 'operate' and set(request) == {'action', 'preferred', 'disabled', 'seconds'}:
                        return self.operational.change(request['preferred'], request['disabled'], request['seconds'])
                    if action == 'automatic' and set(request) == {'action'}:
                        return self.operational.clear()
        if self.coordinator and action in ('apply', 'confirm', 'revert'):
            with self.coordinator.lock:
                if self.enable_test_apply and not self.storage_fault:
                    if action == 'apply' and set(request) == {'action', 'generation', 'timeout'}:
                        result = self.coordinator.begin(request['generation'], request['timeout'])
                        try:
                            if self.operational: self.operational.clear()
                        except (ValueError, OSError, TypeError):
                            self.coordinator.journal.cancel('apply-failed')
                            raise
                        return result
                    if action == 'confirm' and set(request) == {'action', 'change_id'}:
                        return self.coordinator.confirm(request['change_id'])
                    if action == 'revert' and set(request) == {'action', 'change_id'}:
                        return {'requested': self.coordinator.revert(request['change_id']), 'recovery_proven': False}
        if self.storage_fault:
            raise ValueError('Repair private storage and reconcile recovery before any new preparation/change.')
        if self.coordinator and action in ('archive','restore'):
            with self.coordinator.lock:
                with self.coordinator.journal.read_only_snapshot() as state:
                    change=state['change']
                    if change and change['phase'] in ('pending','rollback-requested'):
                        raise ValueError('Finish or recover the current change before archiving.')
                    if action=='archive' and request.get('generation') in (
                        state['state']['active'],state['state']['desired'],self.coordinator.driver.generation):
                        raise ValueError('Confirmed, desired or running settings cannot be archived.')
                self.generations.retire_completed_pointers(self.coordinator.journal)
                return super().dispatch(request)
        if self.coordinator and action == 'preview' and set(request) == {'action', 'generation'}:
            with self.coordinator.lock:
                return {'generation': request['generation'], **self.coordinator.plan(request['generation'])}
        return super().dispatch(request)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--management-dir', default='/management')
    parser.add_argument('--socket-dir', default='/control')
    parser.add_argument('--application-file', required=True)
    controls=parser.add_mutually_exclusive_group()
    controls.add_argument('--enable-test-apply', action='store_true', help='Owned disposable acceptance only')
    controls.add_argument('--enable-managed-changes', action='store_true', help='Explicit operator opt-in; retain all review, readiness and rollback checks')
    args = parser.parse_args()
    if sys.platform != 'linux' or os.geteuid() != 0:
        parser.error('The managed engine requires its root-owned Linux container.')
    os.umask(0o077)
    application = pathlib.Path(args.application_file)
    if (application.is_symlink() or not application.is_file() or application.stat().st_size > 4096
        or application.stat().st_mode & 0o077 or application.stat().st_uid != 0):
        parser.error('Use an initialized private application readiness file.')
    settings = json.loads(application.read_text())
    store = ManagedBroker(args.management_dir, '/app/doctor.py', enable_test_apply=args.enable_test_apply or args.enable_managed_changes)
    boot = pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    journal = Journal(args.management_dir, boot)
    driver = EngineDriver(application=settings)
    coordinator = ApplyCoordinator(store, journal, driver)
    store.coordinator = coordinator
    store.operational = OperationalControls(coordinator)
    stop = False
    watcher = None
    server = None
    thread = None
    storage_target = None
    def storage_recovery():
        nonlocal storage_target
        with coordinator.lock:
            store.enable_test_apply = False
            store.storage_fault = True
            storage_target = coordinator.storage_recovery()
        print(json.dumps({'event': 'storage-recovery-requested', 'generation': storage_target,
            'database_recovery_acknowledged': False, 'change_commands_enabled': False}), flush=True)
    def stopping(*_):
        nonlocal stop
        stop = True
    signal.signal(signal.SIGTERM, stopping)
    signal.signal(signal.SIGINT, stopping)
    try:
        # Never start an unconfirmed candidate after a container/service restart.
        try:
            coordinator.restart_recovery()
        except sqlite3.OperationalError as exc:
            if not storage_full(exc): raise
            storage_recovery()
        watcher = subprocess.Popen([sys.executable, '-u', str(pathlib.Path(__file__).with_name('rollback_watch.py')),
                                   '--state-dir', args.management_dir])
        with socket_directory(args.socket_dir) as target:
            with BrokerServer(target, store) as server:
                if target.stat().st_uid != 0 or target.stat().st_gid != 65532:
                    raise ValueError('The preinitialized control directory must inherit the web GID.')
                os.chmod(target, 0o660)
                thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .2}, daemon=True)
                thread.start()
                previous = None
                while not stop:
                    if watcher.poll() is not None and not store.storage_fault:
                        try:
                            journal.cancel('watcher-failure')
                        except sqlite3.OperationalError as exc:
                            if not storage_full(exc): raise
                            storage_recovery()
                        else:
                            raise TransactionError('Independent watcher exited; engine will stop and recover on supervised restart.')
                    if store.storage_fault:
                        if not driver.running():
                            driver.stop(); driver.start(storage_target)
                    else:
                        try:
                            coordinator.tick()
                        except sqlite3.OperationalError as exc:
                            if not storage_full(exc): raise
                            storage_recovery()
                    running = driver.generation
                    ready = bool(running and driver.ready(running))
                    with journal.read_only_snapshot() as snapshot:
                        pass
                    marker = (running, ready, snapshot['change']['phase'] if snapshot['change'] else 'baseline', store.storage_fault)
                    if marker != previous:
                        print(json.dumps({'event': 'managed-generation-status', 'generation': running,
                            'ready': ready, 'phase': marker[2], 'storage_fault': store.storage_fault,
                            'live_apply_enabled': store.enable_test_apply}), flush=True)
                        previous = marker
                    time.sleep(.5)
    finally:
        if server and thread and thread.is_alive():
            server.shutdown()
        if thread:
            thread.join(timeout=2)
        driver.stop()
        if watcher:
            watcher.terminate()
            try: watcher.wait(timeout=2)
            except subprocess.TimeoutExpired: watcher.kill(); watcher.wait(timeout=2)
        journal.close()


if __name__ == '__main__':
    main()
