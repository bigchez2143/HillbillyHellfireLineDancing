/* Complete private backup. Archives restore into a separate data profile. */
'use strict';
(() => {
  const host=document.querySelector('[data-page="settings"]');
  if(!host)return;
  const base='/api/creator/backup';
  let exportPreview=null,importPreview=null,busy=false;
  host.insertAdjacentHTML('beforeend',`<section class="card private-backup" id="privateBackup"><h2>Back up everything private</h2><p>Keep all saved dances, accepted versions, named milestones, library history, reusable phrases, favorites and teaching records together. This private archive includes your notes and lyrics. Keep it for your own recovery.</p><p>Music and teaching media are optional. Only files already stored inside your projects or move library can be included. External files stay linked in the report for relinking. AI keys, provider addresses, models and caches are excluded.</p><div class="fields"><label class="check-label"><input id="backupMusic" type="checkbox"> Include stored music</label><label class="check-label"><input id="backupPhotos" type="checkbox"> Include stored photos</label><label class="check-label"><input id="backupVideos" type="checkbox"> Include stored videos</label></div><p class="muted">Up to 2 GiB per archive and 512 MiB per media file. Your current draft is saved before the snapshot. Changes made after the snapshot need another backup.</p><button id="previewFullBackup">Prepare backup preview</button><div id="fullBackupPreview" hidden></div><a id="downloadFullBackup" class="button" hidden download>Download private backup</a><hr><h3>Restore into a separate profile</h3><p>Your current data stays unchanged. Review the file, restore its contents, then open the restored copy with its own launcher.</p><label>Complete private backup<input id="fullRestoreFile" type="file" accept=".zip,application/zip"></label><button id="previewFullRestore">Preview restore</button><div id="fullRestorePreview" hidden></div><button id="applyFullRestore" class="primary" hidden>Restore into a new profile</button><div id="fullRestoreResult" hidden></div><p id="fullBackupStatus" role="status" aria-live="polite"></p></section>`);
  const el=id=>document.getElementById(id);
  const bytes=n=>n==null?'Size unavailable':n<1024?`${n} bytes`:n<1024**2?`${(n/1024).toFixed(1)} KiB`:`${(n/1024**2).toFixed(2)} MiB`;
  const explain={included:'Included',not_selected:'Not selected',missing_file:'Missing — relink',external_path_relink_required:'External file — relink',relative_path_relink_required:'Relative path — relink',unsupported_or_generated_file:'Generated or unsupported file omitted',generated_or_unowned_subdirectory:'Generated or unowned folder omitted'};
  function status(message){el('fullBackupStatus').textContent=message;}
  function lock(value){busy=value;for(const id of ['previewFullBackup','previewFullRestore','applyFullRestore','backupMusic','backupPhotos','backupVideos','fullRestoreFile'])el(id).disabled=value;}
  function preview(target,data){
    const s=data.summary;
    target.hidden=false;
    target.innerHTML=`<p><strong>${escapeHtml(bytes(data.archive_bytes))}</strong> · ${s.projects} projects · ${s.named_versions} named versions · ${s.last_good_copies} recovery copies</p><p>${s.library_records} library moves / ${s.library_versions} versions · ${s.phrases} reusable phrases / ${s.phrase_versions} versions · ${s.teaching_dances} teaching records · ${s.setlists} setlists · ${s.events} events</p><p>${s.media_included} media files included · ${s.media_to_relink} omitted or needing relink</p><details><summary>Media and omissions</summary><ul>${data.media.map(m=>`<li>${escapeHtml(m.original_path)} — ${escapeHtml(explain[m.reason]||m.reason)} (${escapeHtml(bytes(m.bytes))})</li>`).join('')||'<li>No local media references.</li>'}</ul><ul>${data.omissions.map(m=>`<li>${escapeHtml(m)}</li>`).join('')}</ul><p>${escapeHtml(data.consistency)}</p></details>`;
  }
  async function discard(value){if(value)await api(`${base}/previews/${value.token}`,{method:'DELETE'}).catch(()=>{});}
  async function invalidateExport(){const old=exportPreview;exportPreview=null;el('downloadFullBackup').hidden=true;el('fullBackupPreview').hidden=true;await discard(old);}
  for(const id of ['backupMusic','backupPhotos','backupVideos'])el(id).onchange=invalidateExport;
  el('previewFullBackup').onclick=async()=>{
    if(busy)return;lock(true);status('Saving your draft and preparing the private snapshot…');
    try{
      await invalidateExport();
      if(typeof save==='function')await save();
      if(typeof dirty==='function'&&dirty())throw new Error('Save the current draft before preparing the backup.');
      const browser=typeof browserPreferenceSnapshot==='function'?browserPreferenceSnapshot():{};
      exportPreview=await api(`${base}/exports/preview`,{method:'POST',body:{options:{include_music:el('backupMusic').checked,include_photos:el('backupPhotos').checked,include_videos:el('backupVideos').checked},browser_preferences:browser}});
      preview(el('fullBackupPreview'),exportPreview);
      el('downloadFullBackup').href=`${base}/exports/${exportPreview.token}/download?manifest_digest=${exportPreview.manifest_digest}&confirmed=true`;
      el('downloadFullBackup').hidden=false;
      status('Private snapshot ready. Review its contents, then download the backup.');
    }catch(error){status(error.message);}finally{lock(false);}
  };
  el('fullRestoreFile').onchange=async()=>{const old=importPreview;importPreview=null;el('applyFullRestore').hidden=true;el('fullRestorePreview').hidden=true;el('fullRestoreResult').hidden=true;await discard(old);};
  el('previewFullRestore').onclick=async()=>{
    if(busy)return;const file=el('fullRestoreFile').files[0];
    if(!file)return status('Choose a complete private backup ZIP.');
    if(file.size>2*1024**3)return status('This file exceeds the 2 GiB archive limit.');
    lock(true);status('Checking the manifest, saved data and media hashes…');
    try{
      await discard(importPreview);importPreview=null;el('applyFullRestore').hidden=true;
      const form=new FormData();form.append('file',file);
      importPreview=await api(`${base}/imports/preview`,{method:'POST',body:form});
      preview(el('fullRestorePreview'),importPreview);el('applyFullRestore').hidden=false;
      status('Backup checked. Restore will create a separate profile and leave current data unchanged.');
    }catch(error){status(error.message);}finally{lock(false);}
  };
  el('applyFullRestore').onclick=async()=>{
    if(busy||!importPreview)return;
    const selected=importPreview;
    if(!await askConfirm(`Restore ${selected.summary.projects} projects and the listed private records into a new separate profile? Your current data stays unchanged.`))return;
    lock(true);status('Restoring and verifying the separate data profile…');
    try{
      const result=await api(`${base}/imports/${selected.token}/restore`,{method:'POST',body:{manifest_digest:selected.manifest_digest,confirmed:true}});
      const box=el('fullRestoreResult');box.hidden=false;
      box.innerHTML=`<h3>Restored separately</h3><p>Your current data is unchanged.</p><p class="backup-path">${escapeHtml(result.restored_folder)}</p><ol><li>Download the restored-profile launcher below.</li><li>Open that downloaded launcher to use the restored copy. It opens at a separate local address.</li><li>Keep the restored data folder in place. Relink omitted music or teaching media using the restore report.</li></ol><div class="actions"><a class="button" href="${escapeHtml(result.launcher_url)}" download>Download restored-profile launcher</a><a href="${escapeHtml(result.report_url)}" download>Download private restore report</a></div>`;
      status(result.message);el('applyFullRestore').hidden=true;
    }catch(error){status(error.message);}finally{lock(false);}
  };
})();
