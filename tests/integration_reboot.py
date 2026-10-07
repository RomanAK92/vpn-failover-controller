"""Owned isolated-lab reboot acceptance. This helper never reboots the host.

The private receipt contains disposable credentials. Never publish it. Prepare
through integration_linux.py; verify after a separately authorized host reboot;
cleanup only after verification. Never use this fixture on production.
"""
import argparse
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import time


def run(*args, timeout=30, input=None):
    result = subprocess.run(args, input=input, text=True, capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError('Owned reboot check command failed: '+args[0])
    return result.stdout.strip()


def private_directory(path):
    if not path.is_absolute() or any(p.is_symlink() for p in (path, *path.parents)):
        raise RuntimeError('Use an absolute non-symlink private lab directory.')
    attributes = path.stat()
    if not path.is_dir() or attributes.st_uid != 0 or attributes.st_mode & 0o077:
        raise RuntimeError('Reboot fixture directory requires root ownership and mode 0700.')


def boot():
    return pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()


def inspect(kind, name):
    command = ['docker', 'inspect'] if kind == 'container' else ['docker', kind, 'inspect']
    return json.loads(run(*command, name))[0]


def write_private(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as out:
        json.dump(value, out); out.flush(); os.fsync(out.fileno())
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try: os.fsync(fd)
    finally: os.close(fd)


def prepare(managed, names, containers, networks, volumes, image, temp, directory, default, command, record):
    import integration_managed
    private_directory(directory)
    if volumes or not managed['driver'] or managed['bounded_test_storage']:
        raise RuntimeError('Reboot acceptance requires persistent disk storage, not a tmpfs keeper.')
    receipt = directory/'reboot-receipt.json'
    if receipt.exists(): raise RuntimeError('Never overwrite an existing reboot fixture receipt.')
    tag = managed['tag']
    if not re.fullmatch(r'vpn-release-[a-f0-9]{8}', tag): raise RuntimeError('Invalid fixture ownership.')
    for name in containers+networks:
        if not name.startswith(tag+'-'): raise RuntimeError('Unowned reboot resource.')
    baseline = integration_managed.transaction_wait(names, command, lambda s:s['ready'])['running_generation']
    source = {p.name:p.read_text() for p in (managed['destination']/'config').iterdir()}
    config = json.loads(source['controller.json']); config['interval'] = 9
    source['controller.json'] = json.dumps(config)
    candidate = integration_managed.private_command(names, command,
        {'action':'prepare', 'files':source, 'label':'Owned reboot rollback acceptance'})
    if not candidate['ok']: raise RuntimeError('Reboot candidate preparation refused.')
    generation = candidate['result']['id']
    armed = integration_managed.private_command(names, command,
        {'action':'apply', 'generation':generation, 'timeout':600})
    if not armed['ok']: raise RuntimeError('Reboot candidate arming refused.')
    integration_managed.transaction_wait(names, command,
        lambda s:s['ready'] and s['running_generation']==generation)
    all_names = command('docker','ps','-a','--format','{{.Names}}').splitlines()
    unrelated = {}
    for name in all_names:
        if name not in containers:
            item=inspect('container',name)
            unrelated[name]={'id':item['Id'], 'running':item['State']['Running'],
                'restart':item['HostConfig']['RestartPolicy']['Name']}
    for name in containers:
        command('docker','update','--restart','unless-stopped',name)
    saved = {k:str(v) if isinstance(v,pathlib.Path) else v for k,v in managed.items()}
    value={'version':1,'tag':tag,'boot':boot(),'default':default,'managed':saved,'names':names,
        'temp':str(temp),'previous':baseline,'candidate':generation,'change':armed['result']['change_id'],
        'containers':{n:inspect('container',n)['Id'] for n in containers},
        'networks':{n:inspect('network',n)['Id'] for n in networks},
        'images':{n:inspect('image',n)['Id'] for n in set([image,managed['web_image']])},
        'unrelated':unrelated}
    write_private(receipt,value)
    record('owned-persistent-reboot-fixture-armed-with-unconfirmed-change',confirmation_seconds=600,
        host_reboot_performed=False,credentials_published=False)


def load(path):
    private_directory(path.parent)
    attributes=path.lstat()
    if path.is_symlink() or not path.is_file() or attributes.st_uid!=0 or attributes.st_mode&0o077 or attributes.st_nlink!=1:
        raise RuntimeError('Unsafe private reboot receipt.')
    value=json.loads(path.read_text())
    if value.get('version')!=1 or not re.fullmatch(r'vpn-release-[a-f0-9]{8}',value.get('tag','')):
        raise RuntimeError('Invalid private fixture receipt.')
    temp=pathlib.Path(value['temp'])
    if temp.parent!=path.parent or not temp.name.startswith(value['tag']+'-'):
        raise RuntimeError('Fixture path outside its private owner directory.')
    private_directory(temp)
    for kind,key in [('container','containers'),('network','networks'),('image','images')]:
        for name,identity in value[key].items():
            if not name.startswith(value['tag']) or inspect(kind,name)['Id']!=identity:
                raise RuntimeError('Replaced or unowned fixture resource; refusing operation.')
    return value


def verify(path):
    import integration_managed
    value=load(path)
    if boot()==value['boot']: raise RuntimeError('Actual host boot identity has not changed.')
    if run('ip','route','show','default')!=value['default']:raise RuntimeError('Host default changed.')
    for name,expected in value['unrelated'].items():
        item=inspect('container',name)
        if (item['Id']!=expected['id'] or item['State']['Running']!=expected['running'] or
            item['HostConfig']['RestartPolicy']['Name']!=expected['restart']):
            raise RuntimeError('Unrelated lab service state changed across boot.')
    names=value['names']; managed=value['managed']
    for key in ('destination','management','control'):managed[key]=pathlib.Path(managed[key])
    status=integration_managed.transaction_wait(names,run,
        lambda s:s['ready'] and s['running_generation']==value['previous'] and
            s['transaction']['change'] and s['transaction']['change']['phase']=='rolled-back',timeout=240)
    if status['transaction']['change']['id']!=value['change']:
        raise RuntimeError('Unexpected recovered transaction.')
    # The stored browser session must remain usable after services/host restarted.
    integration_managed.fresh(managed,names,run)
    body=run('docker','exec',names['app'],'python3','-c',
        "import urllib.request;print(urllib.request.urlopen('http://10.60.0.60:18080/',timeout=5).read().decode())")
    if not body.startswith('main|'):raise RuntimeError('Docker application did not recover through the preferred VPN.')
    result={'result':'PASS','actual_boot_changed':True,'all_four_paths_ready':True,
        'unconfirmed_generation_rolled_back':True,'persistent_account_session_available':True,
        'encrypted_docker_application_available':True,'unrelated_services_preserved':True,
        'host_default_preserved':True}
    write_private(path.parent/'reboot-result.json',result)
    print(json.dumps(result),flush=True)


def cleanup(path):
    value=load(path)
    result=path.parent/'reboot-result.json'
    if result.is_symlink() or json.loads(result.read_text()).get('result')!='PASS':
        raise RuntimeError('Preserve failed fixture for investigation; cleanup requires passed verification.')
    # Save operational evidence outside the disposable private credential tree.
    for name in value['containers']:
        output=subprocess.run(['docker','logs',name],text=True,capture_output=True)
        write_private(path.parent/(name+'-boot.log'),{'stdout':output.stdout,'stderr':output.stderr})
    for name in reversed(list(value['containers'])):run('docker','rm','-f',name)
    for name in reversed(list(value['networks'])):run('docker','network','rm',name)
    for name in value['images']:run('docker','image','rm',name)
    temp=pathlib.Path(value['temp']); private_directory(temp);shutil.rmtree(temp)
    path.unlink()  # Disposable account/session material only; result and logs retained.
    print(json.dumps({'result':'PASS','owned_cleanup':True,'private_fixture_credentials_removed':True}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('verify','cleanup'))
    parser.add_argument('receipt',type=pathlib.Path);args=parser.parse_args()
    if os.geteuid()!=0:parser.error('Isolated lab root required.')
    (verify if args.action=='verify' else cleanup)(args.receipt)
