import base64
import importlib.util
import json
import os
import pathlib
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location('vpn_bootstrap', ROOT/'management/bootstrap.py')
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)


@unittest.skipUnless(os.name == 'posix', 'Linux private path/permissions checks')
class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='vpn-bootstrap-unit-')
        self.root = pathlib.Path(self.temporary.name)
        self.config = self.root/'config'
        self.config.mkdir(mode=0o700)
        c = json.loads((ROOT/'config/layouts/wireguard-2.json').read_text())
        peers = json.loads((ROOT/'config/layouts/wireguard-peers.json').read_text())
        for p in c['paths']:
            peers[p['peer']]['public_key'] = base64.b64encode(os.urandom(32)).decode()
            key = self.config/('wg-client-'+p['peer']+'.key')
            key.write_text(base64.b64encode(os.urandom(32)).decode()+'\n')
            key.chmod(0o600)
        for name, data in [('controller.json', c), ('peers.json', peers),
                           ('deployment.json', {'app_subnet': '172.30.0.0/16', 'publication': None})]:
            (self.config/name).write_text(json.dumps(data))
            (self.config/name).chmod(0o600)

    def tearDown(self):
        self.temporary.cleanup()

    def test_actual_engine_validator_and_bad_secret(self):
        c, names = bootstrap.validate_config(self.config)
        self.assertEqual(len(c['paths']), 2)
        self.assertIn('wg-client-peer-1.key', names)
        (self.config/'wg-client-peer-1.key').write_text('not-a-key')
        with self.assertRaises(ValueError):
            bootstrap.validate_config(self.config)

    def test_prepare_private_files_and_refuse_overwrite(self):
        dest = self.root/'installation'
        # Ownership is asserted here; actual UID readability is checked separately
        # by isolated root/Docker acceptance rather than mutating CI ownership.
        with mock.patch.object(bootstrap.os, 'geteuid', return_value=0), mock.patch.object(bootstrap.os, 'chown') as owner:
            result = bootstrap.prepare(dest, self.config, 'admin', 'synthetic-unit-password')
            self.assertFalse(result['started'])
            self.assertEqual(dest.stat().st_mode & 0o777, 0o700)
            self.assertEqual((dest/'config/wg-client-peer-1.key').stat().st_mode & 0o777, 0o600)
            self.assertTrue((dest/'web/mirror.py').is_file())
            owner.assert_any_call(mock.ANY, 65532, 65532)
            before = (dest/'installation.json').read_bytes()
            with self.assertRaises(ValueError):
                bootstrap.prepare(dest, self.config, 'admin', 'another-unit-password')
            self.assertEqual(before, (dest/'installation.json').read_bytes())
            self.assertNotIn(b'synthetic-unit-password', (dest/'data/accounts/accounts.sqlite3').read_bytes())

    def test_failed_password_leaves_no_installation(self):
        dest = self.root/'installation'
        with mock.patch.object(bootstrap.os, 'geteuid', return_value=0), mock.patch.object(bootstrap.os, 'chown'):
            with self.assertRaises(ValueError):
                bootstrap.prepare(dest, self.config, 'admin', 'short')
        self.assertFalse(dest.exists())
        self.assertFalse(any(p.name.startswith('.installation-') for p in self.root.iterdir()))

    def test_config_symlink_rejected_before_read(self):
        (self.config/'controller.json').unlink()
        (self.config/'controller.json').symlink_to('/etc/passwd')
        with self.assertRaises(ValueError):
            bootstrap.validate_config(self.config)

    def test_repository_destination_rejected_before_validation_or_writes(self):
        with mock.patch.object(bootstrap.os, 'geteuid', return_value=0), mock.patch.object(bootstrap, 'validate_config') as validate:
            with self.assertRaises(ValueError):
                bootstrap.prepare(ROOT/'private-test-installation', self.config, 'admin', 'synthetic-unit-password')
            validate.assert_not_called()


if __name__ == '__main__':
    unittest.main()
