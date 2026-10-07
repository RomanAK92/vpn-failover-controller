import importlib.util
import json
import os
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).parents[1]
AVAILABLE = sys.platform == 'linux' and importlib.util.find_spec('cryptography') is not None
if AVAILABLE:
    sys.path.insert(0, str(ROOT/'management'))
    import backup
    from test_drafts import bundle
    import test_bootstrap


@unittest.skipUnless(AVAILABLE, 'Linux maintained cryptography runtime')
class EncryptionTests(unittest.TestCase):
    def payload(self):
        files = bundle()
        subnet = json.loads(files['controller.json'])['subnet']
        address = str(next(__import__('ipaddress').ip_network(subnet).hosts()))
        return {'schema': 1, 'files': files, 'application': {'address': address, 'port': 80}}

    def test_authenticated_randomized_round_trip_without_plaintext_credentials(self):
        payload = self.payload(); password = 'synthetic backup passphrase only'
        first = backup.encrypt(payload, password); second = backup.encrypt(payload, password)
        self.assertNotEqual(first, second)
        self.assertEqual(backup.decrypt(first, password), payload)
        self.assertNotIn(payload['files']['wg-client-peer-1.key'].strip().encode(), first)

    def test_wrong_passphrase_and_modified_nonce_ciphertext_or_tag_rejected(self):
        password = 'synthetic backup passphrase only'
        content = backup.encrypt(self.payload(), password)
        with self.assertRaises(ValueError): backup.decrypt(content, 'a different wrong passphrase')
        for index in (len(backup.HEADER), len(backup.HEADER)+16, len(backup.HEADER)+30, len(content)-1):
            changed = bytearray(content); changed[index] ^= 1
            with self.subTest(index=index), self.assertRaises(ValueError): backup.decrypt(bytes(changed), password)
        with self.assertRaises(ValueError): backup.decrypt(b'x'*(backup.MAX_ENCRYPTED+1), password)
        with self.assertRaises(ValueError): backup.decrypt(content, 'short')

    def test_authenticated_unsupported_files_are_still_rejected(self):
        payload = self.payload(); payload['files']['../escape'] = 'malicious'
        password = 'synthetic backup passphrase only'
        encrypted = backup.encrypt(payload, password)
        with self.assertRaises(ValueError): backup.decrypt(encrypted, password)


@unittest.skipUnless(AVAILABLE and hasattr(os, 'geteuid') and os.geteuid() == 0, 'Root Linux offline recovery fixture')
class OfflineRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_bootstrap.BootstrapTests(); self.fixture.setUp()
        self.directory = self.fixture.root
        config = json.loads((self.fixture.config/'controller.json').read_text())
        self.application = {'address': str(next(__import__('ipaddress').ip_network(config['subnet']).hosts())), 'port': 80}
        self.original = self.directory/'original'
        backup.prepare(self.original, self.fixture.config, 'admin', 'synthetic administrator only',
                       managed=True, application=self.application)

    def tearDown(self): self.fixture.tearDown()

    def test_confirmed_snapshot_restore_is_new_private_installation_without_old_sessions(self):
        snapshot = backup.snapshot(self.original)
        folder = self.directory/'backups'; folder.mkdir(mode=0o700)
        output = folder/'confirmed.vpnbackup'
        encrypted = backup.encrypt(snapshot, 'synthetic backup passphrase only')
        backup.write_backup(output, encrypted)
        self.assertEqual(output.stat().st_mode & 0o777, 0o600)
        with self.assertRaises(FileExistsError): backup.write_backup(output, encrypted)
        restored = self.directory/'restored'
        result = backup.restore(backup.decrypt(output.read_bytes(), 'synthetic backup passphrase only'), restored,
                                'rescue', 'a new administrator passphrase')
        self.assertFalse(result['started'])
        self.assertEqual(backup.snapshot(restored), snapshot)
        import sqlite3
        with sqlite3.connect(restored/'data/accounts/accounts.sqlite3') as database:
            self.assertEqual(database.execute('SELECT name FROM users').fetchall(), [('rescue',)])
            self.assertEqual(database.execute('SELECT COUNT(*) FROM sessions').fetchone()[0], 0)
        with self.assertRaises(ValueError): backup.restore(snapshot, self.original, 'rescue', 'a new administrator passphrase')

    def test_unconfirmed_backup_and_unsafe_permissions_are_rejected(self):
        private = self.original/'data/management'
        journal = backup.Journal(private, pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip())
        try: journal.begin('b'*32, 180)
        finally: journal.close()
        with self.assertRaises(ValueError): backup.snapshot(self.original)
        path = self.original/'installation.json'; path.chmod(0o644)
        with self.assertRaises(ValueError): backup.private_file(path, 32768)


if __name__ == '__main__': unittest.main()
