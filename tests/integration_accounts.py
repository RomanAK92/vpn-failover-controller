"""Disposable account-mode Docker acceptance; no host ports or live VPN changes."""
import json
import os
import pathlib
import secrets
import shutil
import subprocess
import tempfile

ROOT=pathlib.Path(__file__).parents[1]

def run(*args,input=None):
    result=subprocess.run(args,text=True,input=input,capture_output=True,timeout=180)
    if result.returncode:raise RuntimeError('Isolated Docker step failed: '+args[0])
    return result.stdout.strip()


def main():
    tag='vpn-accounts-'+secrets.token_hex(4)
    image=tag+':test'
    temporary=pathlib.Path(tempfile.mkdtemp(prefix=tag+'-'))
    before=run('docker','ps','-a','--format','{{.Names}} {{.State}}').splitlines()
    default=run('ip','route','show','default')
    os.chmod(temporary,0o700);os.chown(temporary,65532,65532)
    try:
        run('docker','build','-t',image,str(ROOT/'dashboard'))
        # Keys/passwords are generated only inside disposable private storage.
        # Network none still permits loopback, with no WAN exposure or host sockets.
        script='''
import json,os,secrets,pathlib,subprocess,time,urllib.request,urllib.error
from accounts import Accounts
password=secrets.token_urlsafe(24)
a=Accounts('/auth',initialize=True);a.put_user('admin',password);a.close()
p=subprocess.Popen(['python3','server.py','--auth-dir','/auth','--origin','http://127.0.0.1:8787','--history','/history'])
try:
 for _ in range(100):
  try:urllib.request.urlopen('http://127.0.0.1:8787/api/auth',timeout=.2).close();break
  except OSError:time.sleep(.05)
 def req(path,data=None,headers=None):
  h={'Origin':'http://127.0.0.1:8787','X-VPN-Request':'1','Content-Type':'application/json'};h.update(headers or {})
  r=urllib.request.Request('http://127.0.0.1:8787'+path,headers=h,data=json.dumps(data).encode() if data is not None else None)
  try:s=urllib.request.urlopen(r,timeout=5)
  except urllib.error.HTTPError as e:s=e
  with s:return s.status,s.headers,json.load(s)
 assert req('/api/status')[0]==401
 code,h,user=req('/api/login',{'username':'admin','password':password});assert code==200
 cookie=h['Set-Cookie'].split(';')[0]
 assert req('/api/status',headers={'Cookie':cookie})[0]==200
 assert req('/api/logout',{}, {'Cookie':cookie})[0]==403
 assert req('/api/logout',{}, {'Cookie':cookie,'X-CSRF-Token':user['csrf']})[0]==200
 assert req('/api/status',headers={'Cookie':cookie})[0]==401
 assert os.stat('/auth/accounts.sqlite3').st_mode&0o777==0o600
 assert os.getuid()==65532
 assert '0000000000000000' in pathlib.Path('/proc/self/status').read_text().split('CapEff:')[1].splitlines()[0]
 print(json.dumps({'passed':True,'checks':8,'mode':'private Docker account acceptance'}))
finally:
 p.terminate();p.wait(timeout=5)
'''
        result=run('docker','run','--rm','--name',tag,'--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true','--memory','128m','--pids-limit','64','-v',str(temporary)+':/auth:rw','--tmpfs','/history:rw,noexec,nosuid,size=4m,uid=65532,gid=65532,mode=0700','--entrypoint','python3',image,'-c',script)
        print(result,flush=True)
        assert run('ip','route','show','default')==default
        after=run('docker','ps','-a','--format','{{.Names}} {{.State}}').splitlines()
        assert all(line in after for line in before)
        print(json.dumps({'passed':True,'checks':2,'mode':'original services/default route preserved'}),flush=True)
    finally:
        subprocess.run(['docker','rm','-f',tag],capture_output=True)
        subprocess.run(['docker','image','rm',image],capture_output=True)
        assert temporary.name.startswith(tag+'-') and temporary.parent==pathlib.Path(tempfile.gettempdir())
        shutil.rmtree(temporary)
        print('Scoped account-test cleanup completed',flush=True)


if __name__=='__main__':main()
