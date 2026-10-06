import copy
import json
import os
import pathlib
import signal
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).parents[1]
sys.path.insert(0, str(ROOT/'management'))
import driver


class ApplicationProbeTests(unittest.TestCase):
    def test_rejects_public_loopback_scripts_queries_and_invalid_ports(self):
        for settings in ({'address': '127.0.0.1', 'port': 80},
                         {'address': '203.0.113.10', 'port': 80},
                         {'address': '10.60.0.60', 'port': True},
                         {'address': '10.60.0.60', 'port': 80, 'path': '/?token=private'},
                         {'address': '10.60.0.60', 'port': 80, 'command': 'id'}):
            with self.assertRaises(ValueError): driver.ApplicationProbe(settings, '10.60.0.0/24')

    def test_oversized_body_and_wrong_http_status_do_not_prove_readiness(self):
        probe = driver.ApplicationProbe({'address': '10.60.0.60', 'port': 80}, '10.60.0.0/24')
        response = mock.Mock(status=200); response.read.return_value = b'x'*4097
        connection = mock.Mock(); connection.getresponse.return_value = response
        with mock.patch.object(driver.http.client, 'HTTPConnection', return_value=connection):
            self.assertFalse(probe.check())
            response.read.return_value = b'ok'; response.status = 503
            self.assertFalse(probe.check())
            response.status = 200
            self.assertTrue(probe.check())
        connection.close.assert_called()

    def test_explicit_tcp_probe_requires_a_real_connection_and_never_claims_http_validation(self):
        probe=driver.ApplicationProbe({'address':'10.60.0.60','port':22,'scheme':'tcp'},'10.60.0.0/24')
        with mock.patch.object(driver.socket,'create_connection',side_effect=OSError()):self.assertFalse(probe.check())
        connection=mock.MagicMock()
        with mock.patch.object(driver.socket,'create_connection',return_value=connection) as connect:
            self.assertTrue(probe.check());connect.assert_called_once_with(('10.60.0.60',22),timeout=2)
            connection.__exit__.assert_called_once()
        with self.assertRaises(ValueError):
            driver.ApplicationProbe({'address':'10.60.0.60','port':22,'scheme':'tcp','path':'/api'},'10.60.0.0/24')


@unittest.skipUnless(sys.platform == 'linux', 'Linux owned process sessions')
class ProcessDriverTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        self.config = self.root/'config'; self.config.mkdir()
        c = json.loads((ROOT/'config/layouts/wireguard-2.json').read_text())
        (self.config/'controller.json').write_text(json.dumps(c))
        for name in ('peers.json', 'deployment.json'):
            (self.config/name).write_text('{}')
        for path in c['paths']:
            (self.config/('wg-client-'+path['peer']+'.key')).write_text('synthetic only')
        self.app = self.root/'app'; self.app.mkdir()
        # This fixture tests process ownership only, not credential/network health.
        (self.app/'doctor.py').write_text('raise SystemExit(0)\n')
        (self.app/'supervisor.py').write_text('import time\ntime.sleep(120)\n')
        self.routes = mock.patch.object(driver.EngineDriver, 'defaults', return_value='[]')
        self.routes.start()
        self.driver = driver.EngineDriver(self.config, self.root/'runtime', self.app)

    def tearDown(self):
        self.driver.stop()
        self.routes.stop()
        self.temp.cleanup()

    def test_owns_its_session_refuses_double_start_and_cannot_be_false_green(self):
        self.driver.start('a'*32)
        self.assertTrue(self.driver.running())
        self.assertEqual(os.getsid(self.driver.process.pid), self.driver.process.pid)
        with self.assertRaises(driver.DriverError): self.driver.start('b'*32)
        self.assertFalse(self.driver.ready('a'*32))  # No application/readiness proof.
        self.driver.stop()
        self.assertFalse(self.driver.running())

    def test_killed_unreaped_leader_still_allows_owned_descendant_cleanup(self):
        ready = self.root/'child-pid'
        (self.app/'supervisor.py').write_text('import pathlib,subprocess,sys,time\n'
            'p=subprocess.Popen([sys.executable,"-c","import time;time.sleep(120)"])\n'
            'pathlib.Path('+repr(str(ready))+').write_text(str(p.pid))\ntime.sleep(120)\n')
        self.driver.start('a'*32)
        deadline = time.monotonic()+3
        while not ready.exists() and time.monotonic()<deadline: time.sleep(.02)
        self.assertTrue(ready.exists())
        child = int(ready.read_text())
        os.kill(self.driver.process.pid, signal.SIGKILL)
        deadline = time.monotonic()+3
        while self.driver.running() and time.monotonic()<deadline: time.sleep(.02)
        self.assertFalse(self.driver.running())
        self.driver.stop()
        try:
            state = pathlib.Path('/proc/'+str(child)+'/stat').read_text().rsplit(')',1)[1].split()[0]
            self.assertEqual(state, 'Z')
        except FileNotFoundError:
            pass

    def test_changed_default_route_refuses_start_before_child_creation(self):
        with mock.patch.object(self.driver, 'defaults', return_value='changed'):
            with self.assertRaises(driver.DriverError): self.driver.start('a'*32)
        self.assertIsNone(self.driver.process)


if __name__ == '__main__':
    unittest.main()
