"""Private HTTPS guided Compose acceptance; engine deliberately not started.

Only owned web/mirror/proxy resources are started. Certificate verification stays
enabled. Synthetic telemetry here is NOT encrypted application acceptance.
"""
import json
import argparse
import ipaddress
import os
import pathlib
import secrets
import socket
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).parents[1]
sys.path.insert(0,str(ROOT/'tests'))
import test_bootstrap
from test_dashboard import fixture


def run(*args):
    result=subprocess.run(args,capture_output=True,text=True,timeout=180)
    if result.returncode:raise RuntimeError('Scoped HTTPS Compose operation failed: '+args[0])
    return result.stdout


def main(network_clients=False):
    if sys.platform!='linux' or os.geteuid()!=0:raise SystemExit('Use a disposable Linux Docker host as root.')
    original=run('docker','ps','-a','--format','{{.Names}} {{.State}}').splitlines()
    default=run('ip','route','show','default')
    project='vpn-private-https-'+secrets.token_hex(4)
    fixture_=test_bootstrap.BootstrapTests();fixture_.setUp()
    dest=fixture_.root/'https-system'
    password=secrets.token_urlsafe(24)
    checks=[]
    command=['docker','compose','--project-name',project,'-f',str(dest/'compose.yaml')]
    image=project+'-web:test'
    network=None
    client_rule=None
    def record(name):
        checks.append(name);print(json.dumps({'test':name,'passed':True}),flush=True)
    try:
        bind='127.0.0.1';allowed=[]
        if network_clients:
            ids=run('docker','network','ls','-q').splitlines()
            for item in json.loads(run('docker','network','inspect',*ids)) if ids else []:
                for value in item.get('IPAM',{}).get('Config') or []:
                    subnet=value.get('Subnet')
                    if subnet and ipaddress.ip_network(subnet).version==4 and ipaddress.ip_network(subnet).overlaps(ipaddress.ip_network('172.28.248.0/24')):
                        raise RuntimeError('Private HTTPS test subnet collision.')
            network=project+'-clients'
            run('docker','network','create','--internal','--subnet','172.28.248.0/24',network)
            bind='172.28.248.1';allowed=['172.28.248.1/32','172.28.248.2/32']
        with socket.socket() as sock:sock.bind((bind,0));port=sock.getsockname()[1]
        if network_clients:
            # Permit only this owned internal bridge to this private test listener.
            # The Nginx allowlist, not the host's default deny, must decide both
            # probes. Remove this exact commented rule in finally; never flush.
            client_rule=['-s','172.28.248.0/24','-d',bind,'-p','tcp','--dport',str(port),
                         '-m','comment','--comment',project,'-j','ACCEPT']
            run('iptables','-w','5','-I','INPUT','1',*client_rule)
        with socket.socket() as sock:
            # Match the server's reuse setting: recent owned TIME_WAIT sockets
            # are not a running listener. An actual occupied backend still fails.
            sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
            sock.bind(('127.0.0.1',8787))
        origin='https://'+bind+':'+str(port)
        certs=fixture_.root/'certs';certs.mkdir(mode=0o700)
        run('openssl','req','-x509','-newkey','ec','-pkeyopt','ec_paramgen_curve:P-256',
            '-nodes','-days','2','-subj','/CN='+bind,'-addext','subjectAltName=IP:'+bind,
            '-keyout',str(certs/'privkey.pem'),'-out',str(certs/'fullchain.pem'))
        (certs/'privkey.pem').chmod(0o600)
        (certs/'fullchain.pem').chmod(0o644)  # Public test CA, not its private key.
        config=json.loads((fixture_.config/'controller.json').read_text())
        address=str(next(__import__('ipaddress').ip_network(config['subnet']).hosts()))
        test_bootstrap.bootstrap.prepare(dest,fixture_.config,'admin',password,managed=True,
            application={'address':address,'port':80},https={'origin':origin,'bind':bind,'directory':str(certs),'allowed_cidrs':allowed})
        override=fixture_.root/'web-image.json'
        override.write_text(json.dumps({'services':{'vpn-dashboard':{'image':image},'vpn-mirror':{'image':image}}}))
        command+=['-f',str(override)]
        parsed=json.loads(run(*command,'config','--format','json'))['services']
        assert len(parsed['vpn-router']['tmpfs'])==2 and all(p.startswith('/') for p in parsed['vpn-router']['tmpfs'])
        assert len(parsed['vpn-dashboard-https']['tmpfs'])==1
        assert '--enable-test-apply' not in parsed['vpn-router']['command']
        assert '--enable-test-apply' not in parsed['vpn-dashboard']['command']
        assert parsed['vpn-dashboard-https']['cap_drop']==['ALL']
        assert parsed['vpn-dashboard-https']['user']=='101:101'
        assert not any(m['target'] in ('/management','/etc/vpn','/var/run/docker.sock') for m in parsed['vpn-dashboard']['volumes'])
        record('persistent-private-https-compose-permissions-and-correct-tmpfs-mounts')
        data=fixture();data['monotonic']=time.monotonic()
        watchdog={'monotonic':time.monotonic(),'controller':True,'ike':True,'integrity':True,'secret':'not-for-export'}
        for name,value in [('status.json',data),('watchdog.json',watchdog)]:
            (dest/'data/runtime'/name).write_text(json.dumps(value));(dest/'data/runtime'/name).chmod(0o600)
        run(*command,'build','vpn-dashboard')
        run(*command,'up','-d','--no-build','vpn-dashboard','vpn-mirror','vpn-dashboard-https')
        # Trust this fixture's own CA explicitly. Hostname and TLS verification
        # remain enabled; this does not weaken host/browser certificate policy.
        context=ssl.create_default_context(cafile=str(certs/'fullchain.pem'))
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPSHandler(context=context))
        cookie=None;csrf=None
        def request(path,body=None,headers=None):
            defaults={'Origin':origin,'Content-Type':'application/json','X-VPN-Request':'1'}
            if cookie:defaults['Cookie']=cookie
            if csrf:defaults['X-CSRF-Token']=csrf
            defaults.update(headers or {})
            req=urllib.request.Request(origin+path,data=json.dumps(body).encode() if body is not None else None,headers=defaults)
            try:response=opener.open(req,timeout=25)
            except urllib.error.HTTPError as exc:response=exc
            with response:
                raw=response.read(131072)
                try:value=json.loads(raw)
                except json.JSONDecodeError:value={}
                return response.status,response.headers,value
        deadline=time.monotonic()+40
        while time.monotonic()<deadline:
            try:
                if request('/api/auth')[0]==200:break
            except OSError:pass
            time.sleep(.2)
        else:raise RuntimeError('Private verified HTTPS listener unavailable.')
        record('certificate-verified-https-listener-with-engine-not-started')
        if network_clients:
            for suffix,client,expected in [('allowed','172.28.248.2',200),('denied','172.28.248.3',403)]:
                code="""import ssl,urllib.request,urllib.error
request=urllib.request.Request(%r,headers={'X-VPN-Client':'172.28.248.2','X-VPN-Ingress':'0'*64})
try:response=urllib.request.urlopen(request,context=ssl.create_default_context(cafile='/test-ca.pem'),timeout=10)
except urllib.error.HTTPError as exc:response=exc
with response:print(response.status)
""" % (origin+'/api/auth')
                client_result=subprocess.run(['docker','run','--rm','--name',project+'-'+suffix,'--network',network,'--ip',client,
                    '--user','65532:65532','--cap-drop','ALL','--security-opt','no-new-privileges:true',
                    '--read-only','--memory','64m','--pids-limit','16',
                    '-v',str(certs/'fullchain.pem')+':/test-ca.pem:ro','--entrypoint','python3',image,'-c',code],
                    capture_output=True,text=True,timeout=30)
                if client_result.returncode:
                    # This fixed probe contains only synthetic network addresses,
                    # a PUBLIC test CA and dummy headers: no credential payload.
                    raise RuntimeError('Owned TLS client '+suffix+' failed: '+client_result.stderr[-1200:])
                assert client_result.stdout.strip()==str(expected)
            record('real-private-client-allowlist-permits-listed-source-and-rejects-unlisted-forged-source')
        req=urllib.request.Request('http://127.0.0.1:8787/api/auth',headers={
            'Host':origin.split('://')[1],'X-VPN-Client':'203.0.113.10','X-VPN-Ingress':'0'*64})
        try:urllib.request.urlopen(req,timeout=5);raise RuntimeError('Direct backend trusted a forged ingress proof.')
        except urllib.error.HTTPError as exc:assert exc.code==403
        record('direct-backend-and-forged-client-identity-rejected')
        assert request('/api/status')[0]==401
        code,headers,user=request('/api/login',{'username':'admin','password':password},
            {'X-VPN-Client':'198.51.100.123','X-VPN-Ingress':'0'*64})
        assert code==200
        cookie=headers['Set-Cookie'].split(';')[0];csrf=user['csrf']
        assert cookie.startswith('__Host-vpn_session=')
        assert all(flag in headers['Set-Cookie'] for flag in ('Secure','HttpOnly','SameSite=Strict','Path=/'))
        assert request('/api/session')[2]['username']=='admin'
        import sqlite3
        with sqlite3.connect(dest/'data/accounts/accounts.sqlite3') as database:
            assert database.execute('SELECT count FROM attempts WHERE bucket=?',('ip:'+bind,)).fetchone()[0]==1
            assert database.execute("SELECT 1 FROM attempts WHERE bucket='ip:198.51.100.123'").fetchone() is None
        record('secure-cookie-session-through-private-proxy')
        assert request('/api/login',{'username':'admin','password':password},{'Origin':'https://attacker.invalid'})[0]==403
        assert request('/api/status',headers={'Host':'attacker.invalid'})[0]==421
        assert request('/api/control/automatic',{'current_password':password},{'X-CSRF-Token':'wrong'})[0]==403
        record('origin-host-and-csrf-rejected-through-https')
        files={p.name:p.read_text() for p in (dest/'config').iterdir()}
        code,_,draft=request('/api/drafts',{'files':files,'label':'Private HTTPS draft'})
        assert code==201 and draft['applied'] is False
        assert all(v.strip() not in json.dumps(draft) for k,v in files.items() if k.endswith('.key'))
        assert request('/api/drafts')[2]['drafts'][0]['id']==draft['id']
        record('authenticated-private-draft-over-verified-https-with-no-key-summary')
        saved={k:v for k,v in files.items() if k.endswith('.key')}
        assert request('/api/drafts/archive',{'id':draft['id'],'current_password':password})[0]==200
        listing=request('/api/drafts')[2]
        assert not listing['drafts'] and listing['archived'][0]['id']==draft['id']
        assert request('/api/drafts/restore',{'id':draft['id'],'current_password':password})[0]==200
        assert request('/api/drafts')[2]['drafts'][0]['id']==draft['id']
        report=request('/api/support')[2]
        assert all(value.strip() not in json.dumps(report) for value in saved.values())
        assert '192.168.' not in json.dumps(report) and report['scope']=='anonymous monitoring only'
        record('private-https-reversible-draft-archive-and-anonymous-support-download')
        assert request('/api/control/apply',{'generation':'a'*32,'timeout':180,'current_password':password})[0]==403
        record('default-live-change-gate-remains-disabled-through-https')
        run(*command,'restart','vpn-dashboard')
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            try:
                if request('/api/session')[0]==200:break
            except OSError:pass
            time.sleep(.2)
        else:raise RuntimeError('Private HTTPS account session failed after web restart.')
        record('private-https-web-restart-preserves-account-session')
        assert request('/api/logout',{})[0]==200
        assert request('/api/session')[0]==401
        record('logout-revokes-session-through-https')
        # Verify engine absence independently through exact project/service labels.
        assert not run('docker','ps','-a','--filter','label=com.docker.compose.project='+project,
            '--filter','label=com.docker.compose.service=vpn-router','--format','{{.Names}}').strip()
        record('vpn-engine-never-started-and-no-live-network-changes')
    finally:
        if client_rule:
            subprocess.run(['iptables','-w','5','-D','INPUT',*client_rule],capture_output=True,timeout=30)
        if (dest/'compose.yaml').exists():
            subprocess.run([*command,'down','--remove-orphans'],capture_output=True,timeout=90)
        subprocess.run(['docker','image','rm',image],capture_output=True,timeout=30)
        if network:
            for suffix in ('allowed','denied'):
                subprocess.run(['docker','rm','-f',project+'-'+suffix],capture_output=True,timeout=30)
            subprocess.run(['docker','network','rm',network],capture_output=True,timeout=30)
        fixture_.tearDown()
    if run('docker','ps','-a','--format','{{.Names}} {{.State}}').splitlines()!=original:
        raise RuntimeError('Original lab container states changed.')
    if run('ip','route','show','default')!=default:raise RuntimeError('Host default changed.')
    record('owned-cleanup-preserves-original-lab-containers-and-host-default')
    print(json.dumps({'result':'PASS','checks':len(checks)}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--network-clients',action='store_true')
    main(parser.parse_args().network_clients)
