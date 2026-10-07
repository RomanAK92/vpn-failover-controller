import importlib.util
import os
import pathlib
import tempfile
import unittest
import subprocess
import sys
import sqlite3

ROOT = pathlib.Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location('transaction_journal', ROOT/'management/journal.py')
journal = importlib.util.module_from_spec(spec)
spec.loader.exec_module(journal)


class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        if os.name == 'posix': os.chmod(self.directory.name, 0o700)
        self.now = 1000
        self.store = journal.Journal(self.directory.name, 'boot-a', lambda: self.now)
        self.previous, self.candidate = 'a'*32, 'b'*32
        self.store.initialize(self.previous)

    def tearDown(self):
        self.store.close()
        self.directory.cleanup()

    def test_rollback_is_durable_before_driver_changes_anything(self):
        change = self.store.begin(self.candidate)
        state = self.store.snapshot()
        self.assertEqual(state['change']['id'], change)
        self.assertEqual(state['change']['previous'], self.previous)
        self.assertEqual(state['state']['active'], self.previous)
        other = journal.Journal(self.directory.name, 'boot-a', lambda: self.now)
        try:
            self.assertEqual(other.snapshot(), state)
        finally:
            other.close()

    def test_independent_watcher_expiry_requests_but_does_not_claim_recovery(self):
        self.store.begin(self.candidate, 60)
        other = journal.Journal(self.directory.name, 'boot-a', lambda: self.now)
        try:
            self.assertFalse(other.watch())
            self.now += 60
            self.assertTrue(other.watch())
            state = self.store.snapshot()
            self.assertEqual(state['state']['desired'], self.previous)
            self.assertEqual(state['change']['phase'], 'rollback-requested')
            with self.assertRaises(journal.TransactionError):
                self.store.restored(self.previous, state['state']['revision'])
            self.store.restored(self.previous, state['state']['revision'], fresh_health=True)
            self.assertEqual(other.snapshot()['change']['phase'], 'rolled-back')
        finally:
            other.close()

    def test_boot_change_and_clock_regression_request_rollback(self):
        for boot, now, reason in [('boot-b', 10, 'boot-changed'), ('boot-a', 999, 'clock-invalid')]:
            with self.subTest(boot=boot), tempfile.TemporaryDirectory() as directory:
                if os.name == 'posix': os.chmod(directory, 0o700)
                a = journal.Journal(directory, 'boot-a', lambda: 1000)
                a.initialize(self.previous); a.begin(self.candidate)
                b = journal.Journal(directory, boot, lambda: now)
                try:
                    self.assertTrue(b.watch())
                    self.assertEqual(a.snapshot()['change']['reason'], reason)
                finally:
                    a.close(); b.close()

    def test_no_confirmation_without_fresh_health_and_current_revision(self):
        change = self.store.begin(self.candidate)
        revision = self.store.snapshot()['state']['revision']
        for identifier, generation, rev, health in [
            ('wrong', self.candidate, revision, True),
            (change, self.previous, revision, True),
            (change, self.candidate, revision+1, True),
            (change, self.candidate, revision, False)]:
            with self.assertRaises(journal.TransactionError):
                self.store.confirm(identifier, generation, rev, health)
        self.store.confirm(change, self.candidate, revision, True)
        self.assertEqual(self.store.snapshot()['state']['active'], self.candidate)
        self.assertFalse(self.store.watch(force=True))

    def test_late_confirm_and_second_change_rejected(self):
        change = self.store.begin(self.candidate, 60)
        revision = self.store.snapshot()['state']['revision']
        with self.assertRaises(journal.TransactionError):
            self.store.begin('c'*32)
        self.now += 60
        with self.assertRaises(journal.TransactionError):
            self.store.confirm(change, self.candidate, revision, True)
        self.store.watch()
        with self.assertRaises(journal.TransactionError):
            self.store.confirm(change, self.candidate, revision, True)

    def test_cannot_overwrite_initial_generation_or_use_paths(self):
        with self.assertRaises(journal.TransactionError):
            self.store.initialize('c'*32)
        for candidate in ('../etc', '/root', '', 3):
            with self.assertRaises(journal.TransactionError):
                self.store.begin(candidate)
        self.assertEqual(self.store.snapshot()['state']['active'], self.previous)

    def test_only_precise_sqlite_full_errors_enable_legacy_storage_fallback(self):
        self.assertTrue(journal.storage_full(sqlite3.OperationalError('database or disk is full')))
        self.assertFalse(journal.storage_full(sqlite3.OperationalError('database is locked')))
        coded = sqlite3.OperationalError('message not relied upon'); coded.sqlite_errorcode = 13
        self.assertTrue(journal.storage_full(coded))
        coded.sqlite_errorcode = 5
        self.assertFalse(journal.storage_full(coded))

    @unittest.skipUnless(sys.platform == 'linux', 'Linux boot identity watcher')
    def test_watcher_process_survives_creator_connection_close_and_never_claims_recovery(self):
        self.store.begin(self.candidate)
        self.store.close()
        try:
            result = subprocess.run([sys.executable, str(ROOT/'management/rollback_watch.py'),
                '--state-dir', self.directory.name, '--once'], capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 0)
            self.assertIn('"recovery_proven": false', result.stdout)
            self.assertIn('"reason": "boot-changed"', result.stdout)
        finally:
            self.store = journal.Journal(self.directory.name, 'boot-a', lambda: self.now)
        self.assertEqual(self.store.snapshot()['change']['phase'], 'rollback-requested')


if __name__ == '__main__':
    unittest.main()
