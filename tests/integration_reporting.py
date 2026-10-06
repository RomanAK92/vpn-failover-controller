"""Owned, network-isolated reporter image acceptance with synthetic telemetry."""
import argparse,json,os,pathlib,secrets,subprocess,tempfile,time


def main(source):
 source=pathlib.Path(source).resolve();owner='vpn-reporting-check-'+secrets.token_hex(8)
 image=owner+':test';created=False
 def run(*args,timeout=30):
  result=subprocess.run(args,text=True,capture_output=True,timeout=timeout)
  if result.returncode:raise RuntimeError('Owned reporter check failed: '+args[0])
  return result.stdout.strip()
 with tempfile.TemporaryDirectory(prefix=owner+'-') as directory:
  temp=pathlib.Path(directory);temp.chmod(0o700)
  try:
   run('docker','build','-t',image,str(source/'monitoring'),timeout=600)
   now=time.monotonic()
   value={'monotonic':now,'status_max_age':20,'active':'main','settings':{'failure_rounds':8},
    'watchdog':{'monotonic':now,'controller':True,'integrity':True,'ike':True},
    'paths':[{'name':n,'kind':k,'healthy':True,'failed_rounds':0,'probes':{'10.60.0.1':True}}
     for n,k in [('main','wireguard'),('backup','ipsec')]],'private_unknown':'never-export-this'}
   telemetry=temp/'telemetry.json';telemetry.write_text(json.dumps(value));telemetry.chmod(0o644)
   private=temp/'kuma.json';private.write_text(json.dumps({'base_url':'http://127.0.0.1:9',
    'tokens':{'main':'A'*24,'backup':'B'*24}}));os.chown(private,65532,65532);private.chmod(0o600)
   run('docker','run','-d','--name',owner,'--label','vpn-test-owner='+owner,'--network','none',
    '--user','65532:65532','--cap-drop','ALL','--security-opt','no-new-privileges:true',
    '--read-only','--memory','64m','--pids-limit','32','--entrypoint','python3',
    '-v',str(telemetry)+':/telemetry.json:ro','-v',str(private)+':/private.json:ro',
    image,'-B','-c','import time;time.sleep(60)');created=True
   item=json.loads(run('docker','inspect',owner))[0]
   assert item['Config']['Labels']['vpn-test-owner']==owner
   assert item['Config']['User']=='65532:65532'
   assert item['HostConfig']['NetworkMode']=='none' and item['HostConfig']['ReadonlyRootfs']
   assert not item['HostConfig']['CapAdd'] and item['HostConfig']['CapDrop']==['ALL']
   assert item['HostConfig']['Memory']==64*1024*1024
   assert all(not m['RW'] for m in item['Mounts']) and len(item['Mounts'])==2
   run('docker','exec',owner,'python3','-B','-c',
    "import kuma_push;assert set(kuma_push.read_bounded('/private.json',True)['tokens'])=={'main','backup'}")
   output=run('docker','exec',owner,'python3','-B','kuma_push.py','--telemetry','/telemetry.json','--dry-run')
   result=json.loads(output);assert all(v[0]=='up' for v in result.values())
   assert 'never-export-this' not in output and '10.60.0.1' not in output
  finally:
   if created:
    item=json.loads(run('docker','inspect',owner))[0]
    if item['Config']['Labels'].get('vpn-test-owner')!=owner:raise RuntimeError('Unowned reporter container')
    run('docker','rm','-f',owner)
   subprocess.run(['docker','image','rm',image],capture_output=True,timeout=30)
 for args in [('docker','inspect',owner),('docker','image','inspect',image)]:
  if subprocess.run(args,capture_output=True,timeout=30).returncode==0:raise RuntimeError('Owned cleanup incomplete')
 print(json.dumps({'result':'PASS','restricted_reporter_image':True,'private_token_file_readable':True,
  'sanitized_projection_dry_run':True,'no_outbound_delivery':True,'owned_resources_cleaned':True}))


if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--source',default=str(pathlib.Path(__file__).parents[1]))
 main(parser.parse_args().source)
