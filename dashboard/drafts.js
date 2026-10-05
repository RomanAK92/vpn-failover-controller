'use strict';
// Credential transfer occurs only after this explicit administrator action.
document.getElementById('saveDraft').onclick = async () => {
  const button = document.getElementById('saveDraft');
  button.disabled = true;
  try {
    if(!prepared)throw new Error('Prepare profiles and click Review before saving a draft.');
    const result = await AccountsUI.saveDraft(prepared.files,document.getElementById('draftLabel').value.trim());
    document.getElementById('draftMessage').textContent='Draft saved and checked by the VPN engine. Active tunnels were not changed.';
    document.getElementById('draftList').textContent=JSON.stringify(result,null,2);
  }catch(error){document.getElementById('draftMessage').textContent=error.message;}
  finally{button.disabled=false;}
};
document.getElementById('showDrafts').onclick = async () => {
  try {
    const result = await AccountsUI.listDrafts();
    document.getElementById('draftList').textContent=JSON.stringify(result.drafts,null,2);
    document.getElementById('draftMessage').textContent='These are saved drafts. None has been applied.';
  }catch(error){document.getElementById('draftMessage').textContent=error.message;}
};
