'use strict';
// Credential transfer occurs only after this explicit administrator action.
document.getElementById('saveDraft').onclick = async () => {
  const button = document.getElementById('saveDraft');
  button.disabled = true;document.getElementById('continueDraft').hidden=true;
  try {
    if(!prepared)throw new Error('Prepare profiles and click Review before saving a draft.');
    const result = await AccountsUI.saveDraft(prepared.files,document.getElementById('draftLabel').value.trim());
    document.getElementById('draftMessage').textContent='Saved successfully. Active tunnels were not changed. Next: Continue to VPN review to check this saved configuration.';
    const next=document.getElementById('continueDraft');next.dataset.draftId=result.id;next.textContent='Continue to VPN review — '+(result.label||document.getElementById('draftLabel').value.trim());next.hidden=false;
    document.getElementById('draftList').textContent=(result.label||'Saved draft')+' — '+(result.paths?.length||0)+' roads. Private saved copy; active settings were not changed.';
  }catch(error){document.getElementById('draftMessage').textContent=error.message;}
  finally{button.disabled=false;}
};
document.getElementById('showDrafts').onclick = async () => {
  try {
    const result = await AccountsUI.listDrafts();
    const choice=document.getElementById('draftArchiveChoice');choice.textContent='';
    for(const [prefix,items] of [['saved',result.drafts],['archived',result.archived||[]]]){
      for(const item of items){const option=document.createElement('option');option.value=prefix+':'+item.id;option.textContent=(item.label||'Private draft')+' — '+prefix;choice.append(option);}
    }
    document.getElementById('draftList').textContent=result.drafts.map(d=>(d.label||'Saved draft')+' — '+(d.paths?.map(p=>p.name+' ('+p.kind+')').join(', ')||'saved settings')).join('\n')||'No saved drafts yet.';
    document.getElementById('draftMessage').textContent='These are saved drafts. None has been applied.';
  }catch(error){document.getElementById('draftMessage').textContent=error.message;}
};
for(const action of ['archive','restore'])document.getElementById(action+'Draft').onclick=async()=>{
  const password=document.getElementById('draftArchivePassword');
  try{
    const [state,id]=document.getElementById('draftArchiveChoice').value.split(':');
    if(!id||state!==(action==='archive'?'saved':'archived'))throw new Error('Choose a '+(action==='archive'?'saved':'archived')+' draft first.');
    await AccountsUI.archiveDraft(action,id,password.value);
    await document.getElementById('showDrafts').onclick();
    document.getElementById('draftMessage').textContent=action==='archive'?'Draft archived privately. It can be restored; traffic was not changed.':'Draft restored for preparation and review. Traffic was not changed.';
  }catch(error){document.getElementById('draftMessage').textContent=error.message;}
  finally{password.value='';}
};

document.getElementById('draftArchiveChoice').onchange=()=>{
  const [state,id]=document.getElementById('draftArchiveChoice').value.split(':');
  const next=document.getElementById('continueDraft');next.hidden=state!=='saved'||!id;
  next.dataset.draftId=state==='saved'?id:'';next.textContent='Continue to VPN review for this saved draft';
};
