"""Generate matching strongSwan selectors from normalized settings; no I/O."""
import json

def render_ipsec(c,meta,secrets):
    connections=[];credentials=[]
    for p in c['paths']:
        if p['kind']!='ipsec':continue
        m=meta[p['peer']];name=p['connection']
        connections.append(f''' {name} {{
  version = 2
  local_addrs = %any
  remote_addrs = {m['endpoint']}
  proposals = {m['ike_proposals']}
  dpd_delay = 10s
  local {{
   auth = psk
   id = {m['local_id']}
  }}
  remote {{
   auth = psk
   id = {m['remote_id']}
  }}
  children {{
   internal-{name} {{
    local_ts = {p['source']}/32
    remote_ts = {c['subnet']}
    if_id_in = {p['if_id']}
    if_id_out = {p['if_id']}
    esp_proposals = {m['esp_proposals']}
    start_action = trap|start
    dpd_action = restart
   }}
  }}
 }}''')
        credentials.append(f''' ike-{name} {{
  id-1 = {m['local_id']}
  id-2 = {m['remote_id']}
  secret = {json.dumps(secrets[p['peer']])}
 }}''')
    return 'connections {\n'+'\n'.join(connections)+'\n}\nsecrets {\n'+'\n'.join(credentials)+'\n}\n'
