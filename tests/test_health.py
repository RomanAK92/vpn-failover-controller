import json
from pathlib import Path
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'build'))
import health


class ReadinessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.runtime = Path(self.temp.name)
        self.status = {'monotonic': time.monotonic(), 'active': 'path-0'}
        self.watchdog = {'monotonic': time.monotonic(), 'controller': True,
                         'ike': True, 'integrity': True}
        self.save()

    def save(self):
        (self.runtime / 'status.json').write_text(json.dumps(self.status))
        (self.runtime / 'watchdog.json').write_text(json.dumps(self.watchdog))

    def test_fresh_files_without_running_owners_are_not_ready(self):
        self.assertFalse(health.healthy(self.runtime, lambda _: False))

    def test_both_owners_are_required(self):
        self.assertFalse(health.healthy(self.runtime,
                         lambda p: p.name == 'supervisor.lock'))

    def test_current_owners_and_fresh_healthy_files_are_ready(self):
        self.assertTrue(health.healthy(self.runtime, lambda _: True))

    def test_startup_or_stopping_watchdog_is_not_ready(self):
        self.watchdog['controller'] = False
        self.save()
        self.assertFalse(health.healthy(self.runtime, lambda _: True))

    def test_stale_or_future_status_is_not_ready(self):
        for timestamp in (time.monotonic() - 60, time.monotonic() + 60):
            self.status['monotonic'] = timestamp
            self.save()
            self.assertFalse(health.healthy(self.runtime, lambda _: True))

    @unittest.skipUnless(sys.platform.startswith('linux'), 'Linux owner locks')
    def test_actual_lock_owner_disappears_on_close(self):
        import fcntl
        path = self.runtime / 'supervisor.lock'
        self.assertFalse(health.owner_running(path))
        with path.open('w') as owner:
            self.assertFalse(health.owner_running(path))
            fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assertTrue(health.owner_running(path))
        self.assertFalse(health.owner_running(path))


if __name__ == '__main__':
    unittest.main()
