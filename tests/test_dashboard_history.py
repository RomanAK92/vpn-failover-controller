import importlib.util
import json
import pathlib
import sys
import tempfile
import time
import unittest

ROOT = pathlib.Path(__file__).parents[1] / 'dashboard'
sys.path.insert(0, str(ROOT))
from history import History, MAX_AGE, valid_event
from server import Monitor
from install import plan, safe_path


class HistoryTests(unittest.TestCase):
    def test_atomic_roundtrip_bounds_and_no_raw_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            events = [{'time': time.time(), 'path': 'wg-main', 'message': 'wg-main: private-network probes are passing.'}] * 220
            history = History(directory)
            history.save(events, None)
            loaded, switch = history.load()
            self.assertEqual(len(loaded), 200)
            self.assertIsNone(switch)
            self.assertFalse((pathlib.Path(directory)/'history.tmp').exists())
            data = json.loads(history.path.read_text())
            self.assertEqual(set(data), {'version', 'events', 'switch_time'})

    def test_retention_and_secret_injection_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            history = History(directory)
            old = {'time': time.time()-MAX_AGE-1, 'path': 'wg-main', 'message': 'wg-main: private-network probes are passing.'}
            history.save([old], None)
            self.assertEqual(history.load()[0], [])
            history.save([dict(old, message='token SECRET')], None)
            with self.assertRaises(ValueError): history.load()

    def test_corrupt_history_does_not_break_live_monitor(self):
        with tempfile.TemporaryDirectory() as telemetry, tempfile.TemporaryDirectory() as saved:
            (pathlib.Path(saved)/'history.json').write_text('{bad')
            monitor = Monitor(telemetry, saved)
            self.assertIsNotNone(monitor.history_warning)
            self.assertFalse(monitor.snapshot()['available'])
            self.assertNotIn('{bad', json.dumps(monitor.snapshot()))

    def test_history_save_failure_is_explicit(self):
        with tempfile.TemporaryDirectory() as telemetry, tempfile.TemporaryDirectory() as saved:
            monitor = Monitor(telemetry, saved)
            def fail(*args): raise OSError('private secret error')
            monitor.history.save = fail
            monitor.history_warning = 'Retry'
            state = monitor.snapshot()
            self.assertIn('could not be saved', state['history_warning'])
            self.assertNotIn('private secret', json.dumps(state))

    def test_retention_removes_old_switch_after_newer_observation(self):
        with tempfile.TemporaryDirectory() as telemetry:
            monitor=Monitor(telemetry)
            monitor.events.extend([{'time':time.time(),'path':None,'message':'recent'},
                                   {'time':time.time()-MAX_AGE-1,'path':None,'message':'old'}])
            state=monitor.snapshot()
            self.assertEqual([e['message'] for e in state['events']], ['recent'])

    def test_route_event_scope(self):
        self.assertTrue(valid_event({'time':time.time(),'path':'ipsec-main','message':'Route changed: wg-main → ipsec-main. current path failure threshold reached.'}))
        self.assertFalse(valid_event({'time':time.time(),'path':'wg-main','message':'Route changed: wg-main → ipsec-main. current path failure threshold reached.'}))


@unittest.skipUnless(sys.platform == 'linux', 'Linux installer paths')
class InstallerTests(unittest.TestCase):
    def test_plan_has_only_two_dashboard_units_and_safe_mounts(self):
        rendered = plan('/opt/vpn-dashboard', '/var/lib/vpn-dashboard', '/run/vpn-router', '/etc/systemd/system')
        self.assertEqual(len(rendered), 3)
        combined = '\n'.join(rendered.values())
        self.assertNotIn('/run/vpn-router:/', combined)
        self.assertNotIn('docker.sock', combined)
        self.assertIn('127.0.0.1', combined)
        self.assertIn('PrivateNetwork=true', combined)
        self.assertIn('RuntimeDirectoryPreserve=yes', combined)
        self.assertIn('Restart=always', combined)

    def test_reject_unsafe_or_overlapping_paths(self):
        for bad in ('/', '/opt', '/opt/../tmp', '/tmp/with space', 'relative'):
            with self.assertRaises(ValueError): safe_path(bad)
        with self.assertRaises(ValueError):plan('/run/vpn-router/dashboard','/var/lib/history','/run/vpn-router','/etc/systemd/system')
        with tempfile.TemporaryDirectory() as directory:
            link = pathlib.Path(directory)/'link';link.symlink_to('/opt')
            with self.assertRaises(ValueError):safe_path(str(link/'dashboard'))
