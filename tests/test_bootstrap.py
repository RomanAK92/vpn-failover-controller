import base64
import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
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
        peers = {p['peer']: peers[p['peer']] for p in c['paths']}
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

    @unittest.skipUnless(hasattr(os, 'geteuid') and os.geteuid() == 0, 'Actual root-owned Linux generation preparation')
    def test_persistent_manager_is_prepared_without_starting_or_enabling_apply(self):
        dest = self.root/'managed'
        config = json.loads((self.config/'controller.json').read_text())
        address = str(next(__import__('ipaddress').ip_network(config['subnet']).hosts()))
        result = bootstrap.prepare(dest, self.config, 'admin', 'synthetic-unit-password',
                                   managed=True, application={'address': address, 'port': 80})
        self.assertFalse(result['started'])
        manifest = json.loads((dest/'installation.json').read_text())
        self.assertTrue(manifest['managed']); self.assertFalse(manifest['live_apply_enabled'])
        private = dest/'data/management'
        self.assertEqual((private/'active').readlink(), pathlib.Path('generations')/manifest['initial_generation'])
        self.assertTrue((private/'readiness.json').is_file())
        self.assertEqual((dest/'data/control').stat().st_mode & 0o7777, 0o2750)
        self.assertEqual((dest/'data/control').stat().st_gid, 65532)
        compose = (dest/'compose.yaml').read_text()
        self.assertIn('./data/management:/management:rw', compose)
        self.assertIn('./data/control:/control:ro', compose)
        self.assertNotIn('--enable-test-apply', compose)
        self.assertNotIn('docker.sock', compose)
        self.assertNotIn('privileged:', compose)
        self.assertNotIn('tmpfs', compose.split('./data/management')[0].split('volumes:')[-1])

    @unittest.skipUnless(hasattr(os, 'geteuid') and os.geteuid() == 0, 'Actual root-owned Linux generation preparation')
    def test_bad_application_probe_discards_only_own_unpublished_stage(self):
        dest = self.root/'rejected-manager'
        with self.assertRaises(ValueError):
            bootstrap.prepare(dest, self.config, 'admin', 'synthetic-unit-password',
                              managed=True, application={'address': '8.8.8.8', 'port': 80})
        self.assertFalse(dest.exists())
        self.assertFalse(any(p.name.startswith('.rejected-manager-') for p in self.root.iterdir()))

    @unittest.skipUnless(hasattr(os, 'geteuid') and os.geteuid() == 0 and shutil.which('openssl'), 'Root OpenSSL certificate fixture')
    def test_private_https_is_staged_with_matching_certificate_and_restricted_proxy(self):
        tls = self.root/'certificates'; tls.mkdir(mode=0o700)
        subprocess.run(['openssl','req','-x509','-newkey','ec','-pkeyopt','ec_paramgen_curve:P-256',
            '-nodes','-days','2','-subj','/CN=vpn.test.invalid','-addext','subjectAltName=DNS:vpn.test.invalid,IP:127.0.0.1',
            '-keyout',str(tls/'privkey.pem'),'-out',str(tls/'fullchain.pem')],check=True,capture_output=True)
        (tls/'privkey.pem').chmod(0o600)
        settings={'origin':'https://vpn.test.invalid:8443','bind':'127.0.0.1','directory':str(tls)}
        destination=self.root/'tls-installation'
        bootstrap.prepare(destination,self.config,'admin','synthetic-unit-password',https=settings)
        key=destination/'data/tls/privkey.pem'
        self.assertEqual(key.stat().st_uid,0);self.assertEqual(key.stat().st_gid,101)
        self.assertEqual(key.stat().st_mode & 0o777,0o640)
        compose=(destination/'compose.yaml').read_text()
        self.assertIn('https://vpn.test.invalid:8443',compose)
        self.assertIn(bootstrap.NGINX_IMAGE,compose)
        self.assertIn('"/tmp:rw,noexec,nosuid,size=16m,uid=101,gid=101,mode=0700"',compose)
        self.assertNotIn('0.0.0.0', (destination/'data/https.conf').read_text())
        rejected=self.root/'bad-tls'
        with self.assertRaises(ValueError):
            bootstrap.prepare(rejected,self.config,'admin','synthetic-unit-password',
                https={**settings,'origin':'https://wrong.test.invalid:8443'})
        self.assertFalse(rejected.exists())
        ip_installation=self.root/'ip-tls-installation'
        bootstrap.prepare(ip_installation,self.config,'admin','synthetic-unit-password',
            https={**settings,'origin':'https://127.0.0.1:8443'})
        self.assertTrue(ip_installation.exists())

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
