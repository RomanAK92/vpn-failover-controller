#!/usr/bin/python3
"""Create only validated, reserved tunnel interfaces and private runtime configs."""
import ipaddress
import json
import pathlib
import guard
from ipsec_config import render_ipsec

def private_write(path, text):
    with path.open('w') as f:
        path.chmod(0o600)
        f.write(text)

def configure(c, meta, config_dir, runtime):
    runtime.mkdir(exist_ok=True, mode=0o700)
    for p in c['paths']:
        iface=p['interface'];exists=guard.check(['ip','link','show',iface])
        if p['kind']=='wireguard':
            peer=meta[p['peer']]
            key=(config_dir/('wg-client-'+p['peer']+'.key')).read_text().strip()
            allowed=str(ipaddress.ip_interface(p['address']).network)+', '+c['subnet']
            text=f'[Interface]\nPrivateKey = {key}\nListenPort = {p["listen_port"]}\n[Peer]\nPublicKey = {peer["public_key"]}\nAllowedIPs = {allowed}\nEndpoint = {peer["endpoint"]}:{peer.get("port",51889)}\nPersistentKeepalive = {p["keepalive"]}\n'
            target=runtime/(iface+'.conf');private_write(target,text)
            if not exists:guard.run(['ip','link','add',iface,'type','wireguard'])
            guard.run(['wg','setconf',iface,str(target)])
        elif not exists:
            guard.run(['ip','link','add',iface,'type','xfrm','if_id',str(p['if_id'])])
        guard.run(['ip','addr','replace',p['address'],'dev',iface])
        guard.run(['ip','link','set',iface,'mtu',str(p['mtu']),'up'])
    if c['ipsec_mode']=='generated':
        secrets={p['peer']:(config_dir/('ipsec-'+p['peer']+'.key')).read_text().strip() for p in c['paths'] if p['kind']=='ipsec'}
        private_write(runtime/'swan-client.conf',render_ipsec(c,meta,secrets))

def main():
    c,d=guard.validate_files();guard.preflight(c,d)
    configure(c,json.loads((guard.P/'peers.json').read_text()),guard.P,pathlib.Path('/run/vpn-router'))
    print('Validated tunnel interfaces configured')

if __name__=='__main__':main()
