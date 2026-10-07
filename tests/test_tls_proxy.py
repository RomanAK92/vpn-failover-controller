import pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).parents[1]/'dashboard'))
from tls_proxy import render

class TLSConfigTests(unittest.TestCase):
    def test_private_tls_config_preserves_host_and_limits_requests(self):
        value=render('https://vpn.example.org:8443','10.250.1.2',allowed_cidrs=['10.60.0.0/24'])
        for expected in ['listen 10.250.1.2:8443 ssl','TLSv1.2 TLSv1.3','proxy_set_header Host $http_host','client_max_body_size 4k','rate=1r/s','ssl_session_tickets off']:
            self.assertIn(expected,value)
        self.assertNotIn('0.0.0.0',value)
        self.assertIn('allow 10.60.0.0/24;',value);self.assertIn('deny all;',value)
    def test_remote_allowlist_required_and_broad_public_or_injected_networks_rejected(self):
        with self.assertRaises(ValueError):render('https://vpn.example.org:8443','10.250.1.2')
        for value in ('0.0.0.0/0','10.0.0.0/8','203.0.113.0/24','10.60.0.1/24','10.60.0.0/24; allow all'):
            with self.subTest(value=value),self.assertRaises(ValueError):
                render('https://vpn.example.org:8443','10.250.1.2',allowed_cidrs=[value])
    def test_injection_public_bind_and_low_port_rejected(self):
        for origin,bind,port in [('https://vpn.example.org:8443','0.0.0.0',8787),('https://vpn.example.org:8443','203.0.113.1',8787),('https://evil;example:8443','127.0.0.1',8787),('https://vpn.example.org','127.0.0.1',8787),('http://127.0.0.1:8443','127.0.0.1',8787),('https://vpn.example.org:8787','127.0.0.1',8787)]:
            with self.assertRaises(ValueError):render(origin,bind,port)
