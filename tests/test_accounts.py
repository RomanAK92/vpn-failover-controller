import importlib.util
import json
import os
import pathlib
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).parents[1]
sys.path.insert(0, str(ROOT/'dashboard'))
from accounts import Accounts, AuthError, IDLE, LIFETIME, origin_policy, cookie_header
PASSWORD = 'fixture passphrase for tests only'


class AccountTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        if os.name == 'posix':os.chmod(self.temp.name, 0o700)
        self.now = 1000000
        self.store = Accounts(self.temp.name, initialize=True, clock=lambda:self.now)
        self.store.put_user('admin', PASSWORD)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_hash_only_storage_and_independent_salts(self):
        self.store.put_user('viewer', PASSWORD, 'viewer')
        rows = self.store.db.execute('SELECT salt,hash FROM users').fetchall()
        self.assertNotEqual(rows[0], rows[1])
        self.assertNotIn(PASSWORD, pathlib.Path(self.temp.name,'accounts.sqlite3').read_bytes().decode('latin1'))

    def test_sessions_require_csrf_and_viewer_cannot_admin(self):
        self.store.put_user('viewer', PASSWORD, 'viewer')
        sid, user = self.store.login('viewer', PASSWORD, '127.0.0.1')
        self.assertEqual(self.store.session(sid)['role'], 'viewer')
        with self.assertRaises(AuthError):self.store.session(sid, admin=True)
        with self.assertRaises(AuthError):self.store.logout(sid, 'wrong')
        self.store.logout(sid, user['csrf'])
        with self.assertRaises(AuthError):self.store.session(sid)

    def test_polling_does_not_extend_idle_expiry(self):
        sid, _ = self.store.login('admin', PASSWORD, '127.0.0.1')
        for _ in range(3):
            self.now += IDLE/4
            self.store.session(sid, touch=False)
        self.now += IDLE/4
        with self.assertRaises(AuthError):self.store.session(sid)

    def test_activity_extends_idle_but_not_absolute_lifetime(self):
        sid, user = self.store.login('admin', PASSWORD, '127.0.0.1')
        for _ in range(int(LIFETIME/(IDLE/2))-1):
            self.now += IDLE/2
            self.store.session(sid, user['csrf'])
        self.now += IDLE/2
        with self.assertRaises(AuthError):self.store.session(sid)

    def test_lockout_survives_process_restart_and_ip_change(self):
        for i in range(5):
            with self.assertRaises(AuthError) as caught:self.store.login('admin', 'incorrect', '10.0.0.'+str(i+1))
            self.assertEqual(caught.exception.status, 401)
        self.store.close();self.store = Accounts(self.temp.name, clock=lambda:self.now)
        with self.assertRaises(AuthError) as caught:self.store.login('admin', PASSWORD, '10.0.0.10')
        self.assertEqual(caught.exception.status, 429)
        self.now += 901
        self.store.login('admin', PASSWORD, '10.0.0.10')

    def test_reset_invalidates_all_existing_sessions(self):
        sid, _ = self.store.login('admin', PASSWORD, '127.0.0.1')
        self.store.put_user('admin', 'a replacement fixture passphrase', replace=True)
        with self.assertRaises(AuthError):self.store.session(sid)
        with self.assertRaises(AuthError):self.store.login('admin', PASSWORD, '127.0.0.1')
        self.store.login('admin', 'a replacement fixture passphrase', '127.0.0.1')

    def test_account_change_requires_admin_csrf_and_reauthentication(self):
        self.store.put_user('viewer', PASSWORD, 'viewer')
        sid, user = self.store.login('admin', PASSWORD, '127.0.0.1')
        viewer, vu = self.store.login('viewer', PASSWORD, '127.0.0.1')
        with self.assertRaises(AuthError):self.store.change_user(viewer, vu['csrf'], PASSWORD, 'other', PASSWORD, 'viewer')
        with self.assertRaises(AuthError):self.store.change_user(sid, 'wrong', PASSWORD, 'other', PASSWORD, 'viewer')
        with self.assertRaises(AuthError):self.store.change_user(sid, user['csrf'], 'wrong', 'other', PASSWORD, 'viewer')
        self.store.change_user(sid, user['csrf'], PASSWORD, 'other', PASSWORD, 'viewer')
        self.assertEqual(self.store.list_users(sid)[1]['username'], 'other')

    def test_last_admin_cannot_be_demoted_and_self_reset_revokes_cookie(self):
        sid, user = self.store.login('admin', PASSWORD, '127.0.0.1')
        with self.assertRaises(ValueError):self.store.put_user('admin', PASSWORD, 'viewer', replace=True)
        result=self.store.change_user(sid, user['csrf'], PASSWORD, 'admin', 'new fixture passphrase for reset', 'admin', True)
        self.assertTrue(result['reauthenticate'])
        with self.assertRaises(AuthError):self.store.session(sid)

    def test_unknown_schema_is_not_overwritten_by_account_initialization(self):
        self.store.db.execute('PRAGMA user_version=9');self.store.db.commit()
        with self.assertRaises(ValueError):Accounts(self.temp.name, initialize=True)
        self.assertEqual(self.store.db.execute('PRAGMA user_version').fetchone()[0], 9)

    def test_restart_preserves_session_and_logout_revokes_it(self):
        sid, user = self.store.login('admin', PASSWORD, '127.0.0.1')
        self.store.close();self.store = Accounts(self.temp.name, clock=lambda:self.now)
        self.assertEqual(self.store.session(sid)['username'], 'admin')
        self.store.logout(sid, user['csrf'])
        with self.assertRaises(AuthError):self.store.session(sid)

    def test_security_events_do_not_contain_secrets(self):
        sid, _ = self.store.login('admin', PASSWORD, '127.0.0.1')
        data = json.dumps(self.store.events(sid))
        self.assertIn('login-success', data)
        self.assertNotIn(sid, data);self.assertNotIn(PASSWORD, data)

    def test_credentials_and_invalid_origin_rejected(self):
        for name, password in [('INVALID', PASSWORD), ('admin2', 'short')]:
            with self.assertRaises(ValueError):self.store.put_user(name, password)
        for origin in ['http://10.0.0.1:8787', 'https://user:pass@example.org', 'https://example.org/path', 'https://example.org?x=1']:
            with self.assertRaises(ValueError):origin_policy(origin)
        self.assertTrue(origin_policy('https://vpn.example.org'))
        self.assertFalse(origin_policy('http://127.0.0.1:8787'))
        self.assertIn('Secure', cookie_header('test', True))
        self.assertIn('HttpOnly', cookie_header('test', True))
        self.assertIn('SameSite=Strict', cookie_header('test', True))

    def test_missing_or_insecure_storage_cannot_start_anonymous(self):
        with self.assertRaises(ValueError):Accounts(pathlib.Path(self.temp.name)/'missing')
        if os.name == 'posix':
            os.chmod(pathlib.Path(self.temp.name)/'accounts.sqlite3', 0o644)
            with self.assertRaises(ValueError):Accounts(self.temp.name)
            os.chmod(pathlib.Path(self.temp.name)/'accounts.sqlite3', 0o600)


class AccountHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        if os.name == 'posix':os.chmod(cls.temp.name, 0o700)
        store=Accounts(cls.temp.name, initialize=True)
        store.put_user('admin', PASSWORD);store.put_user('viewer', PASSWORD, 'viewer');store.close()
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));cls.port=sock.getsockname()[1]
        cls.origin='http://127.0.0.1:'+str(cls.port)
        cls.log=open(pathlib.Path(cls.temp.name)/'http-test.log','w')
        cls.process=subprocess.Popen([sys.executable,str(ROOT/'dashboard/server.py'),'--port',str(cls.port),'--auth-dir',cls.temp.name,'--origin',cls.origin,'--telemetry',cls.temp.name],stdout=cls.log,stderr=cls.log)
        for _ in range(100):
            try:
                urllib.request.urlopen(cls.origin+'/api/auth',timeout=.2).close();break
            except OSError:time.sleep(.05)
        else:
            cls.process.terminate();cls.process.wait();raise RuntimeError('Account HTTP test startup failed')

    @classmethod
    def tearDownClass(cls):
        cls.process.terminate();cls.process.wait(timeout=5);cls.log.close();cls.temp.cleanup()

    def request(self,path,data=None,headers=None):
        defaults={'Content-Type':'application/json','Origin':self.origin,'X-VPN-Request':'1'}
        defaults.update(headers or {})
        req=urllib.request.Request(self.origin+path,data=json.dumps(data).encode() if data is not None else None,headers=defaults)
        try:response=urllib.request.urlopen(req,timeout=5)
        except urllib.error.HTTPError as exc:response=exc
        with response:return response.status,response.headers,json.load(response)

    def login(self,name='admin'):
        status, headers, user=self.request('/api/login',{'username':name,'password':PASSWORD})
        self.assertEqual(status,200)
        return headers['Set-Cookie'].split(';')[0],user

    def test_status_requires_session_without_token_bypass(self):
        self.assertEqual(self.request('/api/status',headers={'Authorization':'Bearer '+('a'*32)})[0],401)
        cookie,user=self.login()
        status,_,data=self.request('/api/status',headers={'Cookie':cookie})
        self.assertEqual(status,200);self.assertFalse(data['available'])
        self.assertNotIn('csrf',data)

    def test_cross_origin_login_and_host_rebinding_rejected(self):
        self.assertEqual(self.request('/api/login',{'username':'admin','password':PASSWORD},{'Origin':'https://attacker.example'})[0],403)
        self.assertEqual(self.request('/api/login',{'username':'admin','password':PASSWORD},{'Host':'attacker.example'})[0],403)
        self.assertEqual(self.request('/api/login',{'username':'admin','password':PASSWORD},{'X-VPN-Request':''})[0],403)

    def test_logout_requires_csrf_and_invalidates_cookie(self):
        cookie,user=self.login()
        self.assertEqual(self.request('/api/logout',{}, {'Cookie':cookie})[0],403)
        status, headers,_=self.request('/api/logout',{}, {'Cookie':cookie,'X-CSRF-Token':user['csrf']})
        self.assertEqual(status,200);self.assertIn('Max-Age=0',headers['Set-Cookie'])
        self.assertEqual(self.request('/api/session',headers={'Cookie':cookie})[0],401)

    def test_viewer_role_and_nonexistent_control_endpoint(self):
        cookie,_=self.login('viewer')
        self.assertEqual(self.request('/api/security-events',headers={'Cookie':cookie})[0],403)
        self.assertEqual(self.request('/api/apply',{}, {'Cookie':cookie})[0],404)

    def test_http_account_management_reauth_and_roles(self):
        cookie,user=self.login()
        body={'username':'operator','password':PASSWORD,'role':'viewer','current_password':PASSWORD,'replace':False}
        self.assertEqual(self.request('/api/accounts',body,{'Cookie':cookie})[0],403)
        headers={'Cookie':cookie,'X-CSRF-Token':user['csrf']}
        self.assertEqual(self.request('/api/accounts',dict(body,current_password='incorrect'),headers)[0],401)
        self.assertEqual(self.request('/api/accounts',body,headers)[0],200)
        result=self.request('/api/accounts',headers={'Cookie':cookie})
        self.assertIn({'username':'operator','role':'viewer'},result[2]['users'])
        viewer,v=self.login('operator')
        self.assertEqual(self.request('/api/accounts',dict(body,username='third'),{'Cookie':viewer,'X-CSRF-Token':v['csrf']})[0],403)

    def test_request_size_and_malformed_json_bounded(self):
        self.assertEqual(self.request('/api/login',{'password':'x'*5000})[0],413)
        self.assertEqual(self.request('/api/login',[]) [0],400)
        cookie,_=self.login()
        status,headers,_=self.request('/api/security-events',headers={'Cookie':cookie})
        self.assertEqual(status,200);self.assertEqual(headers['Cache-Control'],'no-store')


if __name__=='__main__':unittest.main()
