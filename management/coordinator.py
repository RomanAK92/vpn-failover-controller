"""Development apply state machine. Not exposed by the web/private socket API.

Requires the independently supervised watcher, atomic generation mount and real
network failure-injection acceptance before distribution. Its tests use a fake
driver and must not be presented as successful live rollback.
"""
import json
import threading
from journal import TransactionError
from plan import preview


class ApplyCoordinator:
    def __init__(self, store, journal, driver):
        self.store, self.journal, self.driver = store, journal, driver
        self.generations = store.generations
        self.lock = threading.RLock()

    def plan(self, candidate):
        current = self.journal.snapshot()['state']['active']
        old = self.store.load(current)
        new = self.store.load(candidate)
        old_c, new_c = json.loads(old['controller.json']), json.loads(new['controller.json'])
        result = preview(old_c, json.loads(old['deployment.json']), new_c, json.loads(new['deployment.json']))
        old_peers, new_peers = json.loads(old['peers.json']), json.loads(new['peers.json'])
        old_paths = {p['name']: p for p in old_c['paths']}
        for path in new_c['paths']:
            previous = old_paths.get(path['name'])
            if path['kind'] == 'ipsec' and previous and previous['kind'] == 'ipsec':
                if old_peers[previous['peer']]['endpoint'] != new_peers[path['peer']]['endpoint']:
                    result['reasons'].append('IPsec endpoint changes require validated retired-SA reconciliation.')
                    result['live_footprint_compatible'] = False
        return result

    def begin(self, candidate, timeout=180):
        with self.lock:
            if not self.plan(candidate)['live_footprint_compatible']:
                raise TransactionError('This draft requires network reconciliation not enabled by the first driver.')
            baseline = self.journal.snapshot()['state']['active']
            if self.generations.active() != baseline:
                raise TransactionError('The selected baseline is not the confirmed generation.')
            if not self.driver.ready(baseline):
                raise TransactionError('Prove the current baseline and application healthy before arming a replacement.')
            self.generations.retire_completed_pointers(self.journal)
            change = self.journal.begin(candidate, timeout)
            snapshot = self.journal.snapshot()
            try:
                self.generations.pointers(change, snapshot['change']['previous'], candidate)
            except Exception:
                self.journal.cancel('apply-failed')
                raise TransactionError('Private candidate staging failed; recovery remains requested.') from None
            return {'change_id': change, 'phase': 'pending', 'applied': False}

    def confirm(self, change):
        with self.lock:
            snapshot = self.journal.snapshot()
            c = snapshot['change']
            if not c or c['id'] != change or c['phase'] != 'pending':
                raise TransactionError('No matching pending transaction.')
            if self.generations.active() != c['candidate'] or not self.driver.ready(c['candidate']):
                raise TransactionError('Fresh independent candidate readiness is required.')
            self.journal.confirm(change, c['candidate'], snapshot['state']['revision'], fresh_health=True)
            return {'phase': 'confirmed', 'generation': c['candidate']}

    def revert(self, change):
        with self.lock:
            snapshot = self.journal.snapshot()
            if not snapshot['change'] or snapshot['change']['id'] != change:
                raise TransactionError('No matching transaction to revert.')
            return self.journal.cancel('operator-revert')

    def restart_recovery(self):
        """Called before any engine start after a management-service restart."""
        with self.lock:
            self.driver.stop()
            self.journal.cancel('service-restarted')

    def storage_recovery(self):
        """Privileged full-database fallback; caller disables ALL change commands.

        Stop the engine before selecting a previous generation. No database
        acknowledgement can be claimed until storage is repaired. Not a web verb.
        """
        with self.lock:
            self.driver.stop()
            with self.journal.read_only_snapshot() as snapshot:
                c = snapshot['change']
                if c and c['phase'] in ('pending', 'rollback-requested'):
                    self.generations._recover(snapshot)
                    target = c['previous']
                else:
                    target = snapshot['state']['active']
                    if self.generations.active() != target:
                        raise TransactionError('Storage recovery cannot identify a confirmed baseline.')
            self.driver.start(target)
            return target

    def tick(self):
        with self.lock:
            self.journal.watch()
            snapshot = self.journal.snapshot()
            c, state = snapshot['change'], snapshot['state']
            if c and c['phase'] == 'pending':
                if self.driver.generation == c['candidate'] and not self.driver.running():
                    self.journal.cancel('engine-failure')
                    return
                if self.driver.generation != c['candidate']:
                    # Stop is bounded and must succeed before filesystem selection.
                    self.driver.stop()
                    try:
                        self.generations.select(c['id'], c['candidate'], self.journal)
                        self.driver.start(c['candidate'])
                    except Exception:
                        self.journal.cancel('apply-failed')
                        return
            elif c and c['phase'] == 'rollback-requested':
                previous = c['previous']
                if self.driver.generation != previous or self.generations.active() != previous:
                    self.driver.stop()
                    self.generations.recover(self.journal)
                    self.driver.start(previous)
                elif not self.driver.running():
                    self.driver.stop()
                    self.driver.start(previous)
                if self.driver.ready(previous):
                    fresh = self.journal.snapshot()
                    self.journal.restored(previous, fresh['state']['revision'], fresh_health=True)
            else:
                if self.generations.active() != state['active']:
                    self.driver.stop()
                    raise TransactionError('Selected and confirmed generations disagree; inspect privately.')
                if self.driver.generation != state['active'] or not self.driver.running():
                    self.driver.stop()
                    self.driver.start(state['active'])
