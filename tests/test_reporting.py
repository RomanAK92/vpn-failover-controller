import importlib.util
import json
import os
import pathlib
import tempfile
import threading
import unittest
import urllib.error
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from unittest import mock

ROOT=pathlib.Path(__file__).parents[1]
spec=importlib.util.spec_from_file_location('safe_kuma_reporter',ROOT/'monitoring/kuma_push.py')
reporter=importlib.util.module_from_spec(spec);spec.loader.exec_module(reporter)


def projected():
 return {'monotonic':100,'status_max_age':20,'active':'main','settings':{'failure_rounds':8},
  'watchdog':{'monotonic':100,'controller':True,'integrity':True,'ike':True},
  'paths':[{'name':name,'kind':kind,'healthy':True,'failed_rounds':0,'probes':{'10.60.0.1':True}}
    for name,kind in [('main','wireguard'),('backup','ipsec')]],'unknown_secret':'never-export-this'}


class ReportingTests(unittest.TestCase):
 def test_projection_health_and_ike_failure_are_protocol_specific(self):
  value=projected();results=reporter.classify_projection(value,100)
  self.assertTrue(all(v[0]=='up' for v in results.values()))
  self.assertNotIn('never-export-this',json.dumps(results));self.assertNotIn('10.60.0.1',json.dumps(results))
  value['watchdog']['ike']=False;results=reporter.classify_projection(value,100)
  self.assertEqual(results['main'][0],'up');self.assertEqual(results['backup'][0],'down')
 def test_projection_preserves_failure_threshold_and_refuses_stale_status(self):
  value=projected();value['paths'][0].update(healthy=False,failed_rounds=7)
  self.assertEqual(reporter.classify_projection(value,100)['main'][0],'up')
  value['paths'][0]['failed_rounds']=8
  self.assertEqual(reporter.classify_projection(value,100)['main'][0],'down')
  self.assertTrue(all(v[0]=='down' for v in reporter.classify_projection(value,121).values()))
 def test_malformed_fields_never_echo_private_values_or_become_healthy(self):
  value=projected();value['monotonic']='private-value-do-not-transmit'
  results=reporter.classify_projection(value,100)
  self.assertTrue(all(v[0]=='down' for v in results.values()))
  self.assertNotIn('private-value',json.dumps(results))
  value=projected();value['watchdog']['integrity']='true'
  self.assertTrue(all(v[0]=='down' for v in reporter.classify_projection(value,100).values()))
  value['paths'][0]['name']='untrusted\nlabel'
  with self.assertRaises(ValueError):reporter.classify_projection(value,100)
 def test_wrong_token_mapping_never_sends_a_request(self):
  with mock.patch.object(reporter,'push') as push:
   with self.assertRaises(ValueError):reporter.deliver({'base_url':'https://monitor.example.com','tokens':{}},{'main':('up','available')})
   push.assert_not_called()
 @unittest.skipUnless(os.name=='posix','Linux private configuration mode')
 def test_private_configuration_and_symlink_refusal(self):
  with tempfile.TemporaryDirectory() as directory:
   path=pathlib.Path(directory)/'private.json';path.write_text('{}');path.chmod(0o600)
   self.assertEqual(reporter.read_bounded(path,True),{})
   path.chmod(0o644)
   with self.assertRaises(ValueError):reporter.read_bounded(path,True)
   link=path.parent/'alias';link.symlink_to(path)
   with self.assertRaises(ValueError):reporter.read_bounded(link)
 def test_real_loopback_push_and_redirect_refusal(self):
  requests=[]
  class Handler(BaseHTTPRequestHandler):
   def do_GET(self):
    requests.append(self.path)
    if self.path.startswith('/api/push/'+'B'*24):
     self.send_response(302);self.send_header('Location','/unapproved-destination');self.end_headers();return
    body=b'{"ok":true}';self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
   def log_message(self,*args):pass
  server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
  thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
  try:
   base='http://127.0.0.1:'+str(server.server_port)
   reporter.push(base,'A'*24,'up','main ACTIVE')
   with self.assertRaises(urllib.error.HTTPError):reporter.push(base,'B'*24,'down','standby unavailable')
   self.assertEqual(len(requests),2);self.assertFalse(any('/unapproved-destination' in p for p in requests))
  finally:server.shutdown();server.server_close();thread.join()
