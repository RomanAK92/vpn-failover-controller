"""Guided package + four real encrypted paths, in disposable Docker namespaces.

Called by integration_linux.py --management. No host-network VPN, router or
published web port. Generated accounts/keys stay in the owned private fixture.
This is not host-reboot, upgrade or transactional apply acceptance.
"""
import copy
import hashlib
import json
import os
import pathlib
import secrets
import shutil
import sys
import time


def prepare(root, temp, controller, tag, run, containers, volumes, persistent=False):
    sys.path.insert(0, str(root/'management'))
    import bootstrap
    from broker import PrepareBroker, SOCKET_OWNER
    from journal import Journal
    config = json.loads((controller/'controller.json').read_text())
    config['ipsec_mode'] = 'generated'
    previous_peers = json.loads((controller/'peers.json').read_text())
    peers = {}
    for path in config['paths']:
        old = path['peer']; kind = path['kind']
        path['peer'] = ('wg-' if kind == 'wireguard' else 'ipsec-')+old
        fields = ('endpoint', 'port', 'public_key') if kind == 'wireguard' else (
            'endpoint', 'local_id', 'remote_id', 'ike_proposals', 'esp_proposals')
        peers[path['peer']] = {key: previous_peers[old][key] for key in fields}
        prefix = 'wg-client-' if kind == 'wireguard' else 'ipsec-'
        data = (controller/(prefix+old+'.key')).read_bytes()
        target = controller/(prefix+path['peer']+'.key')
        target.write_bytes(data); target.chmod(0o600)
    (controller/'controller.json').write_text(json.dumps(config))
    (controller/'peers.json').write_text(json.dumps(peers))
    destination = temp/'installation'
    password = secrets.token_urlsafe(24)
    old_umask = os.umask(0o077)
    try:
        receipt = bootstrap.prepare(destination, controller, 'admin', password, managed=persistent,
            application={'address': '10.60.0.60', 'port': 18080, 'path': '/'} if persistent else None)
    finally:
        os.umask(old_umask)
    if not receipt['prepared'] or receipt['started']:
        raise RuntimeError('Guided preparation receipt invalid.')
    if persistent:
        manifest = json.loads((destination/'installation.json').read_text())
        return {'destination': destination, 'config': config, 'password': password,
            'web_image': tag+'-managed-web:test', 'tag': tag, 'driver': True,
            'generation': manifest['initial_generation'], 'management': destination/'data/management',
            'control': destination/'data/control', 'management_mount': str(destination/'data/management'),
            'bounded_test_storage': False}
    driver_directory = destination/'engine/management'
    driver_directory.mkdir(mode=0o755)
    for name in ('driver.py', 'lifecycle.py', 'manager.py', 'operational.py', 'broker.py', 'coordinator.py',
                 'journal.py', 'generations.py', 'plan.py', 'rollback_watch.py'):
        shutil.copyfile(root/'management'/name, driver_directory/name)
        (driver_directory/name).chmod(0o644)
    with (destination/'engine/Dockerfile').open('a') as out:
        out.write('\nCOPY management /app/management/\nCOPY broker_support /app/dashboard/\n'
                  'RUN test ! -e /etc/vpn && ln -s /management/active /etc/vpn\n')
    support = destination/'engine/broker_support'; support.mkdir(mode=0o755)
    shutil.copyfile(root/'dashboard/drafts.py', support/'drafts.py')
    (support/'drafts.py').chmod(0o644)
    management = destination/'data/management'; management.mkdir(mode=0o700)
    (management/'generations').mkdir(mode=0o700)
    store = PrepareBroker(management, root/'build/doctor.py')
    files = {p.name: p.read_text() for p in (destination/'config').iterdir()}
    baseline = store.store.save(files, 'Initial acceptance baseline')['id']
    store.generations.initialize(baseline)
    journal = Journal(management, pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip())
    journal.initialize(baseline); journal.close()
    control = destination/'data/control'; control.mkdir(mode=0o750)
    os.chown(control, 0, 65532); control.chmod(0o2750)
    (control/'owner.json').write_text(json.dumps({'owner': SOCKET_OWNER}))
    (control/'owner.json').chmod(0o600)
    readiness = management/'readiness.json'
    readiness.write_text(json.dumps({'address': '10.60.0.60', 'port': 18080, 'path': '/'}))
    readiness.chmod(0o600)
    # Acceptance-only bounded filesystem: never fill the shared host's disk.
    # A keeper retains this tmpfs across test engine restarts; this is NOT a
    # production storage design or host-reboot proof.
    volume = tag+'-management-state'
    run('docker', 'volume', 'create', '--label', 'vpn-test-owner='+tag,
        '--driver', 'local', '--opt', 'type=tmpfs', '--opt', 'device=tmpfs',
        '--opt', 'o=size=2m,mode=0700', volume)
    volumes.append(volume)
    keeper = tag+'-state-keeper'
    run('docker', 'run', '-d', '--name', keeper, '--label', 'vpn-test-owner='+tag, '--network', 'none',
        '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true', '--read-only',
        '--memory', '64m', '--pids-limit', '16', '-v', volume+':/keep:ro',
        '--entrypoint', 'python3', tag+':test', '-c', 'import time;time.sleep(3600)')
    containers.append(keeper)
    run('docker', 'run', '--rm', '--label', 'vpn-test-owner='+tag, '--network', 'none', '--cap-drop', 'ALL',
        '--security-opt', 'no-new-privileges:true', '--read-only', '-v', str(management)+':/from:ro',
        '-v', volume+':/to:rw', '--entrypoint', 'python3', tag+':test', '-c',
        "import shutil;shutil.copytree('/from','/to',symlinks=True,dirs_exist_ok=True)")
    return {'destination': destination, 'config': config, 'password': password,
            'web_image': tag+'-managed-web:test', 'tag': tag,
            'driver': True, 'generation': baseline, 'management': management, 'control': control,
            'management_mount': volume, 'bounded_test_storage': True}


def call(managed, names, run, path, data=None, authenticated=True):
    headers = {'Origin': 'http://127.0.0.1:8787', 'X-VPN-Request': '1', 'Content-Type': 'application/json'}
    if authenticated:
        headers['Cookie'] = managed['cookie']
        headers['X-CSRF-Token'] = managed['csrf']
    # Private account/profile payload passes stdin, not command arguments/logs.
    code = '''import json,urllib.request
headers=%r
data=%r
request=urllib.request.Request('http://127.0.0.1:8787'+%r,
 data=None if data is None else json.dumps(data).encode(),headers=headers)
with urllib.request.urlopen(request,timeout=20) as response:
 print(json.dumps({'status':response.status,'cookie':response.headers.get('Set-Cookie'),'body':json.load(response)}))
''' % (headers, data, path)
    return json.loads(run('docker', 'exec', '-i', names['managed-web'], 'python3', '-', input=code))


def fresh(managed, names, run):
    deadline = time.monotonic()+30
    while time.monotonic() < deadline:
        result = call(managed, names, run, '/api/status')['body']
        # Use projected availability; never accept merely a container's green label.
        if result.get('available'):
            return result
        time.sleep(.5)
    raise RuntimeError('Managed telemetry did not become available.')


def start(managed, names, temp, containers, run, record):
    destination = managed['destination']
    run('docker', 'build', '-t', managed['web_image'], str(destination/'web'), timeout=600)
    names['managed-mirror'] = managed['tag']+'-managed-mirror'
    names['managed-web'] = managed['tag']+'-managed-web'
    for key, user, volumes, command in (
        ('managed-mirror', '0:0', [(destination/'data/runtime', '/runtime', 'ro'),
                                 (destination/'data/telemetry', '/telemetry', 'rw')],
         ['python3', 'mirror.py', '--source', '/runtime', '--destination', '/telemetry']),
        ('managed-web', '65532:65532', [(destination/'data/telemetry', '/telemetry', 'ro'),
          (destination/'data/accounts', '/auth', 'rw'), (destination/'data/history', '/history', 'rw'),
          (destination/'data/drafts', '/drafts', 'rw'), (managed['control'], '/control', 'ro')],
         ['python3', 'server.py', '--bind', '127.0.0.1', '--port', '8787', '--auth-dir', '/auth',
          '--origin', 'http://127.0.0.1:8787', '--history', '/history', '--draft-dir', '/drafts',
          '--control-dir', '/control', '--enable-test-apply'])):
        args = ['docker', 'run', '-d', '--name', names[key], '--network', 'none', '--user', user,
                '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true', '--read-only',
                '--memory', '128m', '--pids-limit', '64', '--entrypoint', 'python3']
        for source, target, mode in volumes:
            args += ['-v', str(source)+':'+target+':'+mode]
        run(*args, managed['web_image'], *command[1:])
        containers.append(names[key])
    # Wait for web startup using its private Docker namespace, no exposed host port.
    deadline = time.monotonic()+30
    while time.monotonic() < deadline:
        try:
            login = call(managed, names, run, '/api/login',
                         {'username': 'admin', 'password': managed['password']}, authenticated=False)
            break
        except RuntimeError:
            time.sleep(.5)
    else:
        raise RuntimeError('Combined managed login unavailable.')
    managed['cookie'] = login['cookie'].split(';')[0]
    managed['csrf'] = login['body']['csrf']
    status = fresh(managed, names, run)
    if managed['password'] in json.dumps(status):
        raise RuntimeError('Telemetry exposed a private credential.')
    record('guided-account-login-and-real-engine-telemetry')
    files = {p.name: p.read_text() for p in (destination/'config').iterdir()}
    hashes = {key: hashlib.sha256(value.encode()).hexdigest() for key, value in files.items()}
    draft = call(managed, names, run, '/api/drafts', {'files': files, 'label': 'Encrypted fixture draft'})
    if draft['status'] != 201 or draft['body']['applied']:
        raise RuntimeError('Managed draft receipt invalid.')
    if any(hashlib.sha256((destination/'config'/key).read_bytes()).hexdigest() != digest
           for key, digest in hashes.items()):
        raise RuntimeError('Draft save changed the active engine files.')
    inspect = json.loads(run('docker', 'inspect', names['managed-web']))[0]
    if inspect['HostConfig']['CapAdd'] or inspect['HostConfig']['CapDrop'] != ['ALL']:
        raise RuntimeError('Web acquired networking privileges.')
    if any(item['Destination'] in ('/etc/vpn', '/run/vpn-router', '/var/run/docker.sock')
           for item in inspect['Mounts']):
        raise RuntimeError('Web mounted private engine credentials/control.')
    record('guided-private-draft-with-live-engine-unchanged')
    run('docker', 'restart', names['managed-web'], timeout=40)
    # The account and hashed session survive ordinary container recreation/restart.
    deadline = time.monotonic()+30
    while time.monotonic() < deadline:
        try:
            if call(managed, names, run, '/api/session')['body']['role'] != 'admin':
                raise RuntimeError('Managed account session lost.')
            break
        except RuntimeError:
            time.sleep(.5)
    else:
        raise RuntimeError('Managed account storage did not survive restart.')
    fresh(managed, names, run)
    record('guided-web-restart-preserves-account-and-fresh-monitoring')
    wait_ready(managed, names, run)
    record('owned-engine-driver-fresh-four-path-and-application-readiness')


def wait_ready(managed, names, run, after=0):
    deadline = time.monotonic()+40
    while time.monotonic() < deadline:
        logs = run('docker', 'logs', names['vpn'])
        count = sum(1 for line in logs.splitlines() if '"event": "managed-generation-status"' in line
                    and '"ready": true' in line and managed['generation'] in line)
        if count > after: return count
        time.sleep(.5)
    raise RuntimeError('Owned driver did not independently prove fresh application readiness.')


def finish(managed, names, run, record):
    status = fresh(managed, names, run)
    # Legacy engine suite already swept application traffic through all four paths
    # and required every path healthy following controller/charon recovery.
    drafts = call(managed, names, run, '/api/drafts')['body']
    if not drafts.get('drafts'):
        raise RuntimeError('Managed private draft disappeared.')
    wait_ready(managed, names, run)
    record('guided-monitoring-and-drafts-after-encrypted-failover-and-engine-recovery')


def upgrade(managed,names,root,temp,wan,appnet,containers,run,record,previous_image):
    """Review-backed fresh-install upgrade in this disposable namespace only.

    Restore with the new source in a fresh Python process; imported old modules
    must never accidentally build the successor from the predecessor's code.
    Old accounts/sessions/TLS are intentionally not part of this VPN backup.
    """
    old_receipt=json.loads((managed['destination']/'installation.json').read_text())
    destination=temp/'upgraded-installation';password=secrets.token_urlsafe(24)
    code='''import json,sys,pathlib
p=json.load(sys.stdin);sys.path.insert(0,str(pathlib.Path(p['source'])/'management'))
import backup
payload=backup.snapshot(p['previous']);encrypted=backup.encrypt(payload,p['backup_password'])
backup.write_backup(p['backup_file'],encrypted)
receipt=backup.restore(backup.decrypt(encrypted,p['backup_password']),p['destination'],'admin',p['password'])
assert not receipt['started'] and backup.snapshot(p['destination'])==payload
print(json.dumps(receipt))
'''
    receipt=json.loads(run(sys.executable,'-c',code,input=json.dumps({
        'source':str(root),'previous':str(managed['destination']),'destination':str(destination),
        'backup_file':str(temp/'upgrade-confirmed.vpnbackup'),
        'backup_password':secrets.token_urlsafe(24),'password':password})))
    new_receipt=json.loads((destination/'installation.json').read_text())
    if (receipt['started'] or old_receipt['source_sha256']['management/manager.py']
        ==new_receipt['source_sha256']['management/manager.py']):
        raise RuntimeError('Different-source upgrade must prepare new code without starting it.')
    for key in ('vpn','managed-web','managed-mirror'):
        # Retain operational evidence before exact owned old containers are removed.
        logs=run('docker','logs',names[key])
        path=root.parent/(managed['tag']+'-predecessor-'+key+'.log')
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'w') as stream:stream.write(logs);stream.flush();os.fsync(stream.fileno())
    image=managed['tag']+'-upgraded:test'
    managed['upgrade_image']=image
    run('docker','build','-t',image,str(destination/'engine'),timeout=600)
    # Never run the old and new network owners simultaneously.
    for key in ('managed-web','managed-mirror','vpn'):
        run('docker','stop','--time','20',names[key],timeout=40)
        run('docker','rm',names[key])
        containers.remove(names[key])
    managed.update(destination=destination,password=password,generation=new_receipt['initial_generation'],
        management=destination/'data/management',control=destination/'data/control',
        management_mount=str(destination/'data/management'),previous_image=previous_image)
    names['vpn']=managed['tag']+'-upgraded-vpn'
    run('docker','run','-d','--name',names['vpn'],'--network',wan,'--ip','172.28.241.10',
        '--cap-drop','ALL','--cap-add','NET_ADMIN','--cap-add','NET_RAW','--cap-add','NET_BIND_SERVICE',
        '--security-opt','no-new-privileges:true','--read-only','--memory','256m','--pids-limit','128',
        '--restart','unless-stopped','--sysctl','net.ipv4.ip_forward=1','--sysctl','net.ipv4.conf.all.rp_filter=0',
        '--tmpfs','/run:rw,nosuid,size=16m','--tmpfs','/tmp:rw,noexec,nosuid,size=16m','--entrypoint','sh',
        '-v',str(destination/'data/management')+':/management:rw',
        '-v',str(destination/'data/control')+':/control:rw',
        '-v',str(destination/'data/runtime')+':/run/vpn-router',image,'-c',
        'ip route replace default via 172.28.241.1 && iptables -N DOCKER-USER && '
        'iptables -A FORWARD -j DOCKER-USER && exec python3 -u /app/management/manager.py '
        '--application-file /management/readiness.json --enable-test-apply')
    containers.append(names['vpn'])
    run('docker','network','connect','--ip','172.28.240.2',appnet,names['vpn'])
    start(managed,names,temp,containers,run,record)
    record('different-source-encrypted-upgrade-new-code-new-account-no-simultaneous-owner')
    return image


def private_command(names, run, request):
    code = '''import json,socket,sys
sys.path.insert(0,'/app/management')
from broker import send,receive,MAX_REQUEST,MAX_RESPONSE
with socket.socket(socket.AF_UNIX) as connection:
 connection.settimeout(25); connection.connect('/control/prepare.sock')
 send(connection,json.loads(sys.stdin.read()),MAX_REQUEST)
 print(json.dumps(receive(connection,MAX_RESPONSE)))
'''
    # Code and payload share stdin through a fixed bootstrap expression; no keys
    # or authentication values go into process command arguments or test logs.
    bootstrap = 'import json,sys; d=json.load(sys.stdin); import io; sys.stdin=io.StringIO(json.dumps(d["request"])); exec(d["code"])'
    return json.loads(run('docker', 'exec', '-i', names['vpn'], 'python3', '-c', bootstrap,
                         input=json.dumps({'code': code, 'request': request})))


def transaction_wait(names, run, condition, timeout=140):
    deadline = time.monotonic()+timeout
    while time.monotonic()<deadline:
        try:
            result = private_command(names, run, {'action': 'status'})
            if result['ok'] and condition(result['result']): return result['result']
        except RuntimeError:
            pass  # A supervised container restart briefly removes its private socket.
        time.sleep(.5)
    raise RuntimeError('Transactional manager did not reach the required independently healthy state.')


def transactions(managed, names, run, record, application_check):
    original = {p.name: p.read_text() for p in (managed['destination']/'config').iterdir()}
    def candidate(interval, bad_key=False, web=False):
        files = copy.deepcopy(original)
        config = json.loads(files['controller.json']); config['interval'] = interval
        files['controller.json'] = json.dumps(config)
        if bad_key:
            import base64
            files['wg-client-wg-a.key'] = base64.b64encode(os.urandom(32)).decode()+'\n'
        if web:
            draft = call(managed, names, run, '/api/drafts', {'files': files, 'label': 'Web acceptance draft'})['body']
            result = call(managed, names, run, '/api/control/prepare',
                          {'draft': draft['id'], 'current_password': managed['password']})['body']
            plan = call(managed, names, run, '/api/control/preview', {'generation': result['id']})['body']
            if not plan['live_footprint_compatible']:
                raise RuntimeError('Web could not independently review the compatible candidate.')
            return result['id']
        result = private_command(names, run, {'action': 'prepare', 'files': files, 'label': 'Owned apply acceptance'})
        if not result['ok']: raise RuntimeError('Private candidate preparation failed.')
        return result['result']['id']
    def begin(generation, timeout=180):
        result = private_command(names, run, {'action': 'apply', 'generation': generation, 'timeout': timeout})
        if not result['ok']: raise RuntimeError('Private transaction arming failed.')
        return result['result']['change_id']
    def recovered(status, previous):
        c = status['transaction']['change']
        return c and c['phase']=='rolled-back' and status['running_generation']==previous and status['ready']
    transaction_wait(names, run, lambda s: s['ready'])
    run('docker','exec',names['vpn'],'python3','-c',
        "import sys;sys.path.insert(0,'/app/management');from driver import ApplicationProbe;"
        "assert ApplicationProbe({'address':'10.60.0.60','port':18080,'scheme':'tcp'},'10.60.0.0/24').check();"
        "assert not ApplicationProbe({'address':'10.60.0.60','port':18079,'scheme':'tcp'},'10.60.0.0/24').check()")
    record('real-private-tcp-readiness-permits-open-port-and-refuses-closed-port')
    def selected(path, timeout=None):
        if timeout is None:
            timeout=max(45,managed['config']['interval']*managed['config']['recovery_rounds']+20)
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            state=json.loads(run('docker','exec',names['vpn'],'cat','/run/vpn-router/status.json'))
            if state['active']==path:return state
            time.sleep(.5)
        raise RuntimeError('Temporary operational selection did not reach its expected path.')
    operation = call(managed,names,run,'/api/control/operate',{
        'preferred':'wg-secondary','disabled':['wg-main'],'seconds':15,'current_password':managed['password']})['body']
    if operation.get('switch_proven') is not False:
        raise RuntimeError('Operational request incorrectly claimed a completed switch.')
    state=selected('wg-secondary')
    if 'wg-main' not in state['operations']['disabled']:
        raise RuntimeError('Engine did not independently read the temporary policy.')
    response=application_check('secondary')
    transaction_wait(names,run,lambda s:s['operations']['mode']=='automatic',timeout=25)
    state=selected('wg-main')
    if state['operations']['mode']!='automatic':
        raise RuntimeError('Expired operational policy did not return to automatic mode.')
    record('authenticated-temporary-maintenance-carries-traffic-and-expires-to-automatic',
        request_seconds=15, temporary_response=response, automatic_response=application_check('main'))
    call(managed,names,run,'/api/control/operate',{
        'preferred':'wg-secondary','disabled':['wg-main'],'seconds':300,'current_password':managed['password']})
    selected('wg-secondary');application_check('secondary')
    automatic=call(managed,names,run,'/api/control/automatic',{'current_password':managed['password']})['body']
    if automatic.get('switch_proven') is not False:
        raise RuntimeError('Automatic request incorrectly claimed a completed switch.')
    selected('wg-main')
    record('authenticated-explicit-return-to-automatic-selection',response=application_check('main'))
    # Inert foreign objects in this disposable namespace must survive in-place
    # engine changes. Docker namespace recreation itself legitimately removes
    # them, so check and retire these exact test objects before restart tests.
    run('docker', 'exec', names['vpn'], 'ip', 'route', 'add', 'blackhole', '198.51.100.0/24', 'table', '501', 'proto', '187')
    run('docker', 'exec', names['vpn'], 'ip', 'rule', 'add', 'priority', '32001', 'from', '198.51.100.254/32', 'lookup', '501')
    run('docker', 'exec', names['vpn'], 'iptables', '-w', '5', '-N', 'LAB-FOREIGN')
    run('docker', 'exec', names['vpn'], 'iptables', '-w', '5', '-A', 'LAB-FOREIGN', '-s', '198.51.100.254/32', '-j', 'RETURN')
    def foreign_objects():
        return (run('docker', 'exec', names['vpn'], 'ip', '-j', 'route', 'show', 'table', '501'),
                run('docker', 'exec', names['vpn'], 'ip', '-j', 'rule', 'show', 'priority', '32001'),
                run('docker', 'exec', names['vpn'], 'iptables', '-w', '5', '-S', 'LAB-FOREIGN'))
    foreign = foreign_objects()
    good = candidate(3, web=True)
    change = call(managed, names, run, '/api/control/apply', {'generation': good, 'timeout': 180,
                  'current_password': managed['password']})['body']['change_id']
    transaction_wait(names, run, lambda s: s['running_generation']==good and s['ready'])
    confirmation = call(managed, names, run, '/api/control/confirm',
        {'change_id': change, 'current_password': managed['password']})['body']
    if confirmation['phase'] != 'confirmed':
        raise RuntimeError('Healthy candidate could not be explicitly confirmed.')
    managed['generation'] = good
    record('real-authenticated-web-prepare-review-apply-confirm-with-all-tunnels-and-http-readiness', response=application_check('main'))
    bad = candidate(3, bad_key=True)
    bad_change = begin(bad, timeout=60)
    transaction_wait(names, run, lambda s: s['running_generation']==bad and not s['ready'], timeout=35)
    rejected = private_command(names, run, {'action': 'confirm', 'change_id': bad_change})
    if rejected['ok']: raise RuntimeError('Unhealthy standby credential was incorrectly confirmed.')
    duplicate = private_command(names, run, {'action': 'apply', 'generation': bad, 'timeout': 60})
    if duplicate['ok']: raise RuntimeError('A second pending transaction was accepted.')
    transaction_wait(names, run, lambda s: recovered(s, good))
    record('real-expired-unhealthy-credential-restores-previous-traffic',
           confirmation_seconds=60, duplicate_and_false_confirmation_rejected=True, response=application_check('main'))
    if foreign_objects() != foreign:
        raise RuntimeError('In-place transaction changed unrelated route/rule/firewall objects.')
    run('docker', 'exec', names['vpn'], 'ip', 'route', 'del', 'blackhole', '198.51.100.0/24', 'table', '501', 'proto', '187')
    run('docker', 'exec', names['vpn'], 'ip', 'rule', 'del', 'priority', '32001', 'from', '198.51.100.254/32', 'lookup', '501')
    run('docker', 'exec', names['vpn'], 'iptables', '-w', '5', '-D', 'LAB-FOREIGN', '-s', '198.51.100.254/32', '-j', 'RETURN')
    run('docker', 'exec', names['vpn'], 'iptables', '-w', '5', '-X', 'LAB-FOREIGN')
    record('real-apply-and-expired-rollback-preserve-unrelated-owned-test-objects')
    pending = candidate(4)
    begin(pending)
    transaction_wait(names, run, lambda s: s['running_generation']==pending and s['ready'])
    # Kill only the owned watcher inside this disposable container's PID namespace.
    code = "import pathlib,os,signal; p=next(p for p in pathlib.Path('/proc').iterdir() if p.name.isdigit() and b'rollback_watch.py' in (p/'cmdline').read_bytes() and int(p.name)!=os.getpid()); os.kill(int(p.name),signal.SIGKILL)"
    run('docker', 'exec', names['vpn'], 'python3', '-c', code)
    transaction_wait(names, run, lambda s: recovered(s, good), timeout=180)
    record('real-watcher-failure-supervised-restart-restores-confirmed-generation', response=application_check('main'))
    pending = candidate(5)
    begin(pending)
    transaction_wait(names, run, lambda s: s['running_generation']==pending and s['ready'])
    run('docker', 'restart', names['vpn'], timeout=40)
    transaction_wait(names, run, lambda s: recovered(s, good), timeout=180)
    record('real-container-restart-reverts-unconfirmed-generation-before-startup', response=application_check('main'))
    unused=candidate(8)
    before=transaction_wait(names,run,lambda s:s['ready'])['running_generation']
    receipt=call(managed,names,run,'/api/control/archive',{
        'generation':unused,'current_password':managed['password']})['body']
    if receipt['applied'] or receipt['state']!='archived':raise RuntimeError('Archive receipt invalid.')
    status=transaction_wait(names,run,lambda s:s['ready'])
    if status['running_generation']!=before or not any(p['id']==unused for p in status['archived']):
        raise RuntimeError('Archiving changed active traffic or failed to retain the private version.')
    call(managed,names,run,'/api/control/restore',{'generation':unused,'current_password':managed['password']})
    restored=transaction_wait(names,run,lambda s:s['ready'])
    if restored['running_generation']!=before or not any(p['id']==unused for p in restored['prepared']):
        raise RuntimeError('Private restore changed active traffic or failed to retain prepared settings.')
    record('authenticated-unused-generation-archive-restore-preserves-encrypted-traffic',response=application_check('main'))
    if not managed['bounded_test_storage']:
        # This is a real disk bind, so NEVER fill it as a failure injection.
        import backup
        payload = backup.snapshot(managed['destination'])
        password = secrets.token_urlsafe(24)
        encrypted = backup.encrypt(payload, password)
        restored = managed['destination'].parent/'offline-restored'
        receipt = backup.restore(backup.decrypt(encrypted, password), restored,
                                 'rescue', secrets.token_urlsafe(24))
        if receipt['started'] or backup.snapshot(restored) != payload:
            raise RuntimeError('Persistent encrypted settings recovery changed or started settings.')
        record('persistent-disk-generations-and-encrypted-offline-fresh-install-restore',
               restored_engine_started=False, host_disk_filled=False, response=application_check('main'))
        fresh(managed, names, run)
        return
    pending = candidate(6)
    change = begin(pending)
    transaction_wait(names, run, lambda s: s['running_generation']==pending and s['ready'])
    # Fill ONLY the owned 2 MiB tmpfs mounted at /management in this container.
    # Runtime/application/host disk are separate and deliberately not filled.
    filler_code = '''import os,errno,json
fd=os.open('/management/owned-storage-filler',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
try:
 while True: os.write(fd,b'x'*4096)
except OSError as exc:
 assert exc.errno==errno.ENOSPC
finally: os.close(fd)
assert os.statvfs('/management').f_bavail==0
print('Owned private-generation filesystem is full.')
'''
    run('docker', 'exec', '-i', names['vpn'], 'python3', '-', input=filler_code)
    full = transaction_wait(names, run, lambda s: s['storage_fault'] and s['running_generation']==good and s['ready'], timeout=240)
    if full['live_apply_enabled'] or full['database_recovery_acknowledged']:
        raise RuntimeError('Full-storage emergency claimed an impossible writable acknowledgement.')
    if private_command(names, run, {'action': 'confirm', 'change_id': change})['ok']:
        raise RuntimeError('Full-storage emergency still accepted confirmation.')
    record('real-full-private-generation-storage-restores-previous-http-traffic',
           database_acknowledgement=False, new_changes_blocked=True, host_disk_filled=False, response=application_check('main'))
    run('docker', 'exec', names['vpn'], 'python3', '-c',
        "import pathlib;p=pathlib.Path('/management/owned-storage-filler');assert p.is_file() and not p.is_symlink();p.unlink()")
    run('docker', 'restart', names['vpn'], timeout=40)
    transaction_wait(names, run, lambda s: recovered(s, good) and not s['storage_fault'], timeout=180)
    record('repaired-private-storage-reconciles-durable-rollback-after-supervised-restart', response=application_check('main'))
    fresh(managed, names, run)
