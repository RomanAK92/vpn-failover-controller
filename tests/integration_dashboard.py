"""Optional dashboard acceptance: runs only within the disposable Linux integration suite."""
import json, os, pathlib, secrets, subprocess, time

def check(root, tag, names, temp, runtime, dx, run, state, wait_path, block, record, network_snapshot, http_from_app):
    image=tag+':dashboard';name=tag+'-dashboard';mirror=None
    directory=temp/'dashboard-telemetry';directory.mkdir(mode=0o755)
    token_file=temp/'dashboard-token';token_file.write_text(secrets.token_hex(32));os.chown(token_file,65532,65532);token_file.chmod(0o400)
    def request(address, auth='valid', path='/api/status', origin='main'):
        code="""import pathlib, http.client, json
token=pathlib.Path('/tmp/dashboard-test-token').read_text().strip()
headers={} if AUTH=='none' else {'Authorization':'Bearer '+(token if AUTH=='valid' else 'wrong')}
c=http.client.HTTPConnection(ADDRESS,8787,timeout=5,source_address=(SOURCE,0));c.request('GET',PATH,headers=headers);r=c.getresponse()
print(json.dumps({'status':r.status,'body':r.read().decode(),'csp':r.headers.get('Content-Security-Policy')}))
"""
        code="AUTH=%r;ADDRESS=%r;PATH=%r;SOURCE=%r\n"%(auth,address,path,'10.60.0.60' if origin=='main' else address)+code
        return json.loads(dx(origin,'python3','-c',code))
    def wait_dashboard(want=None, available=True):
        deadline=time.monotonic()+35;last='No response'
        while time.monotonic()<deadline:
            try:
                row=request('10.250.102.2',origin='vpn');data=json.loads(row['body'])
                if row['status']==200 and data['available']==available and (want is None or data['active']==want):return data
            except (RuntimeError,ValueError) as e:last=str(e)
            time.sleep(1)
        raise RuntimeError('Dashboard freshness/active path did not match controller: '+last)
    def start_mirror():
        return subprocess.Popen(['python3',str(root/'dashboard/mirror.py'),'--source',str(runtime),'--destination',str(directory)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    def start_dashboard(address):
        run('docker','run','-d','--name',name,'--network','container:'+names['vpn'],
            '--cap-drop','ALL','--security-opt','no-new-privileges:true','--read-only','--memory','128m','--pids-limit','64',
            '-v',str(directory)+':/telemetry:ro','-v',str(token_file)+':/token:ro',image,'python3','server.py',
            '--bind',address,'--token-file','/token')
    try:
        run('docker','build','-t',image,str(root/'dashboard'),timeout=600)
        run('docker','cp',str(token_file),names['main']+':/tmp/dashboard-test-token')
        dx('main','chmod','600','/tmp/dashboard-test-token')
        run('docker','cp',str(token_file),names['vpn']+':/tmp/dashboard-test-token')
        dx('vpn','chmod','600','/tmp/dashboard-test-token')
        before=network_snapshot();mirror=start_mirror();start_dashboard('10.250.102.2')
        data=wait_dashboard('wg-main')
        if len(data['paths'])!=4 or not all(p['healthy'] for p in data['paths']):raise RuntimeError('Live four-path telemetry missing')
        if request('10.250.102.2')['status']!=200:raise RuntimeError('Authenticated external WG request failed')
        for auth in ('none','wrong'):
            if request('10.250.102.2',auth)['status']!=401:raise RuntimeError('Authentication bypass')
        route=dx('main','ip','route','get','10.250.102.2')
        if 'peer-wg' not in route:raise RuntimeError('WG dashboard request did not use VPN route')
        record('dashboard-authenticated-live-wireguard',paths=4,unauthenticated=401,wrong_token=401)
        info=json.loads(run('docker','inspect',name))[0]
        host=info['HostConfig']
        if info['Config']['User']!='65532:65532' or not host['ReadonlyRootfs'] or host['CapDrop']!=['ALL'] or host['CapAdd']:raise RuntimeError('Dashboard privilege boundary incorrect')
        mounts={p['Destination'] for p in info['Mounts']}
        if mounts!={'/telemetry','/token'}:raise RuntimeError('Unexpected dashboard mount')
        page=request('10.250.102.2',path='/');missing=request('10.250.102.2',path='/../server.py')
        if page['status']!=200 or 'frame-ancestors' not in page['csp'] or missing['status']!=404:raise RuntimeError('Static asset protection failed')
        if network_snapshot()!=before:raise RuntimeError('Dashboard start or reads changed VPN networking')
        record('dashboard-no-network-mutation-and-least-privilege')
        # Read live switch telemetry locally while office return routing changes.
        # Direct VPN management is verified separately on the selected path.
        block('main','wg',True);wait_path('wg-secondary');data=wait_dashboard('wg-secondary')
        if not any('wg-secondary' in e['message'] and 'Route changed' in e['message'] for e in data['events']):raise RuntimeError('Live switch event missing')
        http_from_app('secondary');record('dashboard-real-failover-and-application-connectivity')
        block('secondary','wg',True);wait_path('ipsec-main');wait_dashboard('ipsec-main');http_from_app('main')
        run('docker','rm','-f',name);start_dashboard('10.251.102.2');time.sleep(3)
        row=request('10.251.102.2')
        if row['status']!=200 or json.loads(row['body'])['active']!='ipsec-main':raise RuntimeError('IPsec authenticated dashboard access failed')
        if 'peer-ipsec' not in dx('main','ip','route','get','10.251.102.2'):raise RuntimeError('IPsec dashboard request did not use VPN route')
        if request('10.251.102.2','none')['status']!=401:raise RuntimeError('IPsec access unprotected')
        record('dashboard-authenticated-live-ipsec')
        run('docker','rm','-f',name);start_dashboard('10.250.102.2');wait_dashboard('ipsec-main')
        before=network_snapshot();mirror.terminate();mirror.wait(timeout=5);mirror=None
        wait_dashboard(available=False)
        if network_snapshot()!=before:raise RuntimeError('Stale mirror changed VPN networking')
        http_from_app('main');record('dashboard-stale-telemetry-fails-closed-vpn-unaffected')
        mirror=start_mirror();wait_dashboard('ipsec-main');record('dashboard-telemetry-recovery')
        block('main','wg',False);block('secondary','wg',False);wait_path('wg-main',all_healthy=True);wait_dashboard('wg-main')
        if request('10.250.102.2')['status']!=200:raise RuntimeError('External WG access did not recover')
        record('dashboard-preferred-route-recovery')
    finally:
        if mirror is not None:mirror.terminate();mirror.wait(timeout=5)
        subprocess.run(['docker','rm','-f',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        subprocess.run(['docker','image','rm',image],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
