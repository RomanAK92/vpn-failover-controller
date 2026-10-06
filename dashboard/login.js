'use strict';
const AccountsUI = (() => {
  let mode = 'local', user = null, lastActivity = 0, draftsEnabled = false, controlEnabled = false, testApply = false;
  const element = id => document.getElementById(id);
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
    if(!user&&element('draftList'))element('draftList').textContent='';
    if(!user){element('usersList').textContent='';element('securityEvents').textContent='';element('newPassword').value='';element('currentPassword').value='';}
    element('accountStatus').textContent = message || (user ? 'Signed in as '+user.username+' ('+user.role+').' : 'Sign in to view this server.');
    document.querySelector('.unlock').hidden = mode === 'accounts';
  }
  async function request(path, body) {
    const response = await fetch(path, {method:'POST',credentials:'same-origin',cache:'no-store',headers:{'Content-Type':'application/json','X-VPN-Request':'1',...(user?{'X-CSRF-Token':user.csrf}:{})},body:JSON.stringify(body)});
    const data = await response.json();
    if (response.status===401 && path!=='/api/login')forgetSession('Session expired. Sign in again.');
    if (!response.ok) throw new Error(data.error || 'Request failed.');
    return data;
  }
  const ready = (async () => {
    try {
      const info = await fetch('/api/auth',{cache:'no-store'});
      if (!info.ok) throw new Error();
      const features = await info.json(); mode = features.mode; draftsEnabled = features.drafts === true;
      controlEnabled = features.private_control === true; testApply = features.test_apply === true;
      if (mode === 'accounts') {
        const response = await fetch('/api/session',{credentials:'same-origin',cache:'no-store'});
        if (response.ok) user = await response.json();
      }
      render();
    } catch (_) {mode='unavailable';render('Authentication service unavailable.');}
  })();
  element('signIn').onclick = async () => {
    element('signIn').disabled = true;
    try {user = await request('/api/login',{username:element('username').value,password:element('password').value});render();if(typeof refresh==='function')await refresh();}
    catch (error) {user=null;render(error.message);}
    finally {element('password').value='';element('signIn').disabled=false;}
  };
  element('signOut').onclick = async () => {
    try {await request('/api/logout',{});user=null;render('Signed out.');element('clear').click();if(typeof refresh==='function')await refresh();}
    catch (error) {render(error.message);}
  };
  element('listUsers').onclick = async () => {
    try {
      const accounts = await fetch('/api/accounts',{cache:'no-store',credentials:'same-origin'});
      const security = await fetch('/api/security-events',{cache:'no-store',credentials:'same-origin'});
      if(!accounts.ok||!security.ok)throw new Error('Administrator session required.');
      element('usersList').textContent=(await accounts.json()).users.map(u=>u.username+' — '+u.role).join('\n');
      element('securityEvents').textContent=(await security.json()).events.map(e=>new Date(e.time*1000).toLocaleString()+' — '+e.event+(e.username?' — '+e.username:'')).join('\n');
    }catch(error){element('usersMessage').textContent=error.message;}
  };
  element('saveUser').onclick = async () => {
    element('saveUser').disabled=true;
    try {
      if(!/^[a-z][a-z0-9_.-]{2,31}$/.test(element('newUsername').value))throw new Error('Use 3–32 lowercase letters, numbers, dots, underscores or hyphens, starting with a letter.');
      if(element('newPassword').value.length<15||element('newPassword').value.length>128)throw new Error('Use a new passphrase of 15–128 characters.');
      const result=await request('/api/accounts',{username:element('newUsername').value,role:element('newRole').value,password:element('newPassword').value,current_password:element('currentPassword').value,replace:element('replaceUser').checked});
      element('usersMessage').textContent='Account saved. Previous sessions were revoked if this was a reset.';
      if(result.reauthenticate){user=null;render('Your account changed. Sign in again.');element('clear').click();if(typeof refresh==='function')await refresh();}
    }catch(error){element('usersMessage').textContent=error.message;}
    finally{element('newPassword').value='';element('currentPassword').value='';element('saveUser').disabled=false;}
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
    expired:()=>{user=null;render('Session expired. Sign in again.');element('clear').click();}};
})();
