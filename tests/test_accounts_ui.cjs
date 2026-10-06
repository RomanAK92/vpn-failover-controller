'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const elements=new Map();
const get=id=>{if(!elements.has(id))elements.set(id,{value:'',hidden:false,disabled:false,textContent:'',appendChild(){},click(){this.clicked=true;}});return elements.get(id);};
const calls=[],listeners={};let logged=false,failSave=false;
const users=[{username:'admin',role:'admin'}];
const user={username:'admin',role:'admin',csrf:'fixture-csrf-only'};
const context={document:{getElementById:get,createElement:()=>({value:'',textContent:''}),querySelector:()=>get('unlockBox'),addEventListener:(name,callback)=>listeners[name]=callback},Date,console,fetch:async(path,options={})=>{
 calls.push({path,options});
 if(path==='/api/auth')return {ok:true,json:async()=>({mode:'accounts',private_control:true,live_changes_enabled:true,test_apply:false})};
 if(path==='/api/session')return {ok:false,json:async()=>({})};
 if(path==='/api/login'){logged=true;return {ok:true,json:async()=>user};}
 if(path==='/api/accounts'){
  if(options.method==='POST'){
   if(failSave)return {ok:false,status:503,json:async()=>({error:'Management service unavailable. Check status before retrying.'})};
   const data=JSON.parse(options.body);users.push({username:data.username,role:data.role});
   return {ok:true,json:async()=>({username:data.username,role:data.role,reauthenticate:false})};
  }
  return {ok:true,json:async()=>({users})};
 }
 if(path==='/api/security-events')return {ok:true,json:async()=>({events:[]})};
 if(path.startsWith('/api/accounts/')){
  const body=JSON.parse(options.body),action=path.split('/').pop();
  const index=users.findIndex(u=>u.username===body.username);
  if(action==='delete')users.splice(index,1);else users[index].enabled=action==='enable';
  return {ok:true,json:async()=>({username:body.username,action,sessions_revoked:true})};
 }
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
 assert.equal(vm.runInContext('AccountsUI.testApplyEnabled()',context),true);
 assert.equal(vm.runInContext('AccountsUI.canControl()',context),true);
 assert.match(get('usersList').textContent,/admin — Administrator/);
 const login=calls.find(c=>c.path==='/api/login');assert.equal(login.options.credentials,'same-origin');assert.equal(login.options.headers['X-VPN-Request'],'1');
 await listeners.pointerdown();const count=calls.filter(c=>c.path==='/api/activity').length;
 await listeners.keydown();assert.equal(calls.filter(c=>c.path==='/api/activity').length,count);
 const activity=calls.find(c=>c.path==='/api/activity');assert.equal(activity.options.headers['X-CSRF-Token'],user.csrf);
 await get('listUsers').onclick();assert.match(get('usersList').textContent,/admin/);
 get('newUsername').value='test';get('newPassword').value='short';
 await get('saveUser').onclick();assert.match(get('usersMessage').textContent,/15–128/);
 assert.equal(calls.filter(c=>c.path==='/api/accounts'&&c.options.method==='POST').length,0);
 get('newPassword').value='fixture new passphrase';get('currentPassword').value='';
 await get('saveUser').onclick();assert.match(get('usersMessage').textContent,/current administrator passphrase/);
 assert.equal(calls.filter(c=>c.path==='/api/accounts'&&c.options.method==='POST').length,0);
 get('newUsername').value=' operator ';get('newRole').value='viewer';get('newPassword').value='fixture new passphrase';get('currentPassword').value='fixture current passphrase';get('replaceUser').checked=false;await get('saveUser').onclick();
 const save=calls.find(c=>c.path==='/api/accounts'&&c.options.method==='POST');assert.equal(save.options.headers['X-CSRF-Token'],user.csrf);assert.equal(JSON.parse(save.options.body).replace,false);assert.equal(get('newPassword').value,'');assert.equal(get('currentPassword').value,'');
 assert.equal(JSON.parse(save.options.body).username,'operator');
 assert.match(get('usersMessage').textContent,/operator.*created/);
 assert.match(get('usersList').textContent,/operator — Viewer/);
 failSave=true;get('newPassword').value='fixture new passphrase';get('currentPassword').value='fixture current passphrase';
 await get('saveUser').onclick();assert.match(get('usersMessage').textContent,/Management service unavailable/);
 assert.equal(get('saveUser').disabled,false);assert.equal(get('saveUser').textContent,'Save account');
 get('accountActionUser').value='operator';get('accountAction').value='delete';get('accountActionPassword').value='fixture current passphrase';get('accountActionConfirmed').checked=true;get('accountDeleteName').value='wrong';
 await get('runAccountAction').onclick();assert.match(get('accountActionMessage').textContent,/exact account name/);
 assert.ok(!calls.some(c=>c.path==='/api/accounts/delete'));
 get('accountAction').value='disable';get('accountActionPassword').value='fixture current passphrase';get('accountActionConfirmed').checked=true;
 await get('runAccountAction').onclick();assert.match(get('accountActionMessage').textContent,/disabled/);assert.match(get('usersList').textContent,/operator — Viewer — Disabled/);
 get('accountAction').value='enable';get('accountActionPassword').value='fixture current passphrase';get('accountActionConfirmed').checked=true;
 await get('runAccountAction').onclick();assert.match(get('usersList').textContent,/operator — Viewer — Active/);
 get('accountAction').value='delete';get('accountActionPassword').value='fixture current passphrase';get('accountActionConfirmed').checked=true;get('accountDeleteName').value='operator';
 await get('runAccountAction').onclick();assert.match(get('accountActionMessage').textContent,/permanently deleted/);assert.doesNotMatch(get('usersList').textContent,/operator/);
 assert.equal(get('accountActionPassword').value,'');assert.equal(get('accountDeleteName').value,'');assert.equal(get('accountActionConfirmed').checked,false);
 await get('signOut').onclick();assert.equal(logged,false);assert.equal(get('clear').clicked,true);
 assert.equal(vm.runInContext('AccountsUI.canRead()',context),false);
 const logout=calls.find(c=>c.path==='/api/logout');assert.equal(logout.options.headers['X-CSRF-Token'],user.csrf);
 assert.ok(!fs.readFileSync(require.resolve('../dashboard/login.js'),'utf8').match(/localStorage|sessionStorage|document\.cookie/));
 console.log('Login, logout, activity debounce, CSRF and no browser credential persistence passed.');
}
main().catch(e=>{console.error(e);process.exitCode=1;});
