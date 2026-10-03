"""Single-owner supervision with bounded liveness checks and restart backoff."""
import pathlib,json,subprocess as s,os,time,signal,fcntl,re
from eventlog import write_event
import guard
from configuration import status_max_age
os.umask(0o077)
R=pathlib.Path('/run/vpn-router');R.mkdir(exist_ok=True)
owner=open(R/'supervisor.lock','w')
try:fcntl.flock(owner,fcntl.LOCK_EX|fcntl.LOCK_NB)
except BlockingIOError:raise SystemExit('Another supervisor owns this runtime; no network changes made')
children=[];stop=False;failure=None

def stopping(*_):
 global stop
 stop=True
signal.signal(signal.SIGTERM,stopping);signal.signal(signal.SIGINT,stopping)
def log(event,**kw):write_event(event,**kw)
def execute(args,timeout=20):return s.run(args,check=True,capture_output=True,text=True,timeout=timeout).stdout

def live_ike():
 try:return s.run(['swanctl','--stats','--uri','unix:///run/vpn-router/charon.vici'],stdout=s.DEVNULL,stderr=s.DEVNULL,timeout=2).returncode==0
 except s.TimeoutExpired:return False

def write_watchdog(controller,ike,integrity,detail=''):
 d={'time':time.time(),'monotonic':time.monotonic(),'controller':controller,'ike':ike,'integrity':integrity,'detail':detail}
 p=R/'watchdog.tmp';p.write_text(json.dumps(d));p.replace(R/'watchdog.json')
try:
 execute(['python3','/app/doctor.py'])
 cfg,_=guard.validate_files();max_age=status_max_age(cfg)
 baseline=execute(['ip','route','show','default'])
 execute(['python3','/app/setup.py'])
 orphan_cleanup=json.loads(execute(['python3','/app/cleanup_ipsec.py']))
 pending_recovery={p['name']:p['connection'] for p in cfg['paths'] if p['kind']=='ipsec'} if orphan_cleanup['owned_orphan_objects_removed'] else {}
 log('orphan-cleanup',removed=orphan_cleanup['owned_orphan_objects_removed'])
 execute(['python3','/app/guard.py'],30)
 if execute(['ip','route','show','default'])!=baseline:raise RuntimeError('Public default changed during setup')
 ike=s.Popen(['/usr/lib/ipsec/charon']);children.append(ike)
 started=time.monotonic()
 while not live_ike():
  if ike.poll() is not None or time.monotonic()-started>15:raise RuntimeError('IPsec control daemon unavailable at startup')
  time.sleep(.2)
 execute(['swanctl','--load-all','--noprompt','--file',('/run/vpn-router/swan-client.conf' if cfg['ipsec_mode']=='generated' else '/etc/vpn/swan-client.conf'),'--uri','unix:///run/vpn-router/charon.vici'])
 children.append(s.Popen(['python3','-u','/app/controller.py']))
 start=time.monotonic();next_check=0;next_integrity=0;ike_bad=0;integrity=True;last_detail=''
 log('supervisor-start',public_default_preserved=True)
 while not stop:
  if any(p.poll() is not None for p in children):raise RuntimeError('Supervised process exited')
  now=time.monotonic()
  if now>=next_check:
   try:
    state=json.loads((R/'status.json').read_text());heartbeat=float(state['monotonic']);read_now=time.monotonic();controller=start<=heartbeat<=read_now and read_now-heartbeat<max_age
   except (OSError,ValueError,KeyError,TypeError):controller=False
   ike_ok=live_ike();ike_bad=0 if ike_ok else ike_bad+1
   if now-start>max(20,max_age) and not controller:raise RuntimeError('Controller heartbeat stalled')
   if ike_bad>=3:raise RuntimeError('IPsec control daemon unresponsive on three checks')
   if now>=next_integrity:
    try:
     result=json.loads(execute(['python3','/app/guard.py'],20));integrity=True;detail=''
     if result['repairs']:log('integrity-repaired',repairs=result['repairs'])
    except s.CalledProcessError as exc:
     if exc.returncode==3:raise RuntimeError('Owned VPN interface missing; bounded restart will recreate it')
     integrity=False;detail='Network integrity conflict or command failure; inspect reserved routes/rules'
    except s.TimeoutExpired:raise RuntimeError('Network integrity checker stalled')
    if detail!=last_detail:
     log('integrity-status',healthy=integrity,detail=detail);last_detail=detail
    next_integrity=time.monotonic()+10
   # A forced daemon kill can leave the peer's old policy binding behind.
   # Only after owned orphan cleanup, allow one clean IKE replacement per affected path.
   if pending_recovery and controller and ike_ok and now-start>20:
    sas=execute(['swanctl','--list-sas','--uri','unix:///run/vpn-router/charon.vici'],5)
    for path,conn in list(pending_recovery.items()):
     if state.get('healthy',{}).get(path):del pending_recovery[path]
     elif re.search(r'^'+re.escape(conn)+r':.*ESTABLISHED',sas,re.M):
      try:
       execute(['swanctl','--terminate','--ike',conn,'--timeout','3','--uri','unix:///run/vpn-router/charon.vici'],5)
       log('orphan-peer-recovery',path=path,action='one clean IKE renegotiation')
      except (s.CalledProcessError,s.TimeoutExpired):log('orphan-peer-recovery',path=path,action='bounded termination did not complete')
      del pending_recovery[path]
   write_watchdog(controller,ike_ok,integrity,last_detail)
   if now-start>300:(R/'restart-backoff.json').write_text('{"failures":0}')
   next_check=time.monotonic()+5
  time.sleep(.2)
except Exception as e:
 failure=type(e).__name__+': '+str(e)
 if isinstance(e,s.CalledProcessError):failure='Startup or local control command failed; no command output logged'
 log('supervisor-fault',detail=failure);write_watchdog(False,False,False,failure)
finally:
 for p in reversed(children):
  if p.poll() is None:p.terminate()
 for p in children:
  try:p.wait(timeout=2)
  except s.TimeoutExpired:p.kill();p.wait(timeout=2)
 log('supervisor-stop',routes='retained')
if failure:
 try:count=int(json.loads((R/'restart-backoff.json').read_text()).get('failures',0))+1
 except Exception:count=1
 (R/'restart-backoff.json').write_text(json.dumps({'failures':min(count,6)}))
 delay=min(60,2**min(count,6));log('restart-backoff',seconds=delay)
 deadline=time.monotonic()+delay
 while not stop and time.monotonic()<deadline:time.sleep(.2)
 raise SystemExit(1)
