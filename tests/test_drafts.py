import base64
import json
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).parents[1]
sys.path.insert(0, str(ROOT/'dashboard'))
from drafts import Drafts, DraftError, MAX_DRAFTS
import test_accounts


def bundle():
    c = json.loads((ROOT/'config/layouts/wireguard-2.json').read_text())
    peers = {p['peer']: {'endpoint': '203.0.113.'+str(i+10), 'port': 51889,
             'public_key': base64.b64encode(os.urandom(32)).decode()} for i, p in enumerate(c['paths'])}
    files = {'controller.json': json.dumps(c), 'peers.json': json.dumps(peers),
             'deployment.json': json.dumps({'app_subnet': '172.30.0.0/16', 'publication': None})}
    for peer in peers:
        files['wg-client-'+peer+'.key'] = base64.b64encode(os.urandom(32)).decode()+'\n'
    return files


@unittest.skipUnless(os.name == 'posix', 'Linux draft durability/permissions')
class DraftTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        os.chmod(self.temporary.name, 0o700)
        self.root = pathlib.Path(self.temporary.name)
        self.store = Drafts(self.root, ROOT/'build/doctor.py')

    def tearDown(self):
        self.temporary.cleanup()

    def test_persist_private_validated_draft_without_secret_summary(self):
        files = bundle()
        result = self.store.save(files, 'Two office roads')
        self.assertFalse(result['applied'])
        self.assertEqual(len(result['paths']), 2)
        self.assertNotIn(files['wg-client-peer-1.key'].strip(), json.dumps(result))
        again = Drafts(self.root, ROOT/'build/doctor.py')
        self.assertEqual(again.entries(), [result])
        for p in (self.root/result['id']).iterdir():
            self.assertEqual(p.stat().st_mode & 0o777, 0o600)

    def test_invalid_secret_never_becomes_generation(self):
        files = bundle()
        files['wg-client-peer-1.key'] = 'broken'
        with self.assertRaises(DraftError):
            self.store.save(files, 'Invalid draft')
        self.assertEqual(list(self.root.iterdir()), [])

    def test_private_transfer_rejects_modified_files_and_unsafe_receipt(self):
        files = bundle()
        summary = self.store.save(files, 'Private transfer')
        self.assertEqual(self.store.package(summary['id']), files)
        path = self.root/summary['id']/'controller.json'
        path.write_text('{}')
        with self.assertRaises(DraftError): self.store.package(summary['id'])
        path.write_text(files['controller.json'])
        path.chmod(0o644)
        with self.assertRaises(DraftError): self.store.package(summary['id'])

    def test_no_paths_hooks_raw_ipsec_or_unknown_settings(self):
        for change in ('path', 'hook', 'raw', 'field'):
            files = bundle()
            if change == 'path': files['../escaped'] = 'private'
            elif change == 'hook': files['PostUp'] = 'touch /tmp/should-never-run'
            elif change == 'raw': files['swan-client.conf'] = 'include /etc/passwd'
            else:
                c = json.loads(files['controller.json']); c['command'] = 'id'
                files['controller.json'] = json.dumps(c)
            with self.subTest(change=change), self.assertRaises(DraftError):
                self.store.save(files, 'Rejected')
        self.assertEqual(list(self.root.iterdir()), [])

    def test_limit_and_crash_staging_do_not_overwrite(self):
        for i in range(MAX_DRAFTS):
            (self.root/('.pending-'+str(i))).mkdir(mode=0o700)
        with self.assertRaises(DraftError):
            self.store.save(bundle(), 'Too many')
        self.assertEqual(len(list(self.root.iterdir())), MAX_DRAFTS)

    def test_wrong_owner_and_symlink_fail_closed(self):
        (self.root/'unrelated').mkdir()
        with self.assertRaises(DraftError):
            self.store.entries()
        (self.root/'unrelated').rmdir()
        (self.root/('a'*32)).symlink_to('/etc')
        with self.assertRaises(DraftError):
            self.store.inspect('a'*32)
        with self.assertRaises(DraftError):
            self.store.inspect('../etc')

    def test_validator_timeout_cleans_only_owned_staging(self):
        import subprocess
        import drafts
        files = bundle()
        with mock.patch.object(drafts.subprocess, 'run', side_effect=subprocess.TimeoutExpired('validator', 15)):
            with self.assertRaises(subprocess.TimeoutExpired):
                self.store.save(files, 'Timed out')
        self.assertEqual(list(self.root.iterdir()), [])


@unittest.skipUnless(os.name == 'posix', 'Linux draft storage')
class DraftHTTPTests(unittest.TestCase):
    @staticmethod
    def server_args(root):
        p = pathlib.Path(root)/'drafts'; p.mkdir(mode=0o700)
        return ['--draft-dir', str(p), '--validator', str(ROOT/'build/doctor.py')]

    @classmethod
    def setUpClass(cls):
        test_accounts.AccountHTTPTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        test_accounts.AccountHTTPTests.tearDownClass.__func__(cls)

    request = test_accounts.AccountHTTPTests.request
    login = test_accounts.AccountHTTPTests.login

    def test_authenticated_admin_csrf_and_viewer_boundary(self):
        body = {'files': bundle(), 'label': 'Office draft'}
        self.assertEqual(self.request('/api/drafts', body)[0], 401)
        viewer, v = self.login('viewer')
        self.assertEqual(self.request('/api/drafts', headers={'Cookie': viewer})[0], 403)
        self.assertEqual(self.request('/api/drafts', body,
            {'Cookie': viewer, 'X-CSRF-Token': v['csrf']})[0], 403)
        admin, a = self.login()
        self.assertEqual(self.request('/api/drafts', body, {'Cookie': admin})[0], 403)
        response = self.request('/api/drafts', body, {'Cookie': admin, 'X-CSRF-Token': a['csrf']})
        self.assertEqual(response[0], 201)
        self.assertFalse(response[2]['applied'])
        listing = self.request('/api/drafts', headers={'Cookie': admin})
        self.assertIn(response[2], listing[2]['drafts'])
        self.assertNotIn(body['files']['wg-client-peer-1.key'].strip(), json.dumps(listing[2]))

    def test_oversize_and_unknown_hooks_rejected_without_apply(self):
        admin, a = self.login()
        headers = {'Cookie': admin, 'X-CSRF-Token': a['csrf']}
        self.assertEqual(self.request('/api/drafts', {'files': {'x': 'a'*70000}, 'label': 'Huge'}, headers)[0], 413)
        files = bundle(); files['script.sh'] = 'id'
        self.assertEqual(self.request('/api/drafts', {'files': files, 'label': 'Rejected'}, headers)[0], 400)
        self.assertEqual(self.request('/api/apply', {}, headers)[0], 404)


if __name__ == '__main__':
    unittest.main()
