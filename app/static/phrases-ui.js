/* Reusable eight-count phrases. Persist full move snapshots, never catalog IDs alone. */
"use strict";
let phraseRows = [], phraseLoaded = false, phraseLoading = null, phrasePreview = null;

function phraseLabel(value) { return typeof MoveTiming !== 'undefined' ? MoveTiming.label(value) : String(numeric(value) + 1); }
function phraseNumber(value) { return value&&typeof value==='object'?Number(value.numerator)/Number(value.denominator):numeric(value); }
function phraseDuration(move) {
  const definition=move.definition?{...move.definition,...move}:move;
  if(definition.duration_counts!=null||definition.counts!=null)return phraseNumber(definition.duration_counts??definition.counts);
  if(!Array.isArray(definition.events)||!definition.events.length)return NaN;
  return definition.events.reduce((cursor,event)=>phraseNumber(event.offset_counts??cursor)+phraseNumber(event.duration_counts??(event.instant?0:NaN)),0);
}
function phraseMessage(text) { const el = $('phraseStatus'); if (el) el.textContent = text; }
function phraseContext() { return {pid:project?.id,partId:selectedPart()?.id,version:changeVersion}; }
function phraseContextMatches(context) { return context.pid===project?.id && context.partId===selectedPart()?.id && context.version===changeVersion; }

function ensurePhraseUI() {
  if ($('phraseTools')) return;
  const edit = document.querySelector('[data-page="edit"]');
  if (!edit) return;
  const card = document.createElement('section'); card.className = 'card'; card.id = 'phraseTools';
  card.innerHTML = `<details id="phraseDetails"><summary><strong>Your eight-count phrases</strong> · Save a sequence and use it again</summary>
    <p>Save consecutive whole moves totaling eight counts. Every inserted phrase is an independent copy you can edit and undo.</p>
    <div class="phrase-columns"><div><h3>Save from this part</h3><form id="phraseSaveForm">
    <div class="fields"><label>First move<select id="phraseFirst"></select></label><label>Last move<select id="phraseLast"></select></label></div>
    <p id="phraseSelection" role="status"></p><label>Phrase name<input id="phraseName" maxlength="200" placeholder="My chorus eight" required></label>
    <button id="phraseSaveBtn" class="primary">Save eight-count phrase</button></form></div>
    <div><h3>Use a saved phrase</h3><div class="fields"><label>Search phrases<input id="phraseSearch" type="search" placeholder="Name or move…"></label>
    <label class="check-label"><input id="phraseFavorites" type="checkbox"> Favorites only</label><label class="check-label"><input id="phraseArchived" type="checkbox"> Show archived</label></div>
    <label>Insert position<select id="phraseInsertAt"></select></label><div id="phraseList" class="phrase-list"></div></div></div>
    <p id="phraseStatus" role="status"></p></details>`;
  edit.querySelector('.edit-layout')?.insertAdjacentElement('afterend',card);
  document.body.insertAdjacentHTML('beforeend',`<dialog id="phrasePreviewDialog" aria-labelledby="phrasePreviewTitle"><h2 id="phrasePreviewTitle">Phrase preview</h2>
    <p id="phrasePreviewNotice"></p><div id="phrasePreviewRows"></div><p id="phrasePreviewStatus" role="status"></p>
    <div class="actions"><button id="phrasePreviewClose">Close</button><button id="phraseInsertBtn" class="primary">Insert this phrase</button></div></dialog>`);
  $('phraseFirst').onchange=updatePhraseSelection; $('phraseLast').onchange=updatePhraseSelection;
  $('phraseSaveForm').onsubmit=savePhraseSelection;
  $('phraseSearch').oninput=renderPhraseList; $('phraseFavorites').onchange=renderPhraseList;
  $('phraseArchived').onchange=renderPhraseList;
  $('phrasePreviewClose').onclick=()=>$('phrasePreviewDialog').close();
  $('phraseInsertBtn').onclick=insertPreviewedPhrase;
  $('phraseDetails').ontoggle=()=>{if($('phraseDetails').open&&!phraseLoaded)loadPhrases();};
}

function renderPhrasePicker() {
  ensurePhraseUI(); if (!$('phraseTools')) return;
  const rows=selectedPart()?.moves||[], first=$('phraseFirst').value, last=$('phraseLast').value, insertion=$('phraseInsertAt').value;
  let count=0;
  const options=rows.map((m,i)=>{const option=`<option value="${escapeHtml(m.id||String(i))}">${phraseLabel(count)} · ${escapeHtml(m.name||'Written move')}</option>`;count+=phraseDuration(m);return option;}).join('');
  $('phraseFirst').innerHTML=options; $('phraseLast').innerHTML=options;
  const has=value=>rows.some((m,i)=>(m.id||String(i))===value);
  if(has(first))$('phraseFirst').value=first;
  if(has(last))$('phraseLast').value=last;else {let sum=0;const end=rows.findIndex(m=>{sum+=phraseDuration(m);return sum>=8;});if(end>=0)$('phraseLast').selectedIndex=end;}
  $('phraseInsertAt').innerHTML='<option value="end">End of this part</option>'+rows.map((m,i)=>`<option value="${escapeHtml(m.id||String(i))}">Before ${i+1}. ${escapeHtml(m.name||'Written move')}</option>`).join('');
  if(has(insertion))$('phraseInsertAt').value=insertion;
  updatePhraseSelection(); renderPhraseList();
  if($('phraseDetails').open&&!phraseLoaded)loadPhrases();
}

function updatePhraseSelection() {
  const rows=selectedPart()?.moves||[], a=$('phraseFirst').selectedIndex, b=$('phraseLast').selectedIndex;
  const count=a>=0&&b>=a?rows.slice(a,b+1).reduce((n,m)=>n+phraseDuration(m),0):0;
  const valid=!!draft&&a>=0&&b>=a&&Number.isFinite(count)&&Math.abs(count-8)<1e-9;
  $('phraseSaveBtn').disabled=!valid;
  $('phraseSelection').textContent=!rows.length?'Add moves to this part first.':b<a?'Choose a last move after the first move.':valid?'Eight counts selected. Ready to save.':`${Number.isFinite(count)?count:'Unknown'} counts selected. Choose whole moves totaling exactly eight counts.`;
}

async function loadPhrases(force=false) {
  if(phraseLoading){await phraseLoading;if(force)return loadPhrases();return;}
  phraseLoading=(async()=>{try{const response=await api('/api/creator/phrases?include_archived=true');phraseRows=response.phrases;phraseLoaded=true;renderPhraseList();}catch(error){phraseMessage(error.message);}finally{phraseLoading=null;}})();
  return phraseLoading;
}

async function savePhraseSelection(event) {
  event.preventDefault();const part=selectedPart(),a=$('phraseFirst').selectedIndex,b=$('phraseLast').selectedIndex;
  if(!part||a<0||b<a)return;
  const rows=clone(part.moves.slice(a,b+1)), name=$('phraseName').value.trim();
  if(!name)return;
  $('phraseSaveBtn').disabled=true;phraseMessage('Saving phrase…');
  try{await api('/api/creator/phrases',{method:'POST',body:{name,moves:rows}});if($('phraseName').value.trim()===name)$('phraseName').value='';await loadPhrases(true);phraseMessage(`Saved “${name}” for any dance.`);}
  catch(error){phraseMessage(error.message);}finally{updatePhraseSelection();}
}

function renderPhraseList() {
  if(!$('phraseList'))return;
  const q=$('phraseSearch').value.trim().toLowerCase(), favorites=$('phraseFavorites').checked, archived=$('phraseArchived').checked;
  const rows=phraseRows.filter(r=>(archived||!r.archived)&&(!favorites||r.favorite)&&`${r.name} ${r.notes} ${r.moves.map(m=>m.name).join(' ')}`.toLowerCase().includes(q));
  $('phraseList').innerHTML=rows.map(r=>`<article class="phrase-tile"><div class="section-heading"><strong>${escapeHtml(r.name)}</strong><button class="subtle" data-phrase-favorite="${r.id}" aria-pressed="${r.favorite}" aria-label="${r.favorite?'Remove favorite':'Favorite'} ${escapeHtml(r.name)}">${r.favorite?'★':'☆'}</button></div>
    <p>${escapeHtml(r.moves.map(m=>m.name||'Written move').join(' · '))}</p><small>Eight counts · ${r.moves.length} moves${r.archived?' · Archived':''}</small>
    <div class="actions">${r.archived?`<button data-phrase-archive="${r.id}">Restore phrase</button>`:`<button data-phrase-preview="${r.id}">Preview &amp; insert</button><button data-phrase-mirror="${r.id}">Mirror &amp; preview</button>`}<button class="subtle" data-phrase-rename="${r.id}">Rename</button>${!r.archived?`<button class="subtle" data-phrase-archive="${r.id}">Archive</button>`:''}</div></article>`).join('')||`<p>${phraseLoaded?'No matching phrases yet. Save eight counts from a dance to begin.':'Open this panel to load your saved phrases.'}</p>`;
  $('phraseList').querySelectorAll('[data-phrase-favorite]').forEach(b=>b.onclick=()=>editPhrase(b.dataset.phraseFavorite,r=>({favorite:!r.favorite})));
  $('phraseList').querySelectorAll('[data-phrase-archive]').forEach(b=>b.onclick=()=>editPhrase(b.dataset.phraseArchive,r=>({archived:!r.archived})));
  $('phraseList').querySelectorAll('[data-phrase-rename]').forEach(b=>b.onclick=async()=>{const record=phraseRows.find(r=>r.id===b.dataset.phraseRename);if(!record)return;const name=await askText('Phrase name:',record.name);if(name?.trim())editPhrase(record.id,()=>({name:name.trim()}),record.version);});
  $('phraseList').querySelectorAll('[data-phrase-preview]').forEach(b=>b.onclick=()=>previewPhrase(b.dataset.phrasePreview,false));
  $('phraseList').querySelectorAll('[data-phrase-mirror]').forEach(b=>b.onclick=()=>previewPhrase(b.dataset.phraseMirror,true));
}

async function editPhrase(id,fields,expectedVersion) {
  const record=phraseRows.find(r=>r.id===id);if(!record)return;
  try{await api('/api/creator/phrases/'+id,{method:'PATCH',body:{expected_version:expectedVersion??record.version,fields:fields(record)}});await loadPhrases(true);phraseMessage('Phrase updated. Existing dances keep their inserted copies.');}
  catch(error){phraseMessage(error.message);if(error.status===409)await loadPhrases(true);}
}

function phraseInstructions(move) {
  const def=move.definition?{...move.definition,...move}:move;
  if(Array.isArray(def.events))return def.events.map(e=>e.text||e.action_text||'').join(' · ');
  return(def.lines||[]).map(l=>l.text).join(' · ')||def.text||def.explanation||'';
}

async function previewPhrase(id,mirrored) {
  const record=phraseRows.find(r=>r.id===id);if(!record)return;
  const context=phraseContext(),position=$('phraseInsertAt').value;
  phraseMessage('Preparing phrase preview…');
  try{
    const result=await api(`/api/creator/phrases/${id}/insertion`,{method:'POST',body:{expected_version:record.version,mirrored}});
    if(!phraseContextMatches(context))return phraseMessage('The selected dance changed. Preview the phrase again.');
    phrasePreview={id,version:record.version,mirrored,context,position};
    $('phrasePreviewTitle').textContent=result.name+(mirrored?' · Mirrored':'');
    $('phrasePreviewNotice').textContent=result.notice;
    let count=0;
    $('phrasePreviewRows').innerHTML=result.moves.map(m=>{const start=count;count+=phraseDuration(m);const facing=m.required_start_facing??m.events?.[0]?.facing_before_deg;return`<article class="phrase-tile"><strong>${phraseLabel(start)} · ${escapeHtml(m.name)}</strong><p>${escapeHtml(phraseInstructions(m))}</p>${facing!=null?`<p>Required entry facing: ${escapeHtml(typeof MoveTiming!=='undefined'?MoveTiming.facing(facing):facing+'°')}</p>`:''}</article>`;}).join('');
    $('phrasePreviewStatus').textContent=draft?`Insert in ${project.name||'this dance'} · ${selectedPart()?.name||'this part'}${position==='end'?' at the end':', before the selected move'}.`:'Open a dance to insert this phrase.';
    $('phraseInsertBtn').disabled=!draft;$('phrasePreviewDialog').showModal();phraseMessage('');
  }catch(error){phraseMessage(error.message);if(error.status===409)await loadPhrases();}
}

async function insertPreviewedPhrase() {
  const preview=phrasePreview;if(!preview)return;
  if(!phraseContextMatches(preview.context)){$('phraseInsertBtn').disabled=true;return $('phrasePreviewStatus').textContent='The dance changed. Close and preview this phrase again.';}
  $('phraseInsertBtn').disabled=true;
  try{
    const result=await api(`/api/creator/phrases/${preview.id}/insertion`,{method:'POST',body:{expected_version:preview.version,mirrored:preview.mirrored}});
    if(!phraseContextMatches(preview.context))throw new Error('The dance changed. Close and preview this phrase again.');
    const part=selectedPart(),index=preview.position==='end'?part.moves.length:part.moves.findIndex((m,i)=>(m.id||String(i))===preview.position);
    if(index<0)throw new Error('The insertion position changed. Preview the phrase again.');
    change(()=>part.moves.splice(index,0,...clone(result.moves)));
    $('phrasePreviewDialog').close();phrasePreview=null;notify(result.notice);
  }catch(error){$('phrasePreviewStatus').textContent=error.message;if(error.status===409)await loadPhrases();}
  finally{if(phrasePreview)$('phraseInsertBtn').disabled=false;}
}

ensurePhraseUI();
