'use strict';
// IDs and public status only. Passphrases never enter browser storage or the engine.
(() => {
  const el = id => document.getElementById(id);
  let status = null, busy = false, previewed = null, pathSignature = null, preparedSignature = null;
  function reset() {
    status = null; previewed = null;
    el('managementPassword').value = '';
    el('managementStatus').textContent = '';
    el('managementMessage').textContent = '';
    el('generationId').value = '';
    el('managedDraft').textContent = '';
    el('preparedGeneration').textContent = '';preparedSignature=null;
    el('archivedGeneration').textContent='';
    el('preferredPath').textContent='';el('maintenancePath').textContent='';pathSignature=null;
  }
  function buttons() {
    const pending = status?.transaction?.change;
    el('applyGeneration').disabled = busy || !AccountsUI.testApplyEnabled()
      || !status?.live_apply_enabled || !status?.ready || previewed !== el('generationId').value.trim()
      || pending?.phase === 'pending' || pending?.phase === 'rollback-requested';
    el('confirmGeneration').disabled = busy || !AccountsUI.testApplyEnabled()
      || !status?.live_apply_enabled || !status?.ready || pending?.phase !== 'pending'
      || status?.running_generation !== pending?.candidate || status.confirmation_seconds_remaining <= 0;
    el('revertGeneration').disabled = busy || !AccountsUI.testApplyEnabled()
      || !status?.live_apply_enabled || pending?.phase !== 'pending';
    const operating = busy || !AccountsUI.testApplyEnabled() || !status?.live_apply_enabled
      || !status?.path_names?.length || pending?.phase === 'pending' || pending?.phase === 'rollback-requested';
    el('temporaryOperation').disabled=operating;el('automaticOperation').disabled=operating;
    const retaining=busy||!status||status.storage_fault||pending?.phase==='pending'||pending?.phase==='rollback-requested';
    el('archiveGeneration').disabled=retaining||!el('generationId').value||el('generationId').value===status?.selected_generation;
    el('restoreGeneration').disabled=retaining||!el('archivedGeneration').value;
  }
  async function refreshStatus() {
    if (!AccountsUI.canControl()) {reset(); buttons(); return;}
    try {
      status = await AccountsUI.controlStatus();
      if(!AccountsUI.canControl()){reset();buttons();return;}
      const change = status.transaction?.change;
      const prepared=status.prepared||[], archives=status.archived||[], versions=JSON.stringify([prepared,archives,status.selected_generation]);
      if(versions!==preparedSignature){
        const previous=el('generationId').value;
        el('preparedGeneration').textContent='';
        const none=document.createElement('option');none.value='';none.textContent='Choose previously prepared settings';el('preparedGeneration').append(none);
        for(const item of prepared){const option=document.createElement('option');option.value=item.id;option.textContent=item.label+(item.id===status.selected_generation?' — currently selected':'');el('preparedGeneration').append(option);}
        el('preparedGeneration').value=prepared.some(item=>item.id===previous)?previous:'';
        el('archivedGeneration').textContent='';
        for(const item of archives){const option=document.createElement('option');option.value=item.id;option.textContent=item.label;el('archivedGeneration').append(option);}
        preparedSignature=versions;
      }
      const names=status.path_names||[], signature=JSON.stringify(names);
      if(signature!==pathSignature){
        for(const [id,label] of [['preferredPath','Use normal priority'],['maintenancePath','Keep every road eligible']]){
          el(id).textContent='';const none=document.createElement('option');none.value='';none.textContent=label;el(id).append(none);
          for(const name of names){const option=document.createElement('option');option.value=name;option.textContent=name;el(id).append(option);}
        }pathSignature=signature;
      }
      el('managementStatus').textContent = [
        'Engine: '+(status.ready?'application and tunnels checked':'waiting for health checks'),
        'Selected settings: '+(status.selected_generation===status.transaction?.state?.active?'confirmed':status.transaction?.change?.phase==='pending'?'awaiting confirmation':'checking'),
        change ? 'Change: '+change.phase : 'Change: none',
        change?.phase === 'pending' ? 'Confirm within '+status.confirmation_seconds_remaining+' seconds or the previous settings will return.' : '',
        status.storage_fault ? 'Private storage needs repair. New changes are blocked; database recovery is not acknowledged.' : '',
        !status.live_apply_enabled ? 'Live changes are disabled.' : ''
        ,status.operations?.mode==='temporary'?'Temporary selection: preferred '+(status.operations.preferred||'normal priority')+'; excluded '+(status.operations.disabled.join(', ')||'none')+'; '+status.operations.seconds_remaining+' seconds remaining.':'Selection uses automatic priority.'
      ].filter(Boolean).join('\n');
    } catch (error) {status=null;el('managementStatus').textContent=error.message;}
    buttons();
  }
  async function action(name, data, sensitive=false) {
    if(busy)return;
    busy=true;buttons();
    try {
      if(sensitive){
        if(!el('managementPassword').value)throw new Error('Enter your current administrator passphrase again for this action. It is cleared after every sensitive action.');
        data.current_password=el('managementPassword').value;
      }
      const result=await AccountsUI.control(name,data);
      if(!AccountsUI.canControl()){reset();return;}
      if(name==='prepare') {el('generationId').value=result.id;previewed=null;el('managementMessage').textContent='Engine prepared this draft. Active tunnels have not changed. Review before Apply.';}
      else if(name==='archive'||name==='restore'){el('generationId').value=name==='restore'?result.id:'';previewed=null;el('managementMessage').textContent=name==='archive'?'Unused prepared settings archived privately. Traffic was not changed.':'Settings restored privately. Review them before applying. Traffic was not changed.';}
      else if(name==='preview') {previewed=result.live_footprint_compatible?data.generation:null;el('managementMessage').textContent=[result.live_footprint_compatible?'These settings keep the same reserved network resources.':'These settings need a network layout change, which this Apply driver does not support.',...(result.changes||[]),...(result.reasons||[]),'Preferred order: '+(result.path_order||[]).join(' → '),'Credentials are checked privately. After Apply, the engine must prove all tunnels and the real application work before confirmation.'].join('\n');}
      else el('managementMessage').textContent=name==='apply'?'Change started. Check your real application, re-enter your administrator passphrase, then confirm before the timer ends.':name==='confirm'?'Engine confirmed the change after fresh tunnel and application checks.':name==='operate'?'Temporary preference saved. Check Connection overview to see which road actually carries traffic. Automatic priority returns when the timer ends.':name==='automatic'?'Automatic priority requested. Healthy recovery thresholds still apply.':'Return requested. Wait for recovery health checks.';
    }catch(error){el('managementMessage').textContent=error.message;}
    finally {if(sensitive)el('managementPassword').value='';busy=false;await refreshStatus();}
  }
  el('loadManagedDrafts').onclick=async()=>{
    try{const result=await AccountsUI.listDrafts();if(!AccountsUI.canControl())return;el('managedDraft').textContent='';for(const draft of result.drafts){const option=document.createElement('option');option.value=draft.id;option.textContent=draft.label+' ('+draft.paths.length+' roads)';el('managedDraft').append(option);}}
    catch(error){el('managementMessage').textContent=error.message;}
  };
  el('refreshManagementStatus').onclick=refreshStatus;
  el('prepareGeneration').onclick=()=>action('prepare',{draft:el('managedDraft').value},true);
  el('previewGeneration').onclick=()=>action('preview',{generation:el('generationId').value.trim()});
  el('applyGeneration').onclick=()=>action('apply',{generation:el('generationId').value.trim(),timeout:180},true);
  el('confirmGeneration').onclick=()=>action('confirm',{change_id:status?.transaction?.change?.id},true);
  el('revertGeneration').onclick=()=>action('revert',{change_id:status?.transaction?.change?.id},true);
  el('temporaryOperation').onclick=()=>action('operate',{preferred:el('preferredPath').value||null,
    disabled:el('maintenancePath').value?[el('maintenancePath').value]:[],seconds:Number(el('operationSeconds').value)},true);
  el('automaticOperation').onclick=()=>action('automatic',{},true);
  el('generationId').oninput=()=>{previewed=null;buttons();};
  el('preparedGeneration').onchange=()=>{el('generationId').value=el('preparedGeneration').value;previewed=null;el('managementMessage').textContent='Review these settings before applying them.';buttons();};
  el('archivedGeneration').onchange=buttons;
  el('archiveGeneration').onclick=()=>action('archive',{generation:el('generationId').value},true);
  el('restoreGeneration').onclick=()=>action('restore',{generation:el('archivedGeneration').value},true);
  document.addEventListener('pointerdown',()=>{if(!AccountsUI.canControl())reset();});
  AccountsUI.ready.then(()=>{refreshStatus();setInterval(refreshStatus,3000);});
})();
