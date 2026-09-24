/* One library view, retaining versioned personal moves and separate glossary terms. */
'use strict';
let browserFavorites=[],browserRows=[],browserPage=0,browserTab='moves',browserPreviewRow=null;
let favoriteBusy=false,catalogRequest=null,favoriteChange=0;
const movePage=document.querySelector('[data-page="moves"]');
for(const child of [...movePage.children])child.hidden=true;
movePage.insertAdjacentHTML('afterbegin',`<div id="unifiedMoveBrowser"><div class="page-heading"><div><span class="eyebrow">MOVE LIBRARY</span><h1>Find your next step.</h1><p>Browse moves, keep favorites, and build your own teaching library.</p></div></div><div class="card"><div class="browser-tabs" role="group" aria-label="Library collection"><button data-library-tab="moves" aria-pressed="true">All moves</button><button data-library-tab="personal" aria-pressed="false">My moves</button><button data-library-tab="glossary" aria-pressed="false">Glossary</button></div><div class="fields"><label>Find a move<input id="unifiedMoveSearch" type="search" placeholder="Name, alias or family…"></label><label>Difficulty<select id="unifiedMoveLevel"><option value="all">All difficulties</option>${['Absolute Beginner','Beginner','Improver','Intermediate','Advanced','Unspecified'].map(x=>`<option>${x}</option>`).join('')}</select></label><label>Move family<select id="unifiedMoveFamily"><option value="all">All families</option></select></label><label id="browserLeadLabel">Variation lead foot<select id="unifiedMoveLead"><option value="R">Right</option><option value="L">Left</option></select></label></div><div class="actions"><label class="check-label"><input id="unifiedFavorites" type="checkbox"> Favorites only</label><span id="browserArchiveFilter"></span></div><p id="browserHelp"></p><p id="browserSummary" role="status"></p><div id="browserManagement" class="actions"></div><details><summary>Import templates &amp; advanced tools</summary><div id="browserTemplates" class="actions"></div></details></div><div id="browserResults" class="project-grid"></div><div class="browser-pagination"><button id="browserPrev">Previous page</button><span id="browserPageLabel"></span><button id="browserNext">Next page</button></div></div>`);
for(const id of ['newLibraryMove','openMoveImport'])$('browserManagement').appendChild($(id));
for(const link of [...movePage.querySelectorAll(`a[href^="${libraryRoot}/templates/"]`)])$('browserTemplates').appendChild(link);
$('browserTemplates').appendChild($('legacyLibraryBtn'));
$('legacyLibraryBtn').classList.add('advanced');
$('browserArchiveFilter').appendChild($('showArchivedMoves').closest('label'));
document.body.insertAdjacentHTML('beforeend',`<dialog id="browserMovePreview"><h2 id="browserPreviewName"></h2><p id="browserPreviewInfo"></p><p id="browserPreviewText"></p><div class="pack-table-wrap"><table class="pack-timing-table"><thead id="browserPreviewHead"></thead><tbody id="browserPreviewRows"></tbody></table></div><div id="browserPreviewLinks" class="actions"></div><p id="browserPreviewNote"></p><div id="browserRelated" class="actions"></div><div class="actions"><button id="browserPreviewAdd" class="primary">Add to dance</button><button id="browserPreviewEdit">Edit / media</button><button id="browserPreviewClose">Close</button></div></dialog>`);
function indexedBrowserRows(lead=$('unifiedMoveLead').value){return MoveBrowserModel.index(moves,userMoveLibrary,catalog,lead);}
function browserOptions(){return {query:$('unifiedMoveSearch').value,tab:browserTab,difficulty:$('unifiedMoveLevel').value,family:$('unifiedMoveFamily').value,favoritesOnly:$('unifiedFavorites').checked,favorites:browserFavorites,archived:browserTab==='personal'&&$('showArchivedMoves').checked};}
function browserDuration(row){const m=row.data,d=m.duration_counts??m.counts;return row.kind==='expansion'?packDurationLabel(m):MoveBrowserModel.durationLabel(d);}
function browserKind(row){return {core:'Built-in',expansion:'Expanded',legacy:'My older move',user:row.deleted?'Archived personal move':'My move',reference:'Glossary reference'}[row.kind];}
function renderUnifiedBrowser(reset=false){
  if(reset)browserPage=0;
  const all=indexedBrowserRows(),currentFamily=$('unifiedMoveFamily').value;
  const families=[...new Set(all.filter(r=>browserTab==='glossary'?r.kind==='reference':browserTab==='personal'?MoveBrowserModel.isPersonal(r):r.kind!=='reference').map(r=>r.family))].sort((a,b)=>MoveBrowserModel.familyLabel(a).localeCompare(MoveBrowserModel.familyLabel(b)));
  $('unifiedMoveFamily').innerHTML='<option value="all">All families</option>'+families.map(f=>`<option value="${escapeHtml(f)}">${escapeHtml(MoveBrowserModel.familyLabel(f))}</option>`).join('');
  $('unifiedMoveFamily').value=families.includes(currentFamily)?currentFamily:'all';
  browserRows=MoveBrowserModel.filter(all,browserOptions());
  const pages=Math.max(1,Math.ceil(browserRows.length/24));browserPage=Math.min(browserPage,pages-1);
  const shown=browserRows.slice(browserPage*24,browserPage*24+24),stars=new Set(browserFavorites);
  $('browserArchiveFilter').hidden=browserTab!=='personal';$('browserLeadLabel').hidden=browserTab!=='moves'&&!(browserTab==='personal'&&all.some(r=>r.kind==='legacy'));
  $('browserHelp').textContent=browserTab==='glossary'?'Reference terms explain dance vocabulary. Use a timed move where one is available, or explicitly add written instructions.':browserTab==='personal'?'Your own moves retain their teaching notes. Older moves use the older move manager; other personal moves have count rows and teaching media.':'Count-by-count personal moves keep their authored footwork. The lead selector changes built-in, expanded and older move variations. Expanded moves remain available for manual choreography while instructor review is pending.';
  $('browserSummary').textContent=`${MoveBrowserModel.quantity(browserRows.length,browserTab==='glossary'?'reference entry':'move',browserTab==='glossary'?'reference entries':'moves')} found · ${MoveBrowserModel.quantity(all.filter(r=>MoveBrowserModel.isPersonal(r)&&!r.deleted).length,'personal move')} · ${MoveBrowserModel.quantity(browserFavorites.length,'favorite')}`;
  $('browserResults').innerHTML=shown.map(row=>`<article class="project-tile"><div class="browser-card-top"><small>${escapeHtml(browserKind(row))} · ${escapeHtml(row.level)}</small><button data-browser-star="${escapeHtml(row.key)}" ${favoriteBusy?'disabled':''} aria-pressed="${stars.has(row.key)}" aria-label="${stars.has(row.key)?'Remove':'Add'} ${escapeHtml(row.name)} ${stars.has(row.key)?'from':'to'} favorites">${stars.has(row.key)?'★':'☆'}</button></div><strong>${escapeHtml(row.name)}</strong><small>${escapeHtml(browserDuration(row))} · ${escapeHtml(MoveBrowserModel.familyLabel(row.family))}</small><p>${escapeHtml(row.data.explanation||row.data.description||row.data.header||'')}</p><div class="actions"><button data-browser-preview="${escapeHtml(row.key)}">${row.kind==='reference'?'Read reference':'Preview steps'}</button>${row.kind==='user'?`<button data-browser-edit="${escapeHtml(row.key)}">Edit / media</button><button data-browser-archive="${escapeHtml(row.key)}">${row.deleted?'Restore':'Archive'}</button>`:row.kind==='legacy'?`<button data-browser-legacy="${escapeHtml(row.key)}">Open older move manager</button>`:''}</div></article>`).join('')||'<p class="empty">No matches. Try another name or filter, or add your own move.</p>';
  $('browserPageLabel').textContent=`Page ${browserPage+1} of ${pages}`;$('browserPrev').disabled=browserPage===0;$('browserNext').disabled=browserPage===pages-1;
  document.querySelectorAll('[data-library-tab]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.libraryTab===browserTab)));
  $('browserResults').querySelectorAll('[data-browser-preview]').forEach(b=>b.onclick=()=>previewBrowserMove(browserRows.find(r=>r.key===b.dataset.browserPreview)));
  $('browserResults').querySelectorAll('[data-browser-edit]').forEach(b=>b.onclick=()=>editLibraryMove(browserRows.find(r=>r.key===b.dataset.browserEdit).data));
  $('browserResults').querySelectorAll('[data-browser-archive]').forEach(b=>b.onclick=()=>archiveBrowserMove(browserRows.find(r=>r.key===b.dataset.browserArchive)));
  $('browserResults').querySelectorAll('[data-browser-legacy]').forEach(b=>b.onclick=()=>legacy('editor'));
  $('browserResults').querySelectorAll('[data-browser-star]').forEach(b=>b.onclick=()=>toggleBrowserFavorite(b.dataset.browserStar));
}
function updateFavoriteControls(){document.querySelectorAll('[data-browser-star]').forEach(button=>button.disabled=favoriteBusy);}
async function toggleBrowserFavorite(key){
  if(favoriteBusy)return;favoriteBusy=true;favoriteChange++;updateFavoriteControls();
  try{const r=await api('/api/creator/move-browser/favorites',{method:'PUT',body:{key,favorite:!browserFavorites.includes(key)}});browserFavorites=r.favorites;renderUnifiedBrowser();renderMoveChoices();}
  catch(e){notify(e.message);}finally{favoriteBusy=false;updateFavoriteControls();}
}
async function archiveBrowserMove(row){
  if(!row)return;
  if(!row.deleted&&!await askConfirm('Archive this personal move? Its history and the copies saved in dances will remain available.'))return;
  try{await api(`${libraryRoot}/records/${row.data.id}${row.deleted?'/restore':''}`,{method:row.deleted?'POST':'DELETE',body:{expected_version:row.data.version}});await loadUserMoves();}catch(e){notify(e.message);}
}
function previewBrowserMove(row){
  if(!row)return;
  if(row.kind==='expansion')return previewExpansionSnapshot(row.data);
  browserPreviewRow=clone(row);const m=row.data,advanced=document.body.dataset.mode==='advanced';
  $('browserPreviewName').textContent=row.name;$('browserPreviewInfo').textContent=`${browserKind(row)} · ${row.level} · ${browserDuration(row)}`;
  $('browserPreviewText').textContent=m.explanation||m.description||m.header||'';
  const explicit=Array.isArray(m.events)&&m.events.length;
  $('browserPreviewHead').innerHTML=explicit?'<tr><th>Count</th><th>Action</th><th>Weight ends on</th><th>Turn</th></tr>':'<tr><th>Count</th><th>Action</th></tr>';
  const weights={R:'Right foot',L:'Left foot',both:'Both feet',neither:'Neither foot',same:'Unchanged',unknown:'Not specified'};
  $('browserPreviewRows').innerHTML=MoveBrowserModel.previewRows(m).map(({row:e,label})=>explicit?`<tr><td>${escapeHtml(label)}</td><td>${escapeHtml(e.text||'')}</td><td>${escapeHtml(weights[e.support_after]||'Not specified')}</td><td>${escapeHtml(MoveBrowserModel.turn(e.rotation_deg,advanced))}</td></tr>`:`<tr><td>${escapeHtml(label)}</td><td>${escapeHtml(e.text||'')}</td></tr>`).join('');
  $('browserPreviewLinks').innerHTML=(m.links||[]).filter(l=>safeUrl(l.url)).map(l=>`<a href="${escapeHtml(l.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(l.label||'Teaching reference')} ↗</a>`).join('');
  $('browserPreviewNote').textContent=row.kind==='reference'?'This is a reference description. Adding it as written instructions does not verify its footwork.':row.kind==='user'?'This is your saved teaching version. Edit / media opens its count rows, notes, pictures and videos.':row.kind==='legacy'?'This is your move from the older manager. Its concrete instructions are copied into the dance when added. Use the older manager to change the library definition.':'Check how the ending foot and turn join the next move.';
  $('browserPreviewEdit').hidden=!MoveBrowserModel.isPersonal(row);$('browserPreviewEdit').textContent=row.kind==='legacy'?'Open older move manager':'Edit / media';$('browserPreviewAdd').hidden=!!row.deleted;$('browserPreviewAdd').textContent=row.kind==='reference'?'Add as written instructions':'Add to dance';
  $('browserRelated').innerHTML=(m.expansion_ids||[]).filter(id=>moves.some(x=>x.move_id===id)).map(id=>`<button data-related-move="${escapeHtml(id)}">Timed variation: ${escapeHtml(moves.find(x=>x.move_id===id&&x.lead===$('unifiedMoveLead').value)?.name||id)}</button>`).join('');
  $('browserRelated').querySelectorAll('[data-related-move]').forEach(b=>b.onclick=()=>{$('browserMovePreview').close();previewExpansionMove(b.dataset.relatedMove,$('unifiedMoveLead').value);});
  $('browserMovePreview').showModal();
}
async function addBrowserMove(row){
  if(!draft)return notify('Start or open a dance first.');
  const context={pid:project.id,partId:activePart,version:changeVersion};
  try{
    let item=row.data;
    if(row.kind==='user'){
      if(item.duration_counts===null&&!item.events?.length){notify('Set the move’s counts before adding it to a dance.');return editLibraryMove(item);}
      item=await api(`${libraryRoot}/records/${item.id}/snapshot?version=${item.version}`);
    }else if(row.kind==='reference'){
      item=await api(`${libraryRoot}/reference/${item.referenceId}/snapshot`);
      if(item.requires_counts){const duration=await askText('How many counts will these written instructions use?','4');if(duration===null)return;item=await api(`${libraryRoot}/reference/${row.data.referenceId}/snapshot?duration_counts=${encodeURIComponent(duration)}`);}
    }else if((row.kind==='core'||row.kind==='legacy')&&item.start==='F'){
      const free=MoveTiming.endingFreeFoot(selectedPart().moves,draft.choreography.start.free_foot);
      if(!free)return notify('Review the previous move’s ending weight before adding a free-foot cue.');
      item=moves.find(m=>m.move_id===item.move_id&&m.lead===free)||item;
    }
    if(!requestStillCurrent(context))return notify('The selected dance changed; add the move again.');
    change(()=>selectedPart().moves.push({...clone(item),id:uid('move')}));showView('edit');
  }catch(e){notify(e.message);}
}
$('browserPreviewClose').onclick=()=>$('browserMovePreview').close();
$('browserPreviewEdit').onclick=()=>{$('browserMovePreview').close();if(browserPreviewRow.kind==='legacy')legacy('editor');else editLibraryMove(browserPreviewRow.data);};
$('browserPreviewAdd').onclick=()=>{const row=browserPreviewRow;$('browserMovePreview').close();addBrowserMove(row);};
document.querySelectorAll('[data-library-tab]').forEach(b=>b.onclick=()=>{browserTab=b.dataset.libraryTab;$('unifiedMoveFamily').value='all';renderUnifiedBrowser(true);});
for(const id of ['unifiedMoveSearch','unifiedMoveLevel','unifiedMoveFamily','unifiedMoveLead','unifiedFavorites','showArchivedMoves'])$(id).addEventListener(id==='unifiedMoveSearch'?'input':'change',()=>renderUnifiedBrowser(true));
$('browserPrev').onclick=()=>{browserPage--;renderUnifiedBrowser();};$('browserNext').onclick=()=>{browserPage++;renderUnifiedBrowser();};
renderCatalog=async function(){
  if(!catalog.length){catalogRequest||=api('/api/creator/catalog').then(r=>catalog=r.steps||[]).finally(()=>catalogRequest=null);await catalogRequest;}
  renderUnifiedBrowser();
};
renderUserMoves=function(){renderUnifiedBrowser();renderMoveChoices();};
const originalRenderChoices=renderMoveChoices;
renderMoveChoices=function(){
  if(!window.MoveBrowserModel)return originalRenderChoices();
  const list=MoveBrowserModel.filter(indexedBrowserRows($('moveLead').value),{query:$('moveSearch').value,difficulty:$('moveLevel').value,tab:'moves'});
  $('moveChoices').innerHTML=list.map(row=>`<button class="move-choice" data-picker-key="${escapeHtml(row.key)}"><span>${browserFavorites.includes(row.key)?'★ ':''}${escapeHtml(row.name)}${row.kind==='user'?'<small> · My move</small>':row.kind==='legacy'?'<small> · My older move</small>':''}</span><small>${escapeHtml(browserDuration(row))} ${row.kind==='core'?'＋':'Preview'}</small></button>`).join('')||'<p class="empty">No matching moves. Open the library to add your own.</p>';
  $('moveChoices').querySelectorAll('[data-picker-key]').forEach(b=>b.onclick=()=>{const row=list.find(r=>r.key===b.dataset.pickerKey);if(row.kind==='core')addBrowserMove(row);else previewBrowserMove(row);});
};
for(const id of ['moveSearch','moveLevel','moveLead'])$(id)[id==='moveSearch'?'oninput':'onchange']=renderMoveChoices;
async function loadMoveBrowser(){
  try{await creatorReady;const preferenceRequest=favoriteChange;const prefs=await api('/api/creator/move-browser/preferences');if(preferenceRequest===favoriteChange)browserFavorites=prefs.favorites;await loadUserMoves();await renderCatalog();renderMoveChoices();}catch(e){notify('Move library: '+e.message);}
}
loadMoveBrowser();
