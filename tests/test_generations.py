import importlib.util
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).parents[1]
sys.path.insert(0, str(ROOT/'management'))
from journal import Journal, TransactionError
from generations import Generations


@unittest.skipUnless(sys.platform == 'linux', 'Linux atomic private generation pointers')
class GenerationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        os.chmod(self.root, 0o700)
        (self.root/'generations').mkdir(mode=0o700)
        self.previous, self.candidate = 'a'*32, 'b'*32
        for name in (self.previous, self.candidate):
            (self.root/'generations'/name).mkdir(mode=0o700)
        self.now = 1000
        self.journal = Journal(self.root, 'boot-a', lambda: self.now)
        self.journal.initialize(self.previous)
        self.pointers = Generations(self.root)
        self.pointers.initialize(self.previous)

    def tearDown(self):
        self.journal.close()
        self.temp.cleanup()

    def test_candidate_requires_preallocated_previous_pointer(self):
        change = self.journal.begin(self.candidate)
        with self.assertRaises(TransactionError):
            self.pointers.select(change, self.candidate, self.journal)
        self.assertEqual(self.pointers.active(), self.previous)
        self.pointers.pointers(change, self.previous, self.candidate)
        self.pointers.select(change, self.candidate, self.journal)
        self.assertEqual(self.pointers.active(), self.candidate)
        self.assertEqual(self.journal.snapshot()['change']['phase'], 'pending')

    def test_recovery_reuses_existing_pointer_and_does_not_claim_traffic(self):
        change = self.journal.begin(self.candidate)
        self.pointers.pointers(change, self.previous, self.candidate)
        self.pointers.select(change, self.candidate, self.journal)
        self.now += 181; self.journal.watch()
        # Simulates inability to allocate new files/symlinks during recovery.
        # It does not claim a real disk-full filesystem acceptance test.
        with mock.patch('generations.os.symlink', side_effect=OSError('no new allocation')):
            self.assertTrue(self.pointers.recover(self.journal))
        self.assertEqual(self.pointers.active(), self.previous)
        self.assertEqual(self.journal.snapshot()['change']['phase'], 'rollback-requested')
        self.assertFalse(self.pointers.recover(self.journal))

    def test_readonly_recovery_checks_actual_expiry_not_supplied_browser_state(self):
        change = self.journal.begin(self.candidate, 60)
        self.pointers.pointers(change, self.previous, self.candidate)
        self.pointers.select(change, self.candidate, self.journal)
        with self.assertRaises(TransactionError): self.pointers.recover(self.journal)
        self.now += 60  # No UPDATE is needed to verify independently expired intent.
        self.assertTrue(self.pointers.recover(self.journal))
        self.assertEqual(self.journal.snapshot()['change']['phase'], 'pending')
        with self.assertRaises(TransactionError):
            self.journal.confirm(change, self.candidate, 2, True)

    def test_a_newer_or_unrelated_generation_is_never_rolled_back(self):
        change = self.journal.begin(self.candidate, 60)
        self.pointers.pointers(change, self.previous, self.candidate)
        self.pointers.select(change, self.candidate, self.journal)
        unrelated = 'c'*32
        (self.root/'generations'/unrelated).mkdir(mode=0o700)
        (self.root/'active').unlink(); (self.root/'active').symlink_to('generations/'+unrelated)
        self.now += 60
        with self.assertRaises(TransactionError): self.pointers.recover(self.journal)
        self.assertEqual(self.pointers.active(), unrelated)

    def test_expired_or_foreign_pointer_selection_is_rejected(self):
        change = self.journal.begin(self.candidate, 60)
        self.pointers.pointers(change, self.previous, self.candidate)
        self.now += 60
        with self.assertRaises(TransactionError):
            self.pointers.select(change, self.candidate, self.journal)
        self.assertEqual(self.pointers.active(), self.previous)
        (self.root/'active').unlink(); (self.root/'active').symlink_to('/etc')
        with self.assertRaises(TransactionError): self.pointers.active()

    def test_unrelated_staging_file_is_preserved(self):
        change = self.journal.begin(self.candidate)
        p = self.root/('recovery-'+change); p.write_text('unrelated evidence')
        with self.assertRaises(TransactionError):
            self.pointers.pointers(change, self.previous, self.candidate)
        self.assertEqual(p.read_text(), 'unrelated evidence')
        self.assertEqual(self.pointers.active(), self.previous)


if __name__ == '__main__':
    unittest.main()
