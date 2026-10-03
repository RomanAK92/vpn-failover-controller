import importlib.util
import json
import pathlib
import tempfile
import unittest

SPEC=importlib.util.spec_from_file_location('dashboard_server',pathlib.Path(__file__).parents[1]/'dashboard/server.py')
server=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(server)

def fixture():
    return {'monotonic':100,'status_max_age':15,'active':'road-1','private_key':'DO-NOT-EXPORT',
            'settings':{'interval':2,'quorum':1,'failure_rounds':8,'recovery_rounds':30},
            'paths':[{'name':'road-1','kind':'wireguard','interface':'vpn-path-1'}],
            'healthy':{'road-1':True},'probes':{'road-1':{'10.60.0.10':True}},
            'failure_rounds':[0],'recovery_rounds':[30]}

class DashboardTests(unittest.TestCase):
    def test_allowlist_and_projection_roundtrip(self):
        data=server.project(fixture(),{'monotonic':100,'controller':True,'ike':True,'integrity':True,'secret':'DO-NOT-EXPORT'})
        self.assertNotIn('DO-NOT-EXPORT',json.dumps(data))
        self.assertEqual(server.project(data,data['watchdog']),data)

    def test_stale_and_supervisor_fault_cannot_show_connected(self):
        with tempfile.TemporaryDirectory() as directory:
            data=server.project(fixture(),{'monotonic':100,'controller':True,'ike':True,'integrity':True})
            path=pathlib.Path(directory)/'telemetry.json';path.write_text(json.dumps(data))
            monitor=server.Monitor(directory)
            self.assertTrue(monitor.snapshot(101)['available'])
            self.assertFalse(monitor.snapshot(120)['available'])
            data['watchdog']['controller']=False;path.write_text(json.dumps(data))
            self.assertFalse(monitor.snapshot(101)['available'])

    def test_bind_requires_private_address_and_authentication(self):
        server.check_binding('127.0.0.1','')
        server.check_binding('10.250.1.2','a'*32)
        for address,token in [('0.0.0.0','a'*32),('203.0.113.10','a'*32),('192.168.1.2','')]:
            with self.assertRaises(ValueError):server.check_binding(address,token)

    def test_corrupt_or_missing_telemetry_is_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            monitor=server.Monitor(directory)
            self.assertFalse(monitor.snapshot()['available'])
            (pathlib.Path(directory)/'telemetry.json').write_text('{invalid SECRET}')
            state=monitor.snapshot()
            self.assertFalse(state['available'])
            self.assertNotIn('SECRET',json.dumps(state))

    def test_unknown_switch_reason_not_exported(self):
        data=fixture();data['last_switch']={'time':99,'new':'road-1','reason':'password SECRET'}
        self.assertNotIn('SECRET',json.dumps(server.project(data,{})))
