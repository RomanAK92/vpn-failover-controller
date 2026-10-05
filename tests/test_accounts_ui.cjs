'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const elements=new Map();
const get=id=>{if(!elements.has(id))elements.set(id,{value:'',hidden:false,disabled:false,textContent:'',click(){this.clicked=true;}});return elements.get(id);};
const calls=[],listeners={};let logged=false;
const user={username:'admin',role:'admin',csrf:'fixture-csrf-only'};
const context={document:{getElementById:get,querySelector:()=>get('unlockBox'),addEventListener:(name,callback)=>listeners[name]=callback},Date,console,fetch:async(path,options={})=>{
 calls.push({path,options});
 if(path==='/api/auth')return {ok:true,json:async()=>({mode:'accounts'})};
 if(path==='/api/session')return {ok:false,json:async()=>({})};
 if(path==='/api/login'){logged=true;return {ok:true,json:async()=>user};}
 if(path==='/api/logout'){logged=false;return {ok:true,json:async()=>({logged_out:true})};}
 return {ok:true,json:async()=>user};
},refresh:async()=>{}};
vm.createContext(context);vm.runInContext(fs.readFileSync(require.resolve('../dashboard/login.js'),'utf8'),context);
async function main(){
 await vm.runInContext('AccountsUI.ready',context);
 assert.equal(get('accountPanel').hidden,false);assert.equal(get('unlockBox').hidden,true);
 assert.equal(vm.runInContext('AccountsUI.canRead()',context),false);
 get('username').value='admin';get('password').value='fixture passphrase';await get('signIn').onclick();
 assert.equal(get('password').value,'');assert.equal(get('loginFields').hidden,true);
 assert.equal(vm.runInContext('AccountsUI.canRead()',context),true);
 const login=calls.find(c=>c.path==='/api/login');assert.equal(login.options.credentials,'same-origin');assert.equal(login.options.headers['X-VPN-Request'],'1');
 await listeners.pointerdown();const count=calls.filter(c=>c.path==='/api/activity').length;
 await listeners.keydown();assert.equal(calls.filter(c=>c.path==='/api/activity').length,count);
 const activity=calls.find(c=>c.path==='/api/activity');assert.equal(activity.options.headers['X-CSRF-Token'],user.csrf);
 await get('signOut').onclick();assert.equal(logged,false);assert.equal(get('clear').clicked,true);
 assert.equal(vm.runInContext('AccountsUI.canRead()',context),false);
 const logout=calls.find(c=>c.path==='/api/logout');assert.equal(logout.options.headers['X-CSRF-Token'],user.csrf);
 assert.ok(!fs.readFileSync(require.resolve('../dashboard/login.js'),'utf8').match(/localStorage|sessionStorage|document\.cookie/));
 console.log('Login, logout, activity debounce, CSRF and no browser credential persistence passed.');
}
main().catch(e=>{console.error(e);process.exitCode=1;});
