import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).parents[1]
if sys.platform == 'linux':
    sys.path.insert(0, str(ROOT/'management'))
    from manager import ManagedBroker
    import test_coordinator


@unittest.skipUnless(sys.platform == 'linux', 'Linux development manager command gates')
class ManagerCommandTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_coordinator.CoordinatorTests(); self.fixture.setUp()
        self.service = ManagedBroker(self.fixture.fixture.root, ROOT/'build/doctor.py',
                                     self.fixture.coordinator)

    def tearDown(self): self.fixture.tearDown()

    def test_default_service_refuses_apply_and_reports_it_disabled(self):
        self.assertFalse(self.service.dispatch({'action': 'status'})['live_apply_enabled'])
        with self.assertRaises(ValueError):
            self.service.dispatch({'action': 'apply', 'generation': self.fixture.candidate, 'timeout': 180})
        self.assertIsNone(self.fixture.journal.snapshot()['change'])

    def test_test_gate_delegates_to_real_state_machine_and_never_accepts_health_boolean(self):
        self.service.enable_test_apply = True
        result = self.service.dispatch({'action': 'apply', 'generation': self.fixture.candidate, 'timeout': 180})
        with self.assertRaises(ValueError):
            self.service.dispatch({'action': 'confirm', 'change_id': result['change_id'], 'healthy': True})
        with self.assertRaises(ValueError):
            self.service.dispatch({'action': 'confirm', 'change_id': result['change_id']})
        self.assertEqual(self.fixture.journal.snapshot()['change']['phase'], 'pending')

    def test_command_and_pid_injection_are_rejected(self):
        self.service.enable_test_apply = True
        for request in ({'action': 'shell', 'command': 'id'}, {'action': 'kill', 'pid': 1},
                        {'action': 'apply', 'generation': '../etc', 'timeout': 180},
                        {'action': 'status', 'path': '/etc/shadow'}):
            with self.assertRaises(ValueError): self.service.dispatch(request)
        self.assertIsNone(self.fixture.journal.snapshot()['change'])

    def test_archive_refuses_confirmed_running_or_pending_changes(self):
        with self.assertRaises(ValueError):
            self.service.dispatch({'action':'archive','generation':self.fixture.previous})
        self.service.enable_test_apply=True
        self.service.dispatch({'action':'apply','generation':self.fixture.candidate,'timeout':180})
        for action in ('archive','restore'):
            with self.assertRaises(ValueError):
                self.service.dispatch({'action':action,'generation':self.fixture.candidate})
        self.assertTrue((self.fixture.fixture.root/'generations'/self.fixture.candidate).is_dir())

    def test_status_distinguishes_running_selected_and_confirmed_without_keys(self):
        self.service.enable_test_apply = True
        self.service.dispatch({'action': 'apply', 'generation': self.fixture.candidate, 'timeout': 180})
        self.fixture.coordinator.tick()
        status = self.service.dispatch({'action': 'status'})
        self.assertEqual(status['selected_generation'], self.fixture.candidate)
        self.assertEqual(status['running_generation'], self.fixture.candidate)
        self.assertEqual(status['transaction']['state']['active'], self.fixture.previous)
        self.assertFalse(status['ready'])
        self.assertNotIn('AAAAAAAA', json.dumps(status))

    def test_storage_fallback_stops_candidate_and_disables_all_changes_without_false_ack(self):
        self.service.enable_test_apply = True
        result = self.service.dispatch({'action': 'apply', 'generation': self.fixture.candidate, 'timeout': 180})
        self.fixture.coordinator.tick()
        self.service.storage_fault = True; self.service.enable_test_apply = False
        self.fixture.coordinator.storage_recovery()
        self.fixture.driver.health = True
        status = self.service.dispatch({'action': 'status'})
        self.assertTrue(status['ready'])  # Fake driver proof only, no network claim.
        self.assertTrue(status['storage_fault'])
        self.assertFalse(status['database_recovery_acknowledged'])
        self.assertEqual(status['running_generation'], self.fixture.previous)
        self.assertEqual(status['transaction']['change']['phase'], 'pending')
        with self.assertRaises(ValueError):
            self.service.dispatch({'action': 'confirm', 'change_id': result['change_id']})
        with self.assertRaises(ValueError):
            self.service.dispatch({'action': 'prepare', 'files': self.fixture.fixture.files, 'label': 'x'})


if __name__ == '__main__':
    unittest.main()
