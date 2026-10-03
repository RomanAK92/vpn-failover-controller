const assert=require('node:assert/strict');
const P=require('../dashboard/profiles.js');
const key=Buffer.alloc(32,1).toString('base64');
function wg(n){return {kind:'wireguard',profile:`[Interface]\nPrivateKey = ${key}\nAddress = 10.250.${n}.2/30\n[Peer]\nPublicKey = ${key}\nEndpoint = 203.0.113.${n}:51889\nAllowedIPs = 10.60.0.0/24`};}
function ipsec(n){return {kind:'ipsec',address:`10.251.${n}.2/32`,endpoint:`203.0.113.${n}`,localId:'client',remoteId:'gateway',secret:'a'.repeat(32)};}
const settings={subnet:'10.60.0.0/24',targets:'10.60.0.10,10.60.0.60',appSubnet:'172.18.0.0/16'};
for(const roads of [[wg(1)],[wg(1),wg(2)],[ipsec(1),ipsec(2),ipsec(3)],[ipsec(1),wg(2),ipsec(3),wg(4)]]){
  const output=P.prepare({...settings,roads});assert.equal(JSON.parse(output.files['controller.json']).paths.length,roads.length);
  assert(!JSON.stringify(output.preview).includes(key));assert(!JSON.stringify(output.preview).includes('a'.repeat(32)));
}
for(const change of ['PostUp = touch /tmp/unsafe','DNS = 1.1.1.1','PresharedKey = '+key]){
  assert.throws(()=>P.prepare({...settings,roads:[{...wg(1),profile:wg(1).profile+'\n'+change}]}),/Unsupported/);
}
assert.throws(()=>P.prepare({...settings,roads:[{...wg(1),profile:wg(1).profile.replace('10.60.0.0/24','0.0.0.0/0')}]}),/AllowedIPs/);
assert.throws(()=>P.prepare({...settings,roads:[wg(1),wg(1)]}),/overlap|Duplicate/);
assert.throws(()=>P.prepare({...settings,appSubnet:'10.60.0.0/24',roads:[wg(1)]}),/overlap/);
assert.throws(()=>P.prepare({...settings,roads:[{...wg(1),profile:wg(1).profile+'\n[Peer]'}]}),/Exactly one/);
for(const secret of [' '+ 'a'.repeat(32), 'a'.repeat(32)+' ', 'a'.repeat(31)]){assert.throws(()=>P.prepare({...settings,roads:[{...ipsec(1),secret}]}),/secret/i);}
console.log('Profile import safety and layout checks passed.');
