"""Prepare a private SSH-only human review, never automatic browser acceptance.

No host reboot, public listener or production access. Generated credentials remain
in a root-private receipt outside Git until verified owned fixture cleanup.
"""
import argparse,json,pathlib,socket,subprocess,time
import integration_reboot as owned


def prepare(managed,names,containers,networks,image,temp,directory,run_default,run,record):
 import integration_managed
 owned.private_directory(directory)
 with socket.socket() as listener:
  listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
  listener.bind(('127.0.0.1',8787))
 name=names['managed-web'];tag=managed['tag'];destination=managed['destination']
 if name not in containers or not name.startswith(tag+'-'):raise RuntimeError('Unowned review web service')
 prior=owned.inspect('container',name)
 if prior['Image']!=owned.inspect('image',managed['web_image'])['Id']:raise RuntimeError('Replaced owned web image')
 run('docker','stop','--time','5',name,timeout=20);run('docker','rm',name);containers.remove(name)
 args=['docker','run','-d','--name',name,'--label','vpn-test-owner='+tag,'--network','host',
  '--user','65532:65532','--cap-drop','ALL','--security-opt','no-new-privileges:true',
  '--read-only','--memory','128m','--pids-limit','64','--entrypoint','python3']
 for source,target,mode in [(destination/'data/telemetry','/telemetry','ro'),
  (destination/'data/accounts','/auth','rw'),(destination/'data/history','/history','rw'),
  (destination/'data/drafts','/drafts','rw'),(managed['control'],'/control','ro')]:
  args+=['-v',str(source)+':'+target+':'+mode]
 run(*args,managed['web_image'],'server.py','--bind','127.0.0.1','--port','8787','--auth-dir','/auth',
  '--origin','http://127.0.0.1:8787','--history','/history','--draft-dir','/drafts','--control-dir','/control','--enable-test-apply')
 containers.append(name)
 deadline=time.monotonic()+30
 while time.monotonic()<deadline:
  try:
   integration_managed.fresh(managed,names,run);break
  except RuntimeError:time.sleep(.25)
 else:raise RuntimeError('Private review web startup did not become ready')
 status=integration_managed.transaction_wait(names,run,lambda s:s['ready'])
 original={}
 for name in run('docker','ps','-a','--format','{{.Names}}').splitlines():
  if name not in containers:
   item=owned.inspect('container',name)
   original[name]={'id':item['Id'],'running':item['State']['Running'],
    'restart':item['HostConfig']['RestartPolicy']['Name']}
 receipt={'version':1,'kind':'private-human-review','tag':tag,'temp':str(temp),'boot':owned.boot(),
  'default':run_default,'managed':{k:str(v) if isinstance(v,pathlib.Path) else v for k,v in managed.items()},
  'names':names,'containers':{n:owned.inspect('container',n)['Id'] for n in containers},
  'networks':{n:owned.inspect('network',n)['Id'] for n in networks},
  'images':{n:owned.inspect('image',n)['Id'] for n in (image,managed['web_image'])},'unrelated':original}
 owned.write_private(directory/'review-receipt.json',receipt)
 record('private-human-review-ready-with-real-four-path-traffic',public_listener=False,
  browser_acceptance_passed=False,ordinary_installation_gates_changed=False)


def cleanup(path):
 value=owned.load(path)
 if value.get('kind')!='private-human-review':raise RuntimeError('Not a human-review fixture')
 if owned.run('ip','route','show','default')!=value['default']:raise RuntimeError('Host default changed')
 for name,expected in value['unrelated'].items():
  item=owned.inspect('container',name)
  if item['Id']!=expected['id'] or item['State']['Running']!=expected['running']:
   raise RuntimeError('Unrelated service changed')
 for name in value['containers']:
  logs=subprocess.run(['docker','logs',name],text=True,capture_output=True)
  owned.write_private(path.parent/(name+'-review.log'),{'stdout':logs.stdout,'stderr':logs.stderr})
 for name in reversed(list(value['containers'])):owned.run('docker','rm','-f',name)
 for name in reversed(list(value['networks'])):owned.run('docker','network','rm',name)
 for name in value['images']:owned.run('docker','image','rm',name)
 import shutil
 temp=pathlib.Path(value['temp']);owned.private_directory(temp);shutil.rmtree(temp);path.unlink()
 print(json.dumps({'owned_review_cleaned':True,'operational_logs_preserved':True}))


if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('action',choices=['cleanup']);parser.add_argument('receipt',type=pathlib.Path)
 args=parser.parse_args();cleanup(args.receipt)
