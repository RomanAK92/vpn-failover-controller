import pathlib,json,time,sys
try:
 r=pathlib.Path('/run/vpn-router');d=json.loads((r/'status.json').read_text());w=json.loads((r/'watchdog.json').read_text());now=time.monotonic()
 assert 0<=now-d['monotonic']<15 and d['active'] is not None
 assert 0<=now-w['monotonic']<25 and all(w[k] for k in ('controller','ike','integrity'))
except Exception:sys.exit(1)
