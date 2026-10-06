'use strict';
const AccountsUI = (() => {
  let mode = 'local', user = null, lastActivity = 0, draftsEnabled = false, controlEnabled = false, testApply = false;
  const element = id => document.getElementById(id);
  function accountMessage(message) {
    element('usersMessage').textContent=message;
  }
  async function loadAccounts() {
    if(!user||user.role!=='admin')return;
    const response=await fetch('/api/accounts',{cache:'no-store',credentials:'same-origin'});
    if(response.status===401)forgetSession('Session expired. Sign in again.');
    if(!response.ok)throw new Error('Could not load accounts. Sign in as administrator and refresh accounts.');
    const accounts=(await response.json()).users;
    element('usersList').textContent=accounts.length?accounts.map(u=>u.username+' — '+(u.role==='admin'?'Administrator':'Viewer')+' — '+(u.enabled===false?'Disabled':'Active')).join('\n'):'No accounts to display.';
    const selected=element('accountActionUser').value;
    element('accountActionUser').textContent='';
    for(const account of [{username:'',label:'Choose an account'},...accounts]){
      const option=document.createElement('option');option.value=account.username;option.textContent=account.label||account.username;
      element('accountActionUser').appendChild(option);
    }
    element('accountActionUser').value=accounts.some(a=>a.username===selected)?selected:'';
  }
  function forgetSession(message) {
    user=null;render(message);element('clear').click();
  }
  function render(message = '') {
    element('accountPanel').hidden = mode !== 'accounts' && mode !== 'unavailable';
    element('loginFields').hidden = !!user;
    element('signOut').hidden = !user;
    element('usersPanel').hidden = !user || user.role !== 'admin';
    if(element('draftPanel'))element('draftPanel').hidden = !draftsEnabled || !user || user.role !== 'admin';
    if(element('managementPanel'))element('managementPanel').hidden = !controlEnabled || !user || user.role !== 'admin';
    if(!user&&element('managementPassword')){element('managementPassword').value='';element('managementStatus').textContent='';element('generationId').value='';element('managedDraft').textContent='';}
    if(!user&&element('liveActionPassword'))element('liveActionPassword').value='';
    if(!user&&element('operationPassword'))element('operationPassword').value='';
    if(!user&&element('draftList'))element('draftList').textContent='';
    if(!user&&element('draftArchivePassword'))element('draftArchivePassword').value='';
    if(!user){element('usersList').textContent='';element('securityEvents').textContent='';element('usersMessage').textContent='';element('newPassword').value='';element('currentPassword').value='';}
    if(!user){element('accountActionPassword').value='';element('accountActionUser').textContent='';element('accountDeleteName').value='';element('accountActionConfirmed').checked=false;element('accountActionMessage').textContent='';}
    element('accountStatus').textContent = message || (user ? 'Signed in as '+user.username+' ('+user.role+').' : 'Sign in to view this server.');
    document.querySelector('.unlock').hidden = mode === 'accounts';
  }
  async function request(path, body) {
    const response = await fetch(path, {method:'POST',credentials:'same-origin',cache:'no-store',headers:{'Content-Type':'application/json','X-VPN-Request':'1',...(user?{'X-CSRF-Token':user.csrf}:{})},body:JSON.stringify(body)});
    const data = await response.json();
    if(response.status===401 && path!=='/api/login'){
      let sessionValid=false;
      if(user&&Object.prototype.hasOwnProperty.call(body,'current_password')){
        try{
          const check=await fetch('/api/session',{credentials:'same-origin',cache:'no-store'});
          if(check.ok){const current=await check.json();sessionValid=current.username===user.username&&current.csrf===user.csrf&&current.role===user.role;}
        }catch(_){/* An unverifiable session must not retain administrative controls. */}
      }
      if(sessionValid)throw new Error('Administrator passphrase was not accepted. No action was performed. Re-enter your current passphrase and try again.');
      forgetSession('Session expired or unavailable. Sign in again.');
    }
    if (!response.ok) throw new Error(data.error || 'Request failed.');
    return data;
  }
  const ready = (async () => {
    try {
      const info = await fetch('/api/auth',{cache:'no-store'});
      if (!info.ok) throw new Error();
      const features = await info.json(); mode = features.mode; draftsEnabled = features.drafts === true;
      controlEnabled = features.private_control === true; testApply = features.live_changes_enabled === true || features.test_apply === true;
      if (mode === 'accounts') {
        const response = await fetch('/api/session',{credentials:'same-origin',cache:'no-store'});
        if (response.ok) user = await response.json();
      }
      render();
      if(user&&user.role==='admin')try{await loadAccounts();}catch(error){accountMessage(error.message);}
    } catch (_) {mode='unavailable';render('Authentication service unavailable.');}
  })();
  element('signIn').onclick = async () => {
    element('signIn').disabled = true;
    try {user = await request('/api/login',{username:element('username').value,password:element('password').value});render();if(user.role==='admin')try{await loadAccounts();}catch(error){accountMessage(error.message);}if(typeof refresh==='function')await refresh();}
    catch (error) {user=null;render(error.message);}
    finally {element('password').value='';element('signIn').disabled=false;}
  };
  element('signOut').onclick = async () => {
    try {await request('/api/logout',{});user=null;render('Signed out.');element('clear').click();if(typeof refresh==='function')await refresh();}
    catch (error) {render(error.message);}
  };
  element('listUsers').onclick = async () => {
    try {
      await loadAccounts();
      const security = await fetch('/api/security-events',{cache:'no-store',credentials:'same-origin'});
      if(!security.ok)throw new Error('Could not load security events. Administrator session required.');
      element('securityEvents').textContent=(await security.json()).events.map(e=>new Date(e.time*1000).toLocaleString()+' — '+e.event+(e.username?' — '+e.username:'')).join('\n');
    }catch(error){element('usersMessage').textContent=error.message;}
  };
  element('saveUser').onclick = async () => {
    element('saveUser').disabled=true;
    element('saveUser').textContent='Saving…';
    accountMessage('Checking account details…');
    try {
      element('newUsername').value=element('newUsername').value.trim();
      if(!/^[a-z][a-z0-9_.-]{2,31}$/.test(element('newUsername').value))throw new Error('Use 3–32 lowercase letters, numbers, dots, underscores or hyphens, starting with a letter.');
      if(element('newPassword').value.length<15||element('newPassword').value.length>128)throw new Error('Use a new passphrase of 15–128 characters.');
      if(!element('currentPassword').value)throw new Error('Enter your current administrator passphrase to authorize saving this account.');
      const result=await request('/api/accounts',{username:element('newUsername').value,role:element('newRole').value,password:element('newPassword').value,current_password:element('currentPassword').value,replace:element('replaceUser').checked});
      accountMessage('Account “'+result.username+'” '+(element('replaceUser').checked?'reset. Previous sessions were revoked.':'created. It is listed above.'));
      if(!result.reauthenticate)try{await loadAccounts();}catch(error){accountMessage('Account saved, but the list could not refresh. Use Refresh accounts and security events.');}
      if(result.reauthenticate){user=null;render('Your account changed. Sign in again.');element('clear').click();if(typeof refresh==='function')await refresh();}
    }catch(error){element('usersMessage').textContent=error.message;}
    finally{element('newPassword').value='';element('currentPassword').value='';element('saveUser').disabled=false;element('saveUser').textContent='Save account';}
  };
  element('runAccountAction').onclick=async()=>{
    const button=element('runAccountAction');button.disabled=true;
    element('accountActionMessage').textContent='Checking the account action…';
    try{
      const username=element('accountActionUser').value, action=element('accountAction').value;
      if(!username)throw new Error('Choose the account you want to change.');
      if(!['disable','enable','delete'].includes(action))throw new Error('Choose an account action.');
      if(!element('accountActionConfirmed').checked)throw new Error('Tick the confirmation box before continuing.');
      if(!element('accountActionPassword').value)throw new Error('Enter your current administrator passphrase.');
      if(action==='delete'&&element('accountDeleteName').value!==username)throw new Error('Type the exact account name to confirm permanent deletion.');
      const result=await request('/api/accounts/'+action,{username,current_password:element('accountActionPassword').value,confirmed:true,confirmation:element('accountDeleteName').value});
      element('accountActionMessage').textContent='Account “'+result.username+'” '+({disable:'disabled',enable:'enabled',delete:'permanently deleted'}[action])+'. All previous sessions were revoked.';
      try{await loadAccounts();}catch(error){element('accountActionMessage').textContent+=' The list could not refresh; use Refresh accounts and security events.';}
    }catch(error){element('accountActionMessage').textContent=error.message;}
    finally{element('accountActionPassword').value='';element('accountDeleteName').value='';element('accountActionConfirmed').checked=false;button.disabled=false;}
  };
  async function activity() {
    if (!user || Date.now()-lastActivity<60000) return;
    lastActivity=Date.now();
    try {await request('/api/activity',{});}catch (_) {forgetSession('Session expired. Sign in again.');}
  }
  document.addEventListener('pointerdown',activity);
  document.addEventListener('keydown',activity);
  return {ready,canRead:()=>mode!=='accounts'&&mode!=='unavailable'||!!user,
    canControl:()=>controlEnabled&&!!user&&user.role==='admin',
    testApplyEnabled:()=>testApply,
    control:async(action,body)=>{if(!controlEnabled||!user||user.role!=='admin')throw new Error('Administrator access required.');return request('/api/control/'+action,body);},
    controlStatus:async()=>{if(!controlEnabled||!user||user.role!=='admin')throw new Error('Administrator access required.');const response=await fetch('/api/control/status',{credentials:'same-origin',cache:'no-store'});if(response.status===401)forgetSession('Session expired. Sign in again.');if(!response.ok)throw new Error('Private engine status unavailable.');return response.json();},
    canManageDrafts:()=>draftsEnabled&&!!user&&user.role==='admin',
    saveDraft:async(files,label)=>{if(!draftsEnabled||!user||user.role!=='admin')throw new Error('Sign in as administrator on a draft-enabled installation.');return request('/api/drafts',{files,label});},
    listDrafts:async()=>{if(!draftsEnabled||!user||user.role!=='admin')throw new Error('Administrator access required.');const response=await fetch('/api/drafts',{credentials:'same-origin',cache:'no-store'});if(!response.ok)throw new Error('Draft list unavailable.');return response.json();},
    archiveDraft:async(action,id,password)=>{if(!draftsEnabled||!user||user.role!=='admin'||!['archive','restore'].includes(action))throw new Error('Administrator access required.');return request('/api/drafts/'+action,{id,current_password:password});},
    expired:()=>{user=null;render('Session expired. Sign in again.');element('clear').click();}};
})();
