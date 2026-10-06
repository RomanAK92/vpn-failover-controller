'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const elements=new Map(),calls=[];
const get=id=>{if(!elements.has(id))elements.set(id,{value:'',disabled:false,textContent:'',append(){}});return elements.get(id);};
const context={document:{getElementById:get,createElement:()=>({})},prepared:null,AccountsUI:{
  saveDraft:async(files,label)=>{calls.push({files,label});return {id:'fixture',state:'draft',applied:false};},
  listDrafts:async()=>({drafts:[{id:'fixture',state:'draft',applied:false}]}),
  archiveDraft:async(action,id,password)=>{calls.push({action,id,password});return {state:'archived',applied:false};}}};
vm.createContext(context);vm.runInContext(fs.readFileSync(require.resolve('../dashboard/drafts.js'),'utf8'),context);
async function main(){
  get('draftLabel').value='Office connection';
  assert.equal(calls.length,0);
  await get('saveDraft').onclick();assert.equal(calls.length,0);assert.match(get('draftMessage').textContent,/click Review/);
  context.prepared={files:{'wg-client-peer-1.key':'synthetic fixture only'}};
  await get('saveDraft').onclick();assert.equal(calls.length,1);assert.equal(calls[0].files,context.prepared.files);
  assert.equal(calls[0].label,'Office connection');assert.equal(get('saveDraft').disabled,false);
  assert.match(get('draftMessage').textContent,/Active tunnels were not changed/);
  assert.doesNotMatch(get('draftList').textContent,/synthetic fixture only/);
  await get('showDrafts').onclick();assert.match(get('draftMessage').textContent,/None has been applied/);
  get('draftArchiveChoice').value='archived:fixture';await get('archiveDraft').onclick();assert.equal(calls.length,1);
  get('draftArchiveChoice').value='saved:fixture';get('draftArchivePassword').value='synthetic only';await get('archiveDraft').onclick();
  assert.equal(calls.at(-1).action,'archive');assert.equal(get('draftArchivePassword').value,'');
  assert.match(get('draftMessage').textContent,/traffic was not changed/);
  assert.ok(!fs.readFileSync(require.resolve('../dashboard/drafts.js'),'utf8').match(/localStorage|sessionStorage/));
  console.log('Drafts transfer only after review and explicit save; no live apply or key summary.');
}
main().catch(e=>{console.error(e);process.exitCode=1;});
