'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const elements=new Map(),calls=[];
const el=id=>{if(!elements.has(id))elements.set(id,{value:'',textContent:'',disabled:false,append(){}});return elements.get(id);};
let allowed=true,status={ready:true,live_apply_enabled:true,running_generation:'a'.repeat(32),selected_generation:'a'.repeat(32),transaction:{change:null}};
let refresh;
const context={document:{getElementById:el,createElement:()=>({}),addEventListener(){}},setInterval:f=>refresh=f,JSON,
 AccountsUI:{ready:Promise.resolve(),canControl:()=>allowed,testApplyEnabled:()=>true,
 controlStatus:async()=>status,listDrafts:async()=>({drafts:[]}),control:async(action,data)=>{
 calls.push({action,data});return action==='preview'?{live_footprint_compatible:true}:action==='prepare'?{id:'b'.repeat(32)}:{phase:'pending'};
 }}};
vm.createContext(context);vm.runInContext(fs.readFileSync(require.resolve('../dashboard/management.js'),'utf8'),context);
async function main(){
 await new Promise(r=>setImmediate(r));
 status.prepared=[{id:'b'.repeat(32),label:'My revised priority'}];await refresh();
 el('preparedGeneration').value='b'.repeat(32);el('preparedGeneration').onchange();
 assert.equal(el('generationId').value,'b'.repeat(32));assert.equal(el('applyGeneration').disabled,true);
 el('generationId').value='b'.repeat(32);await el('previewGeneration').onclick();
 assert.equal(el('applyGeneration').disabled,false);
 el('managementPassword').value='fixture-only-secret';await el('applyGeneration').onclick();
 assert.equal(calls.at(-1).data.current_password,'fixture-only-secret');assert.equal(el('managementPassword').value,'');
 assert.equal(calls.at(-1).data.timeout,180);
 status.transaction.change={id:'c'.repeat(32),phase:'pending',candidate:'b'.repeat(32)};status.confirmation_seconds_remaining=80;
 await refresh();assert.equal(el('confirmGeneration').disabled,true);
 status.running_generation='b'.repeat(32);await refresh();assert.equal(el('confirmGeneration').disabled,false);
 const before=calls.length;await el('confirmGeneration').onclick();assert.equal(calls.length,before);
 assert.match(el('managementMessage').textContent,/passphrase again/);
 el('managementPassword').value='fixture-confirm-secret';await el('confirmGeneration').onclick();
 assert.equal(calls.at(-1).action,'confirm');assert.equal(el('managementPassword').value,'');
 status.confirmation_seconds_remaining=0;await refresh();assert.equal(el('confirmGeneration').disabled,true);
 status.storage_fault=true;status.live_apply_enabled=false;await refresh();assert.equal(el('revertGeneration').disabled,true);
 assert.match(el('managementStatus').textContent,/database recovery is not acknowledged/);
 allowed=false;el('managementPassword').value='private';await refresh();assert.equal(el('managementPassword').value,'');assert.equal(el('managementStatus').textContent,'');
 assert.ok(!fs.readFileSync(require.resolve('../dashboard/management.js'),'utf8').match(/localStorage|sessionStorage|innerHTML|document\.cookie/));
 console.log('Management UI gates, expiry, readiness, storage lockout and secret clearing passed.');
}
main().catch(e=>{console.error(e);process.exitCode=1;});
