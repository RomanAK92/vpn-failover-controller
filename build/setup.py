#!/usr/bin/python3
import subprocess as sp,pathlib,json
import guard
c,d=guard.validate_files();guard.preflight(c,d)
P=pathlib.Path('/etc/vpn'); R=pathlib.Path('/run/vpn-router'); R.mkdir(exist_ok=True)
def run(*a):return sp.run(a,check=True,stdout=sp.PIPE,stderr=sp.PIPE,text=True).stdout.strip()
def ip(*a):return run('ip',*a)
def fw(*args):
 a=list(args);check=list(a);idx=next(i for i,x in enumerate(a) if x in ['-A','-I']);check[idx]='-C'
 if a[idx]=='-I' and a[idx+2].isdigit():check.pop(idx+2)
 if sp.run(['iptables']+check,stdout=sp.DEVNULL,stderr=sp.DEVNULL).returncode:run('iptables',*a)

meta=json.loads((P/'peers.json').read_text())
for suffix,i in [('a',101),('b',102)]:
 iface='vpn-wg-'+suffix
 key=(P/('wg-client-'+suffix+'.key')).read_text().strip()
 config=R/('wg-'+suffix+'.conf')
 config.write_text(f'[Interface]\nPrivateKey = {key}\nListenPort = {52000+i}\n[Peer]\nPublicKey = {meta[suffix]["public_key"]}\nAllowedIPs = 10.250.{i}.0/30, {c["subnet"]}\nEndpoint = {meta[suffix]["endpoint"]}:{meta[suffix].get("port",51889)}\nPersistentKeepalive = 25\n');config.chmod(0o600)
 
 if sp.run(['ip','link','show',iface],stdout=sp.DEVNULL,stderr=sp.DEVNULL).returncode:ip('link','add',iface,'type','wireguard')
 run('wg','setconf',iface,str(config));ip('addr','replace',f'10.250.{i}.2/30','dev',iface);ip('link','set',iface,'mtu','1420','up')
 xi='vpn-ipsec-'+suffix
 if sp.run(['ip','link','show',xi],stdout=sp.DEVNULL,stderr=sp.DEVNULL).returncode:ip('link','add',xi,'type','xfrm','if_id',str(i))
 ip('addr','replace',f'10.251.{i}.2/32','dev',xi);ip('link','set',xi,'mtu','1400','up')

print('Validated tunnel interfaces configured')
