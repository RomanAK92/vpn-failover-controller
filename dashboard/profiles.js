'use strict';
// Pure, local preparation. No fetch, storage, subprocesses or live apply.
const Profiles = (() => {
  function fail(message) { throw new Error(message); }
  function ipv4(s) {
    if (!/^(0|[1-9]\d{0,2})(\.(0|[1-9]\d{0,2})){3}$/.test(s)) fail('Use a numeric IPv4 address. DNS names and IPv6 are not supported by this version.');
    const a=s.split('.').map(Number); if(a.some(n=>n>255))fail('IPv4 address contains a number above 255.');
    return a.reduce((n,v)=>n*256+v,0);
  }
  function cidr(s, strict=true) {
    const bits=s.split('/'); if(bits.length!==2 || !/^\d{1,2}$/.test(bits[1]))fail('Use an IPv4 prefix such as 10.60.0.0/24.');
    const ip=ipv4(bits[0]), prefix=Number(bits[1]); if(prefix>32)fail('Invalid IPv4 prefix length.');
    const size=2**(32-prefix), start=Math.floor(ip/size)*size;
    if(strict && start!==ip)fail('Network prefix must use the network address, not a computer address.');
    return {ip,start,end:start+size-1,prefix};
  }
  function privateAddress(ip) { return (ip>=0x0a000000&&ip<=0x0affffff)||(ip>=0xac100000&&ip<=0xac1fffff)||(ip>=0xc0a80000&&ip<=0xc0a8ffff); }
  function overlap(a,b) {return a.start<=b.end&&b.start<=a.end;}
  function key(value) { if(!/^[A-Za-z0-9+/]{43}=$/.test(value)||atob(value).length!==32)fail('WireGuard keys must be valid base64 for 32 bytes.');return value; }
  function integer(s,min,max,label) { if(!/^\d+$/.test(String(s))||Number(s)<min||Number(s)>max)fail(label+' is outside its allowed range.');return Number(s); }
  function endpoint(address) {const ip=ipv4(address);if(ip===0||ip>>>24===127||ip>=0xe0000000)fail('Gateway address cannot be unspecified, loopback, multicast or reserved.');return address;}
  function parseWireGuard(raw) {
    if(raw.length>16384)fail('Profile is too large.');
    const result={Interface:{},Peer:{}};let section='';const seen=new Set();
    for(const original of raw.split(/\r?\n/)) {
      const line=original.trim(); if(!line||line.startsWith('#')||line.startsWith(';'))continue;
      if(line.startsWith('[')) {if(!/^\[(Interface|Peer)\]$/.test(line))fail('Unknown profile section.');section=line.slice(1,-1);if(seen.has(section))fail('Exactly one Interface and one Peer are supported.');seen.add(section);continue;}
      const m=line.match(/^([A-Za-z]+)\s*=\s*(.*)$/);if(!m||!section)fail('Invalid profile line.');
      const allowed=section==='Interface'?['PrivateKey','Address','ListenPort','MTU']:['PublicKey','Endpoint','AllowedIPs','PersistentKeepalive'];
      if(!allowed.includes(m[1]))fail('Unsupported setting: '+m[1]+'. Scripts, DNS changes, preshared keys and other features are never executed or silently removed.');
      if(Object.hasOwn(result[section],m[1]))fail('Duplicate profile setting: '+m[1]);result[section][m[1]]=m[2].trim();
    }
    if(seen.size!==2)fail('Profile needs one Interface and one Peer.');return result;
  }
  function prepare(input) {
    const net=cidr(input.subnet), app=cidr(input.appSubnet);
    for(const n of [net,app])if(n.prefix<16||!privateAddress(n.start)||!privateAddress(n.end))fail('Office and application networks must be private IPv4 prefixes /16 or smaller.');
    if(overlap(net,app))fail('Office and Docker application networks overlap.');
    const targets=input.targets.split(',').map(s=>s.trim());if(targets.length<1||targets.length>8||new Set(targets).size!==targets.length)fail('Use one to eight distinct office probe addresses.');
    for(const target of targets){const ip=ipv4(target);if(ip<net.start||ip>net.end)fail('Every probe must be inside the office network.');}
    if(!Array.isArray(input.roads)||input.roads.length<1||input.roads.length>4)fail('Add one to four roads.');
    const paths=[],peers={},files={},tunnels=[],ports=new Set(),sources=new Set();
    for(let i=0;i<input.roads.length;i++){
      const road=input.roads[i],n=i+1,peer='peer-'+n;
      const path={name:'road-'+n,kind:road.kind,peer,interface:'vpn-path-'+n,table:300+n,priority:13000+n,mark_priority:14000+n,mark:3000+n};
      if(road.kind==='wireguard') {
        const wg=parseWireGuard(road.profile),a=wg.Interface,b=wg.Peer;
        key(a.PrivateKey||'');key(b.PublicKey||'');
        const ep=(b.Endpoint||'').match(/^([^:]+):(\d+)$/);if(!ep)fail('WireGuard endpoint must be IPv4:port.');
        const allowed=cidr(b.AllowedIPs||'');if(allowed.start!==net.start||allowed.prefix!==net.prefix)fail('WireGuard AllowedIPs must contain exactly the chosen office prefix. Full-tunnel/default-route profiles are not supported.');
        path.address=a.Address||'';path.listen_port=integer(a.ListenPort||53000+n,1024,65535,'Local listen port');
        path.keepalive=integer(b.PersistentKeepalive||25,0,65535,'Keepalive');path.mtu=integer(a.MTU||1420,576,9000,'MTU');path.mss=path.mtu-40;
        if(ports.has(path.listen_port))fail('WireGuard local listen ports must be distinct.');ports.add(path.listen_port);
        peers[peer]={endpoint:endpoint(ep[1]),port:integer(ep[2],1,65535,'Gateway port'),public_key:b.PublicKey};files['wg-client-'+peer+'.key']=a.PrivateKey+'\n';
      } else if(road.kind==='ipsec') {
        for(const id of [road.localId,road.remoteId])if(!/^[A-Za-z0-9@._-]{1,128}$/.test(id||''))fail('IPsec identities use letters, numbers, @, dot, dash or underscore.');
        if(!/^[\x21-\x7e]{32,256}$/.test(road.secret||''))fail('IPsec shared secret must contain 32–256 printable characters without spaces.');
        path.address=road.address;path.if_id=100+n;path.connection='connection-'+n;path.mtu=1400;path.mss=1360;
        peers[peer]={endpoint:endpoint(road.endpoint),local_id:road.localId,remote_id:road.remoteId,ike_proposals:'aes256-sha256-modp2048',esp_proposals:'aes256-sha256'};
        files['ipsec-'+peer+'.key']=road.secret+'\n';
      } else fail('Unknown protocol.');
      const tunnel=cidr(path.address,false);if(tunnel.prefix<24||!privateAddress(tunnel.ip))fail('Each tunnel needs one private IPv4 address with a prefix /24 or smaller.');
      if(overlap(tunnel,net)||overlap(tunnel,app)||tunnels.some(t=>overlap(t,tunnel)))fail('Tunnel, office and application networks must not overlap.');
      if(sources.has(tunnel.ip))fail('Duplicate tunnel address.');sources.add(tunnel.ip);tunnels.push(tunnel);paths.push(path);
    }
    const controller={schema_version:2,subnet:input.subnet,targets,quorum:Math.min(2,targets.length),interval:2,failure_rounds:8,recovery_rounds:30,ipsec_mode:'generated',paths};
    files['controller.json']=JSON.stringify(controller,null,2)+'\n';files['peers.json']=JSON.stringify(peers,null,2)+'\n';files['deployment.json']=JSON.stringify({app_subnet:input.appSubnet,publication:null},null,2)+'\n';
    files['INSTALL.txt']='PRIVATE CONFIGURATION PACKAGE\nCredentials must stay private. Extract into config/local, directory0700, files0600.\nConfigure matching gateways and ensure they reach '+input.subnet+'.\nIPsec uses IKEv2 PSK, aes256-sha256-modp2048 / aes256-sha256; gateway proposals must match.\nRun the read-only doctor check before starting. Read QUICKSTART.md.\nNo live apply, DNS changes, scripts or gateway setup performed.\nPrepared by r.abdulkhalek.\n';
    return {files,preview:{controller,peers:Object.fromEntries(Object.entries(peers).map(([n,p])=>[n,{...p,...(p.public_key?{public_key:'[hidden]'}:{})}])),credentials:Object.keys(files).filter(n=>n.endsWith('.key')).map(n=>n+': [hidden]')}};
  }
  function archive(files) {
    const blocks=[],enc=new TextEncoder();
    function field(block,offset,value,length){block.set(enc.encode(value).slice(0,length),offset);}
    for(const [name,content] of Object.entries(files)){
      const data=enc.encode(content),header=new Uint8Array(512);field(header,0,name,100);field(header,100,'0000600\0',8);field(header,108,'0000000\0',8);field(header,116,'0000000\0',8);field(header,124,data.length.toString(8).padStart(11,'0')+'\0',12);field(header,136,'00000000000\0',12);header.fill(32,148,156);header[156]=48;field(header,257,'ustar\0',6);field(header,263,'00',2);const sum=header.reduce((a,b)=>a+b,0);field(header,148,sum.toString(8).padStart(6,'0')+'\0 ',8);blocks.push(header,data,new Uint8Array((512-data.length%512)%512));
    }blocks.push(new Uint8Array(1024));return new Blob(blocks,{type:'application/x-tar'});
  }
  return {parseWireGuard,prepare,archive};
})();
if(typeof module!=='undefined')module.exports=Profiles;
