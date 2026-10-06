import copy
import json
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).parents[1]
if sys.platform == 'linux':
    sys.path.insert(0, str(ROOT/'management'))
    from broker import PrepareBroker
    from coordinator import ApplyCoordinator
    from journal import Journal, TransactionError
    import test_broker


class FakeDriver:
    """No process, route, tunnel or real application traffic: state-machine only."""
    def __init__(self):
        self.generation = None; self.live = False; self.health = False; self.fail_start = None
    def stop(self): self.generation = None; self.live = False
    def start(self, generation):
        if generation == self.fail_start: raise RuntimeError('injected start failure')
        self.generation = generation; self.live = True; self.health = False
    def running(self): return self.live
    def ready(self, generation): return self.live and self.generation == generation and self.health


@unittest.skipUnless(sys.platform == 'linux', 'Linux private generations and fake driver')
class CoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_broker.BrokerTests(); self.fixture.setUp()
        self.store = self.fixture.broker
        self.previous = self.fixture.prepare()['id']
        self.candidate = self.fixture.prepare()['id']
        self.store.generations.initialize(self.previous)
        self.now = 1000
        self.journal = Journal(self.fixture.root, 'boot-a', lambda: self.now)
        self.journal.initialize(self.previous)
        self.driver = FakeDriver()
        self.coordinator = ApplyCoordinator(self.store, self.journal, self.driver)
        self.coordinator.tick()
        self.driver.health = True

    def tearDown(self):
        self.journal.close(); self.fixture.tearDown()

    def test_arm_before_effects_and_confirm_only_fresh_independent_ready(self):
        result = self.coordinator.begin(self.candidate)
        self.assertFalse(result['applied'])
        self.assertEqual(self.driver.generation, self.previous)
        self.assertEqual(self.store.generations.active(), self.previous)
        self.coordinator.tick()
        self.assertEqual(self.driver.generation, self.candidate)
        with self.assertRaises(TransactionError): self.coordinator.confirm(result['change_id'])
        self.driver.health = True
        self.coordinator.confirm(result['change_id'])
        self.assertEqual(self.journal.snapshot()['state']['active'], self.candidate)

    def test_expiry_selects_previous_but_never_claims_unhealthy_recovery(self):
        result = self.coordinator.begin(self.candidate, 60); self.coordinator.tick()
        self.now += 60; self.coordinator.tick()
        self.assertEqual(self.driver.generation, self.previous)
        self.assertEqual(self.journal.snapshot()['change']['phase'], 'rollback-requested')
        with self.assertRaises(TransactionError): self.coordinator.confirm(result['change_id'])
        self.driver.health = True; self.coordinator.tick()
        self.assertEqual(self.journal.snapshot()['change']['phase'], 'rolled-back')

    def test_candidate_start_failure_and_process_death_request_recovery(self):
        self.driver.fail_start = self.candidate
        self.coordinator.begin(self.candidate); self.coordinator.tick()
        self.assertEqual(self.journal.snapshot()['change']['reason'], 'apply-failed')
        self.coordinator.tick(); self.driver.health = True; self.coordinator.tick()
        self.assertEqual(self.journal.snapshot()['change']['phase'], 'rolled-back')
        self.driver.fail_start = None
        self.coordinator.begin(self.candidate); self.coordinator.tick()
        self.driver.live = False; self.coordinator.tick()
        self.assertEqual(self.journal.snapshot()['change']['reason'], 'engine-failure')

    def test_service_restart_requests_previous_before_next_start(self):
        self.coordinator.begin(self.candidate); self.coordinator.tick()
        self.coordinator.restart_recovery()
        self.assertIsNone(self.driver.generation)
        self.assertEqual(self.journal.snapshot()['change']['reason'], 'service-restarted')
        self.coordinator.tick()
        self.assertEqual(self.driver.generation, self.previous)

    def test_expiry_during_bounded_stop_cannot_select_candidate_late(self):
        result = self.coordinator.begin(self.candidate, 60)
        original_stop = self.driver.stop
        def slow_stop():
            original_stop(); self.now += 61
        with mock.patch.object(self.driver, 'stop', side_effect=slow_stop): self.coordinator.tick()
        self.assertEqual(self.store.generations.active(), self.previous)
        self.assertEqual(self.journal.snapshot()['change']['phase'], 'rollback-requested')
        self.assertIsNone(self.driver.generation)

    def test_foreign_selection_double_apply_and_wrong_revert_are_rejected(self):
        result = self.coordinator.begin(self.candidate)
        with self.assertRaises(TransactionError): self.coordinator.begin(self.candidate)
        with self.assertRaises(TransactionError): self.coordinator.revert('wrong')
        self.coordinator.revert(result['change_id']); self.coordinator.tick()
        self.assertEqual(self.store.generations.active(), self.previous)

    def test_structural_change_is_rejected_without_a_transaction(self):
        files = copy.deepcopy(self.fixture.files)
        c = json.loads(files['controller.json']); c['paths'].pop()
        files['controller.json'] = json.dumps(c)
        peers = json.loads(files['peers.json']); peers.pop('peer-2')
        files['peers.json'] = json.dumps(peers); files.pop('wg-client-peer-2.key')
        candidate = self.fixture.prepare(files)['id']
        with self.assertRaises(TransactionError): self.coordinator.begin(candidate)
        self.assertIsNone(self.journal.snapshot()['change'])
        self.assertEqual(self.driver.generation, self.previous)

    def test_unhealthy_baseline_cannot_be_used_as_a_recovery_guarantee(self):
        self.driver.health = False
        with self.assertRaises(TransactionError): self.coordinator.begin(self.candidate)
        self.assertIsNone(self.journal.snapshot()['change'])


if __name__ == '__main__':
    unittest.main()
