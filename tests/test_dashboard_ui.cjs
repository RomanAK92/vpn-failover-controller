const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
class Element {
  constructor(tag='div'){this.tag=tag;this.children=[];this.dataset={};this.value='';this.disabled=false;this.isConnected=true;this.classList={toggle(){}};}
  append(...items){this.children.push(...items);}
  replaceChildren(...items){this.children=items;}
  querySelector(selector){return this.querySelectorAll(selector)[0];}
  querySelectorAll(selector){return this.children.flatMap(c=>[c,...(c.querySelectorAll?.(selector)||[])]).filter(c=>selector==='[data-field]'?c.dataset?.field:selector==='input,textarea'?['input','textarea'].includes(c.tag):selector==='h3'?c.tag==='h3':selector==='.controls'?c.className==='controls':false);}
}
const ids=new Map();const get=id=>{if(!ids.has(id))ids.set(id,new Element());return ids.get(id);};
const context={document:{getElementById:get,createElement:tag=>new Element(tag)},Option:class extends Element {},setInterval(){},setTimeout(){},URL:{},fetch:async()=>({ok:true,json:async()=>({available:false,paths:[],events:[]})}),Profiles:{prepare:input=>({files:{},preview:input}),archive(){}},console};
vm.createContext(context);vm.runInContext(fs.readFileSync(require.resolve('../dashboard/app.js'),'utf8'),context);
async function main(){
  const status={available:true,active:'road-1',paths:[{name:'road-1',kind:'wireguard',healthy:false,probes:{},failed_rounds:1,recovery_rounds:0}],settings:{failure_rounds:8,recovery_rounds:30},events:[]};
  context.show(status);assert.match(get('overall').className,/bad/);assert.match(get('overall').textContent,/probe failing/);
  context.show({...status,available:false,paths:[{...status.paths[0],healthy:true}]});assert.match(get('overall').className,/bad/);assert.equal(get('overall').textContent,'Monitoring unavailable');
  get('addWg').onclick();const card=get('profileList').children[0];const fileInput=card.querySelectorAll('input,textarea').find(e=>e.type==='file');const area=card.querySelectorAll('[data-field]')[0];
  area.value='old profile';get('review').onclick();assert.equal(get('download').disabled,false);assert.match(get('validationStatus').textContent,/✓ Configuration valid/);
  fileInput.files=[{size:16385,text:async()=>{throw Error('Must not read oversized file');}}];await fileInput.onchange();
  assert.equal(get('download').disabled,true);assert.equal(area.value,'');assert.match(get('preview').textContent,/too large/);assert.match(get('validationStatus').textContent,/✕/);
  let finish;const slow={size:100,text:()=>new Promise(resolve=>finish=resolve)};fileInput.files=[slow];const pending=fileInput.onchange();
  fileInput.files=[{size:100,text:async()=>'new profile'}];await fileInput.onchange();finish('old slow profile');await pending;
  assert.equal(area.value,'new profile');assert.equal(get('download').disabled,true);assert.match(get('validationStatus').textContent,/Not checked/);
  fileInput.files=[slow];const removed=fileInput.onchange();card.isConnected=false;finish('removed profile');await removed;assert.equal(area.value,'');
  get('clear').onclick();get('addIpsec').onclick();const secret=get('profileList').children[0].querySelectorAll('[data-field]').find(e=>e.dataset.field==='secret');secret.value=' leading and trailing ';get('review').onclick();
  assert.match(get('preview').textContent,/ leading and trailing /);
  const prepare=context.Profiles.prepare;context.Profiles.prepare=()=>{throw Error('Unsupported WireGuard setting PostUp');};get('review').onclick();assert.equal(get('download').disabled,true);assert.match(get('validationStatus').textContent,/✕/);assert.match(get('preview').textContent,/PostUp/);context.Profiles.prepare=prepare;
  console.log('Dashboard stale/failing status, import invalidation, asynchronous races and secret preservation passed.');
}
main().catch(e=>{console.error(e);process.exitCode=1;});
