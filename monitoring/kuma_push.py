#!/usr/bin/python3
"""Read-only VPN health reporter. Never changes VPN routes, rules or processes."""
import argparse,concurrent.futures,json,pathlib,re,time,urllib.parse,urllib.request
NAMES=('wg-main','wg-secondary','ipsec-main','ipsec-secondary')
LABELS=('WG-main','WG-secondary','IPsec-main','IPsec-secondary')
def classify(v,w,now):
 result={}
 for i,name in enumerate(NAMES):
  try:
   if not 0<=now-float(v['monotonic'])<=20:raise ValueError('controller status stale')
   if not 0<=now-float(w['monotonic'])<=20:raise ValueError('watchdog status stale')
   if not w['controller']:raise ValueError('controller unavailable')
   if not w['integrity']:raise ValueError('VPN integrity check failed')
   if name.startswith('ipsec-') and not w['ike']:raise ValueError('IPsec daemon unavailable')
   healthy=v['healthy'][name];bad=v['failure_rounds'][i]
   if type(healthy) is not bool or type(bad) is not int or bad<0:raise ValueError('invalid health fields')
   probes=v['probes'][name];count=sum(p is True for p in probes.values());active=v['active']
   if active not in NAMES and active is not None:raise ValueError('invalid active path')
   if not healthy and bad>=8:
    result[name]=('down',f'{LABELS[i]} unavailable | {bad} failed rounds | targets {count}/3 | selected {active or "none"}')
   else:
    role='ACTIVE' if active==name else 'STANDBY';detail='available' if healthy else f'transient probe loss ({bad}/8 failed rounds)'
    result[name]=('up',f'{LABELS[i]} {role} | {detail} | targets {count}/3 | selected {active or "none"}')
  except (KeyError,TypeError,ValueError,IndexError) as e:result[name]=('down',f'{LABELS[i]} monitoring invalid: {str(e)[:100]}')
 return result
def push(base,token,status,msg):
 parsed=urllib.parse.urlsplit(base)
 if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('','/'):raise ValueError('Invalid monitoring destination')
 if not re.fullmatch('[A-Za-z0-9_-]{16,128}',token):raise ValueError('Invalid push token')
 base=base.rstrip('/')
 url=base+'/api/push/'+token+'?'+urllib.parse.urlencode({'status':status,'msg':msg})
 # Disable environment proxies: this reporting destination is internal over the VPN.
 opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
 with opener.open(url,timeout=4) as response:
  body=json.load(response)
  if body.get('ok') is not True:raise RuntimeError('Kuma did not accept heartbeat')
def main():
 p=argparse.ArgumentParser();p.add_argument('--config',default='/etc/vpn-kuma.json');p.add_argument('--dry-run',action='store_true');a=p.parse_args()
 try:
  v=json.loads(pathlib.Path('/run/vpn-router/status.json').read_text());w=json.loads(pathlib.Path('/run/vpn-router/watchdog.json').read_text())
 except (OSError,ValueError):v={};w={}
 results=classify(v,w,time.monotonic())
 if a.dry_run:print(json.dumps(results));return
 config=json.loads(pathlib.Path(a.config).read_text());assert set(config['tokens'])==set(NAMES)
 failed=False
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
  jobs={n:pool.submit(push,config['base_url'],config['tokens'][n],*results[n]) for n in NAMES}
  for n,job in jobs.items():
   try:job.result();print(f'{n}: delivered {results[n][0]} | {results[n][1]}',flush=True)
   except Exception as e:failed=True;print(f'{n}: heartbeat delivery failed ({type(e).__name__}); Kuma will expire the heartbeat',flush=True)
 if failed:raise SystemExit(1)
if __name__=='__main__':main()
