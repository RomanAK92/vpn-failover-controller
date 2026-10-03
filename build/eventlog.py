"""Human-readable operational events; no routing or monitoring-state changes."""
from datetime import datetime, timezone, timedelta
import json
import os

NAMES={'wg-main':'WG-main','wg-secondary':'WG-secondary','ipsec-main':'IPsec-main','ipsec-secondary':'IPsec-secondary'}
def name(value):return NAMES.get(value,str(value)) if value is not None else 'none'
def clean(value):return str(value).replace('\r',' ').replace('\n',' ').replace('\x1b','')[:2000]
def render(event, timestamp=None, **data):
 level='INFO'
 if event=='health-change':
  failed=[name(k) for k,v in data['health'].items() if not v]
  if failed:
   level='WARN';message='Health check failed: '+', '.join(failed)+'. This probe result alone does not mean a failover.'
  else:message='All configured VPN paths passed their health checks.'
 elif event=='switch':
  if data.get('new') is None:
   level='WARN';message='No usable VPN path selected. Internal VPN traffic is unavailable.'
  else:message='Active VPN path changed: '+name(data.get('old'))+' -> '+name(data['new'])+'.'
 elif event=='start':message='VPN controller started. Selected path: '+name(data.get('active'))+'.'
 elif event=='stop':message='VPN controller stopped; routes retained.'
 elif event=='supervisor-start':message='VPN supervisor started; public default route preserved.'
 elif event=='supervisor-stop':message='VPN supervisor stopped; routes retained.'
 elif event=='orphan-cleanup':message='Startup IPsec cleanup: removed '+str(data['removed'])+' owned leftover kernel objects.'
 elif event=='restart-backoff':
  level='WARN';message='Local process recovery: waiting '+str(data['seconds'])+' seconds before container restart.'
 elif event=='orphan-peer-recovery':
  level='WARN';message='IPsec crash recovery for '+name(data['path'])+': '+str(data['action'])+'.'
 elif event=='integrity-status':
  if data['healthy']:message='VPN network integrity is healthy again.'
  else:
   level='WARN';message='VPN network integrity check failed: '+str(data.get('detail',''))+'. Foreign entries are not deleted.'
 elif event=='integrity-repaired':
  labels={'nat:POSTROUTING':'outbound VPN NAT rules','nat:PREROUTING':'inbound VPN publication rules','mangle:FORWARD':'TCP MSS rules','SNAT-order':'VPN NAT rule order','main-fallback':'internal unreachable fallback route','filter:DOCKER-USER':'Docker forwarding rules','mangle:PREROUTING':'incoming connection-mark rules','mangle:OUTPUT':'reply connection-mark rules'}
  repairs=[]
  for item in data['repairs']:
   if item.startswith('route:'):label='probe route in table '+item.split(':',1)[1]
   elif item.startswith('policy:'):label='routing rule at priority '+item.split(':',1)[1]
   elif item.startswith('fallback:'):label='unreachable fallback in table '+item.split(':',1)[1]
   else:label=labels.get(item,item)
   repairs.append(label)
  message='Restored missing or misplaced VPN network objects: '+', '.join(repairs)+'.'
 elif event in ('error','supervisor-fault'):
  level='ERROR';message=('VPN controller error: ' if event=='error' else 'VPN supervisor fault: ')+str(data.get('detail',''))
 else:message=str(event)+': '+json.dumps(data,sort_keys=True)
 now=datetime.fromtimestamp(timestamp,timezone(timedelta(hours=3))) if timestamp is not None else datetime.now(timezone(timedelta(hours=3)))
 return now.strftime('%d %b %Y %H:%M:%S MSK')+' | '+level+' | '+clean(message)

def write_event(event, **data):
 # Presentation errors must not stop routing, supervision or status-file updates.
 try:line=render(event,**data)
 except Exception:line='VPN LOG | WARN | Could not format operational event: '+clean(event)
 try:os.write(1,(line+'\n').encode('utf-8',errors='replace'))
 except OSError:pass
