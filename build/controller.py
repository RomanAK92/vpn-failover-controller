#!/usr/bin/python3
"""Small auditable VPN route selector. Scoped configuration, no default-route writes."""
import concurrent.futures as cf,fcntl,ipaddress,json,os,pathlib,re,signal,subprocess as sp,time
import guard
from eventlog import write_event
from selection import select_path
from configuration import status_max_age
CONFIG=pathlib.Path('/etc/vpn/controller.json')
STATE=pathlib.Path('/run/vpn-router');STATE.mkdir(exist_ok=True)
lock=open(STATE/'controller.lock','w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
cfg,deployment=guard.load();net=ipaddress.ip_network(cfg['subnet'],strict=True)
paths=cfg['paths'];names=[p['name'] for p in paths]
def cmd(args,timeout=4):return sp.run(args,text=True,stdout=sp.PIPE,stderr=sp.PIPE,timeout=timeout)
def log(**data):write_event(**data)
def route(active):
 guard.preflight(cfg,deployment)
 if active is None:
  r=cmd(['ip','route','del',str(net),'metric','50','proto','186'])
  if r.returncode and 'No such process' not in r.stderr:raise RuntimeError(r.stderr)
 else:
  p=paths[active];r=cmd(['ip','route','replace',str(net),'dev',p['interface'],'src',p['source'],'metric','50','proto','186'])
  if r.returncode:raise RuntimeError(r.stderr)
def probe(p,t):
 try:
  # Source-specific tables keep standby tests independent of production selection.
  r=cmd(['ip','-j','route','get',t,'from',p['source']])
  if r.returncode or json.loads(r.stdout)[0].get('dev')!=p['interface']:return False
  return cmd(['ping','-n','-I',p['source'],'-c','1','-W','1',t],3).returncode==0
 except Exception:return False
previous_health=None
last_switch=None
try:last_switch=json.loads((STATE/'status.json').read_text()).get('last_switch')
except (OSError,ValueError):pass
active=None;bad=[0]*len(paths);good=[0]*len(paths)
# Preserve selection across process restart, allowing transient failures their full threshold.
try:
 entries=json.loads(cmd(['ip','-j','route','show',str(net)]).stdout)
 for i,p in enumerate(paths):
  if any(e.get('dev')==p['interface'] and e.get('metric')==50 for e in entries):active=i
except Exception:pass
if cmd(['ip','route','replace','unreachable',str(net),'metric','32760','proto','186']).returncode:raise RuntimeError('Cannot install internal unreachable fallback')
stop=False
def stopping(*_):
 global stop
 stop=True
signal.signal(signal.SIGTERM,stopping);signal.signal(signal.SIGINT,stopping)
log(event='start',active=None if active is None else names[active])
with cf.ThreadPoolExecutor(max_workers=12) as pool:
 while not stop:
  tick=time.monotonic()
  jobs={(i,t):pool.submit(probe,p,t) for i,p in enumerate(paths) for t in cfg['targets']}
  results={names[i]:{t:jobs[i,t].result() for t in cfg['targets']} for i in range(len(paths))}
  health=[sum(results[n].values())>=cfg['quorum'] for n in names]
  if health!=previous_health:
   log(event='health-change',health=dict(zip(names,health)));previous_health=health[:]
  for i,h in enumerate(health):
   bad[i]=0 if h else bad[i]+1;good[i]=good[i]+1 if h else 0
  selected=select_path(active,health,bad,good,cfg['failure_rounds'],cfg['recovery_rounds'])
  try:
   if selected!=active:
    reason='all paths unavailable' if selected is None else ('initial path selection' if active is None else ('current path failure threshold reached' if bad[active]>=cfg['failure_rounds'] else 'preferred path recovered for stability threshold'))
    route(selected)
    last_switch={'time':time.time(),'old':None if active is None else names[active],'new':None if selected is None else names[selected],'reason':reason}
    log(event='switch',old=last_switch['old'],new=last_switch['new'],health=health);active=selected
   # Reconcile only the explicitly owned route if another process removed it.
   entries=json.loads(cmd(['ip','-j','route','show',str(net)]).stdout)
   if active is not None and not any(e.get('dev')==paths[active]['interface'] and e.get('metric')==50 for e in entries):route(active)
   state={'time':time.time(),'monotonic':time.monotonic(),'active':None if active is None else names[active],'healthy':dict(zip(names,health)),'probes':results,'failure_rounds':bad,'recovery_rounds':good,'last_switch':last_switch,'status_max_age':status_max_age(cfg),'settings':{k:cfg[k] for k in ('interval','quorum','failure_rounds','recovery_rounds')},'paths':[{k:p[k] for k in ('name','kind','interface','source','mtu','mss')} for p in paths]}
   tmp=STATE/'status.tmp';tmp.write_text(json.dumps(state));os.replace(tmp,STATE/'status.json')
  except Exception as e:log(event='error',detail=str(e))
  time.sleep(max(0.1,cfg['interval']-(time.monotonic()-tick)))
log(event='stop',routes='retained')
