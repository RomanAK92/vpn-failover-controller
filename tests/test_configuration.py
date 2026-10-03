import base64
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'build'))
import configuration as config
import guard
import doctor
import status
from ipsec_config import render_ipsec

class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.c=json.loads((ROOT/'config/examples/controller.json').read_text())
        self.d=json.loads((ROOT/'config/examples/deployment.json').read_text())
        self.meta=json.loads((ROOT/'config/examples/peers.json').read_text())

    def test_custom_layout_generates_matching_rules_and_selectors(self):
        self.c['subnet']='10.70.0.0/24';self.c['targets']=['10.70.0.10']
        self.c['quorum']=1;self.c['interval']=10
        for i,p in enumerate(self.c['paths']):
            p.update(name='route-'+str(i),interface='vpn-road-'+str(i),address=f'10.240.{i}.2/32',
                     table=301+i,priority=13001+i,mark_priority=14001+i,mark=3001+i,mtu=1300,mss=1260)
            if p['kind']=='wireguard':p['listen_port']=53001+i
            else:p.update(if_id=301+i,connection='road-'+str(i))
        c,d=guard.validate(self.c,self.d);config.validate_peers(c,self.meta)
        rules=guard.expected_policies(c,d)
        self.assertEqual(rules[0]['table'],'301');self.assertEqual(rules[0]['priority'],13001)
        self.assertEqual(config.status_max_age(c),35)
        specs=guard.firewall_specs(c,d)
        self.assertTrue(all('1260' in args for table,chain,args,_ in specs if 'TCPMSS' in args))
        text=render_ipsec(c,self.meta,{'a':'a'*64,'b':'b'*64})
        self.assertIn('local_ts = 10.240.2.2/32',text);self.assertIn('remote_ts = 10.70.0.0/24',text)
        self.assertIn('if_id_out = 303',text);self.assertNotIn('10.251.',text)

    def test_legacy_normalizes_without_changing_resources(self):
        legacy={k:v for k,v in self.c.items() if k not in ('schema_version','ipsec_mode','paths')}
        legacy['paths']=[{'name':p['name'],'interface':p['interface'],'source':str(__import__('ipaddress').ip_interface(p['address']).ip)} for p in self.c['paths']]
        c=config.normalize(legacy)
        self.assertEqual(c['ipsec_mode'],'file');self.assertEqual(c['paths'][0]['listen_port'],52102)
        self.assertEqual(c['paths'][0]['mark'],0x5c02)

    def test_duplicate_resources_rejected(self):
        for field in ('table','priority','mark_priority','mark','interface','address','listen_port'):
            c=copy.deepcopy(self.c);c['paths'][1][field]=c['paths'][0][field]
            with self.subTest(field=field),self.assertRaises(ValueError):config.normalize(c)

    def test_cross_priority_collision_rejected(self):
        self.c['paths'][0]['priority']=self.c['paths'][1]['mark_priority']
        with self.assertRaises(ValueError):config.normalize(self.c)

    def test_mtu_mss_and_boolean_validation(self):
        for field,value in [('mtu',True),('mss',1400),('listen_port',70000),('table',254)]:
            c=copy.deepcopy(self.c);c['paths'][0][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):config.normalize(c)

    def test_unsafe_identity_and_proposals_rejected(self):
        c=config.normalize(self.c)
        for field,value in [('local_id','evil\n}'),('esp_proposals','aes256\nsecret=x')]:
            m=copy.deepcopy(self.meta);m['b'][field]=value
            with self.assertRaises(ValueError):config.validate_peers(c,m)

    def test_ipsec_secret_escaped_in_generated_file(self):
        c=config.normalize(self.c);secret='a'*32+'"\\'
        self.assertIn(json.dumps(secret),render_ipsec(c,self.meta,{'a':secret,'b':secret}))

    def test_checker_file_validation_performs_no_network_commands(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(guard,'P',Path(tmp)),patch.object(guard,'run') as run,patch.object(guard,'check') as check,patch.object(doctor.stat,'S_IMODE',return_value=0o600):
            root=Path(tmp)
            for name,obj in [('controller',self.c),('deployment',self.d),('peers',self.meta)]:
                if name=='peers':
                    for p in obj.values():p['public_key']=base64.b64encode(bytes(range(32))).decode()
                (root/(name+'.json')).write_text(json.dumps(obj))
            for peer in ('a','b'):
                for prefix,text in [('wg-client-',base64.b64encode(bytes(range(32))).decode()),('ipsec-','x'*64)]:
                    p=root/(prefix+peer+'.key');p.write_text(text);p.chmod(0o600)
            findings=doctor.inspect(root,network=False)
            self.assertFalse(any(f['level']=='ERROR' for f in findings))
            run.assert_not_called();check.assert_not_called()

    def test_checker_never_echoes_invalid_secret_content(self):
        with patch.object(guard,'validate_files',side_effect=ValueError('PRIVATE_CONTENT')):
            self.assertNotIn('PRIVATE_CONTENT',json.dumps(doctor.inspect('/unused',network=False)))

    def test_status_fails_on_stale_and_future_heartbeat(self):
        for timestamp in (0,200):
            text,code=status.summarize({'monotonic':timestamp},{},100)
            self.assertEqual(code,2);self.assertIn('stale',text)

    def test_kuma_uses_custom_names_threshold_and_target_count(self):
        spec=importlib.util.spec_from_file_location('kuma',ROOT/'monitoring/kuma_push.py');kuma=importlib.util.module_from_spec(spec);spec.loader.exec_module(kuma)
        v={'monotonic':95,'paths':[{'name':'custom','kind':'wireguard'}],
           'settings':{'failure_rounds':12},'healthy':{'custom':False},'failure_rounds':[8],
           'active':'custom','probes':{'custom':{'10.60.0.10':False}}}
        w={'monotonic':95,'controller':True,'integrity':True,'ike':True}
        result=kuma.classify(v,w,100)['custom'];self.assertEqual(result[0],'up')
        self.assertIn('8/12',result[1]);self.assertIn('0/1',result[1])
        v['failure_rounds']=[12];self.assertEqual(kuma.classify(v,w,100)['custom'][0],'down')

if __name__=='__main__':unittest.main()
