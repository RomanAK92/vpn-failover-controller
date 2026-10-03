"""Pure configuration normalization and validation; never touches networking."""
import copy
import ipaddress
import re

LEGACY = {
    'wg-main': ('wireguard','b','vpn-wg-b','10.250.102.2/30',202,102),
    'wg-secondary': ('wireguard','a','vpn-wg-a','10.250.101.2/30',201,101),
    'ipsec-main': ('ipsec','b','vpn-ipsec-b','10.251.102.2/32',203,102),
    'ipsec-secondary': ('ipsec','a','vpn-ipsec-a','10.251.101.2/32',204,101),
}
PRIVATE = [ipaddress.ip_network(s) for s in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16')]

def integer(value, low, high, label):
    if type(value) is not int or not low <= value <= high:
        raise ValueError('Invalid '+label)
    return value

def private_prefix(value, label):
    net=ipaddress.ip_network(value, strict=True)
    if net.version!=4 or net.prefixlen<16 or not any(net.subnet_of(n) for n in PRIVATE):
        raise ValueError(label+' must be an RFC1918 IPv4 prefix /16 or smaller')
    return net

def normalize(config):
    c=copy.deepcopy(config)
    integer(c.get('schema_version',1),1,2,'schema_version')
    net=private_prefix(c.get('subnet',''),'Managed subnet')
    paths=c.get('paths')
    if not isinstance(paths,list) or not 1<=len(paths)<=4:raise ValueError('One to four paths are required')
    if c.get('schema_version',1)==1 and len(paths)!=4:raise ValueError('Legacy configuration requires four paths; use schema_version 2')
    for index,p in enumerate(paths):
        if not isinstance(p,dict):raise ValueError('Path must be an object')
        name=p.get('name','')
        if not re.fullmatch(r'[a-z][a-z0-9_-]{0,39}',name):raise ValueError('Invalid path name')
        if c.get('schema_version',1)==1:
            if name not in LEGACY:raise ValueError('Legacy path requires a known name; use schema_version 2')
            kind,peer,iface,addr,table,ident=LEGACY[name]
            # Explicit legacy source/interface changes must not silently use defaults.
            if p.get('source',str(ipaddress.ip_interface(addr).ip))!=str(ipaddress.ip_interface(addr).ip) or p.get('interface',iface)!=iface:
                raise ValueError('Changed legacy layout requires schema_version 2')
            defaults={'kind':kind,'peer':peer,'interface':iface,'address':addr,'table':table,
                'priority':12000+table,'mark_priority':12100+table-200,'mark':0x5c00+table-200,
                'mtu':1420 if kind=='wireguard' else 1400,'mss':1380 if kind=='wireguard' else 1360}
            if kind=='wireguard':defaults.update(listen_port=52000+ident,keepalive=25)
            else:defaults.update(if_id=ident,connection='primary' if peer=='b' else 'secondary')
            for key,value in defaults.items():p.setdefault(key,value)
        if p.get('kind') not in ('wireguard','ipsec'):raise ValueError('Invalid path kind')
        if not re.fullmatch(r'[a-z][a-z0-9_-]{0,19}',p.get('peer','')):raise ValueError('Invalid peer identifier')
        if not re.fullmatch(r'vpn-[a-z0-9-]{1,11}',p.get('interface','')):raise ValueError('Interface must start vpn- and fit Linux IFNAMSIZ')
        address=ipaddress.ip_interface(p.get('address',''))
        if address.version!=4 or not any(address.ip in n for n in PRIVATE):raise ValueError('Invalid tunnel address')
        if address.network.overlaps(net):raise ValueError('Managed subnet overlaps tunnel addresses')
        if address.network.prefixlen<24:raise ValueError('Tunnel prefix must be /24 or smaller')
        p['source']=str(address.ip)
        for key,low,high in [('table',1,0xffffffff),('priority',1,32765),('mark_priority',1,32765),('mark',1,0xffffffff),('mtu',576,9000)]:
            integer(p.get(key),low,high,name+'.'+key)
        if p['table'] in (253,254,255):raise ValueError('Reserved system routing table')
        integer(p.get('mss'),536,p['mtu']-40,name+'.mss')
        if p['kind']=='wireguard':
            integer(p.get('listen_port'),1024,65535,name+'.listen_port')
            integer(p.get('keepalive',25),0,65535,name+'.keepalive')
            p.setdefault('keepalive',25)
        else:
            integer(p.get('if_id'),1,0xffffffff,name+'.if_id')
            if not re.fullmatch(r'[a-z][a-z0-9_-]{0,39}',p.get('connection','')):raise ValueError('Invalid IPsec connection name')
    if c.get('schema_version',1)==1 and sorted(p['kind'] for p in paths)!=['ipsec','ipsec','wireguard','wireguard']:raise ValueError('Legacy configuration requires two WireGuard and two IPsec paths')
    for key in ('name','interface','source','table','priority','mark_priority','mark'):
        if len({p[key] for p in paths})!=len(paths):raise ValueError('Duplicate path '+key)
    if len({p[k] for p in paths for k in ('priority','mark_priority')})!=2*len(paths):raise ValueError('Overlapping rule priorities')
    for key,kind in [('listen_port','wireguard'),('if_id','ipsec'),('connection','ipsec')]:
        values=[p[key] for p in paths if p['kind']==kind]
        if len(set(values))!=len(values):raise ValueError('Duplicate '+key)
    for i,p in enumerate(paths):
        for q in paths[:i]:
            if ipaddress.ip_interface(p['address']).network.overlaps(ipaddress.ip_interface(q['address']).network):
                raise ValueError('Overlapping tunnel prefixes')
    targets=c.get('targets')
    if not isinstance(targets,list) or not 1<=len(targets)<=8 or len(set(targets))!=len(targets):raise ValueError('Invalid probe targets')
    if any(ipaddress.ip_address(t) not in net for t in targets):raise ValueError('Probe outside managed prefix')
    for key,low,high in [('quorum',1,len(targets)),('failure_rounds',1,120),('recovery_rounds',1,600),('interval',1,60)]:
        integer(c.get(key),low,high,key)
    c.setdefault('ipsec_mode','file')
    if c['ipsec_mode'] not in ('file','generated'):raise ValueError('Invalid ipsec_mode')
    return c

def status_max_age(c):return max(15,c['interval']*3+5)

def validate_peers(c,meta):
    used={p['peer'] for p in c['paths']}
    for peer in used:
        m=meta[peer];ip=ipaddress.IPv4Address(m['endpoint'])
        if ip.is_unspecified or ip.is_multicast or ip.is_loopback:raise ValueError('Invalid peer endpoint')
        if any(p['kind']=='wireguard' and p['peer']==peer for p in c['paths']):
            integer(m.get('port',51889),1,65535,'WireGuard endpoint port')
        if c['ipsec_mode']=='generated' and any(p['kind']=='ipsec' and p['peer']==peer for p in c['paths']):
            for field in ('local_id','remote_id'):
                if not re.fullmatch(r'[A-Za-z0-9@._-]{1,128}',m.get(field,'')):raise ValueError('Invalid IPsec identity')
            for field in ('ike_proposals','esp_proposals'):
                if not re.fullmatch(r'[a-z0-9_+,-]{1,256}',m.get(field,'')):raise ValueError('Invalid IPsec proposals')
    return meta
