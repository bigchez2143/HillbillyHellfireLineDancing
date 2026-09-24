/* Local choreography workspace. Provider credentials never enter this state. */
"use strict";
const $ = id => document.getElementById(id);
const clone = value => structuredClone(value);
const escapeHtml = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const numeric = value => { const p = String(value ?? 0).split("/"); return Number(p[0]) / (p.length > 1 ? Number(p[1]) : 1); };
let profileStorage=null;
function browserPreferenceSnapshot(){let custom=[];try{custom=JSON.parse(profileStorage.get("resources")||"[]");}catch{}return {mode:$("detailMode").value,resources:custom,lastProject:profileStorage?.get("lastProject")||""};}
async function initializeBrowserProfile(){const info=await api("/api/creator/backup/profile");profileStorage=LineDanceProfileStorage.create(localStorage,info);const mode=profileStorage.get("mode");$("detailMode").value=["basic","advanced"].includes(mode)?mode:"basic";document.body.dataset.mode=$("detailMode").value;$("detailMode").disabled=false;}
const uid = prefix => prefix + "-" + crypto.randomUUID();
let project = null, workspace = null, draft = null, compiled = null, moves = [], projects = [], catalog = [], moveCoverage = {};
let activePart = "A", currentView = "home", cleanJSON = "", undoStack = [], redoStack = [], saving = null, saveTimer = null, compileTimer = null, changeVersion = 0;
let pendingCandidates=null, pendingCandidateContext=null, openRequest=0, generationRequest=0;
let compileRequest = 0, nextStart = "edit", taps = [], analysisPoll = null;
let playing = false, practicePosition = 0, playbackOrigin = 0, playbackTime = 0, lastBeat = null, lastCue = null, audioContext = null, countInRemaining = 0;
let communityShelf = null, communityEditId = "";

async function api(path, options = {}) {
  const init = {...options};
  if (options.body && !(options.body instanceof FormData)) { init.headers = {...options.headers,"Content-Type":"application/json"}; init.body = JSON.stringify(options.body); }
  const response = await fetch(path, init);
  if (!response.ok) { const data = await response.json().catch(() => ({})); const err = new Error(typeof data.detail === "string" ? data.detail : data.detail?.message || data.message || `Request failed (${response.status})`); err.status = response.status; err.data = data; throw err; }
  return response.json();
}
document.body.insertAdjacentHTML('beforeend','<dialog id="textPromptDialog"><form id="textPromptForm"><h2 id="textPromptLabel"></h2><label>Value<input id="textPromptValue" required></label><div class="actions"><button type="button" id="textPromptCancel">Cancel</button><button class="primary">Continue</button></div></form></dialog>');
function askText(question,initial=''){return new Promise(resolve=>{askText.resolve=resolve;$('textPromptLabel').textContent=question;$('textPromptValue').value=initial;$('textPromptDialog').showModal();$('textPromptValue').focus();$('textPromptValue').select();});}
$('textPromptForm').onsubmit=e=>{e.preventDefault();const value=$('textPromptValue').value;askText.resolve?.(value);askText.resolve=null;$('textPromptDialog').close();};
$('textPromptCancel').onclick=()=>$('textPromptDialog').close();$('textPromptDialog').onclose=()=>{askText.resolve?.(null);askText.resolve=null;};
document.body.insertAdjacentHTML('beforeend','<dialog id="confirmActionDialog"><h2>Review this action</h2><p id="confirmActionText"></p><div class="actions"><button id="confirmActionCancel">Cancel</button><button id="confirmActionAccept" class="primary">Continue</button></div></dialog>');
function askConfirm(message){return new Promise(resolve=>{askConfirm.resolve=resolve;$('confirmActionText').textContent=message;$('confirmActionDialog').showModal();});}
$('confirmActionAccept').onclick=()=>{askConfirm.resolve?.(true);askConfirm.resolve=null;$('confirmActionDialog').close();};$('confirmActionCancel').onclick=()=>$('confirmActionDialog').close();$('confirmActionDialog').onclose=()=>{askConfirm.resolve?.(false);askConfirm.resolve=null;};
function notify(message) { $("notice").textContent = message; $("notice").classList.add("show"); clearTimeout(notify.timer); notify.timer = setTimeout(() => $("notice").classList.remove("show"), 5500); }
function status(text, state = "saved") { $("saveState").textContent = text; $("saveState").dataset.state = state; }
function dirty() { return draft && JSON.stringify(draft) !== cleanJSON; }
function backupDraft() { if (!project || !draft) return; try { profileStorage.set("recovery." + project.id, JSON.stringify({draft,revision:workspace.document_revision,when:Date.now()})); } catch { status("Unsaved · browser backup unavailable", "error"); } }
function change(operation, redraw = true) {
  if (!draft) return notify("Start or open a dance first.");
  undoStack.push(clone(draft)); if (undoStack.length > 80) undoStack.shift(); redoStack = [];
  operation(draft); changeVersion++; status("Unsaved changes", "dirty"); backupDraft();
  clearTimeout(saveTimer); saveTimer = setTimeout(() => save().catch(() => {}), 1200);
  if (redraw) renderEditor(); updateHistory(); scheduleCompile();
}
function updateHistory() { $("undoBtn").disabled = !undoStack.length; $("redoBtn").disabled = !redoStack.length; }
function restoreEdit(from, to) { if (!from.length) return; to.push(clone(draft)); draft = from.pop(); changeVersion++; renderForms(); renderEditor(); updateHistory(); scheduleCompile(); backupDraft(); status("Unsaved changes", "dirty"); clearTimeout(saveTimer); saveTimer = setTimeout(() => save().catch(() => {}), 1200); }
async function save() {
  if(!draft||!project)return;
  clearTimeout(saveTimer);
  if(saving){await saving;if(dirty())return save();return;}
  if(!dirty()){status('Saved locally');profileStorage.remove('recovery.'+project.id);return;}
  const payload=clone(draft),sentVersion=changeVersion,pid=project.id,revision=workspace.document_revision;
  status('Saving…','saving');
  saving=(async()=>{
    if(payload.music_map)await api('/api/creator/music-map/validate',{method:'POST',body:payload.music_map});
    const result=await api(`/api/projects/${encodeURIComponent(pid)}/workspace`,{method:'PUT',body:{expected_revision:revision,draft:payload}});
    if(project?.id!==pid)return;
    workspace=result;cleanJSON=JSON.stringify(payload);
    if(!dirty()){status('Saved locally');profileStorage.remove('recovery.'+pid);}else{status('Unsaved changes','dirty');backupDraft();}
  })().catch(err=>{if(project?.id===pid){status(err.status===409?'Save conflict · draft retained':'Save failed · draft retained','error');backupDraft();notify(err.status===409?'Another window changed this project. Your draft is retained in this browser. Reopen to review recovery.':err.message);}throw err;}).finally(()=>{saving=null;});
  await saving;
  if(project?.id===pid&&changeVersion!==sentVersion&&dirty()){clearTimeout(saveTimer);saveTimer=setTimeout(()=>save().catch(()=>{}),200);}
}
function requestStillCurrent(context){return project?.id===context.pid&&activePart===context.partId&&changeVersion===context.version;}
async function mergeRemoteWorkspace(pid){
  const [p,w]=await Promise.all([api(`/api/projects/${pid}`),api(`/api/projects/${pid}/workspace`)]);
  if(project?.id!==pid)return false;
  const merged=LineDanceMerge.merge(JSON.parse(cleanJSON),draft,w.draft);
  if(merged.conflicts.length){clearTimeout(saveTimer);backupDraft();status('Save conflict · draft retained','error');notify('Another window changed '+merged.conflicts.join(', ')+'. Reopen to review both drafts.');return false;}
  project=p;workspace=w;draft=merged.value;cleanJSON=JSON.stringify(w.draft);changeVersion++;return true;
}
function blankChoreography() { return {schema_version:1,start:{free_foot:"R",support:"L",facing_deg:"0"},meter:{beats:4,unit:4,group_counts:8},repeat:false,parts:[{id:"A",name:"Part A",kind:"part",moves:[]}],routine:[{id:uid("run"),part_id:"A",repeat:1}]}; }
function migrateChoreography() {
  if (draft.choreography?.parts) return;
  const doc = blankChoreography();
  let original = draft.editor?.moves || [];
  if (!original.length && workspace.accepted_dance) {
    const d = workspace.accepted_dance;
    original = d.source === "custom" ? d.custom || [] : d.candidates?.[d.chosen || 0]?.moves || [];
  }
  doc.parts[0].moves = original.map(item => {
    const concrete = item.lines ? item : moves.find(m => m.move_id === item.move_id && m.lead === (item.lead || "R"));
    return {...clone(concrete || {name:item.move_id || "Unresolved move",duration_counts:item.counts || "0",text:"Original move definition unavailable; restore the original definition."}),id:uid("move")};
  });
  draft.choreography = doc;
}
async function loadProjects() { projects = await api("/api/projects"); renderProjects(); }
function renderProjects() {
  const query = $("projectSearch").value.toLowerCase();
  const list = projects.filter(p => `${p.name} ${p.title || ""}`.toLowerCase().includes(query));
  $("projectList").innerHTML = list.length ? list.map(p => `<article class="project-tile"><small>${p.has_dance ? "DANCE SAVED" : "WORKING DRAFT"}</small><strong>${escapeHtml(p.name)}</strong><span>${p.has_audio ? "Local audio attached" : "No local audio"}</span><div class="tile-actions"><button type="button" data-project="${escapeHtml(p.id)}">Open dance</button><button type="button" data-publish="${escapeHtml(p.id)}">Publish</button></div></article>`).join("") : '<p class="empty">Your next dance starts here. Choose a starting path above.</p>';
  document.querySelectorAll("[data-project]").forEach(b => b.onclick = () => openProject(b.dataset.project).catch(e => notify(e.message)));
  document.querySelectorAll("[data-publish]").forEach(b => b.onclick = () => publishDance(b.dataset.publish));
}
async function openProject(pid, view = "edit") {
  const request=++openRequest,viewAtOpen=currentView;++compileRequest;stopPractice(); if (dirty()) await save();
  const versionBeforeOpen=changeVersion;
  const [p,w] = await Promise.all([api(`/api/projects/${encodeURIComponent(pid)}`),api(`/api/projects/${encodeURIComponent(pid)}/workspace`)]);
  if(request!==openRequest)return;
  if(changeVersion!==versionBeforeOpen&&dirty()){notify("The current draft changed while opening. Save it, then open the other dance again.");return;}
  project = p; workspace = w; draft = clone(w.draft || {}); const originalDraftJSON=JSON.stringify(draft); migrateChoreography(); draft.music_map ||= {bpm:p.analysis?.bpm || 120,first_count:0,meter:4,key:""};
  draft.song = clone(p.song || draft.song || {}); draft.sheet_meta ||= clone(p.sheet_meta || {});
  activePart = draft.choreography.parts[0]?.id || "A"; undoStack = []; redoStack = []; cleanJSON = originalDraftJSON; changeVersion = 0;
  const cached = profileStorage.get("recovery." + pid);
  if (cached) { try { const recovered = JSON.parse(cached); if (JSON.stringify(recovered.draft) !== cleanJSON && await askConfirm("This browser has a recovered draft. Restore it for review? The saved project stays unchanged until you save.")) { undoStack.push(clone(draft)); draft = recovered.draft; migrateChoreography(); changeVersion++; } } catch {} }
  profileStorage.set("lastProject", pid); $("projectTitle").textContent = p.name; $("saveBtn").disabled = false; $("versionsBtn").disabled = false; $("publishBtn").disabled = false;
  renderForms(); renderEditor(); updateHistory(); await compile(); showView(currentView===viewAtOpen?view:currentView); status(dirty() ? "Draft ready · unsaved" : w.recovery ? "Recovered saved copy" : "Saved locally", dirty() ? "dirty" : "saved");
}
function showView(view) { currentView = view; document.querySelectorAll("[data-page]").forEach(p => p.hidden = p.dataset.page !== view); document.querySelectorAll("[data-view]").forEach(b => b.classList.toggle("active", b.dataset.view === view)); if (view !== "practice") stopPractice(); document.querySelectorAll(".project-required").forEach(el => el.textContent = project ? "" : "Start or open a dance in My Dances to use this workspace."); if (view === "home") loadProjects().catch(e=>notify(e.message)); if(view === "moves") renderCatalog(); if(view === "practice") compile().then(renderPractice).catch(e=>notify(e.message)); if(view === "tools" && !communityShelf) loadCommunity().catch(e=>notify(e.message)); }
function renderForms() {
  if (!draft) return;
  const song = draft.song || {}, meta = draft.sheet_meta || {}, map = draft.music_map || {};
  for (const [id,value] of Object.entries({songTitle:song.title,songArtist:song.artist,spotifyUrl:meta.spotify_url,bpm:map.bpm || 120,firstCount:map.first_count || 0,meter:map.meter || 4,musicalKey:map.key,danceTitle:meta.dance_title || project.name,choreographer:meta.choreographer,levelLabel:meta.level_label,demoUrl:meta.youtube_url,sheetUrl:meta.sheet_url,sheetNotes:meta.description})) $(id).value = value ?? "";
  const plan = songPlan();
  $("audioName").textContent = plan.kind === "local" && project.song?.filename ? `${project.song.filename} — rehearsal plays this local file.` : LineDanceSongCard.help.localEmpty;
  $("practiceSource").textContent = plan.note;
  $("openSpotifyBtn").disabled = !plan.openUrl;
  $("copySpotifyBtn").disabled = !plan.openUrl;
  const url = LineDanceSongCard.playbackUrl(project.id, project.song, meta.spotify_url);
  if ($("musicAudio").getAttribute("src") !== url) { if (url) $("musicAudio").src = url; else $("musicAudio").removeAttribute("src"); }
  $("startFoot").value = draft.choreography.start?.free_foot || "R"; $("startFacing").value = draft.choreography.start?.facing_deg || "0"; $("countGrouping").value = draft.choreography.meter?.group_counts || 8; $("repeatDance").checked = !!draft.choreography.repeat;
  renderTimingAnchors(); refreshRecordingReview();
  $("musicEvidence").textContent = project.analysis ? `Measured BPM: ${project.analysis.bpm ?? "unknown"}. Your corrections are saved separately. Key ${map.key_source === "estimate" ? "estimate" : "entry"}: ${map.key || "unknown"}${map.key_source === "estimate" ? " ("+(map.key_estimate?.confidence||"unrated")+" confidence; review by ear)" : ""}.` : "Manual timing is available without audio analysis.";
}
function songPlan() { return LineDanceSongCard.rehearsalPlan(project?.song, draft?.sheet_meta?.spotify_url); }
function usesLocalFile() { return songPlan().kind === "local"; }
function selectedPart() { return draft?.choreography.parts.find(p => p.id === activePart) || draft?.choreography.parts[0]; }
function renderMoveChoices() {
  const query = $("moveSearch").value.toLowerCase(), level = $("moveLevel").value, lead = $("moveLead").value;
  const list = moves.filter(m => m.lead === lead && (level === "all" || m.level === level) && `${m.name} ${m.family} ${(m.aliases||[]).join(" ")}`.toLowerCase().includes(query));
  $("moveChoices").innerHTML = list.map(m => `<button class="move-choice" data-add-move="${escapeHtml(m.move_id)}"><span>${escapeHtml(m.name)}</span><small>${escapeHtml(m.definition_hash?packDurationLabel(m):m.counts+' counts')} ${m.definition_hash ? "Preview" : "＋"}</small></button>`).join("");
  document.querySelectorAll("[data-add-move]").forEach(b => b.onclick = () => {const chosen=moves.find(m=>m.move_id===b.dataset.addMove&&m.lead===lead);if(chosen?.definition_hash)return previewExpansionMove(chosen.move_id,lead);change(d => { const part = selectedPart(); let item = moves.find(m => m.move_id === b.dataset.addMove && m.lead === lead); if (item.start === "F") { const free = MoveTiming.endingFreeFoot(part.moves,d.choreography.start.free_foot);if(!free)return notify("The previous move’s ending support is unknown. Review it before adding a free-foot cue."); item = moves.find(m => m.move_id === b.dataset.addMove && m.lead === free) || item; } part.moves.push({...clone(item),id:uid("move")}); });});
}
function renderEditor() {
  renderMoveChoices(); if (!draft) {if(typeof renderPhrasePicker==="function")renderPhrasePicker();return;}
  const doc = draft.choreography, part = selectedPart(); if (!part) return; activePart = part.id;
  $("partSelect").innerHTML = doc.parts.map(p => `<option value="${escapeHtml(p.id)}">${escapeHtml(p.name || p.id)} · ${p.kind || "part"}</option>`).join(""); $("partSelect").value = activePart;
  let count = 0;
  $("sequence").innerHTML = part.moves.length ? part.moves.map((m,i) => { const duration = numeric(m.duration_counts ?? m.counts), start = count; count += duration; const text = m.text || m.action_text || (m.lines || []).map(l=>l.text).join("; ") || (m.events || []).map(e=>e.action_text || e.text).join("; "); return `<li id="move-${escapeHtml(m.id)}"><span class="count-label">${escapeHtml(MoveTiming.label(start))}${duration>1 ? "–"+escapeHtml(MoveTiming.label(count-1)) : ""}</span><div><strong>${escapeHtml(m.name || "Written move")}</strong><p>${escapeHtml(text)}</p></div><div class="row-actions">${m.definition_hash?`<button data-saved-preview="${i}" aria-label="Preview saved ${escapeHtml(m.name)} steps">Steps</button>`:""}<button data-lock="${i}" aria-label="${m.locked?"Unlock":"Lock"} ${escapeHtml(m.name)}">${m.locked?"Locked":"Lock"}</button><button data-order="${i}:up" aria-label="Move ${escapeHtml(m.name)} earlier">↑</button><button data-order="${i}:down" aria-label="Move ${escapeHtml(m.name)} later">↓</button><button data-order="${i}:remove" aria-label="Remove ${escapeHtml(m.name)} from this dance">×</button></div></li>`; }).join("") : '<li class="empty">Choose a move to start this part.</li>';
  document.querySelectorAll("[data-order]").forEach(b=>b.onclick=()=>change(()=>{const [index,action]=b.dataset.order.split(":"),i=+index;if(action==="remove")part.moves.splice(i,1);else{const j=i+(action==="up"?-1:1);if(j>=0&&j<part.moves.length)[part.moves[i],part.moves[j]]=[part.moves[j],part.moves[i]];}}));
  document.querySelectorAll("[data-saved-preview]").forEach(b=>b.onclick=()=>previewExpansionSnapshot(part.moves[+b.dataset.savedPreview]));
  document.querySelectorAll("[data-lock]").forEach(b=>b.onclick=()=>change(()=>{part.moves[+b.dataset.lock].locked=!part.moves[+b.dataset.lock].locked;}));
  $("routineList").innerHTML = doc.routine.map((r,i)=>`<div class="routine-row"><span>${i+1}.</span><label>Part<select data-routine="${i}:part_id">${doc.parts.map(p=>`<option value="${escapeHtml(p.id)}" ${p.id===r.part_id?"selected":""}>${escapeHtml(p.name)}</option>`).join("")}</select></label><label>Times<input data-routine="${i}:repeat" type="number" min="1" max="100" value="${r.repeat||1}"></label><label>Restart after count<input data-routine="${i}:end_after_counts" value="${escapeHtml(r.end_after_counts||"")}" placeholder="Whole part"></label><button data-remove-routine="${i}" aria-label="Remove order item ${i+1}">×</button></div>`).join("");
  document.querySelectorAll("[data-routine]").forEach(el=>el.onchange=()=>change(d=>{const [i,key]=el.dataset.routine.split(":");const r=d.choreography.routine[+i];if(key==="repeat")r[key]=Math.max(1,Math.min(100,+el.value||1));else if(key==="end_after_counts"){if(el.value.trim()){r[key]=el.value.trim();r.reason="restart";}else{delete r[key];delete r.reason;}}else r[key]=el.value;}));
  document.querySelectorAll("[data-remove-routine]").forEach(b=>b.onclick=()=>change(d=>d.choreography.routine.splice(+b.dataset.removeRoutine,1)));
  if(typeof renderPhrasePicker==="function")renderPhrasePicker();
}
function scheduleCompile() { clearTimeout(compileTimer); compileTimer=setTimeout(()=>compile().catch(e=>notify(e.message)),200); }
async function compile() {
  if(!draft)return; const token=++compileRequest;
  const result=await api("/api/creator/compile",{method:"POST",body:{document:draft.choreography}}); if(token!==compileRequest)return;
  compiled=result; const box=$("danceCheck"); box.className="check "+(result.status==="VALID"?"good":result.status==="INVALID"?"bad":"warning");
  box.textContent=`${result.total_counts || 0} counts · ${result.status === "VALID" ? "Count and stored movement checks passed" : result.status === "INVALID" ? "Needs attention" : "Some mechanics need review"}`;
  for(const issue of result.issues||[]){const b=document.createElement("button");b.textContent=issue.message || issue.code;b.onclick=()=>{ const part=draft.choreography.parts.find(p=>p.id===issue.part_id || p.moves.some(m=>m.id===issue.move_id));if(part){activePart=part.id;renderEditor();} const item=document.getElementById("move-"+issue.move_id);if(item)item.scrollIntoView({behavior:"smooth",block:"center"});};box.appendChild(b);}
  $("practiceSeek").max=numeric(result.total_counts)||1; $("loopEnd").max=numeric(result.total_counts)||1; return result;
}
async function renderCatalog() {renderExpansionLibrary();if(!catalog.length){const r=await api("/api/creator/catalog");catalog=r.steps||[];}$('catalogSummary').textContent=`${catalog.length} reference entries · ${moveCoverage.legacy_patterns||0} core patterns · ${moveCoverage.expansion_patterns||0} new timed variations (instructor review pending). Add any reference as a written move and review its timing. Vocabulary continues to grow; this is not a claim that every named variation is cataloged.`;const q=$('catalogSearch').value.toLowerCase();const list=catalog.map((m,index)=>({...m,referenceId:'reference-'+index})).filter(m=>`${m.name} ${(m.aliases||[]).join(' ')}`.toLowerCase().includes(q));$('catalogList').innerHTML=list.map(m=>`<article class="project-tile"><small>${escapeHtml(m.category.replaceAll('_',' '))} · ${escapeHtml(m.level)}</small><strong>${escapeHtml(m.name)}</strong><p>${escapeHtml(m.description)}</p><button data-use-reference="${m.referenceId}">Use as a written move</button><details class="advanced"><summary>Stored reference notes</summary><p>${escapeHtml(m.flags)}</p></details></article>`).join('');document.querySelectorAll('[data-use-reference]').forEach(button=>button.onclick=async()=>{if(!draft)return notify('Open a dance first.');const context={pid:project.id,partId:activePart,version:changeVersion};try{let snapshot=await api(`/api/creator/library/reference/${button.dataset.useReference}/snapshot`);if(snapshot.requires_counts){const count=await askText('How many counts will this move or styling action use?','4');if(count===null)return;snapshot=await api(`/api/creator/library/reference/${button.dataset.useReference}/snapshot?duration_counts=${encodeURIComponent(count)}`);}if(!requestStillCurrent(context))return notify('The selected dance changed; add the move again.');change(()=>selectedPart().moves.push({...snapshot,id:uid('reference-move')}));showView('edit');notify('Reference added with mechanics marked for review.');}catch(e){notify(e.message);}});}
function safeUrl(value) { try{const u=new URL(value);return ["https:","http:"].includes(u.protocol)?u.href:null;}catch{return null;} }
async function loadCommunity(){
  communityShelf ||= LineDanceCommunity.create(api);
  await communityShelf.load();
  if(!communityShelf.saved && profileStorage){
    let custom=[]; try{custom=JSON.parse(profileStorage.get("resources")||"[]");}catch{}
    let added=0;
    for(const link of custom){try{communityShelf.add(link); added++;}catch{}}
    if(added){try{await communityShelf.save(); profileStorage.remove("resources");}catch(e){await communityShelf.load(); $("communityStatus").textContent=e.message;}}
  }
  renderCommunity();
}
function renderCommunity(){
  if(!$("communityLinks")||!communityShelf)return;
  const links=communityShelf.links.filter(link=>safeUrl(link.url));
  $("communityLinks").innerHTML=links.length?links.map(link=>`<div class="community-row"><div><a href="${escapeHtml(safeUrl(link.url))}" target="_blank" rel="noopener noreferrer">${escapeHtml(link.name)} ↗</a>${link.note?`<p>${escapeHtml(link.note)}</p>`:""}</div><div class="actions"><button type="button" data-community-edit="${escapeHtml(link.id)}">Edit</button><button type="button" data-community-remove="${escapeHtml(link.id)}">Remove</button></div></div>`).join(""):'<p class="empty">No links yet. Add a website below, or restore the starter links.</p>';
  document.querySelectorAll("[data-community-edit]").forEach(button=>button.onclick=()=>beginCommunityEdit(button.dataset.communityEdit));
  document.querySelectorAll("[data-community-remove]").forEach(button=>button.onclick=()=>removeCommunityLink(button.dataset.communityRemove));
  if(communityShelf.warning)$("communityStatus").textContent=communityShelf.warning;
}
function beginCommunityEdit(id){
  const link=communityShelf?.links.find(item=>item.id===id); if(!link)return;
  communityEditId=id; $("communityName").value=link.name; $("communityUrl").value=link.url; $("communityNote").value=link.note||"";
  $("communitySave").textContent="Save changes"; $("communityCancelEdit").hidden=false; $("communityName").focus();
}
function cancelCommunityEdit(){communityEditId=""; $("communityForm").reset(); $("communitySave").textContent="Add link"; $("communityCancelEdit").hidden=true;}
async function removeCommunityLink(id){
  if(!await askConfirm("Remove this link? You can add it again later."))return;
  communityShelf.remove(id); if(communityEditId===id)cancelCommunityEdit();
  try{await communityShelf.save(); $("communityStatus").textContent="Saved on this computer."; renderCommunity();}
  catch(e){$("communityStatus").textContent=e.message; await communityShelf.load().catch(()=>{}); renderCommunity();}
}
function publishOptions(){return {paper:$("paperSize").value||"letter", large_print:!!$("largePrint").checked, print_qr:!!$("printQR").checked, include_lyrics:!!$("includeLyrics").checked};}
function showPublishPicker(pid, view){
  $("publishNote").textContent=view.note; $("publishFolder").value=view.folder;
  $("publishFiles").innerHTML=view.files.map(file=>`<li><strong>${escapeHtml(file.label)}</strong> — ${escapeHtml(file.name)}</li>`).join("");
  $("publishDestinations").innerHTML=view.destinations.map(item=>`<button type="button" data-publish-url="${escapeHtml(item.url)}">${escapeHtml(item.name)}</button>`).join("");
  $("publishDestinations").querySelectorAll("[data-publish-url]").forEach(button=>button.onclick=()=>{window.open(button.dataset.publishUrl,"_blank","noopener,noreferrer"); $("publishStatus").textContent=button.textContent+" is open. Upload the step sheet there yourself.";});
  $("publishCopyFolder").onclick=async()=>{try{await navigator.clipboard.writeText(view.folder); $("publishStatus").textContent="Folder path copied.";}catch{$("publishFolder").focus(); $("publishFolder").select(); $("publishStatus").textContent="Select the folder path and copy it.";}};
  $("publishShowFolder").onclick=async()=>{try{await api(`/api/creator/projects/${encodeURIComponent(pid)}/publish-pack/open`,{method:"POST",body:{folder:view.folder}}); $("publishStatus").textContent="The folder is open on this computer.";}catch(e){$("publishStatus").textContent=e.message;}};
  $("publishStatus").textContent="Ready. Nothing was sent to a website.";
  if(!$("publishDialog").open)$("publishDialog").showModal();
}
async function publishDance(pid){
  if(!pid)return notify("Open a dance first.");
  const current=project?.id;
  try{
    if(draft && (pid===current || dirty())) await save();
    if(current && project?.id!==current)return;
    const pack=await api(`/api/creator/projects/${encodeURIComponent(pid)}/publish-pack`,{method:"POST",body:publishOptions()});
    showPublishPicker(pid, LineDancePublish.publishView(pack));
  }catch(e){notify(e.message);}
}
async function legacy(tab="song",ai=false) { const pid=project?.id;try{await save();if(project?.id!==pid)return;const q=new URLSearchParams({project:pid||"",tab});if(ai)q.set("ai","1");location.href="/legacy?"+q;}catch{} }
async function openVersions() { if(!project)return;const pid=project.id;await save();if(project?.id!==pid)return;const r=await api(`/api/projects/${pid}/versions`);if(project?.id!==pid)return;const list=Array.isArray(r)?r:r.versions||[];$("versionList").innerHTML=list.length?list.map(v=>`<div class="version-row"><div><strong>${escapeHtml(v.label || v.name || v.id)}</strong><small> · ${escapeHtml(v.created_at ? new Date(v.created_at*1000).toLocaleString() : "")}</small></div><button data-restore-version="${escapeHtml(v.id || v.version_id)}">Restore draft</button></div>`).join(""):'<p class="empty">Save a named milestone before a major change.</p>';document.querySelectorAll("[data-restore-version]").forEach(b=>b.onclick=async()=>{if(!await askConfirm("Restore this version as a new working draft? The current draft remains recoverable."))return;try{if(project?.id!==pid)return;await save();if(project?.id!==pid)return;await api(`/api/projects/${pid}/versions/${b.dataset.restoreVersion}/restore`,{method:"POST",body:{expected_revision:workspace.document_revision}});if(project?.id!==pid)return;cleanJSON=JSON.stringify(draft);await openProject(pid,currentView);$("versionDialog").close();notify("Draft restored; accepted dance preserved.");}catch(e){notify(e.message);}});$("versionDialog").showModal();}

/* Rehearsal uses the compiler's occurrence timeline, never a second footwork engine. */
function practiceOccurrences(){return (compiled?.events||[]).map(e=>({...e,part_name:compiled.occurrences.find(o=>o.id===e.occurrence_id)?.part_name}));}
function occurrenceStart(o){return numeric(o.start_count ?? o.start ?? o.offset_counts);}
function occurrenceEnd(o){return numeric(o.end_count ?? o.end ?? (occurrenceStart(o)+numeric(o.duration_counts)));}
function renderPractice(){const list=practiceOccurrences(),pos=Math.max(0,practicePosition),o=list.find(x=>pos>=occurrenceStart(x)&&pos<occurrenceEnd(x))||list[0];if(!o){$("practiceMove").textContent="Add moves to begin";return;}const index=list.indexOf(o),group=+(draft.choreography.meter?.group_counts||8);$("practiceCount").textContent=countInRemaining>0?Math.ceil(countInRemaining):MoveTiming.practice(pos,occurrenceStart(o),group);$("practiceMove").textContent=countInRemaining>0?"Ready…":o.name||o.move_name||"Move";$("practicePart").textContent=o.part_name||o.part_id||"Part A";$("practiceFacing").textContent=MoveTiming.facing(o.state_before?.facing_deg ?? o.before?.facing_deg);$("practiceInstruction").textContent=o.instruction || (o.lines||[]).map(l=>l.text).join("; ") || o.text || (compiled.events||[]).filter(e=>e.id===o.id).map(e=>e.action_text||e.text||"").join("; ");$("practiceNext").textContent=list[index+1]?.name||list[index+1]?.move_name||(draft.choreography.repeat?list[0]?.move_name:"Finish");$("practiceSeek").value=pos;const beat=Math.floor(practicePosition);if(playing&&beat!==lastBeat){lastBeat=beat;if($("metronome").checked)tick(beat%group===0);}if(playing&&countInRemaining<=0&&o.id!==lastCue){lastCue=o.id;if($("voiceCues").checked&&"speechSynthesis"in window){speechSynthesis.cancel();const utterance=new SpeechSynthesisUtterance(o.name||o.move_name||"");const localVoice=speechSynthesis.getVoices().find(v=>v.localService);if(localVoice){utterance.voice=localVoice;speechSynthesis.speak(utterance);}else{$("practiceStatus").textContent="No local voice available; visual cues remain active.";}}}}
function tick(accent){try{audioContext ||= new (window.AudioContext||window.webkitAudioContext)();const osc=audioContext.createOscillator(),gain=audioContext.createGain();osc.frequency.value=accent?1000:650;gain.gain.setValueAtTime(.12,audioContext.currentTime);gain.gain.exponentialRampToValueAtTime(.001,audioContext.currentTime+.065);osc.connect(gain).connect(audioContext.destination);osc.start();osc.stop(audioContext.currentTime+.07);}catch{}}
function stopPractice(reset=false){playing=false;$("musicAudio").pause();if("speechSynthesis"in window)speechSynthesis.cancel();$("practicePlay").textContent="Play";if(reset){practicePosition=0;lastBeat=null;lastCue=null;countInRemaining=0;renderPractice();}}
function mapValue(value, source, target) {
  const m=draft.music_map||{}, points=m.anchors||[], fallback=source==='count'?x=>(+m.first_count||0)+x*60/(+m.bpm||120):x=>(x-(+m.first_count||0))*(+m.bpm||120)/60;
  if(!points.length)return fallback(value);
  if(points.length===1)return points[0][target]+fallback(value)-fallback(points[0][source]);
  let i=0;while(i<points.length-2&&value>points[i+1][source])i++;const a=points[i],b=points[i+1];
  return a[target]+(value-a[source])*(b[target]-a[target])/(b[source]-a[source]);
}
function countToTime(count){return mapValue(count,'count','time');}
function timeToCount(time){return mapValue(time,'time','count');}
function practiceFrame(now){if(!playing)return;const speed=+$("practiceSpeed").value,bpm=+(draft.music_map?.bpm||120),audio=$("musicAudio"),total=numeric(compiled.total_counts);if(countInRemaining>0){countInRemaining=Math.max(0,playbackOrigin-(now-playbackTime)/1000*bpm/60*speed);practicePosition=-countInRemaining;renderPractice();if(countInRemaining===0){practicePosition=0;playbackOrigin=0;playbackTime=now;if(usesLocalFile()){audio.currentTime=countToTime(0);audio.play().catch(e=>{stopPractice();notify(e.message);});}}}else{practicePosition=usesLocalFile()?timeToCount(audio.currentTime):playbackOrigin+(now-playbackTime)/1000*bpm/60*speed;const looping=$("loopEnabled").checked,start=Math.max(0,+$("loopStart").value-1),end=Math.min(total,+$("loopEnd").value);if(looping&&end>start&&practicePosition>=end){practicePosition=start;playbackOrigin=start;playbackTime=now;if(usesLocalFile())audio.currentTime=countToTime(start);lastCue=null;}else if(practicePosition>=total){if(draft.choreography.repeat){practicePosition=0;playbackOrigin=0;playbackTime=now;if(usesLocalFile())audio.currentTime=countToTime(0);lastCue=null;}else{stopPractice();practicePosition=Math.max(0,total-.001);}}renderPractice();}if(playing)requestAnimationFrame(practiceFrame);}
async function playPractice(){if(playing){stopPractice();return;}if(!draft)return notify("Open a dance first.");const pid=project.id,version=changeVersion;await compile();if(project?.id!==pid||changeVersion!==version)return;if(!numeric(compiled.total_counts))return notify("Add moves before rehearsing.");if(compiled.status==="INVALID")return notify("Resolve the count or movement errors before rehearsal.");playing=true;lastBeat=null;lastCue=null;const audio=$("musicAudio");audio.playbackRate=+$("practiceSpeed").value;audio.preservesPitch=true;countInRemaining=practicePosition===0?+$("practiceCountIn").value:0;playbackOrigin=countInRemaining||practicePosition;playbackTime=performance.now();if(!countInRemaining&&usesLocalFile()){audio.currentTime=countToTime(practicePosition);try{await audio.play();}catch(e){stopPractice();return notify(e.message);}}$("practicePlay").textContent="Pause";requestAnimationFrame(practiceFrame);}

/* Bindings are deliberately explicit so saved fields have a clear contract. */
document.querySelectorAll("[data-view]").forEach(b=>b.onclick=()=>showView(b.dataset.view));
document.querySelectorAll("[data-close]").forEach(b=>b.onclick=()=>$(b.dataset.close).close());
$("detailMode").value="basic";$("detailMode").disabled=true;document.body.dataset.mode="basic";
$("detailMode").onchange=()=>{document.body.dataset.mode=$("detailMode").value;profileStorage.set("mode",$("detailMode").value);if(currentView==="studio"&&$("detailMode").value==="basic")showView("settings");};
$("startManual").onclick=()=>{nextStart="edit";$("newDialog").showModal();$("newName").focus();};$("startMusic").onclick=()=>{nextStart="music";$("newDialog").showModal();$("newName").focus();};
$("newForm").onsubmit=async e=>{e.preventDefault();try{const p=await api("/api/projects",{method:"POST",body:{name:$("newName").value.trim(),artist:""}});await openProject(p.id,nextStart);$("newDialog").close();$("newName").value="";}catch(err){$("newError").textContent=err.message;}};
$("projectSearch").oninput=renderProjects;$("saveBtn").onclick=()=>save().catch(()=>{});$("undoBtn").onclick=()=>restoreEdit(undoStack,redoStack);$("redoBtn").onclick=()=>restoreEdit(redoStack,undoStack);$("versionsBtn").onclick=()=>openVersions().catch(e=>notify(e.message));
$("versionForm").onsubmit=async e=>{e.preventDefault();const pid=project?.id;if(!pid)return;try{await save();if(project?.id!==pid)return;await api(`/api/projects/${pid}/versions`,{method:"POST",body:{expected_revision:workspace.document_revision,label:$("versionName").value.trim()}});if(project?.id!==pid)return;await mergeRemoteWorkspace(pid);$("versionDialog").close();await openVersions();$("versionName").value="";}catch(err){notify(err.message);}};
$("moveSearch").oninput=renderMoveChoices;$("moveLevel").onchange=renderMoveChoices;$("moveLead").onchange=renderMoveChoices;$("partSelect").onchange=()=>{activePart=$("partSelect").value;renderEditor();};
$("addPartBtn").onclick=async()=>{if(!draft)return;const name=await askText("Name this part, tag or ending:","Part "+String.fromCharCode(65+draft.choreography.parts.length));if(!name?.trim())return;change(d=>{const id=uid("part");d.choreography.parts.push({id,name:name.trim(),kind:/tag/i.test(name)?"tag":/ending/i.test(name)?"ending":"part",moves:[]});activePart=id;});};
$("renamePartBtn").onclick=async()=>{const p=selectedPart();if(!p)return;const name=await askText("Part name:",p.name);if(name?.trim())change(()=>p.name=name.trim());};$("addRoutineBtn").onclick=()=>change(d=>d.choreography.routine.push({id:uid("run"),part_id:activePart,repeat:1}));
$("startFoot").onchange=()=>change(d=>{d.choreography.start.free_foot=$("startFoot").value;d.choreography.start.support=$("startFoot").value==="R"?"L":"R";});$("startFacing").onchange=()=>change(d=>d.choreography.start.facing_deg=$("startFacing").value);$("countGrouping").onchange=()=>change(d=>d.choreography.meter.group_counts=+$("countGrouping").value);$("repeatDance").onchange=()=>change(d=>d.choreography.repeat=$("repeatDance").checked);
$("addWrittenBtn").onclick=()=>{if(draft)$("writtenDialog").showModal();};$("writtenForm").onsubmit=e=>{e.preventDefault();const counts=$("writtenCounts").value.trim();if(!Number.isFinite(numeric(counts))||numeric(counts)<=0)return notify("Enter a positive count value, such as 4 or 1/2.");change(()=>{const event={offset_counts:"0",duration_counts:counts,text:$("writtenText").value.trim()};if($("writtenFoot").value!=="unknown")event.support_after=({R:"L",L:"R",SAME:"same"})[$("writtenFoot").value];if($("writtenTurn").value!=="")event.rotation_deg=$("writtenTurn").value;selectedPart().moves.push({id:uid("written"),name:$("writtenName").value.trim(),duration_counts:counts,events:[event],review_status:"unverified"});});$("writtenDialog").close();e.target.reset();$("writtenCounts").value="4";};
const fieldMap={songTitle:["song","title"],songArtist:["song","artist"],bpm:["music_map","bpm"],firstCount:["music_map","first_count"],meter:["music_map","meter"],musicalKey:["music_map","key"],danceTitle:["sheet_meta","dance_title"],choreographer:["sheet_meta","choreographer"],levelLabel:["sheet_meta","level_label"],demoUrl:["sheet_meta","youtube_url"],sheetUrl:["sheet_meta","sheet_url"],sheetNotes:["sheet_meta","description"]};
for(const[id,[group,key]]of Object.entries(fieldMap))$(id).onchange=()=>change(d=>{d[group]||={};d[group][key]=$(id).type==="number"?+$(id).value:$(id).value;if(id==="meter")d.choreography.meter.beats=+$(id).value;if(id==="bpm")d.music_map.manually_corrected=true;if(id==="musicalKey")d.music_map.key_source="manual";},false);
function renderTimingAnchors(){const anchors=draft?.music_map?.anchors||[];$("timingAnchors").innerHTML=anchors.length?anchors.map((a,i)=>`<div class="version-row"><span>Count ${a.count+1} → ${a.time.toFixed(3)} seconds</span><button data-remove-anchor="${i}">Remove</button></div>`).join(""):'<p class="muted">Using steady BPM and your first-count time.</p>';document.querySelectorAll("[data-remove-anchor]").forEach(b=>b.onclick=()=>change(d=>{d.music_map.anchors.splice(+b.dataset.removeAnchor,1);renderTimingAnchors();},false));}
$("addAnchorBtn").onclick=async()=>{if(!draft)return;const anchorPid=project.id,anchorVersion=changeVersion;const map=clone(draft.music_map);map.anchors||=[];map.anchors.push({count:+$("anchorCount").value-1,time:+$("anchorTime").value});map.anchors.sort((a,b)=>a.count-b.count);try{await api("/api/creator/music-map/validate",{method:"POST",body:map});if(project?.id!==anchorPid||changeVersion!==anchorVersion)return notify("The draft changed; add the timing anchor again.");change(d=>d.music_map=map,false);renderTimingAnchors();}catch(e){notify(e.message);}};
$("clearAnchorsBtn").onclick=()=>{change(d=>d.music_map.anchors=[],false);renderTimingAnchors();};
$("detectedGridBtn").onclick=async()=>{const beats=(project?.analysis?.beat_times||[]).filter(t=>t>=+(draft?.music_map?.first_count||0));if(beats.length<2)return notify("Analyze the recording and choose its first dance beat first.");if(!await askConfirm("Use the detected beat grid from the first beat at or after count one? Review the result by ear before relying on it."))return;change(d=>{d.music_map.anchors=beats.map((time,count)=>({count,time}));d.music_map.grid_source="detected_needs_review";},false);renderTimingAnchors();};
$("lockPartBtn").onclick=()=>{const part=selectedPart();if(!part)return;const locked=!part.moves.every(m=>m.locked);change(()=>part.moves.forEach(m=>m.locked=locked));};
$("tapBtn").onclick=()=>{const now=performance.now();if(taps.length&&now-taps.at(-1)>2500)taps=[];taps.push(now);taps=taps.slice(-9);if(taps.length>1){$("bpm").value=(60000*(taps.length-1)/(now-taps[0])).toFixed(2);$("bpm").onchange();}};$("halfTempoBtn").onclick=()=>{$("bpm").value=(+$("bpm").value/2).toFixed(2);$("bpm").onchange();};$("doubleTempoBtn").onclick=()=>{$("bpm").value=(+$("bpm").value*2).toFixed(2);$("bpm").onchange();};$("setFirstCountBtn").onclick=()=>{$("firstCount").value=$("musicAudio").currentTime.toFixed(2);$("firstCount").onchange();};
$("spotifyUrl").onchange=()=>{if(!draft)return notify("Start or open a dance first.");let next="";const raw=$("spotifyUrl").value.trim();if(raw){try{next=LineDanceSongCard.normalizeSpotifyUrl(raw);}catch(e){$("spotifyUrl").value=draft.sheet_meta?.spotify_url||"";notify(e.message);return;}}if((draft.sheet_meta?.spotify_url||"")===next){$("spotifyUrl").value=next;renderForms();return;}change(d=>{d.sheet_meta||={};d.sheet_meta.spotify_url=next;},false);renderForms();};
$("openSpotifyBtn").onclick=()=>{const plan=songPlan();if(!plan.openUrl)return notify("Paste a Spotify song, album, or playlist link first.");window.open(plan.openUrl,"_blank","noopener,noreferrer");};
$("copySpotifyBtn").onclick=async()=>{const plan=songPlan();if(!plan.openUrl)return notify("Paste a Spotify song, album, or playlist link first.");try{await navigator.clipboard.writeText(plan.openUrl);notify("Spotify link copied.");}catch{$("spotifyUrl").focus();$("spotifyUrl").select();notify("Select the Spotify link and copy it.");}};
$("songFile").onchange=async()=>{if(!project)return notify('Start a dance first.');const file=$('songFile').files[0],pid=project.id;if(!file)return;try{await save();if(project?.id!==pid)return;const form=new FormData();form.append('file',file);await api(`/api/projects/${pid}/song-upload`,{method:'POST',body:form});if(project?.id===pid){await mergeRemoteWorkspace(pid);renderForms();showView('music');}notify('Local audio file attached. Review its timing before rehearsal.');}catch(e){notify(e.message);}};
$("analyzeBtn").onclick=async()=>{if(!usesLocalFile())return notify('Add a local audio file first. The Spotify link does not play here.');const pid=project.id;try{await save();if(project?.id!==pid)return;await api(`/api/projects/${pid}/analyze`,{method:'POST'});if(project?.id!==pid)return;$('analysisStatus').textContent='Analyzing the recording…';clearInterval(analysisPoll);let polling=false;analysisPoll=setInterval(async()=>{if(polling)return;polling=true;try{const r=await api(`/api/projects/${pid}/analysis-status`);if(project?.id!==pid){clearInterval(analysisPoll);return;}if(r.status==='done'||r.status==='complete'||r.analysis){clearInterval(analysisPoll);if(!await mergeRemoteWorkspace(pid))return;change(d=>{d.music_map.measured_bpm=project.analysis?.bpm;if(!d.music_map.manually_corrected)d.music_map.bpm=project.analysis?.bpm||d.music_map.bpm;},false);renderForms();$('analysisStatus').textContent='Beat analysis complete. Review timing and any octave ambiguity before practice.';const key=await api(`/api/creator/projects/${pid}/key`,{method:'POST'});if(project?.id!==pid)return;change(d=>{d.music_map.key_estimate=key;if(!d.music_map.key){d.music_map.key=key.key||'';d.music_map.key_source='estimate';}},false);renderForms();}else if(r.status==='error'||r.error){clearInterval(analysisPoll);$('analysisStatus').textContent=r.error||'Analysis failed; manual timing remains available.';}}catch(e){clearInterval(analysisPoll);if(project?.id===pid)$('analysisStatus').textContent=e.message;}finally{polling=false;}},900);}catch(e){if(project?.id===pid)$('analysisStatus').textContent=e.message;}};
$("generateBtn").onclick=()=>{pendingCandidates=null;$("candidateChoices").innerHTML="";if(draft)$("generateDialog").showModal();else notify("Start a dance first.");};$("generateForm").onsubmit=async e=>{e.preventDefault();$("generateStatus").textContent="Building a draft…";const context={pid:project.id,partId:activePart,version:changeVersion,request:++generationRequest};try{const r=await api("/api/creator/generate",{method:"POST",body:{counts:+$("genCounts").value,wall:$("genWalls").value,level:$("genLevel").value,seed:+$("genSeed").value,bpm:draft.music_map?.bpm||project?.analysis?.bpm||null,start_foot:draft.choreography.start?.free_foot||"R",part:selectedPart()}});if(!requestStillCurrent(context)||context.request!==generationRequest){$("generateStatus").textContent="The draft changed. Build options again for the current part.";return;}pendingCandidateContext=context;pendingCandidates=r.candidates;$("generateStatus").textContent=`${r.candidates.length} drafts ready. Compare the steps, then choose one.`;$("candidateChoices").innerHTML=r.candidates.map((c,i)=>`<div class="card"><h3>Option ${i+1}</h3><p>${c.moves.map(m=>escapeHtml(m.name)).join(" · ")}</p><button data-candidate="${i}">Use option ${i+1}</button></div>`).join("");document.querySelectorAll("[data-candidate]").forEach(button=>button.onclick=()=>{if(!requestStillCurrent(pendingCandidateContext))return notify("The draft changed. Generate fresh options before applying.");const candidate=pendingCandidates[+button.dataset.candidate];change(d=>{selectedPart().moves=candidate.moves.map(m=>({...clone(m),id:m.locked?m.id:uid("move")}));});$("generateDialog").close();notify("Selected part updated. Undo restores the previous draft.");});}catch(err){$("generateStatus").textContent=err.message;}};
$("practicePlay").onclick=()=>playPractice().catch(e=>notify(e.message));$("practiceStop").onclick=()=>stopPractice(true);$("practiceSpeed").onchange=()=>{const was=playing;stopPractice();if(was)playPractice();};$("practiceSeek").oninput=()=>{const was=playing;stopPractice();practicePosition=+$("practiceSeek").value;renderPractice();if(was)playPractice();};$("loopCurrentBtn").onclick=()=>{const size=+(draft?.choreography.meter?.group_counts||8);$("loopStart").value=Math.floor(Math.max(0,practicePosition)/size)*size+1;$("loopEnd").value=Math.min(numeric(compiled?.total_counts)||size,+$("loopStart").value+size-1);$("loopEnabled").checked=true;};$("fullscreenBtn").onclick=()=>document.fullscreenElement?document.exitFullscreen():document.querySelector('[data-page="practice"]').requestFullscreen();
$("openMovesBtn").onclick=()=>showView("moves");$("legacyLibraryBtn").onclick=()=>legacy("editor");$("advancedMusicBtn").onclick=()=>legacy("sections");document.querySelectorAll("[data-legacy]").forEach(b=>b.onclick=()=>legacy(b.dataset.legacy));$("repairStudioBtn").onclick=async()=>{try{await save();location.href="/repair";}catch{}};$("aiSetupBtn").onclick=()=>legacy("generate",true);$("settingsAiBtn").onclick=()=>legacy("song",true);$("catalogSearch").oninput=()=>renderCatalog().catch(e=>notify(e.message));
$("communityForm").onsubmit=async e=>{e.preventDefault();if(!communityShelf)return;const link={name:$("communityName").value,url:$("communityUrl").value,note:$("communityNote").value};try{if(communityEditId)communityShelf.replace(communityEditId,link);else communityShelf.add(link);}catch(err){$("communityStatus").textContent=err.message;return;}try{await communityShelf.save();cancelCommunityEdit();$("communityStatus").textContent="Saved on this computer.";renderCommunity();}catch(err){$("communityStatus").textContent=err.message;await communityShelf.load().catch(()=>{});renderCommunity();}};
$("communityCancelEdit").onclick=()=>cancelCommunityEdit();
$("communityReset").onclick=async()=>{if(!await askConfirm("Put the starter websites back? Links you added will be removed from this list."))return;try{await communityShelf.reset();cancelCommunityEdit();$("communityStatus").textContent="Starter links restored.";renderCommunity();}catch(e){$("communityStatus").textContent=e.message;}};
$("openCommunityBtn").onclick=()=>{showView("tools");$("communityShelf").scrollIntoView({block:"start"});};
$("publishBtn").onclick=()=>publishDance(project?.id);
$("acceptDanceBtn").onclick=async()=>{if(!project)return;const pid=project.id;try{await save();if(project?.id!==pid)return;await api(`/api/creator/projects/${pid}/accept`,{method:"POST",body:{expected_revision:workspace.document_revision}});if(project?.id!==pid)return;await mergeRemoteWorkspace(pid);$("acceptStatus").textContent="Accepted version saved. Practice and exports use the complete choreography; older production tools require a legacy flat dance.";}catch(e){$("acceptStatus").textContent=e.message;}};
for(const [format,label]of [["pdf","PDF sheet"],["docx","Word document"],["txt","Plain text"],["html","Web / print sheet"],["csv","CSV table"],["xlsx","Excel table"],["srt","Subtitle cues"],["vtt","Web captions"],["zip","Portable working draft"],["json","Editable JSON draft"]]){const b=document.createElement("button");b.textContent=label;b.onclick=async()=>{if(!project)return notify("Open a dance first.");const pid=project.id;try{await save();if(project?.id!==pid)return;const title=draft.sheet_meta?.dance_title||project.name;const params=new URLSearchParams({paper:$("paperSize").value,large_print:$("largePrint").checked?"1":"0",print_qr:$("printQR").checked?"1":"0",include_lyrics:$("includeLyrics").checked?"1":"0"});const r=await fetch(`/api/creator/projects/${pid}/export/${format}?${params}`);if(!r.ok){const e=await r.json().catch(()=>({}));throw new Error(e.detail||"Export could not be created.");}const url=URL.createObjectURL(await r.blob());const a=document.createElement("a");a.href=url;a.download=title.replace(/[<>:"/\\|?*]/g,"-")+"."+format;a.click();setTimeout(()=>URL.revokeObjectURL(url),10000);$("exportStatus").textContent="Export created from the saved working draft.";}catch(e){$("exportStatus").textContent=e.message;}};$("exportChoices").appendChild(b);}
$("restoreBtn").onclick=async()=>{const file=$("restoreFile").files[0];if(!file)return notify("Choose an editable project package.");const body=new FormData();body.append("file",file);try{const preview=await api("/api/creator/import/preview",{method:"POST",body});if(!await askConfirm(`Restore ${preview.name || file.name} as a new project? Existing dances will be preserved.`))return;const form=new FormData();form.append("file",file);const r=await api("/api/creator/import",{method:"POST",body:form});await openProject(r.id);$("restoreStatus").textContent="Project restored.";}catch(e){$("restoreStatus").textContent=e.message;}};
window.addEventListener("beforeunload",e=>{if(dirty()){backupDraft();e.preventDefault();e.returnValue="";}});document.addEventListener("keydown",e=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==="s"){e.preventDefault();save().catch(()=>{});}if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==="z"&&!/INPUT|TEXTAREA/.test(document.activeElement?.tagName)){e.preventDefault();e.shiftKey?restoreEdit(redoStack,undoStack):restoreEdit(undoStack,redoStack);}});
async function init(){try{await initializeBrowserProfile();const library=await api("/api/creator/moves");moves=library.moves;moveCoverage=library.coverage;await loadProjects();renderMoveChoices();await loadCommunity();if(window.LineDanceAdvanced)LineDanceAdvanced.mount(document, api);const pid=new URLSearchParams(location.search).get("project");if(pid)await openProject(pid);api("/api/creator/addons").then(r=>$("addonStatus").textContent=r.summary).catch(()=>{});}catch(e){notify(e.message);$("projectList").innerHTML='<p class="empty">Could not load projects. Check that the local application is running, then refresh.</p>';}}
const creatorReady=init();

async function refreshRecordingReview(){
  const pid=project?.id;if(!pid)return;
  try{const result=await api(`/api/creator/projects/${pid}/recording/status`);if(project?.id!==pid)return;
    $('reviewRecordingBtn').disabled=!result.has_audio;
    $('recordingReviewStatus').textContent=!result.has_audio?(draft?.sheet_meta?.spotify_url?'No local audio file. The Spotify link is not used for timing or rehearsal.':'No recording attached.'):result.review_needed?'Review needed: check BPM, count one and any tempo changes.':'Saved recording timing reviewed.';
    if(draft?.music_map?.bpm_source==='PROVISIONAL_DEFAULT'&&!draft.music_map.measured_bpm&&!draft.music_map.manually_corrected)$('musicEvidence').textContent='120 BPM is a temporary starting value, not an audio measurement. Analyze the song or enter its timing.';
  }catch(e){if(project?.id===pid)$('recordingReviewStatus').textContent=e.message;}
}
$('reviewRecordingBtn').onclick=async()=>{if(!project)return;const pid=project.id;try{await save();if(project?.id!==pid)return;await api(`/api/creator/projects/${pid}/recording/review`,{method:'POST',body:{expected_revision:workspace.document_revision,confirmed:true}});if(project?.id===pid&&await mergeRemoteWorkspace(pid)){renderForms();status(dirty()?'Unsaved changes':'Saved locally',dirty()?'dirty':'saved');}}catch(e){notify(e.message);}};
