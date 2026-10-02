"""Validated configuration and exact, scoped network reconciliation."""
import base64,ipaddress,json,pathlib,subprocess as s,shlex
P=pathlib.Path('/etc/vpn')
PATHS=[('vpn-wg-a','10.250.101.2',201),('vpn-wg-b','10.250.102.2',202),('vpn-ipsec-b','10.251.102.2',203),('vpn-ipsec-a','10.251.101.2',204)]
class Conflict(RuntimeError):pass
class LocalFault(RuntimeError):pass
def run(a):return s.run(a,check=True,capture_output=True,text=True,timeout=8).stdout.strip()
def check(a):return s.run(a,capture_output=True,text=True,timeout=8).returncode==0
def validate(c,d):
 net=ipaddress.ip_network(c.get('subnet',''),strict=True)
 if net.version!=4 or not net.is_private or net.prefixlen<16:raise ValueError('Managed subnet must be a private IPv4 prefix /16 or smaller')
 if any(net.overlaps(ipaddress.ip_network(src+'/30',strict=False)) for _,src,_ in PATHS):raise ValueError('Managed subnet overlaps tunnel addresses')
 expected=[('wg-main','vpn-wg-b','10.250.102.2'),('wg-secondary','vpn-wg-a','10.250.101.2'),('ipsec-main','vpn-ipsec-b','10.251.102.2'),('ipsec-secondary','vpn-ipsec-a','10.251.101.2')]
 if [(p.get('name'),p.get('interface'),p.get('source')) for p in c.get('paths',[])]!=expected:raise ValueError('Unexpected ordered path definitions')
 targets=c.get('targets');net=ipaddress.ip_network(c['subnet'])
 if not isinstance(targets,list) or not 1<=len(targets)<=3 or len(set(targets))!=len(targets):raise ValueError('Invalid targets')
 if any(ipaddress.ip_address(t) not in net for t in targets):raise ValueError('Target outside internal prefix')
 for key,low,high in [('quorum',1,len(targets)),('failure_rounds',1,120),('recovery_rounds',1,600),('interval',1,60)]:
  if type(c.get(key)) is not int or not low<=c[key]<=high:raise ValueError('Invalid '+key)
 if set(d)!={'app_subnet','publication'}:raise ValueError('Unexpected deployment fields')
 app=ipaddress.ip_network(d['app_subnet'],strict=True)
 if app.version!=4 or not app.is_private or app.prefixlen<16 or app.overlaps(net):raise ValueError('Invalid application subnet')
 pub=d['publication']
 if pub is not None:
  if set(pub)!={'address','port','tunnel_port'} or ipaddress.ip_address(pub['address']) not in app:raise ValueError('Invalid publication address')
  for key in ('port','tunnel_port'):
   if type(pub[key]) is not int or not 1<=pub[key]<=65535:raise ValueError('Invalid publication port')
 return c,d

def load():return validate(json.loads((P/'controller.json').read_text()),json.loads((P/'deployment.json').read_text()))
def validate_files():
 c,d=load();meta=json.loads((P/'peers.json').read_text())
 for suffix in ('a','b'):
  key=(P/('wg-client-'+suffix+'.key')).read_text().strip()
  if len(base64.b64decode(key,validate=True))!=32 or len(base64.b64decode(meta[suffix]['public_key'],validate=True))!=32:raise ValueError('Invalid WireGuard key length')
  ipaddress.IPv4Address(meta[suffix]['endpoint'])
 if not (P/'swan-client.conf').is_file():raise ValueError('Missing IPsec configuration')
 return c,d

def expected_policies(d):
 rules=[]
 for iface,src,table in PATHS:
  rules.append({'priority':12000+table,'src':src,'table':str(table)})
  if d['publication'] is not None:rules.append({'priority':12100+table-200,'src':'all','fwmark':hex(0x5c00+table-200),'table':str(table)})
 return rules

def normalize_rule(r):
 out={k:v for k,v in r.items() if k not in ('protocol','flags')}
 if r.get('flags'):out['flags']=r['flags']
 out['table']=str(out.get('table',''))
 if isinstance(out.get('src'),str):out['src']=out['src'].removesuffix('/32')
 return out

def validate_policies(actual,expected):
 for e in expected:
  rows=[r for r in actual if r.get('priority')==e['priority']]
  if len(rows)>1 or (rows and normalize_rule(rows[0])!=e):raise Conflict('Routing-rule collision at priority '+str(e['priority']))

def preflight(c,d):
 validate_policies(json.loads(run(['ip','-j','rule','show'])),expected_policies(d))
 for iface,src,table in PATHS:
  rr=s.run(['ip','-j','route','show','table',str(table)],capture_output=True,text=True,timeout=8)
  if rr.returncode and 'does not exist' not in rr.stderr:raise Conflict('Cannot inspect table '+str(table))
  routes=[] if rr.returncode else json.loads(rr.stdout or '[]')
  for r in routes:
   normal=r.get('dst')==c['subnet'] and r.get('dev')==iface and r.get('prefsrc')==src and r.get('scope')=='link' and not any(k in r for k in ('gateway','metric','multipath'))
   fallback=r.get('dst')=='default' and r.get('type')=='unreachable' and r.get('metric')==32760
   if not(normal or fallback):raise Conflict('Unexpected route in reserved table '+str(table))
 links=json.loads(run(['ip','-d','-j','link','show']))
 for iface,src,table in PATHS:
  for link in [l for l in links if l['ifname']==iface]:
   kind=link.get('linkinfo',{}).get('info_kind');expected='wireguard' if '-wg-' in iface else 'xfrm'
   if kind!=expected:raise Conflict('Wrong interface type for '+iface)
   if expected=='xfrm':
    value=link['linkinfo'].get('info_data',{}).get('if_id');want=101 if iface.endswith('-a') else 102
    if int(str(value),0)!=want:raise Conflict('Wrong XFRM identity for '+iface)
 for r in json.loads(run(['ip','-j','route','show',c['subnet']])):
  if r.get('dst')!=c['subnet']:continue
  if r.get('protocol') not in ('bgp','186',186):raise Conflict('Internal prefix route not owned by VPN')
  if not ((r.get('metric')==50 and r.get('dev') in [p[0] for p in PATHS]) or (r.get('type')=='unreachable' and r.get('metric')==32760)):raise Conflict('Conflicting internal prefix route')

def firewall_specs(c,d):
 app=d['app_subnet'];lan=c['subnet'];pub=d['publication'];specs=[]
 def add(table,chain,args,first=False):specs.append((table,chain,args,first))
 for iface,src,table in PATHS:
  add('nat','POSTROUTING',['-s',app,'-d',lan,'-o',iface,'-j','SNAT','--to-source',src],True)
  add('filter','DOCKER-USER',['-i',iface,'-s',lan,'-d',app,'-j','ACCEPT'],True)
  cap=1380 if '-wg-' in iface else 1360
  for scope in (['-s',app,'-d',lan,'-o',iface],['-s',lan,'-d',app,'-i',iface]):
   add('mangle','FORWARD',scope+['-p','tcp','--tcp-flags','SYN,RST','SYN','-m','tcpmss','--mss',str(cap+1)+':65535','-m','comment','--comment','VPN-APP-MSS','-j','TCPMSS','--set-mss',str(cap)])
  if pub:
   ingress=['-i',iface,'-s',lan,'-d',src+'/32','-p','tcp','--dport',str(pub['tunnel_port'])]
   add('nat','PREROUTING',ingress+['-j','DNAT','--to-destination',pub['address']+':'+str(pub['port'])])
   add('mangle','PREROUTING',ingress+['-m','comment','--comment','VPN-INBOUND','-j','CONNMARK','--set-mark',str(0x5c00+table-200)],True)
 if pub:add('mangle','PREROUTING',['-s',pub['address']+'/32','-d',lan,'-p','tcp','--sport',str(pub['port']),'-m','comment','--comment','VPN-REPLY','-j','CONNMARK','--restore-mark'],True)
 return specs

def reconcile(c,d):
 # Check every reserved priority/table before any mutation. Never delete foreign rules.
 preflight(c,d);repairs=[]
 if not check(['iptables','-w','5','-S','DOCKER-USER']):raise Conflict('Docker firewall chain unavailable; wait for Docker')
 for iface,src,table in PATHS:
  if not check(['ip','link','show',iface]):raise LocalFault('Missing VPN interface '+iface)
  rr=s.run(['ip','-j','route','show','table',str(table)],capture_output=True,text=True,timeout=8)
  if rr.returncode and 'does not exist' not in rr.stderr:raise Conflict('Cannot inspect table '+str(table))
  routes=[] if rr.returncode else json.loads(rr.stdout or '[]')
  if not any(r.get('dst')==c['subnet'] for r in routes):run(['ip','route','add',c['subnet'],'dev',iface,'src',src,'table',str(table)]);repairs.append('route:'+str(table))
  if not any(r.get('type')=='unreachable' and r.get('dst')=='default' for r in routes):run(['ip','route','add','unreachable','default','table',str(table),'metric','32760']);repairs.append('fallback:'+str(table))
 actual=json.loads(run(['ip','-j','rule','show']))
 for e in expected_policies(d):
  if not any(r.get('priority')==e['priority'] for r in actual):
   args=['ip','rule','add','priority',str(e['priority'])]
   args+=['fwmark',e['fwmark']] if 'fwmark' in e else ['from',e['src']+'/32']
   run(args+['lookup',e['table']]);repairs.append('policy:'+str(e['priority']))
 routes=json.loads(run(['ip','-j','route','show',c['subnet']]))
 if not any(r.get('type')=='unreachable' and r.get('metric')==32760 for r in routes):run(['ip','route','add','unreachable',c['subnet'],'metric','32760','proto','186']);repairs.append('main-fallback')
 for table,chain,args,first in firewall_specs(c,d):
  base=['iptables','-w','5','-t',table]
  if not check(base+['-C',chain]+args):
   run(base+(['-I',chain,'1'] if first else ['-A',chain])+args);repairs.append(table+':'+chain)
 # Ensure owned SNAT is ahead of Docker general MASQUERADE without touching unrelated rules.
 lines=run(['iptables','-w','5','-t','nat','-S','POSTROUTING']).splitlines()
 masquerade=next((i for i,l in enumerate(lines) if '-j MASQUERADE' in l),len(lines))
 for i,line in enumerate(lines):
  if i>masquerade and '-j SNAT' in line and any(src in line and iface in line and d['app_subnet'] in line for iface,src,_ in PATHS):
   args=shlex.split(line)[2:];run(['iptables','-w','5','-t','nat','-D','POSTROUTING']+args);run(['iptables','-w','5','-t','nat','-I','POSTROUTING','1']+args);repairs.append('SNAT-order')
 return repairs

if __name__=='__main__':
 import sys
 c,d=validate_files()
 if '--preflight' in sys.argv:preflight(c,d);print('Preflight OK')
 else:
  try:print(json.dumps({'repairs':reconcile(c,d)}))
  except LocalFault as exc:
   print(str(exc),file=sys.stderr);raise SystemExit(3)
