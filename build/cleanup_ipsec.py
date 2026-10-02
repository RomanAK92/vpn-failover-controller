"""Remove only owned orphan XFRM objects before starting a fresh charon."""
import guard,json,re,ipaddress
c,d=guard.validate_files();meta=json.loads((guard.P/'peers.json').read_text())
local={a['local'] for row in json.loads(guard.run(['ip','-j','addr','show'])) for a in row.get('addr_info',[]) if a.get('family')=='inet'}
owned={p['if_id']:p for p in c['paths'] if p['kind']=='ipsec'}
expected={ident:meta[p['peer']]['endpoint'] for ident,p in owned.items()};deletes=[]
for kind in ('state','policy'):
 # iproute2 on this host does not provide JSON for XFRM. Never log raw state: it contains keys.
 text=guard.run(['ip','-s','xfrm',kind])
 for block in re.split(r'(?=^src )',text,flags=re.M):
  ident=re.search(r'\bif_id (0x[0-9a-f]+|\d+)',block)
  if not ident or int(ident.group(1),0) not in expected:continue
  ident=int(ident.group(1),0);pair=re.match(r'src (\S+) dst (\S+)',block)
  if not pair:raise guard.Conflict('Unrecognized owned XFRM selector')
  src,dst=pair.groups()
  if kind=='state':
   peer=expected[ident]
   if not ((src in local and dst==peer) or (dst in local and src==peer)):raise guard.Conflict('Foreign endpoint occupies reserved XFRM identity')
   spi=re.search(r'proto esp spi (0x[0-9a-f]+)',block)
   if not spi:raise guard.Conflict('Unexpected protocol in reserved XFRM identity')
   deletes.append(['ip','xfrm','state','delete','src',src,'dst',dst,'proto','esp','spi',spi.group(1)])
  else:
   tunnel=owned[ident]['source']+'/32'
   if (src,dst) not in [(tunnel,c['subnet']),(c['subnet'],tunnel)]:raise guard.Conflict('Foreign selector occupies reserved XFRM identity')
   direction=re.search(r'\bdir (in|out|fwd)\b',block);index=re.search(r'\bindex (\d+)',block)
   if not direction or not index:raise guard.Conflict('Unrecognized owned XFRM policy')
   deletes.append(['ip','xfrm','policy','delete','index',index.group(1),'dir',direction.group(1),'if_id',str(ident)])
# All objects are validated before deletion; no flush operation is used.
for args in deletes:guard.run(args)
print(json.dumps({'owned_orphan_objects_removed':len(deletes)}))
