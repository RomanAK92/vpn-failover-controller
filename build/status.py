#!/usr/bin/python3
"""Explain runtime state without changing networking or contacting a gateway."""
import argparse
import datetime
import json
import pathlib
import time

def summarize(v,w,now):
    try:
        age=now-float(v['monotonic'])
        if not 0<=age<=v.get('status_max_age',15):return 'ERROR: Controller status is stale or invalid',2
        if not 0<=now-float(w['monotonic'])<=25:return 'ERROR: Supervisor status is stale or invalid',2
        if not all(w[k] is True for k in ('controller','ike','integrity')):return 'ERROR: Supervisor reports a local VPN fault',2
        paths=v['paths'];names=[p['name'] for p in paths];active=v['active'];settings=v['settings']
        if active is not None and active not in names:raise ValueError()
        lines=['Active tunnel: '+(active or 'NONE — managed network is unreachable'),f'Status age: {age:.1f}s']
        if w.get('ike_required') is False:lines.append('IPsec daemon: not required by this configuration')
        code=0 if active is not None and v['healthy'].get(active) is True else 1
        for i,p in enumerate(paths):
            name=p['name'];probes=v['probes'][name];healthy=v['healthy'][name]
            if type(healthy) is not bool:raise ValueError()
            role='ACTIVE' if name==active else 'STANDBY';ok=sum(x is True for x in probes.values())
            detail='available' if healthy else f'probe loss {v["failure_rounds"][i]}/{settings["failure_rounds"]} rounds'
            if healthy and active in names and i<names.index(active):
                remaining=max(0,settings['recovery_rounds']-v['recovery_rounds'][i])*settings['interval']
                detail+=f'; preferred-path recovery wait approximately {remaining}s'
            lines.append(f'{name}: {role}, {p["kind"]}, {detail}, targets {ok}/{len(probes)} (quorum {settings["quorum"]}), MTU {p["mtu"]}, MSS {p["mss"]}')
        switch=v.get('last_switch')
        if switch:
            timestamp=datetime.datetime.fromtimestamp(switch['time'],datetime.timezone.utc).isoformat()
            lines.append(f'Last switch: {timestamp} | {switch["old"] or "none"} -> {switch["new"] or "none"} | {switch["reason"]}')
        else:lines.append('Last switch: none recorded')
        lines.append('Waiting times are estimates; probes and command execution add delay.')
        return '\n'.join(lines),code
    except (KeyError,TypeError,ValueError,IndexError,OverflowError):return 'ERROR: Runtime status fields are invalid',2

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--state-dir',default='/run/vpn-router');parser.add_argument('--json',action='store_true');a=parser.parse_args()
    try:
        root=pathlib.Path(a.state_dir);v=json.loads((root/'status.json').read_text());w=json.loads((root/'watchdog.json').read_text())
    except (OSError,ValueError):v={};w={}
    message,code=summarize(v,w,time.monotonic())
    print(json.dumps({'message':message,'exit_code':code}) if a.json else message)
    raise SystemExit(code)

if __name__=='__main__':main()
