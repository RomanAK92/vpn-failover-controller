#!/usr/bin/python3
"""Read-only installation checks. No interface, firewall or route writes."""
import argparse
import json
import pathlib
import shutil
import stat
import guard

def inspect(config_dir, network=True):
    guard.P=pathlib.Path(config_dir);findings=[]
    def report(level,message):findings.append({'level':level,'message':message})
    try:c,d=guard.validate_files()
    except Exception as exc:
        # Parser errors may contain file content. Never echo them.
        report('ERROR','Configuration or credential validation failed ('+type(exc).__name__+'); check the configuration guide')
        return findings
    report('OK','Configuration, four paths and credential formats validated')
    for path in guard.P.iterdir():
        if path.is_file() and (path.suffix=='.key' or path.name=='swan-client.conf'):
            if stat.S_IMODE(path.stat().st_mode)&0o077:report('ERROR','Private credential file requires mode 0600: '+path.name)
    if not network:return findings
    for tool in ('ip','iptables','wg','swanctl','ping'):
        if not shutil.which(tool):report('ERROR','Required command missing: '+tool)
    if any(f['level']=='ERROR' for f in findings):return findings
    try:
        guard.preflight(c,d)
        report('OK','Reserved routing tables, priorities and interfaces have no detected conflicts')
        if pathlib.Path('/proc/sys/net/ipv4/ip_forward').read_text().strip()!='1':report('ERROR','IPv4 forwarding is disabled; configure it on the test host before startup')
        else:report('OK','IPv4 forwarding is enabled')
        if not guard.check(['iptables','-w','5','-S','DOCKER-USER']):report('ERROR','Docker iptables DOCKER-USER chain is unavailable')
        else:report('OK','Docker firewall chain is available')
        occupied=set()
        for table in ('/proc/net/udp','/proc/net/udp6'):
            for line in pathlib.Path(table).read_text().splitlines()[1:]:occupied.add(int(line.split()[1].rsplit(':',1)[1],16))
        for p in c['paths']:
            if p['kind']=='wireguard' and p['listen_port'] in occupied:
                owned=guard.check(['ip','link','show',p['interface']])
                port=guard.run(['wg','show',p['interface'],'listen-port']) if owned else ''
                if port!=str(p['listen_port']):report('ERROR','WireGuard listen port occupied: '+str(p['listen_port']))
        if occupied.intersection({500,4500}):report('ERROR','UDP 500/4500 already in use; stop the separate IKE service before starting this instance')
        modules=pathlib.Path('/proc/modules').read_text()
        for module in ('wireguard','xfrm_interface'):
            if module+' ' in modules:report('OK','Kernel module loaded: '+module)
            else:report('WARN','Kernel support not proven by read-only checks: '+module+'; may be built in or loaded on first use')
        if pathlib.Path('/proc/sys/net/ipv4/conf/all/rp_filter').read_text().strip()=='1':report('WARN','Strict reverse-path filtering may reject asymmetric VPN traffic; review host and interface settings')
    except Exception as exc:report('ERROR','Network inspection failed ('+type(exc).__name__+'); check permissions and reserved resources')
    return findings

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--config-dir',default='/etc/vpn');parser.add_argument('--files-only',action='store_true');parser.add_argument('--json',action='store_true')
    args=parser.parse_args();findings=inspect(args.config_dir,not args.files_only)
    if args.json:print(json.dumps(findings))
    else:
        for f in findings:print(f['level']+': '+f['message'])
    raise SystemExit(1 if any(f['level']=='ERROR' for f in findings) else 0)

if __name__=='__main__':main()
