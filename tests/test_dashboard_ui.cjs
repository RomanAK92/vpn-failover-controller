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
  get('addWg').onclick();const card=get('profileList').children[0];const fileInput=card.querySelectorAll('input,textarea').find(e=>e.type==='file');const area=card.querySelectorAll('[data-field]')[0];
  area.value='old profile';get('review').onclick();assert.equal(get('download').disabled,false);
  fileInput.files=[{size:16385,text:async()=>{throw Error('Must not read oversized file');}}];await fileInput.onchange();
  assert.equal(get('download').disabled,true);assert.equal(area.value,'');assert.match(get('preview').textContent,/too large/);
  let finish;const slow={size:100,text:()=>new Promise(resolve=>finish=resolve)};fileInput.files=[slow];const pending=fileInput.onchange();
  fileInput.files=[{size:100,text:async()=>'new profile'}];await fileInput.onchange();finish('old slow profile');await pending;
  assert.equal(area.value,'new profile');assert.equal(get('download').disabled,true);
  fileInput.files=[slow];const removed=fileInput.onchange();card.isConnected=false;finish('removed profile');await removed;assert.equal(area.value,'');
  get('clear').onclick();get('addIpsec').onclick();const secret=get('profileList').children[0].querySelectorAll('[data-field]').find(e=>e.dataset.field==='secret');secret.value=' leading and trailing ';get('review').onclick();
  assert.match(get('preview').textContent,/ leading and trailing /);
  console.log('Dashboard import invalidation, asynchronous races and secret preservation passed.');
}
main().catch(e=>{console.error(e);process.exitCode=1;});
