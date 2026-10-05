import pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).parents[1]/'dashboard'))
from tls_proxy import render

class TLSConfigTests(unittest.TestCase):
    def test_private_tls_config_preserves_host_and_limits_requests(self):
        value=render('https://vpn.example.org:8443','10.250.1.2')
        for expected in ['listen 10.250.1.2:8443 ssl','TLSv1.2 TLSv1.3','proxy_set_header Host $http_host','client_max_body_size 4k','rate=1r/s','ssl_session_tickets off']:
            self.assertIn(expected,value)
        self.assertNotIn('0.0.0.0',value)
    def test_injection_public_bind_and_low_port_rejected(self):
        for origin,bind,port in [('https://vpn.example.org:8443','0.0.0.0',8787),('https://vpn.example.org:8443','203.0.113.1',8787),('https://evil;example:8443','127.0.0.1',8787),('https://vpn.example.org','127.0.0.1',8787),('http://127.0.0.1:8443','127.0.0.1',8787),('https://vpn.example.org:8787','127.0.0.1',8787)]:
            with self.assertRaises(ValueError):render(origin,bind,port)
