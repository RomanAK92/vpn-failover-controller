"""Encrypted flexible-layout tests on disposable Docker networks only.

Run only on a dedicated Linux test host. No public ports or live routers.
Each tunnel has an independent Linux gateway; generated credentials are deleted.
"""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess as sp
import sys
import tempfile
import time
from integration_linux import run

def peer_mode():
    p=json.loads(Path('/test/peer.json').read_text());i=p['index'];kind=p['kind']
    for addr in ('10.60.0.1','10.60.0.10','10.60.0.60'):run('ip','addr','add',addr+'/32','dev','lo')
    if kind=='wireguard':
        run('ip','link','add','peer-vpn','type','wireguard')
        run('wg','setconf','peer-vpn','/test/wg.conf')
        run('ip','addr','add',f'10.250.{i}.1/30','dev','peer-vpn')
        run('ip','link','set','peer-vpn','mtu','1420','up')
    else:
        run('ip','link','add','peer-vpn','type','xfrm','if_id',str(301+i))
        run('ip','link','set','peer-vpn','mtu','1400','up')
        run('ip','route','add',f'10.251.{i}.2/32','dev','peer-vpn')
        Path('/run/vpn-router').mkdir(exist_ok=True)
        sp.Popen(['/usr/lib/ipsec/charon'],stdout=sp.DEVNULL,stderr=sp.DEVNULL)
        for _ in range(100):
            if Path('/run/vpn-router/charon.vici').exists():break
            time.sleep(.1)
        run('swanctl','--load-all','--noprompt','--file','/test/swan.conf','--uri','unix:///run/vpn-router/charon.vici')
    from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
    import socket
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body=(p['name']+'|'+self.client_address[0]+'|'+str(self.connection.getsockopt(socket.IPPROTO_TCP,socket.TCP_MAXSEG))).encode()
            self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        def log_message(self,*args):pass
    ThreadingHTTPServer(('0.0.0.0',18080),Handler).serve_forever()

def app_mode():
    run('ip','route','add','10.60.0.0/24','via','172.28.244.2')
    from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body=b'application-ok';self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        def log_message(self,*args):pass
    ThreadingHTTPServer(('0.0.0.0',8080),Handler).serve_forever()

def suite(root, managed_layouts=False):
    root=Path(root).resolve();sys.path.insert(0,str(root/'build'))
    from configuration import normalize
    prefix='vpn-flex-'+secrets.token_hex(4);image=prefix+':test'
    baseline=run('ip','route','show','default');results=[]
    ids=run('docker','network','ls','-q').splitlines()
    for row in json.loads(run('docker','network','inspect',*ids)) if ids else []:
        for cfg in row.get('IPAM',{}).get('Config') or []:
            if cfg.get('Subnet'):
                net=ipaddress.ip_network(cfg['Subnet'])
                if net.version==4 and any(net.overlaps(ipaddress.ip_network(s)) for s in ('172.28.244.0/24','172.28.245.0/24')):raise RuntimeError('Test subnet collision')
    def record(name,**detail):
        results.append({'test':name,'passed':True,**detail});print(json.dumps(results[-1]),flush=True)
    try:
        run('docker','build','-t',image,str(root/'build'),timeout=600)
        layouts=[('wireguard-1',['wireguard']),('wireguard-2',['wireguard']*2),
                 ('wireguard-3',['wireguard']*3),('wireguard-4',['wireguard']*4),
                 ('ipsec-1',['ipsec']),('ipsec-2',['ipsec']*2),
                 ('ipsec-3',['ipsec']*3),('ipsec-4',['ipsec']*4),
                 ('ipsec-first-3',['ipsec','wireguard','ipsec']),
                 ('interleaved-4',['wireguard','ipsec','wireguard','ipsec'])]
        for label,kinds in layouts:
            count=len(kinds);tag=prefix+'-'+label;wan=tag+'-wan';appnet=tag+'-app'
            containers=[];networks=[];layout_image=None;managed=None;temp=Path(tempfile.mkdtemp(prefix=tag+'-'));temp.chmod(0o700)
            vpn=tag+'-vpn';app=tag+'-app';peers=[]
            def dx(name,*cmd,timeout=30):return run('docker','exec',name,*cmd,timeout=timeout)
            def state():return json.loads(dx(vpn,'cat','/run/vpn-router/status.json'))
            def wait(want,all_healthy=False,since=0,timeout=120):
                end=time.monotonic()+timeout;last={}
                while time.monotonic()<end:
                    try:
                        last=state()
                        if last['monotonic']>=since and last['active']==want and (not all_healthy or all(last['healthy'].values())):return last
                    except (RuntimeError,KeyError,ValueError):pass
                    time.sleep(1)
                raise RuntimeError(label+' path timeout '+str(want)+' '+json.dumps(last))
            def application(index):
                response=dx(app,'python3','-c',"import urllib.request; print(urllib.request.urlopen('http://10.60.0.60:18080/',timeout=5).read().decode())")
                p=c['paths'][index];parts=response.split('|')
                if parts[:2]!=[p['name'],p['source']] or not 0<int(parts[2])<=p['mss']:raise RuntimeError('Application route/SNAT/MSS mismatch '+response)
            def block(index,enabled):
                args=['iptables','-w','5','-I' if enabled else '-D','INPUT']
                if enabled:args+=['1']
                dx(peers[index],*args,'-i','peer-vpn','-s','10.0.0.0/8','-d','10.60.0.0/24','-j','DROP')
            try:
                for name,subnet in [(wan,'172.28.245.0/24'),(appnet,'172.28.244.0/24')]:
                    run('docker','network','create','--internal','--subnet',subnet,name);networks.append(name)
                config=temp/'config';config.mkdir(mode=0o700);runtime=temp/'runtime';runtime.mkdir(mode=0o700)
                c=json.loads((root/'config/examples/controller.json').read_text());c['paths']=[]
                # Shorter test-only timing; production defaults remain unchanged.
                c.update(interval=1,failure_rounds=4,recovery_rounds=8,ipsec_mode='generated')
                meta={}
                for i in range(count):
                    kind=kinds[i]
                    name='path-'+str(i);peer='peer-'+str(i);endpoint='172.28.245.'+str(11+i)
                    p=dict(name=name,kind=kind,peer=peer,interface='vpn-path-'+str(i),address=f'10.{250 if kind=="wireguard" else 251}.{i}.2/{30 if kind=="wireguard" else 32}',table=301+i,priority=13001+i,mark_priority=14001+i,mark=3001+i,mtu=1420 if kind=='wireguard' else 1400,mss=1380 if kind=='wireguard' else 1360)
                    directory=temp/peer;directory.mkdir(mode=0o700)
                    (directory/'peer.json').write_text(json.dumps({'index':i,'kind':kind,'name':name}))
                    meta[peer]={'endpoint':endpoint}
                    if kind=='wireguard':
                        p.update(listen_port=53001+i,keepalive=25)
                        key=run('docker','run','--rm','--network','none','--entrypoint','wg',image,'genkey')
                        client=run('docker','run','--rm','--network','none','--entrypoint','wg',image,'genkey')
                        pub=run('docker','run','--rm','-i','--network','none','--entrypoint','wg',image,'pubkey',input=key+'\n')
                        client_pub=run('docker','run','--rm','-i','--network','none','--entrypoint','wg',image,'pubkey',input=client+'\n')
                        meta[peer].update(public_key=pub,port=51889)
                        (config/('wg-client-'+peer+'.key')).write_text(client)
                        (directory/'wg.conf').write_text(f'[Interface]\nPrivateKey = {key}\nListenPort = 51889\n[Peer]\nPublicKey = {client_pub}\nAllowedIPs = 10.250.{i}.2/32\n')
                    else:
                        p.update(if_id=301+i,connection=name)
                        secret=secrets.token_hex(32);local='client-'+str(i);remote='gateway-'+str(i)
                        meta[peer].update(local_id=local,remote_id=remote,ike_proposals='aes256-sha256-modp2048',esp_proposals='aes256-sha256')
                        (config/('ipsec-'+peer+'.key')).write_text(secret)
                        text=f'''connections {{
 {name} {{
  version = 2
  local_addrs = {endpoint}
  remote_addrs = 172.28.245.10
  proposals = aes256-sha256-modp2048
  local {{ auth = psk
   id = {remote}
  }}
  remote {{ auth = psk
   id = {local}
  }}
  children {{ internal {{
   local_ts = 10.60.0.0/24
   remote_ts = 10.251.{i}.2/32
   if_id_in = {301+i}
   if_id_out = {301+i}
   esp_proposals = aes256-sha256
  }} }}
 }}
}}
secrets {{ ike-test {{
 id-1 = {local}
 id-2 = {remote}
 secret = "{secret}"
}} }}
'''
                        (directory/'swan.conf').write_text(text)
                    c['paths'].append(p)
                    peer_name=tag+'-'+peer;peers.append(peer_name)
                c=normalize(c)
                for name,obj in [('controller',c),('peers',meta),('deployment',{'app_subnet':'172.28.244.0/24','publication':{'address':'172.28.244.10','port':8080,'tunnel_port':18081}})]:
                    (config/(name+'.json')).write_text(json.dumps(obj))
                for path in temp.rglob('*'):
                    if path.is_file():path.chmod(0o600)
                if managed_layouts:
                    import integration_managed
                    managed=integration_managed.prepare(root,temp,config,tag,run,containers,[],persistent=True)
                    layout_image=tag+'-managed:test'
                    run('docker','build','-t',layout_image,str(managed['destination']/'engine'),timeout=600)
                    runtime=managed['destination']/'data/runtime'
                    c=managed['config']
                    record(label+'-persistent-guided-manager-prepared',live_apply_enabled=False)
                mounts=['-v',str(root/'tests')+':/tests:ro']
                for i,peer_name in enumerate(peers):
                    run('docker','run','-d','--name',peer_name,'--network',wan,'--ip','172.28.245.'+str(11+i),'--no-healthcheck','--cap-add','NET_ADMIN','--sysctl','net.ipv4.conf.all.rp_filter=0','--entrypoint','python3',*mounts,'-v',str(temp/('peer-'+str(i)))+':/test:ro',image,'/tests/integration_flexible.py','--peer');containers.append(peer_name)
                run('docker','run','-d','--name',vpn,'--network',wan,'--ip','172.28.245.10','--cap-drop','ALL','--cap-add','NET_ADMIN','--cap-add','NET_RAW','--cap-add','NET_BIND_SERVICE','--security-opt','no-new-privileges:true','--read-only','--memory','256m','--pids-limit','128','--restart','unless-stopped','--sysctl','net.ipv4.ip_forward=1','--sysctl','net.ipv4.conf.all.rp_filter=0','--tmpfs','/run:rw,nosuid,size=16m','--tmpfs','/tmp:rw,noexec,nosuid,size=16m','--entrypoint','sh',*(['-v',managed['management_mount']+':/management:rw','-v',str(managed['control'])+':/control:rw'] if managed else ['-v',str(config)+':/etc/vpn:ro']),'-v',str(runtime)+':/run/vpn-router',layout_image or image,'-c','ip route replace default via 172.28.245.1 && iptables -N DOCKER-USER && iptables -A FORWARD -j DOCKER-USER && exec python3 -u '+('/app/management/manager.py --application-file /management/readiness.json' if managed else '/app/supervisor.py'));containers.append(vpn)
                run('docker','network','connect','--ip','172.28.244.2',appnet,vpn)
                run('docker','run','-d','--name',app,'--network',appnet,'--ip','172.28.244.10','--no-healthcheck','--cap-add','NET_ADMIN','--entrypoint','python3',*mounts,image,'/tests/integration_flexible.py','--app');containers.append(app)
                wait('path-0',True);application(0);record(label+'-startup-and-application')
                for i,p in enumerate(c['paths']):
                    code="import http.client; c=http.client.HTTPConnection(%r,18081,timeout=5,source_address=('10.60.0.60',0)); c.request('GET','/'); r=c.getresponse(); print(r.read().decode() if r.status==200 else 'ERROR')"%p['source']
                    if dx(peers[i],'python3','-c',code)!='application-ok':raise RuntimeError('Inbound publication failed')
                record(label+'-all-inbound-pinned-replies')
                if all(kind=='wireguard' for kind in kinds):
                    if (runtime/'swan-client.conf').exists() or (runtime/'charon.vici').exists():raise RuntimeError('WireGuard-only started IPsec')
                    links=json.loads(dx(vpn,'ip','-d','-j','link','show'))
                    if any(p.get('linkinfo',{}).get('info_kind')=='xfrm' for p in links):raise RuntimeError('Unexpected XFRM interface')
                    record(label+'-no-ipsec-daemon-or-interfaces')
                elif all(kind=='ipsec' for kind in kinds) and dx(vpn,'wg','show','interfaces'):raise RuntimeError('Unexpected WireGuard interface')
                for i in range(count-1):
                    block(i,True);wait('path-'+str(i+1));application(i+1)
                record(label+'-ordered-failover-snat-mss')
                block(count-1,True);wait(None)
                if 'unreachable' not in dx(vpn,'ip','route','show','10.60.0.0/24'):raise RuntimeError('Fail-closed route missing')
                record(label+'-all-down-fails-closed')
                block(count-1,False);wait('path-'+str(count-1));application(count-1)
                if count>1:block(0,False)
                wait('path-0');application(0)
                for i in range(1,count-1):block(i,False)
                wait('path-0',True);record(label+'-recovery-and-failback')
                for restart_round in range(3):
                    run('docker','restart',vpn,timeout=40)
                    # Shutdown may write a heartbeat after the restart request.
                    # Require a heartbeat newer than Docker completing the restart.
                    since=time.monotonic();wait('path-0',True,since=since,timeout=180)
                    end=time.monotonic()+30
                    while time.monotonic()<end:
                        if sp.run(['docker','exec',vpn,'python3','/app/health.py'],capture_output=True).returncode==0:break
                        time.sleep(1)
                    else:raise RuntimeError('Healthcheck unavailable')
                    end=time.monotonic()+30;retries=0
                    while True:
                        try:application(0);break
                        except RuntimeError:
                            retries+=1
                            print(json.dumps({'event':'post-restart-application-retry','layout':label,'restart':restart_round+1,'retry':retries}),flush=True)
                            if time.monotonic()>=end:raise
                            time.sleep(1)
                    record(label+'-restart-'+str(restart_round+1)+'-application',retries=retries)
                info=json.loads(run('docker','inspect',vpn))[0]
                if info['State']['OOMKilled'] or info['HostConfig']['Memory']!=256*1024*1024:raise RuntimeError('Memory boundary failed')
                defaults=json.loads(dx(vpn,'ip','-j','route','show','default'))
                if len(defaults)!=1 or defaults[0].get('gateway')!='172.28.245.1':raise RuntimeError('Container default gateway changed')
                addresses=json.loads(dx(vpn,'ip','-j','addr','show','dev',defaults[0]['dev']))
                if not any(a.get('local')=='172.28.245.10' for link in addresses for a in link['addr_info']):raise RuntimeError('Default gateway uses wrong network')
                if run('ip','route','show','default')!=baseline:raise RuntimeError('Host default changed')
                if managed:
                    response=json.loads(dx(vpn,'python3','-c',"import sys,socket,json;sys.path.insert(0,'/app/management');from broker import send,receive,MAX_REQUEST,MAX_RESPONSE;s=socket.socket(socket.AF_UNIX);s.settimeout(20);s.connect('/control/prepare.sock');send(s,{'action':'status'},MAX_REQUEST);print(json.dumps(receive(s,MAX_RESPONSE)))"))
                    if not response.get('ok') or not response['result']['ready'] or response['result']['live_apply_enabled']:
                        raise RuntimeError('Persistent manager readiness or ordinary Apply gate invalid.')
                    if response['result']['selected_generation']!=managed['generation']:
                        raise RuntimeError('Persistent confirmed generation changed across restarts.')
                    record(label+'-manager-fresh-readiness-and-live-gate-disabled')
                record(label+'-restart-health-memory-default-route')
            except Exception:
                for container in containers:
                    print(container+' logs: '+run('docker','logs','--tail','25',container),flush=True)
                    print(container+' routes: '+run('docker','exec',container,'ip','route','show','table','all'),flush=True)
                    print(container+' addresses: '+run('docker','exec',container,'ip','-j','addr'),flush=True)
                print('VPN firewall: '+dx(vpn,'iptables-save'),flush=True)
                print('Application neighbors: '+dx(app,'ip','neigh'),flush=True)
                raise
            finally:
                for container in reversed(containers):sp.run(['docker','rm','-f',container],capture_output=True)
                for network in reversed(networks):sp.run(['docker','network','rm',network],capture_output=True)
                if layout_image:sp.run(['docker','image','rm',layout_image],capture_output=True)
                shutil.rmtree(temp)
        print(json.dumps({'result':'PASS','checks':len(results),'layouts':[name for name,_ in layouts]}),flush=True)
    finally:
        sp.run(['docker','image','rm',image],capture_output=True)
        if run('ip','route','show','default')!=baseline:raise RuntimeError('Host default changed after cleanup')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',default=str(Path(__file__).resolve().parents[1]));p.add_argument('--peer',action='store_true');p.add_argument('--app',action='store_true');p.add_argument('--managed-layouts',action='store_true');a=p.parse_args()
    if a.peer:peer_mode()
    elif a.app:app_mode()
    else:suite(a.root,a.managed_layouts)
