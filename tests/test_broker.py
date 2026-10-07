import copy
import importlib.util
import json
import os
import pathlib
import socket
import struct
import sys
import tempfile
import threading
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).parents[1]
if sys.platform == 'linux':
    sys.path.insert(0, str(ROOT/'management'))
    import broker


@unittest.skipUnless(sys.platform == 'linux', 'Linux private Unix socket broker')
class BrokerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        os.chmod(self.root, 0o700)
        (self.root/'generations').mkdir(mode=0o700)
        self.broker = broker.PrepareBroker(self.root, ROOT/'build/doctor.py')
        config = json.loads((ROOT/'config/layouts/wireguard-2.json').read_text())
        key = 'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAE='
        peers = {p['peer']: {'endpoint': '203.0.113.10', 'port': 51820, 'public_key': key}
                 for p in config['paths']}
        self.files = {'controller.json': json.dumps(config), 'peers.json': json.dumps(peers),
                      'deployment.json': json.dumps({'app_subnet': '172.30.0.0/16', 'publication': None})}
        self.files.update({'wg-client-'+p['peer']+'.key': key+'\n' for p in config['paths']})

    def tearDown(self):
        self.temp.cleanup()

    def prepare(self, files=None):
        return self.broker.dispatch({'action': 'prepare', 'files': files or self.files, 'label': 'Private test'})

    def test_archive_refuses_active_and_recovery_references_but_preserves_unused_version(self):
        first=self.prepare()['id'];second=self.prepare()['id']
        self.broker.generations.initialize(first)
        with self.assertRaises(ValueError):self.broker.dispatch({'action':'archive','generation':first})
        pointer=self.root/('recovery-'+'c'*32);pointer.symlink_to('generations/'+second)
        with self.assertRaises(ValueError):self.broker.dispatch({'action':'archive','generation':second})
        pointer.unlink()  # Owned fake reference only; no live cleanup.
        self.broker.dispatch({'action':'archive','generation':second})
        self.assertEqual(self.broker.generations.active(),first)
        self.assertEqual(self.broker.dispatch({'action':'status'})['archived'][0]['id'],second)
        self.broker.dispatch({'action':'restore','generation':second})
        self.assertEqual(self.broker.load(second),self.files)

    def test_private_prepare_and_priority_preview_never_apply(self):
        first = self.prepare()
        self.assertEqual(first['state'], 'prepared')
        self.assertFalse(first['applied'])
        self.broker.generations.initialize(first['id'])  # Offline fixture only, not a broker verb.
        second_files = copy.deepcopy(self.files)
        config = json.loads(second_files['controller.json']); config['paths'].reverse()
        second_files['controller.json'] = json.dumps(config)
        second = self.prepare(second_files)
        result = self.broker.dispatch({'action': 'preview', 'generation': second['id']})
        self.assertTrue(result['live_footprint_compatible'])
        self.assertFalse(result['applied'])
        self.assertEqual(self.broker.generations.active(), first['id'])
        self.assertNotIn('AAAAAAAA', json.dumps(self.broker.dispatch({'action': 'status'})))

    def test_unpermitted_verbs_fields_and_paths_are_rejected(self):
        for request in ({'action': 'apply'}, {'action': 'shell', 'command': 'id'},
                        {'action': 'status', 'path': '/etc'},
                        {'action': 'preview', 'generation': '../etc'},
                        {'action': 'prepare', 'files': self.files, 'label': 'x', 'health': True}):
            with self.subTest(request=request['action']), self.assertRaises(ValueError):
                self.broker.dispatch(request)
        self.assertEqual(list((self.root/'generations').iterdir()), [])

    def test_corrupted_key_or_receipt_cannot_be_previewed(self):
        first = self.prepare(); self.broker.generations.initialize(first['id'])
        second = self.prepare()
        directory = self.root/'generations'/second['id']
        name = next(p for p in directory.iterdir() if p.suffix == '.key')
        name.write_text('changed credential')
        with self.assertRaises(ValueError): self.broker.load(second['id'])
        name.unlink(); name.symlink_to('/etc/passwd')
        with self.assertRaises(ValueError): self.broker.load(second['id'])
        self.assertEqual(self.broker.generations.active(), first['id'])

    def test_changed_generation_permissions_are_rejected(self):
        item = self.prepare(); directory = self.root/'generations'/item['id']
        (directory/'controller.json').chmod(0o644)
        with self.assertRaises(ValueError): self.broker.load(item['id'])

    def run_server(self, allowed_uids):
        server = broker.BrokerServer(self.root/'test.sock', self.broker, allowed_uids)
        thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01})
        thread.start()
        self.addCleanup(thread.join, 2)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server

    def test_socket_uses_kernel_peer_identity_and_fixed_size_frames(self):
        self.run_server((os.geteuid(),))
        with socket.socket(socket.AF_UNIX) as connection:
            connection.settimeout(2); connection.connect(str(self.root/'test.sock'))
            broker.send(connection, {'action': 'status'}, broker.MAX_REQUEST)
            result = broker.receive(connection, broker.MAX_RESPONSE)
        self.assertTrue(result['ok'])
        self.assertFalse(result['result']['live_apply_enabled'])
        with socket.socket(socket.AF_UNIX) as connection:
            connection.settimeout(2); connection.connect(str(self.root/'test.sock'))
            connection.sendall(struct.pack('!I', broker.MAX_REQUEST+1))
            self.assertFalse(broker.receive(connection, broker.MAX_RESPONSE)['ok'])

    def test_other_kernel_uid_is_refused_before_reading_payload(self):
        self.run_server((os.geteuid()+100000,))
        with socket.socket(socket.AF_UNIX) as connection:
            connection.settimeout(2); connection.connect(str(self.root/'test.sock'))
            self.assertEqual(connection.recv(4), b'')

    def test_validation_errors_do_not_echo_credential_payload(self):
        self.run_server((os.geteuid(),))
        bad = copy.deepcopy(self.files); bad['controller.json'] = 'secret-not-json'
        with socket.socket(socket.AF_UNIX) as connection:
            connection.settimeout(2); connection.connect(str(self.root/'test.sock'))
            broker.send(connection, {'action': 'prepare', 'files': bad, 'label': 'x'}, broker.MAX_REQUEST)
            result = broker.receive(connection, broker.MAX_RESPONSE)
        self.assertFalse(result['ok'])
        self.assertNotIn('secret-not-json', json.dumps(result))
        self.assertEqual(list((self.root/'generations').iterdir()), [])

    @unittest.skipUnless(os.name == 'posix' and hasattr(os, 'geteuid') and os.geteuid() == 0,
                         'Root-only socket ownership fixture')
    def test_socket_directory_umask_lock_and_foreign_file_refusal(self):
        path = self.root/'socket'
        old = os.umask(0o077)
        try:
            with broker.socket_directory(path) as target:
                self.assertEqual(path.stat().st_mode & 0o777, 0o750)
                with self.assertRaises(BlockingIOError):
                    with broker.socket_directory(path): pass
                target.write_text('unrelated')
            with self.assertRaises(ValueError):
                with broker.socket_directory(path): pass
            self.assertEqual((path/'prepare.sock').read_text(), 'unrelated')
        finally:
            os.umask(old)


if __name__ == '__main__':
    unittest.main()
