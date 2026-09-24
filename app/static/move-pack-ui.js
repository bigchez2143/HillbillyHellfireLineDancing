/* Bundled teaching variants remain frozen when placed in a working draft. */
'use strict';
let previewPackMove=null;
document.querySelector('[data-page="moves"]').insertAdjacentHTML('afterbegin',`<section class="card" id="expandedPackSection"><h2>Intermediate &amp; advanced move pack</h2><p>Choose a specific variation and review its timing before teaching it. These new definitions are available for manual choreography; instructor review is still pending.</p><div class="fields"><label>Search new moves<input id="packSearch" type="search" placeholder="Name or alias…"></label><label>Suggested level<select id="packLevel"><option value="all">All levels</option><option value="I">Improver foundations</option><option value="INT">Intermediate</option><option value="A">Advanced</option></select></label><label>Lead foot<select id="packLead"><option value="R">Right</option><option value="L">Left</option></select></label></div><p id="packSummary" role="status"></p><div id="packCards" class="project-grid"></div></section>`);
document.body.insertAdjacentHTML('beforeend',`<dialog id="packPreview"><h2 id="packPreviewName"></h2><p id="packPreviewSummary"></p><p id="packPreviewNote" class="pack-review-note"></p><div class="pack-table-wrap"><table class="pack-timing-table"><thead><tr><th>Count</th><th>Action</th><th>Weight ends on</th><th>Turn</th></tr></thead><tbody id="packPreviewRows"></tbody></table></div><div id="packPreviewLinks" class="actions"></div><p id="packPreviewEntry"></p><div class="actions"><button id="packPreviewAdd" class="primary">Add this variation to dance</button><button id="packPreviewClose">Close</button></div></dialog>`);
function packMoves(){return moves.filter(m=>m.definition_hash&&Array.isArray(m.events));}
function levelName(level){return {AB:'Absolute Beginner',B:'Beginner',I:'Improver',INT:'Intermediate',A:'Advanced'}[level]||level;}
function packDurationLabel(m){return `${m.duration_counts??m.counts} ${m.mechanically_complete?'counts':'count practice window'}`;}
function renderExpansionLibrary(){
  const q=$('packSearch').value.toLowerCase(),level=$('packLevel').value,lead=$('packLead').value;
  const all=packMoves(),list=all.filter(m=>m.lead===lead&&(level==='all'||m.level===level)&&`${m.name} ${(m.aliases||[]).join(' ')} ${m.group||''}`.toLowerCase().includes(q));
  $('packSummary').textContent=`${new Set(all.map(m=>m.move_id)).size} new variations · ${list.length} shown for ${lead==='R'?'right':'left'} lead. Exact definitions are saved with your dance.`;
  $('packCards').innerHTML=list.map(m=>`<article class="project-tile"><small>${escapeHtml(levelName(m.level))} · ${escapeHtml(packDurationLabel(m))}</small><strong>${escapeHtml(m.name)}</strong><p>${escapeHtml(m.explanation||'')}</p><small>${m.mechanically_complete?'Timed definition · instructor review pending':'Mechanics need review'}</small><button data-preview-pack="${escapeHtml(m.move_id)}" data-pack-lead="${lead}">Preview steps</button></article>`).join('')||'<p class="empty">No matching variations. Try another name or level.</p>';
  document.querySelectorAll('[data-preview-pack]').forEach(b=>b.onclick=()=>previewExpansionMove(b.dataset.previewPack,b.dataset.packLead));
}
function previewExpansionMove(id,lead){
  const m=packMoves().find(m=>m.move_id===id&&m.lead===lead);if(!m)return;
  previewExpansionSnapshot(m);
}
function previewExpansionSnapshot(m){
  const lead=m.lead;
  previewPackMove=clone(m);$('packPreviewName').textContent=m.name;
  $('packPreviewSummary').textContent=`${packDurationLabel(m)} · suggested ${levelName(m.level)} · ${m.start_free_foot?`${lead==='R'?'right':'left'} foot free to start`:'starting support unspecified'}. ${m.explanation||''}`;
  $('packPreviewNote').textContent=(m.mechanically_complete?'New teaching variation — instructor review pending.':'Provisional practice cue. The displayed duration is a placeholder, not a standard move length. Footwork and facing remain unverified.')+(m.review_note&&!m.review_note.startsWith('One explicit teaching variation.')?' '+m.review_note:'');
  $('packPreviewRows').innerHTML=m.events.map(e=>`<tr><td>${escapeHtml(MoveTiming.label(e.offset_counts??0))}</td><td>${escapeHtml(e.text||'')}</td><td>${escapeHtml({R:'Right',L:'Left',both:'Both',neither:'Neither',same:'Unchanged',unknown:'Unspecified'}[e.support_after]||'Unspecified')}</td><td>${e.rotation_deg===null||e.rotation_deg===undefined?'Unspecified':escapeHtml(MoveBrowserModel.turn(e.rotation_deg,document.body.dataset.mode==='advanced'))}</td></tr>`).join('');
  $('packPreviewLinks').innerHTML=(Array.isArray(m.sources)?m.sources:[]).filter(s=>safeUrl(s.url)).map(s=>`<a href="${escapeHtml(safeUrl(s.url))}" target="_blank" rel="noopener noreferrer">${escapeHtml(s.title||'Teaching reference')} ↗</a>`).join('');
  const entryFacing=MoveTiming.facing(m.required_start_facing).toLowerCase();
  $('packPreviewEntry').textContent=m.required_start_facing===null||m.required_start_facing===undefined?'Use the dance check to confirm how this variation joins your other moves.':`Start ${document.body.dataset.mode==='advanced'?entryFacing:entryFacing.replace(/ \([^)]*°\)$/,'')} for this variation. Set that starting direction or choreograph a turn into it.`;
  $('packPreview').showModal();
}
function addPackSnapshot(m){
  if(!draft)return notify('Start or open a dance first.');
  change(()=>selectedPart().moves.push({...clone(m),id:uid('move')}));showView('edit');
  notify(m.mechanically_complete?'Variation added. Review its transition and teaching instructions.':'Variation added with mechanics marked for review.');
}
$('packPreviewClose').onclick=()=>$('packPreview').close();
$('packPreviewAdd').onclick=()=>{if(!draft)return notify('Start or open a dance first.');addPackSnapshot(previewPackMove);$('packPreview').close();};
$('packSearch').oninput=renderExpansionLibrary;$('packLevel').onchange=renderExpansionLibrary;$('packLead').onchange=renderExpansionLibrary;
