"""Protocol-independent configuration and credential boundary tests."""
import base64
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'build'))
import configuration
import guard
import doctor
import setup
from selection import select_path

def layout(kinds):
    c=json.loads((ROOT/'config/examples/controller.json').read_text())
    c['paths']=[]
    for i,kind in enumerate(kinds):
        p=dict(name='path-'+str(i),kind=kind,peer='peer-'+str(i),interface='vpn-path-'+str(i),
               address=f'10.240.{i}.2/32',table=301+i,priority=13001+i,
               mark_priority=14001+i,mark=3001+i,mtu=1400,mss=1360)
        if kind=='wireguard':p.update(listen_port=53001+i,keepalive=25)
        else:p.update(if_id=301+i,connection='path-'+str(i))
        c['paths'].append(p)
    return c

class FlexibleTests(unittest.TestCase):
    def test_priority_selection_for_two_and_four_paths(self):
        for n in (2,4):
            for active in range(n):
                healthy=[False]*n;healthy[active]=True
                self.assertEqual(select_path(None,healthy,[0]*n,[0]*n,8,30),active)
                healthy[active]=False
                self.assertIsNone(select_path(active,healthy,[8]*n,[0]*n,8,30))
                if active:
                    healthy[0]=True
                    self.assertEqual(select_path(active,healthy,[0]*n,[29]*n,8,30),active)
                    self.assertEqual(select_path(active,healthy,[0]*n,[30]*n,8,30),0)

    def test_all_protocol_combinations_one_to_four(self):
        import itertools
        for count in range(1,5):
            for kinds in itertools.product(('wireguard','ipsec'),repeat=count):
                with self.subTest(kinds=kinds):
                    c=configuration.normalize(layout(kinds))
                    self.assertEqual(len(c['paths']),count)
                    d=json.loads((ROOT/'config/examples/deployment.json').read_text())
                    self.assertEqual(len(guard.expected_policies(c,d)),count)
                    d['publication']={'address':'172.28.240.10','port':8080,'tunnel_port':18081}
                    self.assertEqual(len(guard.expected_policies(c,d)),2*count)

    def test_empty_and_five_paths_rejected(self):
        for n in (0,5):
            with self.assertRaises(ValueError):configuration.normalize(layout(['wireguard']*n))

    def test_two_path_collisions_still_rejected(self):
        for field in ('table','priority','mark_priority','mark','interface','address','listen_port'):
            c=layout(['wireguard']*2);c['paths'][1][field]=c['paths'][0][field]
            with self.subTest(field=field),self.assertRaises(ValueError):configuration.normalize(c)

    def test_legacy_count_not_relaxed(self):
        c=layout(['wireguard']*2);c['schema_version']=1
        with self.assertRaises(ValueError):configuration.normalize(c)

    def test_only_configured_protocol_credentials_required(self):
        key=base64.b64encode(bytes(range(32))).decode()
        for kind in ('wireguard','ipsec'):
            for mode in ('file','generated'):
                with self.subTest(kind=kind,mode=mode),tempfile.TemporaryDirectory() as tmp,patch.object(guard,'P',Path(tmp)):
                    root=Path(tmp);c=layout([kind]*2);c['ipsec_mode']=mode
                    meta={p['peer']:{'endpoint':'203.0.113.'+str(10+i),'public_key':key,
                          'local_id':'client-'+str(i),'remote_id':'peer-'+str(i),
                          'ike_proposals':'aes256-sha256-modp2048','esp_proposals':'aes256-sha256'}
                          for i,p in enumerate(c['paths'])}
                    for m in meta.values():
                        if kind=='ipsec':del m['public_key']
                        else:
                            for field in ('local_id','remote_id','ike_proposals','esp_proposals'):del m[field]
                    for name,obj in [('controller',c),('deployment',json.loads((ROOT/'config/examples/deployment.json').read_text())),('peers',meta)]:
                        (root/(name+'.json')).write_text(json.dumps(obj))
                    for p in c['paths']:
                        if kind=='wireguard':(root/('wg-client-'+p['peer']+'.key')).write_text(key)
                        elif mode=='generated':(root/('ipsec-'+p['peer']+'.key')).write_text('x'*64)
                    if kind=='ipsec' and mode=='file':(root/'swan-client.conf').write_text('connections {}')
                    guard.validate_files()
                    original_read=Path.read_text
                    def read(path,*args,**kwargs):
                        value=path.as_posix()
                        if value in ('/proc/net/udp','/proc/net/udp6'):
                            return 'header\n 0: 00000000:01F4 00000000:0000\n 1: 00000000:1194 00000000:0000\n' if kind=='wireguard' else 'header\n'
                        if value=='/proc/sys/net/ipv4/ip_forward':return '1'
                        if value=='/proc/sys/net/ipv4/conf/all/rp_filter':return '0'
                        if value=='/proc/modules':return ''
                        return original_read(path,*args,**kwargs)
                    unused='swanctl' if kind=='wireguard' else 'wg'
                    with patch.object(Path,'read_text',read),patch.object(guard,'preflight'),patch.object(guard,'check',return_value=True),patch.object(doctor.stat,'S_IMODE',return_value=0o600),patch.object(doctor.shutil,'which',side_effect=lambda tool:None if tool==unused else '/bin/'+tool) as which:
                        findings=doctor.inspect(root)
                        self.assertFalse(any(f['level']=='ERROR' for f in findings),findings)
                        self.assertNotIn(unused,[call.args[0] for call in which.call_args_list])
                    if kind=='wireguard':
                        with patch.object(guard,'check',return_value=True),patch.object(guard,'run'):
                            runtime=root/'runtime';setup.configure(configuration.normalize(c),meta,root,runtime)
                            self.assertFalse((runtime/'swan-client.conf').exists())

if __name__=='__main__':unittest.main()
