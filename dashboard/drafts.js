'use strict';
// Credential transfer occurs only after this explicit administrator action.
document.getElementById('saveDraft').onclick = async () => {
  const button = document.getElementById('saveDraft');
  button.disabled = true;
  try {
    if(!prepared)throw new Error('Prepare profiles and click Review before saving a draft.');
    const result = await AccountsUI.saveDraft(prepared.files,document.getElementById('draftLabel').value.trim());
    document.getElementById('draftMessage').textContent='Draft saved and checked by the VPN engine. Active tunnels were not changed.';
    document.getElementById('draftList').textContent=(result.label||'Saved draft')+' — '+(result.paths?.length||0)+' roads. Private saved copy; active settings were not changed.';
  }catch(error){document.getElementById('draftMessage').textContent=error.message;}
  finally{button.disabled=false;}
};
document.getElementById('showDrafts').onclick = async () => {
  try {
    const result = await AccountsUI.listDrafts();
    document.getElementById('draftList').textContent=result.drafts.map(d=>(d.label||'Saved draft')+' — '+(d.paths?.map(p=>p.name+' ('+p.kind+')').join(', ')||'saved settings')).join('\n')||'No saved drafts yet.';
    document.getElementById('draftMessage').textContent='These are saved drafts. None has been applied.';
  }catch(error){document.getElementById('draftMessage').textContent=error.message;}
};
