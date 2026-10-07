#!/usr/bin/python3
"""Read-only VPN health reporter. Never changes VPN routes, rules or processes."""
import argparse,concurrent.futures,json,os,pathlib,re,stat,time,urllib.parse,urllib.request
NAMES=('wg-main','wg-secondary','ipsec-main','ipsec-secondary')
LABELS=('WG-main','WG-secondary','IPsec-main','IPsec-secondary')
def classify(v,w,now):
 result={}
 if not isinstance(v,dict) or not isinstance(w,dict):return {n:('down','Monitoring invalid or stale') for n in NAMES}
 paths=v.get('paths') or [{'name':n,'kind':'wireguard' if n.startswith('wg-') else 'ipsec'} for n in NAMES]
 if (not isinstance(paths,list) or not 1<=len(paths)<=4 or any(not isinstance(p,dict) or
     not re.fullmatch('[a-z][a-z0-9_-]{0,39}',str(p.get('name',''))) or p.get('kind') not in ('wireguard','ipsec') for p in paths)):
  return {n:('down','Monitoring invalid or stale') for n in NAMES}
 if not isinstance(v.get('settings',{}),dict):return {p['name']:('down','Monitoring invalid or stale') for p in paths}
 names=[p['name'] for p in paths];threshold=v.get('settings',{}).get('failure_rounds',8)
 for i,p in enumerate(paths):
  name=p['name'];label=name
  try:
   if not 0<=now-float(v['monotonic'])<=v.get('status_max_age',20):raise ValueError('controller status stale')
   if not 0<=now-float(w['monotonic'])<=20:raise ValueError('watchdog status stale')
   if w['controller'] is not True:raise ValueError('controller unavailable')
   if w['integrity'] is not True:raise ValueError('VPN integrity check failed')
   if p['kind']=='ipsec' and w['ike'] is not True:raise ValueError('IPsec daemon unavailable')
   if type(threshold) is not int or not 1<=threshold<=1000:raise ValueError('invalid failure threshold')
   healthy=v['healthy'][name];bad=v['failure_rounds'][i]
   if type(healthy) is not bool or type(bad) is not int or bad<0:raise ValueError('invalid health fields')
   probes=v['probes'][name];count=sum(p is True for p in probes.values());active=v['active']
   if active not in names and active is not None:raise ValueError('invalid active path')
   if not healthy and bad>=threshold:
    result[name]=('down',f'{label} unavailable | {bad} failed rounds | targets {count}/{len(probes)} | selected {active or "none"}')
   else:
    role='ACTIVE' if active==name else 'STANDBY';detail='available' if healthy else f'transient probe loss ({bad}/{threshold} failed rounds)'
    result[name]=('up',f'{label} {role} | {detail} | targets {count}/{len(probes)} | selected {active or "none"}')
  except (KeyError,TypeError,ValueError,IndexError,AttributeError):result[name]=('down',f'{label} monitoring invalid or stale')
 return result

def classify_projection(value,now):
 """Consume only the mirror's bounded projection, never an IPsec runtime mount."""
 if not isinstance(value,dict):raise ValueError('Invalid telemetry')
 paths=value.get('paths')
 if (not isinstance(paths,list) or not 1<=len(paths)<=4 or
     any(not isinstance(p,dict) or not re.fullmatch('[a-z][a-z0-9_-]{0,39}',str(p.get('name',''))) or
         p.get('kind') not in ('wireguard','ipsec') for p in paths)):
  raise ValueError('Invalid projected paths')
 if len({p['name'] for p in paths})!=len(paths):raise ValueError('Duplicate paths')
 status={k:value.get(k) for k in ('monotonic','status_max_age','settings','active')}
 status.update(paths=[{k:p[k] for k in ('name','kind')} for p in paths],
  healthy={p['name']:p.get('healthy') for p in paths},
  probes={p['name']:p.get('probes') for p in paths},
  failure_rounds=[p.get('failed_rounds') for p in paths])
 watchdog=value.get('watchdog')
 if not isinstance(status['settings'],dict) or not isinstance(watchdog,dict):raise ValueError('Invalid health')
 return classify(status,watchdog,now)

def read_bounded(path,private=False):
 path=pathlib.Path(path);attributes=path.lstat()
 if (not stat.S_ISREG(attributes.st_mode) or attributes.st_nlink!=1 or
     attributes.st_size>(16384 if private else 262144)):
  raise ValueError('Invalid reporting file')
 if private and os.name=='posix' and (attributes.st_mode&0o077 or attributes.st_uid not in (0,os.geteuid())):
  raise ValueError('Reporting configuration requires private ownership/mode0600')
 return json.loads(path.read_text())

class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,req,fp,code,msg,headers,newurl):
  return None  # A push token must never follow a redirect to another destination.
def push(base,token,status,msg):
 parsed=urllib.parse.urlsplit(base)
 if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('','/'):raise ValueError('Invalid monitoring destination')
 if not re.fullmatch('[A-Za-z0-9_-]{16,128}',token):raise ValueError('Invalid push token')
 base=base.rstrip('/')
 url=base+'/api/push/'+token+'?'+urllib.parse.urlencode({'status':status,'msg':msg})
 # Disable environment proxies: this reporting destination is internal over the VPN.
 opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
 with opener.open(url,timeout=4) as response:
  data=response.read(4097)
  if len(data)>4096:raise ValueError('Oversized reporting response')
  body=json.loads(data)
  if body.get('ok') is not True:raise RuntimeError('Kuma did not accept heartbeat')
def deliver(config,results):
 if not isinstance(config,dict) or set(config)!={'base_url','tokens'} or not isinstance(config['tokens'],dict):
  raise ValueError('Invalid private reporting configuration')
 if set(config['tokens'])!=set(results):raise ValueError('Monitoring token mapping must match runtime path names')
 failed=False
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
  jobs={n:pool.submit(push,config['base_url'],config['tokens'][n],*results[n]) for n in results}
  for n,job in jobs.items():
   try:job.result();print(f'{n}: delivered {results[n][0]} | {results[n][1]}',flush=True)
   except Exception as e:failed=True;print(f'{n}: heartbeat delivery failed ({type(e).__name__}); Kuma will expire the heartbeat',flush=True)
 return not failed

def once(a):
 if a.telemetry:
  results=classify_projection(read_bounded(a.telemetry),time.monotonic())
 else:
  try:v=read_bounded('/run/vpn-router/status.json');w=read_bounded('/run/vpn-router/watchdog.json')
  except (OSError,ValueError):v={};w={}
  results=classify(v,w,time.monotonic())
 if a.dry_run:print(json.dumps(results));return True
 return deliver(read_bounded(a.config,private=True),results)

def main():
 p=argparse.ArgumentParser();p.add_argument('--config',default='/etc/vpn-kuma.json');p.add_argument('--dry-run',action='store_true')
 p.add_argument('--telemetry',help='Sanitized mirror telemetry.json; avoids mounting raw VPN runtime')
 p.add_argument('--interval',type=int,default=0,help='0 for one run; 15–3600 seconds for read-only reporting loop')
 a=p.parse_args()
 if a.interval!=0 and not 15<=a.interval<=3600:p.error('Use interval0 or 15–3600 seconds')
 while True:
  try:success=once(a)
  except (OSError,ValueError,KeyError,TypeError,IndexError):
   success=False;print('Reporting unavailable; check private configuration/telemetry. VPN selection is independent.',flush=True)
  if not a.interval:raise SystemExit(0 if success else 1)
  time.sleep(a.interval)
if __name__=='__main__':main()
