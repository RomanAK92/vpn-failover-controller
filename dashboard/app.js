'use strict';
const $=id=>document.getElementById(id);
let latest=null, prepared=null, roads=[];
function node(tag, content, cls){const el=document.createElement(tag);if(content!==undefined)el.textContent=content;if(cls)el.className=cls;return el;}
function invalidate(){prepared=null;$('download').disabled=true;$('preview').textContent='Settings changed. Validate again before downloading.';}
function tab(which){$('monitor').hidden=which!=='monitor';$('setup').hidden=which!=='setup';$('monitorTab').classList.toggle('selected',which==='monitor');$('setupTab').classList.toggle('selected',which==='setup');}
$('monitorTab').onclick=()=>tab('monitor');$('setupTab').onclick=()=>tab('setup');
function show(state){
  latest=state;const available=state.available===true;
  $('overall').textContent=available?(state.active?'Private network connected':'No working road'):'Monitoring unavailable';
  $('overall').className='badge '+(available&&state.active?'good':'bad');
  $('statusMessage').textContent=state.message||(available?'Updated '+state.age_seconds+' seconds ago. Public internet uses its existing route.':'Status is stale or supervision failed. Showing last-known values only.');
  $('roads').replaceChildren();
  for(const [i,p] of (state.paths||[]).entries()){
    const card=node('article',undefined,'road');card.append(node('small','PRIORITY '+(i+1)),node('h2',p.name));
    const classification=!available?'Unknown':p.name===state.active?'Active':p.healthy?'Ready / standby':'Probe failing';
    card.append(node('span',classification,'badge '+(available&&p.healthy?'good':'bad')),node('p',p.kind==='wireguard'?'WireGuard':'IPsec'));
    const list=node('ul');for(const [target,ok] of Object.entries(p.probes))list.append(node('li',target+' — '+(!available?'last known: ':'')+(ok?'answered':'no answer')));card.append(list);
    if(available){const settings=state.settings;const rounds=p.healthy?Math.max(0,settings.recovery_rounds-p.recovery_rounds):Math.max(0,settings.failure_rounds-p.failed_rounds);card.append(node('p',p.name===state.active&&p.healthy?'This road carries selected office traffic.':p.healthy?'Recovery stability: '+rounds+' healthy rounds remaining.':'Failure threshold: '+rounds+' failed rounds remaining.'));}
    $('roads').append(card);
  }
  const selected=$('filter').value;const options=(state.paths||[]).map(p=>p.name);
  $('filter').replaceChildren(new Option('Every road',''),...options.map(n=>new Option(n,n)));if(options.includes(selected))$('filter').value=selected;
  showEvents();
}
function showEvents(){const path=$('filter').value;$('events').replaceChildren();for(const event of (latest?.events||[]).filter(e=>!path||e.path===path||e.path===null)){const li=node('li');li.append(node('time',new Date(event.time*1000).toLocaleString()),node('span',event.message));$('events').append(li);}if(!$('events').children.length)$('events').append(node('li','No recorded events yet.'));}
$('filter').onchange=showEvents;
async function refresh(){try{const token=$('token').value;const response=await fetch('/api/status',{headers:token?{Authorization:'Bearer '+token}:{},cache:'no-store'});if(!response.ok)throw new Error(response.status===401?'Unlock with the dashboard access token.':'Status service unavailable.');show(await response.json());}catch(e){show({available:false,paths:[],message:e.message,events:latest?.events||[]});}}
$('unlock').onclick=refresh;refresh();setInterval(refresh,5000);
function field(label,key,type='text',placeholder=''){const wrap=node('label',label);const input=node('input');input.type=type;input.placeholder=placeholder;input.autocomplete='off';input.dataset.field=key;input.oninput=invalidate;wrap.append(input);return wrap;}
function renderRoads(){
  const list=$('profileList');list.replaceChildren();
  roads.forEach((road,i)=>{
    const card=road.card;card.querySelector('h3').textContent=(i+1)+'. '+(road.kind==='wireguard'?'WireGuard profile':'IPsec settings');
    const controls=card.querySelector('.controls');controls.replaceChildren();
    for(const [label,offset] of [['↑ Higher priority',-1],['↓ Lower priority',1]]){const button=node('button',label);button.disabled=i+offset<0||i+offset>=roads.length;button.onclick=()=>{[roads[i],roads[i+offset]]=[roads[i+offset],roads[i]];invalidate();renderRoads();};controls.append(button);}
    const remove=node('button','Remove');remove.onclick=()=>{for(const input of card.querySelectorAll('input,textarea'))input.value='';roads.splice(i,1);invalidate();renderRoads();};controls.append(remove);list.append(card);
  });
  $('addWg').disabled=$('addIpsec').disabled=roads.length>=4;
}
function addRoad(kind){
  if(roads.length>=4)return;const card=node('section',undefined,'panel');card.append(node('h3'));
  if(kind==='wireguard'){
    const label=node('label','Choose a .conf file (read locally)');const input=node('input');input.type='file';input.accept='.conf,text/plain';const area=node('textarea');area.dataset.field='profile';area.placeholder='Paste the complete WireGuard profile here';area.spellcheck=false;area.oninput=invalidate;
    input.onchange=async()=>{if(input.files[0]){if(input.files[0].size>16384){$('preview').textContent='Profile is too large (limit 16 KiB).';return;}area.value=await input.files[0].text();invalidate();}};label.append(input);card.append(label,area,node('p','Exactly one peer, one IPv4 address and the office prefix in AllowedIPs. DNS changes, scripts, IPv6 and WireGuard preshared keys are unsupported and rejected.'));
  }else{
    const fields=node('div',undefined,'fields');fields.append(field('Gateway IPv4','endpoint','text','203.0.113.10'),field('Client tunnel address','address','text','10.251.'+(roads.length+1)+'.2/32'),field('Our identity','localId','text','vpn-client-1'),field('Gateway identity','remoteId','text','vpn-gateway-1'),field('Shared secret','secret','password','32–256 characters, no spaces'));card.append(fields,node('p','IKEv2 with a shared secret. Proposals: aes256-sha256-modp2048 / aes256-sha256. Certificates, EAP and other proposals need manual advanced configuration; this wizard does not import them.'));
  }
  card.append(node('div',undefined,'controls'));roads.push({kind,card});invalidate();renderRoads();
}
$('addWg').onclick=()=>addRoad('wireguard');$('addIpsec').onclick=()=>addRoad('ipsec');
for(const id of ['subnet','targets','appSubnet'])$(id).oninput=invalidate;
$('review').onclick=()=>{invalidate();try{prepared=Profiles.prepare({subnet:$('subnet').value.trim(),targets:$('targets').value,appSubnet:$('appSubnet').value.trim(),roads:roads.map(r=>({kind:r.kind,...Object.fromEntries(Array.from(r.card.querySelectorAll('[data-field]')).map(e=>[e.dataset.field,e.value.trim()]))}))});$('preview').textContent='Validated locally. Secrets are hidden below. Review addresses and priority; gateway/host checks are still required.\n\n'+JSON.stringify(prepared.preview,null,2);$('download').disabled=false;}catch(e){$('preview').textContent=e.message;}};
$('download').onclick=()=>{if(!prepared)return;const url=URL.createObjectURL(Profiles.archive(prepared.files));const anchor=node('a');anchor.href=url;anchor.download='vpn-private-config.tar';anchor.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
$('clear').onclick=()=>{for(const road of roads)for(const input of road.card.querySelectorAll('input,textarea'))input.value='';roads=[];renderRoads();invalidate();$('preview').textContent='Profile secrets cleared from this page. Previously downloaded files still exist on your computer.';};
