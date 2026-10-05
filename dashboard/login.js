'use strict';
const AccountsUI = (() => {
  let mode = 'local', user = null, lastActivity = 0;
  const element = id => document.getElementById(id);
  function render(message = '') {
    element('accountPanel').hidden = mode !== 'accounts' && mode !== 'unavailable';
    element('loginFields').hidden = !!user;
    element('signOut').hidden = !user;
    element('accountStatus').textContent = message || (user ? 'Signed in as '+user.username+' ('+user.role+').' : 'Sign in to view this server.');
    document.querySelector('.unlock').hidden = mode === 'accounts';
  }
  async function request(path, body) {
    const response = await fetch(path, {method:'POST',credentials:'same-origin',cache:'no-store',headers:{'Content-Type':'application/json','X-VPN-Request':'1',...(user?{'X-CSRF-Token':user.csrf}:{})},body:JSON.stringify(body)});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Request failed.');
    return data;
  }
  const ready = (async () => {
    try {
      const info = await fetch('/api/auth',{cache:'no-store'});
      if (!info.ok) throw new Error();
      mode = (await info.json()).mode;
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
  async function activity() {
    if (!user || Date.now()-lastActivity<60000) return;
    lastActivity=Date.now();
    try {await request('/api/activity',{});}catch (_) {user=null;render('Session expired. Sign in again.');}
  }
  document.addEventListener('pointerdown',activity);
  document.addEventListener('keydown',activity);
  return {ready,canRead:()=>mode!=='accounts'&&mode!=='unavailable'||!!user,expired:()=>{user=null;render('Session expired. Sign in again.');}};
})();
