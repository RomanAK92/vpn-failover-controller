"""Disposable Linux/Docker four-path integration test. Never run on production.

Uses only newly created private Docker networks, two simulated Linux gateways,
one application container and one controller container. Publishes no ports.
Generated credentials remain in a private temporary directory and are removed.
Requires root/Docker and WireGuard/XFRM kernel support. No live router is used.
"""
import argparse, hashlib, http.client, ipaddress, json, os, pathlib, secrets
import shutil, subprocess as sp, sys, tempfile, time, re


def run(*args, timeout=30, input=None):
    p=sp.run(args,input=input,text=True,capture_output=True,timeout=timeout)
    if p.returncode:
        # Never include configuration files or key-bearing command arguments.
        raise RuntimeError('Command failed: '+args[0]+' | '+p.stderr[-1500:])
    return p.stdout.strip()


def peer_mode(config):
    p=json.loads(pathlib.Path(config).read_text());ident=p['id']
    for address in ('10.60.0.1','10.60.0.10','10.60.0.60'):
        run('ip','addr','add',address+'/32','dev','lo')
    run('ip','link','add','peer-wg','type','wireguard')
    run('wg','setconf','peer-wg','/test/wg.conf')
    run('ip','addr','add',f'10.250.{ident}.1/30','dev','peer-wg')
    run('ip','link','set','peer-wg','mtu','1420','up')
    run('ip','link','add','peer-ipsec','type','xfrm','if_id',str(ident))
    run('ip','link','set','peer-ipsec','mtu','1400','up')
    run('ip','route','add',f'10.251.{ident}.2/32','dev','peer-ipsec')
    pathlib.Path('/run/vpn-router').mkdir(exist_ok=True)
    # This is a dedicated synthetic gateway namespace, not the host VPN runtime.
    # A disk-bind VICI socket can survive a host reboot; existence is not readiness.
    socket_path=pathlib.Path('/run/vpn-router/charon.vici')
    if socket_path.exists():
        import stat
        attributes=socket_path.lstat()
        if not stat.S_ISSOCK(attributes.st_mode) or attributes.st_uid!=0:
            raise RuntimeError('Unexpected synthetic gateway control object; refusing removal.')
        socket_path.unlink()
    daemon=sp.Popen(['/usr/lib/ipsec/charon'],stdout=sp.DEVNULL,stderr=sp.DEVNULL)
    for _ in range(100):
        check=sp.run(['swanctl','--stats','--uri','unix:///run/vpn-router/charon.vici'],
            capture_output=True,timeout=3)
        if check.returncode==0:break
        if daemon.poll() is not None:raise RuntimeError('Synthetic IPsec daemon exited before readiness.')
        time.sleep(.1)
    else:raise RuntimeError('Synthetic IPsec daemon did not become ready.')
    run('swanctl','--load-all','--noprompt','--file','/test/swan.conf',
        '--uri','unix:///run/vpn-router/charon.vici')
    from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            import socket
            body=(p['name']+'|'+self.client_address[0]+'|'+str(self.connection.getsockopt(socket.IPPROTO_TCP,socket.TCP_MAXSEG))).encode()
            self.send_response(200);self.send_header('Content-Length',str(len(body)))
            self.end_headers();self.wfile.write(body)
        def log_message(self,*args):pass
    ThreadingHTTPServer(('0.0.0.0',18080),Handler).serve_forever()


def app_mode():
    run('ip','route','add','10.60.0.0/24','via','172.28.240.2')
    from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body=b'application-ok';self.send_response(200)
            self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        def log_message(self,*args):pass
    ThreadingHTTPServer(('0.0.0.0',8080),Handler).serve_forever()


def suite(root,keep=False,soak_seconds=0,dashboard=False,management=False,persistent=False,upgrade_from=None,reboot_directory=None):
    root=pathlib.Path(root).resolve();sys.path.insert(0,str(root/'build'))
    from configuration import normalize
    tag='vpn-release-'+secrets.token_hex(4)
    image=tag+':test';wan=tag+'-wan';appnet=tag+'-app'
    names={'main':tag+'-main','secondary':tag+'-secondary','vpn':tag+'-vpn','app':tag+'-app'}
    if reboot_directory:
        import integration_reboot
        integration_reboot.private_directory(pathlib.Path(reboot_directory))
    temp=pathlib.Path(tempfile.mkdtemp(prefix=tag+'-',dir=reboot_directory));os.chmod(temp,0o700)
    results=[];containers=[];networks=[];volumes=[];managed=None
    host_default=run('ip','route','show','default')
    def record(name,**detail):
        item={'test':name,'passed':True,**detail};results.append(item)
        print(json.dumps(item),flush=True)
    def dx(name,*cmd,timeout=30):return run('docker','exec',names[name],*cmd,timeout=timeout)
    def state():return json.loads(dx('vpn','cat','/run/vpn-router/status.json'))
    def wait_path(want,timeout=100,all_healthy=False,since=0):
        deadline=time.monotonic()+timeout;last={}
        while time.monotonic()<deadline:
            try:
                last=state()
                if last['monotonic']>=since and last['active']==want and (not all_healthy or all(last['healthy'].values())):return last
            except Exception:pass
            time.sleep(1)
        raise RuntimeError('Path timeout: '+str(want)+' | '+json.dumps(last))
    def http_from_app(expected):
        code="import urllib.request; print(urllib.request.urlopen('http://10.60.0.60:18080/',timeout=5).read().decode())"
        body=dx('app','python3','-c',code)
        active=state()['active'];source=next(p['source'] for p in config['paths'] if p['name']==active)
        parts=body.split('|');cap=1380 if active.startswith('wg-') else 1360
        if parts[0]!=expected or parts[1]!=source:raise RuntimeError('Application route or SNAT source incorrect: '+body)
        if not 0<int(parts[2])<=cap:raise RuntimeError('Negotiated TCP MSS exceeds tunnel cap: '+body)
        return body
    def inbound(peer,source,destination):
        code="import http.client; c=http.client.HTTPConnection(%r,18081,timeout=5,source_address=(%r,0)); c.request('GET','/'); r=c.getresponse(); print(r.status,r.read().decode())"%(destination,source)
        body=dx(peer,'python3','-c',code)
        if body!='200 application-ok':raise RuntimeError('Inbound publication failed: '+body)
    def block(peer,protocol,enabled):
        args=['iptables','-w','5','-I' if enabled else '-D','INPUT']
        if enabled:args+=['1']
        iface='peer-wg' if protocol=='wg' else 'peer-ipsec'
        dx(peer,*args,'-i',iface,'-s','10.0.0.0/8','-d','10.60.0.0/24','-j','DROP')
    try:
        # Refuse overlapping Docker subnets before creating any resources.
        ids=run('docker','network','ls','-q').splitlines()
        for row in json.loads(run('docker','network','inspect',*ids)) if ids else []:
            for cfg in row.get('IPAM',{}).get('Config') or []:
                if cfg.get('Subnet'):
                    net=ipaddress.ip_network(cfg['Subnet'])
                    if net.version==4 and any(net.overlaps(ipaddress.ip_network(s)) for s in ('172.28.240.0/24','172.28.241.0/24')):
                        raise RuntimeError('Test subnet collision with existing Docker network')
        run('docker','build','-t',image,str(root/'build'),timeout=600)
        record('image-build')
        run('docker','run','--rm','--network','none','--entrypoint','python3','-v',str(root)+':/source:ro',image,
            '-m','unittest','discover','-s','/source/tests','-v',timeout=60)
        record('linux-unit-tests')
        for name,subnet in ((wan,'172.28.241.0/24'),(appnet,'172.28.240.0/24')):
            run('docker','network','create','--internal','--subnet',subnet,name);networks.append(name)
        controller=temp/'controller';controller.mkdir(mode=0o700)
        runtime=temp/'runtime';runtime.mkdir(mode=0o700)
        config=normalize(json.loads((root/'config/examples/controller.json').read_text()))
        (controller/'controller.json').write_text(json.dumps(config))
        (controller/'deployment.json').write_text(json.dumps({'app_subnet':'172.28.240.0/24',
            'publication':{'address':'172.28.240.10','port':8080,'tunnel_port':18081}}))
        clients={};public={};peer_configs=[]
        for suffix,ident,name,endpoint in [('b',102,'main','172.28.241.11'),('a',101,'secondary','172.28.241.12')]:
            peer=temp/name;peer.mkdir(mode=0o700)
            key=run('docker','run','--rm','--network','none','--entrypoint','wg',image,'genkey')
            client_key=run('docker','run','--rm','--network','none','--entrypoint','wg',image,'genkey')
            peer_pub=run('docker','run','--rm','-i','--network','none','--entrypoint','wg',image,'pubkey',input=key+'\n')
            client_pub=run('docker','run','--rm','-i','--network','none','--entrypoint','wg',image,'pubkey',input=client_key+'\n')
            clients[suffix]=(ident,name,endpoint,secrets.token_hex(32))
            public[suffix]={'endpoint':endpoint,'port':51889,'public_key':peer_pub,
                'local_id':'vpn-client-'+('primary' if suffix=='b' else 'secondary'),
                'remote_id':'vpn-router-'+('primary' if suffix=='b' else 'secondary'),
                'ike_proposals':'aes256-sha256-modp2048','esp_proposals':'aes256-sha256'}
            (controller/('ipsec-'+suffix+'.key')).write_text(clients[suffix][3]+'\n')
            (controller/('wg-client-'+suffix+'.key')).write_text(client_key+'\n')
            (peer/'peer.json').write_text(json.dumps({'id':ident,'name':name}))
            (peer/'wg.conf').write_text(f'[Interface]\nPrivateKey = {key}\nListenPort = 51889\n[Peer]\nPublicKey = {client_pub}\nAllowedIPs = 10.250.{ident}.2/32\n')
            logical='primary' if suffix=='b' else 'secondary'
            peer_conf=f'''connections {{
 {logical} {{
  version = 2
  local_addrs = {endpoint}
  remote_addrs = 172.28.241.10
  proposals = aes256-sha256-modp2048
  local {{
   auth = psk
   id = vpn-router-{logical}
  }}
  remote {{
   auth = psk
   id = vpn-client-{logical}
  }}
  children {{
   internal-{logical} {{
    local_ts = 10.60.0.0/24
    remote_ts = 10.251.{ident}.2/32
    if_id_in = {ident}
    if_id_out = {ident}
    esp_proposals = aes256-sha256
   }}
  }}
 }}
}}
secrets {{
 ike-test {{
  id-1 = vpn-client-{logical}
  id-2 = vpn-router-{logical}
  secret = "{clients[suffix][3]}"
 }}
}}
'''
            (peer/'swan.conf').write_text(peer_conf)
            peer_configs.append((name,peer,endpoint))
        client_conf=(root/'config/examples/swan-client.conf').read_text()
        for suffix,logical,example in [('b','primary','203.0.113.10'),('a','secondary','203.0.113.20')]:
            client_conf=client_conf.replace(example,clients[suffix][2])
            # Replace placeholders in their original ordered sections.
        client_conf=client_conf.replace('REPLACE_WITH_A_UNIQUE_LONG_RANDOM_SECRET',clients['b'][3],1)
        client_conf=client_conf.replace('REPLACE_WITH_A_UNIQUE_LONG_RANDOM_SECRET',clients['a'][3],1)
        (controller/'swan-client.conf').write_text(client_conf)
        (controller/'peers.json').write_text(json.dumps(public))
        for path in temp.rglob('*'):
            if path.is_file():path.chmod(0o600)
        if management:
            import integration_managed
            managed=integration_managed.prepare(pathlib.Path(upgrade_from).resolve() if upgrade_from else root,
                temp,controller,tag,run,containers,volumes,persistent=persistent)
            controller=managed['destination']/'config'
            runtime=managed['destination']/'data/runtime'
            config=managed['config']
            # Build and run the actual guided engine context, not an unrelated image.
            run('docker','build','-t',image,str(managed['destination']/'engine'),timeout=600)
            record('guided-package-preparation-and-engine-build',paths=len(config['paths']))
        for name,directory,endpoint in peer_configs:
            run('docker','run','-d','--name',names[name],'--network',wan,'--ip',endpoint,
                '--cap-add','NET_ADMIN','--cap-add','NET_RAW','--sysctl','net.ipv4.conf.all.rp_filter=0',
                '--entrypoint','python3','-v',str(root/'tests/integration_linux.py')+':/runner.py:ro',
                '-v',str(directory)+':/test:ro',image,'/runner.py','--peer','/test/peer.json')
            containers.append(names[name])
        run('docker','run','-d','--name',names['vpn'],'--network',wan,'--ip','172.28.241.10',
            '--cap-drop','ALL','--cap-add','NET_ADMIN','--cap-add','NET_RAW','--cap-add','NET_BIND_SERVICE',
            '--security-opt','no-new-privileges:true','--read-only','--memory','256m','--pids-limit','128','--restart','unless-stopped',
            '--sysctl','net.ipv4.ip_forward=1','--sysctl','net.ipv4.conf.all.rp_filter=0',
            '--tmpfs','/run:rw,nosuid,size=16m','--tmpfs','/tmp:rw,noexec,nosuid,size=16m',
            '--entrypoint','sh',*(
                ['-v',managed['management_mount']+':/management:rw','-v',str(managed['control'])+':/control:rw']
                if managed else ['-v',str(controller)+':/etc/vpn:ro']),'-v',str(runtime)+':/run/vpn-router',
            image,'-c','ip route replace default via 172.28.241.1 && iptables -N DOCKER-USER && iptables -A FORWARD -j DOCKER-USER && exec python3 -u '+(
                '/app/management/manager.py --application-file /management/readiness.json --enable-test-apply'
                if managed and managed.get('driver') else '/app/supervisor.py'))
        containers.append(names['vpn'])
        run('docker','network','connect','--ip','172.28.240.2',appnet,names['vpn'])
        run('docker','run','-d','--name',names['app'],'--network',appnet,'--ip','172.28.240.10',
            '--cap-add','NET_ADMIN','--entrypoint','python3',
            '-v',str(root/'tests/integration_linux.py')+':/runner.py:ro',image,'/runner.py','--app')
        containers.append(names['app'])
        wait_path('wg-main',timeout=180,all_healthy=True)
        initial_default=dx('vpn','ip','route','show','default')
        record('four-path-startup',active='wg-main')
        if managed:
            integration_managed.start(managed,names,temp,containers,run,record)
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            diagnostic=sp.run(['docker','exec',names['vpn'],'python3','/app/status.py','--json'],capture_output=True,text=True)
            if diagnostic.returncode==0:break
            time.sleep(1)
        else:raise RuntimeError('Readable status did not become healthy after startup')
        command_status=json.loads(diagnostic.stdout)
        if command_status['exit_code']!=0 or 'Active tunnel: wg-main' not in command_status['message']:raise RuntimeError('Readable status failed')
        def network_snapshot():
            # iptables-save includes wall timestamps and changing policy counters.
            firewall='\n'.join(re.sub(r'\[\d+:\d+\]','[COUNTERS]',line) for line in dx('vpn','iptables-save').splitlines() if not line.startswith('#'))
            return dx('vpn','ip','-j','rule','show')+dx('vpn','ip','route','show','table','all')+firewall
        before=network_snapshot()
        dx('vpn','python3','/app/doctor.py','--files-only')
        after=network_snapshot()
        if before!=after:raise RuntimeError('Read-only diagnostics changed networking')
        record('readable-status-and-read-only-file-checker')
        for peer,ident in [('main',102),('secondary',101)]:
            inbound(peer,'10.60.0.60',f'10.250.{ident}.2')
            inbound(peer,'10.60.0.60',f'10.251.{ident}.2')
        record('inbound-publication-and-pinned-replies',paths=4)
        record('docker-application-over-wg-main',response=http_from_app('main'))
        block('main','wg',True);time.sleep(5)
        if state()['active']!='wg-main':raise RuntimeError('Transient loss triggered early failover')
        block('main','wg',False);wait_path('wg-main',all_healthy=True)
        record('five-second-transient-does-not-switch')
        steps=[('main','wg','wg-secondary','secondary'),('secondary','wg','ipsec-main','main'),
               ('main','ipsec','ipsec-secondary','secondary')]
        for peer,protocol,path,expected in steps:
            begin=time.monotonic();block(peer,protocol,True);wait_path(path)
            record('failover-to-'+path,elapsed_seconds=round(time.monotonic()-begin,2),response=http_from_app(expected))
        block('secondary','ipsec',True);wait_path(None)
        routes=dx('vpn','ip','route','show','10.60.0.0/24')
        if 'unreachable' not in routes or 'metric 50' in routes:raise RuntimeError('All-down fail-closed route missing')
        record('all-paths-down-fails-closed')
        block('secondary','ipsec',False);wait_path('ipsec-secondary')
        record('recovery-from-all-down')
        block('main','wg',False);time.sleep(5)
        if state()['active']!='ipsec-secondary':raise RuntimeError('Failback stability delay missing')
        wait_path('wg-main',timeout=100);record('stable-preferred-path-failback')
        block('secondary','wg',False);block('main','ipsec',False)
        wait_path('wg-main',all_healthy=True)
        run('docker','restart',names['vpn'],timeout=40);restarted=time.monotonic()
        wait_path('wg-main',timeout=120,all_healthy=True,since=restarted)
        record('container-restart-restores-four-paths')
        ready_before=integration_managed.wait_ready(managed,names,run) if managed and managed.get('driver') else 0
        killed=time.monotonic()
        dx('vpn','python3','-c',"import os,pathlib,signal; p=next(p for p in pathlib.Path('/proc').iterdir() if p.name.isdigit() and (p/'comm').read_text().strip()=='charon'); os.kill(int(p.name),signal.SIGKILL)")
        # Wait for an actual Docker recovery, not a retained pre-crash status file.
        if managed and managed.get('driver'):
            integration_managed.wait_ready(managed,names,run,after=ready_before)
        else:
            deadline=time.monotonic()+60
            while time.monotonic()<deadline:
                if json.loads(run('docker','inspect',names['vpn']))[0]['RestartCount']>0:break
                time.sleep(1)
            else:raise RuntimeError('Killed IPsec daemon did not trigger bounded container recovery')
        wait_path('wg-main',timeout=180,all_healthy=True,since=killed+5)
        record('ipsec-daemon-crash-automatic-recovery')
        def verify_container_default():
            # Docker may rename its network devices across namespace recreation.
            # Check the gateway and WAN identity, rather than route text/ethN.
            defaults=json.loads(dx('vpn','ip','-j','route','show','default'))
            if len(defaults)!=1 or defaults[0].get('gateway')!='172.28.241.1':
                raise RuntimeError('Controller public default gateway changed: '+json.dumps(defaults))
            addresses=json.loads(dx('vpn','ip','-j','addr','show','dev',defaults[0]['dev']))
            if not any(a.get('local')=='172.28.241.10' for link in addresses for a in link['addr_info']):
                raise RuntimeError('Controller default route uses the wrong network')
            current=dx('vpn','ip','route','show','default')
            if current!=initial_default:
                print(json.dumps({'event':'docker-wan-device-renamed','before':initial_default,'after':current}),flush=True)
        verify_container_default()
        if run('ip','route','show','default')!=host_default:raise RuntimeError('Host default changed')
        record('controller-and-host-default-routes-preserved')
        health=json.loads(run('docker','inspect',names['vpn']))[0]
        if health['State'].get('OOMKilled'):raise RuntimeError('Container was OOM killed')
        # Watchdog updates every five seconds. A fresh route/probe result can
        # legitimately precede the first post-recovery healthy watchdog.
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            healthcheck=sp.run(['docker','exec',names['vpn'],'python3','/app/health.py'],capture_output=True)
            if healthcheck.returncode==0:break
            time.sleep(1)
        else:raise RuntimeError('Healthcheck did not become healthy after recovery')
        http_from_app('main')
        record('healthcheck-and-256m-memory-limit')
        if managed:
            integration_managed.finish(managed,names,run,record)
            if upgrade_from:
                image=integration_managed.upgrade(managed,names,root,temp,wan,appnet,containers,run,record,image)
                wait_path('wg-main',timeout=180,all_healthy=True)
                http_from_app('main')
                record('different-source-upgrade-restores-all-four-tunnels-and-docker-application')
            integration_managed.transactions(managed,names,run,record,http_from_app)
        if dashboard:
            import integration_dashboard
            integration_dashboard.check(root,tag,names,temp,runtime,dx,run,state,wait_path,block,record,network_snapshot,http_from_app)
        if soak_seconds:
            begin=time.monotonic();deadline=begin+soak_seconds;checks=0;last_report=begin
            while time.monotonic()<deadline:
                snapshot=state()
                if snapshot['active']!='wg-main' or not all(snapshot['healthy'].values()):raise RuntimeError('Soak observation detected unhealthy VPN path')
                if time.monotonic()-snapshot['monotonic']>snapshot['status_max_age']:raise RuntimeError('Soak observation found stale controller')
                dx('vpn','python3','/app/health.py');http_from_app('main');checks+=1
                if time.monotonic()-last_report>=300:
                    print(json.dumps({'soak':'running','elapsed_seconds':round(time.monotonic()-begin),'checks':checks}),flush=True);last_report=time.monotonic()
                time.sleep(min(10,max(0,deadline-time.monotonic())))
            record('continuous-four-path-observation',seconds=soak_seconds,checks=checks)
        verify_container_default()
        if run('ip','route','show','default')!=host_default:raise RuntimeError('Host default route changed during observation')
        if reboot_directory:
            import integration_reboot
            integration_reboot.prepare(managed,names,containers,networks,volumes,image,temp,
                pathlib.Path(reboot_directory),host_default,run,record)
            keep=True  # Only after the durable ownership receipt was written.
        print(json.dumps({'result':'PASS','checks':len(results),'resources_prefix':tag}),flush=True)
    except Exception as e:
        print(json.dumps({'result':'FAIL','error':str(e),'passed_checks':len(results),'resources_prefix':tag}),flush=True)
        for key in ('vpn','main','secondary'):
            if names[key] in containers:
                output=sp.run(['docker','logs','--tail','35',names[key]],text=True,capture_output=True)
                print(key+' logs:\n'+output.stdout+output.stderr,flush=True)
        raise
    finally:
        if not keep:
            for name in reversed(containers):sp.run(['docker','rm','-f',name],stdout=sp.DEVNULL,stderr=sp.DEVNULL)
            for name in reversed(networks):sp.run(['docker','network','rm',name],stdout=sp.DEVNULL,stderr=sp.DEVNULL)
            for name in reversed(volumes):sp.run(['docker','volume','rm',name],stdout=sp.DEVNULL,stderr=sp.DEVNULL)
            sp.run(['docker','image','rm',image],stdout=sp.DEVNULL,stderr=sp.DEVNULL)
            if managed:
                sp.run(['docker','image','rm',managed['web_image']],stdout=sp.DEVNULL,stderr=sp.DEVNULL)
                for extra in ('previous_image','upgrade_image'):
                    if managed.get(extra):sp.run(['docker','image','rm',managed[extra]],stdout=sp.DEVNULL,stderr=sp.DEVNULL)
            shutil.rmtree(temp)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',default=str(pathlib.Path(__file__).resolve().parent.parent))
    p.add_argument('--peer');p.add_argument('--app',action='store_true');p.add_argument('--keep',action='store_true');p.add_argument('--soak-seconds',type=int,default=0);p.add_argument('--dashboard',action='store_true');p.add_argument('--management',action='store_true')
    p.add_argument('--management-persistent',action='store_true',help='Owned disk-bind installation; never fills its filesystem')
    p.add_argument('--upgrade-from',help='Reviewed previous manager source, isolated fixture only; requires persistent mode')
    p.add_argument('--reboot-directory',help='Private isolated-lab fixture directory; retains verified resources for a separately authorized host reboot')
    a=p.parse_args()
    if a.peer:peer_mode(a.peer)
    elif a.app:app_mode()
    else:
        if not 0<=a.soak_seconds<=172800:p.error('soak-seconds must be between 0 and 172800')
        if a.upgrade_from and not a.management_persistent:p.error('Upgrade acceptance requires persistent owned storage.')
        if a.reboot_directory and (not a.management_persistent or a.keep):p.error('Reboot preparation requires persistent mode without --keep.')
        suite(a.root,a.keep,a.soak_seconds,a.dashboard,a.management or a.management_persistent,a.management_persistent,a.upgrade_from,a.reboot_directory)
