import json
import os
import pathlib
import socket
import socketserver
import struct
import sys
import tempfile
import threading
import unittest

ROOT = pathlib.Path(__file__).parents[1]
sys.path.insert(0, str(ROOT/'dashboard'))
from control import Control, ControlError
from accounts import Accounts
import test_accounts
from test_drafts import bundle


class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        size = struct.unpack('!I', self.request.recv(4))[0]
        data = bytearray()
        while len(data) < size:
            data.extend(self.request.recv(size-len(data)))
        request = json.loads(data)
        self.server.requests.append(request)
        result = {'id': 'a'*32, 'applied': False} if request['action'] == 'prepare' else {'live_apply_enabled': True}
        encoded = json.dumps({'ok': True, 'result': result}).encode()
        self.request.sendall(struct.pack('!I', len(encoded))+encoded)


@unittest.skipUnless(sys.platform == 'linux' and os.geteuid() == 0, 'Root-owned Linux private IPC')
class ControlHTTPTests(unittest.TestCase):
    @staticmethod
    def server_args(root):
        p = pathlib.Path(root)/'drafts'; p.mkdir(mode=0o700)
        c = pathlib.Path(root)/'control'; c.mkdir(mode=0o750); os.chown(c, 0, 65532)
        ControlHTTPTests.engine = socketserver.UnixStreamServer(str(c/'prepare.sock'), Handler)
        ControlHTTPTests.engine.requests = []
        os.chown(c/'prepare.sock', 0, 65532); os.chmod(c/'prepare.sock', 0o660)
        ControlHTTPTests.thread = threading.Thread(target=ControlHTTPTests.engine.serve_forever, daemon=True)
        ControlHTTPTests.thread.start()
        return ['--draft-dir', str(p), '--validator', str(ROOT/'build/doctor.py'), '--control-dir', str(c)]

    @classmethod
    def setUpClass(cls):
        test_accounts.AccountHTTPTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        cls.engine.shutdown(); cls.engine.server_close(); cls.thread.join(timeout=2)
        test_accounts.AccountHTTPTests.tearDownClass.__func__(cls)

    request = test_accounts.AccountHTTPTests.request
    login = test_accounts.AccountHTTPTests.login

    def test_prepare_transfers_verified_private_bundle_without_http_secret_response(self):
        cookie, user = self.login()
        headers = {'Cookie': cookie, 'X-CSRF-Token': user['csrf']}
        files = bundle()
        code, _, draft = self.request('/api/drafts', {'files': files, 'label': 'Private office'}, headers)
        self.assertEqual(code, 201)
        count = len(self.engine.requests)
        body = {'draft': draft['id'], 'current_password': test_accounts.PASSWORD}
        self.assertEqual(self.request('/api/control/prepare', body, {'Cookie': cookie})[0], 403)
        self.assertEqual(self.request('/api/control/prepare', dict(body, current_password='wrong'), headers)[0], 401)
        self.assertEqual(len(self.engine.requests), count)
        code, _, result = self.request('/api/control/prepare', body, headers)
        self.assertEqual(code, 200)
        self.assertEqual(self.engine.requests[-1]['files'], files)
        self.assertNotIn('current_password', self.engine.requests[-1])
        self.assertNotIn(files['wg-client-peer-1.key'].strip(), json.dumps(result))
        events = self.request('/api/security-events', headers=headers)[2]['events']
        self.assertTrue(any(e['event'] == 'vpn-prepare-requested' and e['username'] == 'admin' for e in events))

    def test_viewer_and_default_apply_gate_cannot_contact_engine(self):
        cookie, user = self.login('viewer')
        headers = {'Cookie': cookie, 'X-CSRF-Token': user['csrf']}
        count = len(self.engine.requests)
        self.assertEqual(self.request('/api/control/status', headers=headers)[0], 403)
        self.assertEqual(self.request('/api/control/preview', {'generation': 'a'*32}, headers)[0], 403)
        cookie, user = self.login()
        headers = {'Cookie': cookie, 'X-CSRF-Token': user['csrf']}
        body = {'generation': 'a'*32, 'timeout': 180, 'current_password': test_accounts.PASSWORD}
        self.assertEqual(self.request('/api/control/apply', body, headers)[0], 403)
        self.assertEqual(self.request('/api/control/preview', {'generation': 'a'*32, 'healthy': True}, headers)[0], 400)
        self.assertEqual(len(self.engine.requests), count)

    def test_socket_replacement_and_oversize_requests_rejected(self):
        client = Control(pathlib.Path(self.temp.name)/'control')
        with self.assertRaises(ControlError):client.request('prepare', files={'x': 'x'*80000})
        path = pathlib.Path(self.temp.name)/'control/prepare.sock'
        os.chmod(path, 0o666)
        try:
            with self.assertRaises(ControlError):client.request('status')
        finally:os.chmod(path, 0o660)


if __name__ == '__main__':unittest.main()
