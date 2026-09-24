/* Line Dance Creator — frontend */
"use strict";

const $ = id => document.getElementById(id);
const IS_FILE_PREVIEW = window.location.protocol === "file:";
let P = null;            // current project object
let STEPS = null;        // step library cache
let boundaries = [];     // section boundary times (seconds)
let labels = [];         // labels[i] = label of section between boundaries[i] and [i+1]
let dragIdx = -1;
let waveZoom = 1;
let legacyLoadedSeq = "[]";
let legacyRevision = null;
let legacyBaseDraft = null, legacyFormBase = null, legacySaving = null, legacyOpenRequest = 0;
let seq = [];            // editor sequence: [{move_id, lead}]
let validateTimer = null;
let alignmentPollTimer = null;
let PROJECT_LIST = [];  // project summaries for the project chooser
let AI_SETTINGS = null; // safe public connection settings; never contains a key
let AI_CONVERSATION = []; // page-only chat history; it is never saved to a project
let LYRIC_MOVE_DRAFT = null; // review-only; persisted separately from the saved dance
let lyricMoveRequestToken = 0;

/* ---------------- helpers ---------------- */
async function api(path, opts = {}) {
  const originProject = P?.id, originOpen = legacyOpenRequest;
  const targetProject = /^\/api\/projects\/([^/]+)(?:\/|$)/.exec(path)?.[1];
  const belongsToOpenProject = originProject && targetProject === encodeURIComponent(originProject);
  if(belongsToOpenProject && opts.method === "PUT" && /\/(lyrics|sections|meta|tutorial)$/.test(path)){
    if(!await saveProjectAll())throw new Error("Save the retained draft or resolve its conflict before this action.");
    if(P?.id!==originProject||legacyOpenRequest!==originOpen)throw new Error("The open project changed; this action was cancelled.");
    opts={...opts,body:{...opts.body,expected_revision:legacyRevision}};
  }
  let r;
  try {
    r = await fetch(path, {
      headers: { "Content-Type": "application/json" },
      ...opts,
      body: opts.body ? JSON.stringify(opts.body) : undefined,
    });
  } catch (e) {
    throw new Error(IS_FILE_PREVIEW
      ? "This preview cannot save projects. Open http://127.0.0.1:8766/dance instead."
      : "Could not reach Line Dance Creator. Check that app/run.bat is still running.");
  }
  if (!r.ok) {
    let msg = r.statusText;
    let data = null;
    try { data = await r.json(); msg = data.detail || data.message || msg; }
    catch (e) { /* not json */ }
    const err = new Error(msg);
    err.data = data;
    err.status = r.status;
    throw err;
  }
  const result=await r.json();
  if (belongsToOpenProject && (P?.id !== originProject || legacyOpenRequest !== originOpen)) {
    const error = new Error("The response belongs to the previously open project. Its saved result is retained there.");
    error.code = "STALE_PROJECT_RESPONSE"; throw error;
  }
  // Author-field baselines only advance after a reviewed three-way save or a
  // complete reload. An unrelated action must not bless stale form values.
  return result;
}

/* Legacy draft state: displayed fields are a delta over a saved base. */
const legacyMetaFields={dance_title:"metaDanceTitle",choreographer:"metaChoreo",country:"metaCountry",contact:"metaContact",level_label:"metaLevel",description:"metaDesc",signature_note:"metaSig",ending_note:"metaEnding",youtube_url:"metaYoutubeUrl",sheet_url:"metaSheetUrl"};
function readLegacyForms() {
  const value={song:{title:$("songTitle").value.trim(),artist:$("songArtist").value.trim()},lyrics_raw:$("lyricsText").value,
    sections:boundaries.length>=2?sectionsFromBoundaries():[],sheet_meta:{},
    editor:{moves:structuredClone(seq),counts:+$("edCounts").value,wall:$("edWall").value,turn_dir:$("edTurnDir").value}};
  for(const [key,id] of Object.entries(legacyMetaFields))value.sheet_meta[key]=$(id).value.trim();
  if(P?.tutorial){
    value.tutorial_edits={provenance_hash:P.tutorial.provenance_hash,
      segments:[...$("tutorialTable").querySelectorAll("tbody tr")].map(row=>({id:row.dataset.segmentId,callout:row.querySelector(".cue-callout").value.trim(),camera:row.querySelector(".cue-camera").value,confirmed:row.querySelector(".cue-confirmed").checked,review_note:row.querySelector(".cue-note").value.trim()})),
      voice_notes:$("tutorialVoiceNotes").value,producer_notes:$("tutorialProducerNotes").value,count_in:$("tutorialCountIn").value,tempo_grid_confirmed:$("tutorialTempoConfirmed").checked};
  }
  return value;
}
function legacyDirty(){return !!(P && legacyFormBase && !LineDanceMerge.equal(readLegacyForms(),legacyFormBase));}
function frozenLegacyMoves(items, startFoot="R"){
  let foot=startFoot;
  return items.map(item=>{
    let concrete=item;
    if(!["lines","counts","start","end","rot"].every(key=>Object.hasOwn(item,key))){
      const record=P?.draft_move_snapshots?.[item.move_id] || P?.movement_snapshots?.[item.move_id];
      const lead=item.lead||"R";
      if(record){concrete=record.variants?.[lead];if(concrete?.start==="F")concrete=record.variants?.[foot];}
      else {concrete=STEPS?.find(move=>move.move_id===item.move_id&&move.lead===lead);if(concrete?.start==="F")concrete=STEPS?.find(move=>move.move_id===item.move_id&&move.lead===foot);}
      if(!concrete)throw new Error(`Restore the frozen definition for ${item.move_id} before saving this sequence.`);
    }
    const result=structuredClone(concrete);if(result.end!=="SAME")foot=result.end;return result;
  });
}
function legacyLocalDraft(forms=readLegacyForms()){
  const draft=structuredClone(legacyBaseDraft||{});
  function apply(before, after, target){
    for(const key of Object.keys(after)){
      if(LineDanceMerge.equal(before?.[key],after[key]))continue;
      if(after[key]&&typeof after[key]==="object"&&!Array.isArray(after[key])&&before?.[key]&&typeof before[key]==="object"&&!Array.isArray(before[key])){
        target[key]||={};apply(before[key],after[key],target[key]);
      }else target[key]=structuredClone(after[key]);
    }
  }
  apply(legacyFormBase||{},forms,draft);
  delete draft.tutorial_edits;
  if(!LineDanceMerge.equal(forms.tutorial_edits,legacyFormBase?.tutorial_edits)&&forms.tutorial_edits)draft.tutorial_edits=structuredClone(forms.tutorial_edits);
  if(!LineDanceMerge.equal(forms.editor.moves,legacyFormBase?.editor?.moves)){
    const graph=draft.choreography;
    const part=graph?.parts?.[0],run=graph?.routine?.[0];
    if(graph && (!part || graph.parts.length!==1 || graph.routine?.length!==1 || (part.kind||"part")!=="part"
      || (run.repeat||1)!==1 || ["reason","end_after_counts","overrides"].some(key=>Object.hasOwn(run,key))
      || Number(graph.pickup_counts||0)!==0 || (part.moves||[]).some(move=>Array.isArray(move.events)))){
      throw new Error("This arrangement needs the main choreography editor. Your legacy sequence is retained; use the main workspace to change parts, restarts, timed events or overrides.");
    }
    const concrete=frozenLegacyMoves(forms.editor.moves,graph?.start?.free_foot||"R");
    draft.choreography=graph?structuredClone(graph):{schema_version:1,start:{support:"L",free_foot:"R",facing_deg:"0"},meter:{beats:4,unit:4,group_counts:8},repeat:false,parts:[{id:"A",name:"Part A",moves:[]}],routine:[{id:"run-A",part_id:"A",repeat:1}]};
    draft.choreography.parts[0].moves=concrete.map((move,index)=>({...move,id:forms.editor.moves[index].id||"legacy-"+index}));
  }
  return draft;
}
function backupLegacyDraft(){if(!P||!legacyFormBase)return;try{localStorage.setItem("ldc.legacyRecovery."+P.id,JSON.stringify({forms:readLegacyForms(),baseForms:legacyFormBase,baseDraft:legacyBaseDraft,revision:legacyRevision,when:Date.now()}));}catch{toast("Browser recovery is unavailable; keep this window open until the draft saves.");}}
function applyLegacyForms(forms){
  if(forms.song){$("songTitle").value=forms.song.title||"";$("songArtist").value=forms.song.artist||"";}
  $("lyricsText").value=forms.lyrics_raw||"";
  for(const [key,id] of Object.entries(legacyMetaFields))$(id).value=forms.sheet_meta?.[key]||"";
  seq=structuredClone(forms.editor?.moves||[]);$("edCounts").value=forms.editor?.counts||32;$("edWall").value=forms.editor?.wall||"2";$("edTurnDir").value=forms.editor?.turn_dir||"L";
  if(forms.sections){P.sections=structuredClone(forms.sections);loadBoundariesFromSections();renderSectionsTable();}
  if(forms.tutorial_edits&&legacyBaseDraft?.tutorial){P.tutorial=structuredClone(legacyBaseDraft.tutorial);renderTutorial(P.tutorial);const edits=new Map(forms.tutorial_edits.segments.map(row=>[row.id,row]));for(const row of $("tutorialTable").querySelectorAll("tbody tr")){const edit=edits.get(row.dataset.segmentId);if(!edit)continue;row.querySelector(".cue-callout").value=edit.callout;row.querySelector(".cue-camera").value=edit.camera;row.querySelector(".cue-confirmed").checked=edit.confirmed;row.querySelector(".cue-note").value=edit.review_note;}$("tutorialVoiceNotes").value=forms.tutorial_edits.voice_notes;$("tutorialProducerNotes").value=forms.tutorial_edits.producer_notes;$("tutorialCountIn").value=forms.tutorial_edits.count_in;$("tutorialTempoConfirmed").checked=forms.tutorial_edits.tempo_grid_confirmed;}
  renderSequence();
}
/* End legacy draft state. */
function toast(msg) {
  const t = $("toast");
  t.textContent = msg;
  t.classList.add("show");
  clearTimeout(t._h);
  t._h = setTimeout(() => t.classList.remove("show"), 2200);
}
function fmtTime(s) {
  const m = Math.floor(s / 60);
  return `${m}:${(s % 60).toFixed(1).padStart(4, "0")}`;
}
function esc(s) {
  const d = document.createElement("div");
  d.textContent = s == null ? "" : String(s);
  return d.innerHTML;
}
const LEVEL_RANK = { AB: 0, B: 1, I: 2, INT: 3, A: 4 };

/* ---------------- tabs ---------------- */
document.querySelectorAll(".tab").forEach(b => {
  b.onclick = () => {
    document.querySelectorAll(".tab").forEach(x => x.classList.remove("active"));
    document.querySelectorAll(".tabpane").forEach(x => x.classList.remove("active"));
    b.classList.add("active");
    $("tab-" + b.dataset.tab).classList.add("active");
    if (b.dataset.tab === "sections") drawWave();
    if (b.dataset.tab === "editor") {
      renderLibrary();
      refreshMoveLibrary();
    }
    if (b.dataset.tab === "generate") renderTempoGate();
    if (b.dataset.tab === "tutorial") refreshTutorial();
    if (b.dataset.tab === "export") refreshExport();
  };
});

/* ---------------- projects ---------------- */
async function loadProjects(selectId) {
  const list = await api("/api/projects");
  PROJECT_LIST = list;
  const sel = $("projectSelect");
  const open = $("openProjectBtn");
  sel.innerHTML = "";
  for (const p of list) {
    const o = document.createElement("option");
    o.value = p.id;
    o.textContent = p.name + (p.has_dance ? " — dance saved" : p.has_analysis ? " — song mapped" : "");
    sel.appendChild(o);
  }
  renderProjectLibrary();
  if (!list.length) {
    P = null;
    const empty = document.createElement("option");
    empty.textContent = "No saved projects yet";
    empty.value = "";
    sel.appendChild(empty);
    sel.disabled = true;
    open.disabled = true;
    $("saveProjectBtn").disabled = true;
    $("deleteProjectBtn").disabled = true;
    return;
  }
  sel.disabled = false;
  open.disabled = false;
  $("saveProjectBtn").disabled = false;
  $("deleteProjectBtn").disabled = false;
  const remembered = new URLSearchParams(location.search).get("project") || localStorage.getItem("lineDanceCreator.lastProject");
  const pick = selectId && list.some(p => p.id === selectId) ? selectId
    : remembered && list.some(p => p.id === remembered) ? remembered : list[0].id;
  sel.value = pick;
  await openProject(pick);
  const requested=new URLSearchParams(location.search);
  const tab=[...document.querySelectorAll(".tab")].find(b=>b.dataset.tab===requested.get("tab"));
  if(tab)tab.click();
  if(requested.get("ai")==="1")$("settingsBtn").click();
}
async function openProject(pid) {
  if (!pid) return toast("Choose a saved project first");
  if(legacyDirty() && !await saveProjectAll())return false;
  const token=++legacyOpenRequest;
  const loaded=await api("/api/projects/" + pid);
  await ensureSteps();
  if(token!==legacyOpenRequest)return false;
  if(legacyDirty())throw new Error("You edited this draft while another project was opening. Save before switching.");
  P=loaded;
  legacyRevision = P.document_revision;
  legacyBaseDraft=structuredClone(P.draft||{});
  seq = structuredClone(P.draft?.editor?.moves || []);
  const graph=P.draft?.choreography;
  if(graph?.parts?.length===1&&graph.routine?.length===1&&(graph.routine[0].repeat||1)===1&&!graph.routine[0].end_after_counts
     &&graph.parts[0].moves?.every(move=>["lines","counts","start","end","rot"].every(key=>Object.hasOwn(move,key))))seq=structuredClone(graph.parts[0].moves);
  legacyLoadedSeq = JSON.stringify(seq);
  $("edCounts").value=P.draft?.editor?.counts || 32;
  $("edWall").value=P.draft?.editor?.wall || "2";
  $("edTurnDir").value=P.draft?.editor?.turn_dir || "L";
  renderSequence();
  localStorage.setItem("lineDanceCreator.lastProject", P.id);
  $("songTitle").value = P.song.title || "";
  $("songArtist").value = P.song.artist || "";
  $("songPath").value = P.song.path || "";
  $("songStatus").textContent = P.song.path ? `Using: ${P.song.filename}` : "No audio set yet.";
  $("lyricsText").value = P.lyrics_raw || "";
  renderLyricTags();
  renderAlignment(P.alignment);
  loadBoundariesFromSections();
  renderAnalysis();
  renderTempoGate();
  renderSectionsTable();
  renderPhrase(P.phrase);
  renderCandidates();
  resetLyricMoveDraft();
  $("lyricFillGaps").checked = true;
  if (P.lyric_move_draft) {
    const savedFillChoice = P.lyric_move_draft.summary?.fill_gaps_requested ??
      P.lyric_move_draft.settings?.fill_gaps;
    if (typeof savedFillChoice === "boolean") $("lyricFillGaps").checked = savedFillChoice;
    LYRIC_MOVE_DRAFT = P.lyric_move_draft;
    renderLyricMoveDraft(LYRIC_MOVE_DRAFT);
  }
  $("editorDraftNotice").hidden = true;
  renderTutorial(P.tutorial || null);
  loadMetaForm();
  const audio = $("audio");
  audio.src = P.song.path ? `/api/projects/${P.id}/audio` : "";
  waveZoom = 1;
  $("waveViewport").scrollLeft = 0;
  updateWaveZoomControls();
  drawWave();
  legacyFormBase=readLegacyForms();
  try{const cached=JSON.parse(localStorage.getItem("ldc.legacyRecovery."+pid)||"null");if(cached?.forms&&cached.baseForms&&cached.baseDraft&&confirm("Restore this browser's unsaved legacy draft for review? Conflicting saved changes will be preserved until you resolve them.")){legacyBaseDraft=cached.baseDraft;legacyFormBase=cached.baseForms;applyLegacyForms(cached.forms);}}catch{}
  resumeAlignmentPolling(P.id).catch(err => setAlignmentStatus(err.message));
  return true;
}
$("projectSelect").onchange = e => {
  // Switching immediately keeps the project picker fast, while Open also
  // gives a clear, familiar action for people returning to a saved project.
  openProject(e.target.value).catch(err => toast(err.message));
};
$("openProjectBtn").onclick = () => {
  if (IS_FILE_PREVIEW) {
    window.location.href = "http://127.0.0.1:8766/dance";
    return;
  }
  renderProjectLibrary();
  $("projectLibraryDialog").showModal();
};
$("closeProjectLibraryBtn").onclick = () => $("projectLibraryDialog").close();
$("libraryNewProjectBtn").onclick = () => {
  $("projectLibraryDialog").close();
  $("newProjectBtn").click();
};
function renderProjectLibrary() {
  const host = $("projectLibraryList");
  host.innerHTML = "";
  if (!PROJECT_LIST.length) {
    host.innerHTML = '<p class="library-empty">No saved projects yet. Start a new one when you are ready.</p>';
    return;
  }
  for (const project of PROJECT_LIST) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "project-choice";
    const status = project.has_dance ? "Dance saved" : project.has_analysis ? "Song mapped" : "Ready to set up";
    const title = project.title && project.title !== project.name ? project.title : "No song title yet";
    button.innerHTML = `<strong>${esc(project.name)}</strong><span class="project-status">${esc(status)}</span><span>${esc(title)}</span>`;
    button.onclick = async () => {
      try {
        await openProject(project.id);
        $("projectSelect").value = project.id;
        $("projectLibraryDialog").close();
        toast(`Opened ${P.name}`);
      } catch (err) {
        toast(err.message);
      }
    };
    host.appendChild(button);
  }
}

/* ---------------- optional AI settings ---------------- */
function renderAISettings(settings) {
  AI_SETTINGS = settings;
  $("aiEnabled").checked = Boolean(settings.enabled);
  $("aiProvider").value = settings.provider || "openai_compatible";
  $("aiEndpoint").value = settings.base_url || "";
  $("aiModel").value = settings.model || "";
  $("aiTimeout").value = String(settings.timeout_seconds || 60);
  $("aiApiKey").value = "";
  $("aiKeyStatus").textContent = settings.api_key_configured
    ? "A protected key is saved. Leave this blank to keep it."
    : "No key saved yet.";
  const status = $("aiSettingsStatus");
  status.classList.toggle("ready", Boolean(settings.ready));
  status.textContent = settings.ready
    ? "Optional AI assistant is configured. The built-in generator is still your default."
    : settings.provider === "custom" && settings.configured
      ? "This custom connection is saved, but needs its own adapter before Ask AI can use it."
      : "AI is optional and currently not ready to use. Your built-in generator works normally.";
  renderAIChatConnection();
}
async function loadAISettings() {
  const settings = await api("/api/settings/ai");
  renderAISettings(settings);
  return settings;
}
$("settingsBtn").onclick = async () => {
  if (IS_FILE_PREVIEW) {
    window.location.href = "http://127.0.0.1:8766/dance";
    return;
  }
  try {
    await loadAISettings();
    $("settingsDialog").showModal();
  } catch (err) {
    toast(err.message);
  }
};
$("closeSettingsBtn").onclick = () => $("settingsDialog").close();
$("aiSettingsForm").onsubmit = async event => {
  event.preventDefault();
  const save = $("saveAiSettingsBtn");
  const status = $("aiSettingsStatus");
  const key = $("aiApiKey").value.trim();
  const body = {
    enabled: $("aiEnabled").checked,
    provider: $("aiProvider").value,
    base_url: $("aiEndpoint").value.trim(),
    model: $("aiModel").value.trim(),
    timeout_seconds: Number($("aiTimeout").value),
  };
  if (key) body.api_key = key;
  save.disabled = true;
  status.classList.remove("ready");
  status.textContent = "Saving optional AI settings...";
  try {
    renderAISettings(await api("/api/settings/ai", { method: "PUT", body }));
    toast("Optional AI settings saved");
  } catch (err) {
    status.textContent = err.message;
  } finally {
    save.disabled = false;
  }
};
$("forgetAiKeyBtn").onclick = async () => {
  if (!AI_SETTINGS || !AI_SETTINGS.api_key_configured) {
    return toast("There is no saved API key to remove");
  }
  if (!confirm("Forget the saved AI API key for this Windows account?")) return;
  try {
    renderAISettings(await api("/api/settings/ai/key", { method: "DELETE" }));
    toast("Saved AI key removed");
  } catch (err) {
    toast(err.message);
  }
};

function renderAIChatConnection() {
  const notice = $("aiChatConnection");
  const send = $("sendAiPromptBtn");
  const ready = Boolean(AI_SETTINGS && AI_SETTINGS.ready);
  notice.classList.toggle("ready", ready);
  notice.textContent = ready
    ? `Ready to ask ${AI_SETTINGS.model}. Your dance stays unchanged until you choose what to use.`
    : AI_SETTINGS && AI_SETTINGS.provider === "custom" && AI_SETTINGS.configured
      ? "This custom connection is saved, but needs its own adapter before it can answer here."
      : "AI is not set up or enabled. The built-in generator still works normally; open AI settings only if you want to connect one.";
  send.disabled = !ready;
}
function renderAIConversation() {
  const host = $("aiChatMessages");
  host.innerHTML = "";
  if (!AI_CONVERSATION.length) {
    host.innerHTML = '<div class="ai-chat-empty">Ask for dance ideas, a teaching review, a chorus signature, or help shaping a draft.</div>';
    return;
  }
  for (const message of AI_CONVERSATION) {
    const bubble = document.createElement("div");
    bubble.className = `ai-message ${message.role}`;
    const label = document.createElement("span");
    label.className = "ai-message-label";
    label.textContent = message.role === "user" ? "You" : "AI idea";
    const body = document.createElement("div");
    body.textContent = message.content;
    bubble.append(label, body);
    host.appendChild(bubble);
  }
  host.scrollTop = host.scrollHeight;
}
async function openAIChat() {
  if (IS_FILE_PREVIEW) {
    window.location.href = "http://127.0.0.1:8766/dance";
    return;
  }
  try {
    await loadAISettings();
    renderAIConversation();
    $("aiChatDialog").showModal();
    $("aiPrompt").focus();
  } catch (err) {
    toast(err.message);
  }
}
$("askAiBtn").onclick = openAIChat;
$("closeAiChatBtn").onclick = () => $("aiChatDialog").close();
$("openAiSettingsBtn").onclick = () => {
  $("aiChatDialog").close();
  $("settingsBtn").click();
};
document.querySelectorAll(".prompt-chip").forEach(button => {
  button.onclick = () => {
    $("aiPrompt").value = button.dataset.prompt || "";
    $("aiPrompt").focus();
  };
});
$("clearAiChatBtn").onclick = () => {
  AI_CONVERSATION = [];
  renderAIConversation();
  toast("AI conversation cleared");
};
$("aiChatForm").onsubmit = async event => {
  event.preventDefault();
  if (!AI_SETTINGS || !AI_SETTINGS.ready) {
    return toast("Finish optional AI settings first, or keep using the built-in generator");
  }
  const prompt = $("aiPrompt").value.trim();
  if (!prompt) return toast("Write a question or dance idea first");
  const send = $("sendAiPromptBtn");
  const history = AI_CONVERSATION.slice(-10);
  const includeProject = Boolean(P && $("includeProjectContext").checked);
  AI_CONVERSATION.push({ role: "user", content: prompt });
  $("aiPrompt").value = "";
  renderAIConversation();
  send.disabled = true;
  send.textContent = "Asking AI...";
  try {
    const result = await api("/api/ai/chat", { method: "POST", body: {
      prompt, history, project_id: P ? P.id : null, include_project: includeProject,
    } });
    AI_CONVERSATION.push({ role: "assistant", content: result.answer });
    renderAIConversation();
  } catch (err) {
    toast(err.message);
  } finally {
    send.textContent = "Ask AI";
    send.disabled = !AI_SETTINGS || !AI_SETTINGS.ready;
  }
};
$("newProjectBtn").onclick = () => {
  if (IS_FILE_PREVIEW) {
    $("fileMode").hidden = false;
    toast("Open http://127.0.0.1:8766/dance to create and save projects");
    return;
  }
  const dialog = $("newProjectDialog");
  $("newProjectError").textContent = "";
  $("newProjectName").value = "";
  dialog.showModal();
  $("newProjectName").focus();
};
$("cancelNewProjectBtn").onclick = () => $("newProjectDialog").close();
$("newProjectForm").onsubmit = async event => {
  event.preventDefault();
  const name = $("newProjectName").value.trim();
  if (!name) return;
  const create = $("createProjectBtn");
  const error = $("newProjectError");
  create.disabled = true;
  error.textContent = "Creating project...";
  try {
    const p = await api("/api/projects", { method: "POST", body: { name } });
    await loadProjects(p.id);
    $("newProjectDialog").close();
    toast(`Created ${p.name}`);
  } catch (e) {
    error.textContent = e.message || "The project could not be created.";
  } finally {
    create.disabled = false;
  }
};
async function saveProjectAll() {
  if (!P) {toast("No project open");return false;}
  if(legacySaving){const success=await legacySaving;if(!success)return false;return legacyDirty()?saveProjectAll():true;}
  const pid=P.id, token=legacyOpenRequest;
  legacySaving=(async()=>{
    try{
      const forms=readLegacyForms(), local=legacyLocalDraft(forms), base=structuredClone(legacyBaseDraft);
      backupLegacyDraft();
      const remote=await api(`/api/projects/${pid}/workspace`);
      const merged=LineDanceMerge.merge(base,local,remote.draft);
      if(merged.conflicts.length)throw new Error("Save conflict in "+merged.conflicts.join(", ")+". Your draft is retained. Reopen to review the saved changes; no fields were overwritten.");
      const result=await api(`/api/projects/${pid}/workspace`,{method:"PUT",body:{expected_revision:remote.document_revision,draft:merged.value}});
      if(P?.id!==pid||token!==legacyOpenRequest)return false;
      legacyRevision=result.document_revision;legacyBaseDraft=structuredClone(result.draft);legacyFormBase=structuredClone(forms);legacyLoadedSeq=JSON.stringify(forms.editor.moves);
      if(result.draft.tutorial&&forms.tutorial_edits){P.tutorial=structuredClone(result.draft.tutorial);legacyFormBase.tutorial_edits.provenance_hash=P.tutorial.provenance_hash;}
      P.document_revision=result.document_revision;P.draft=structuredClone(result.draft);
      if(legacyDirty())backupLegacyDraft();else localStorage.removeItem("ldc.legacyRecovery."+pid);
      toast(legacyDirty()?"Saved; newer edits remain unsaved":"Complete draft saved; accepted dance preserved");return true;
    }catch(error){backupLegacyDraft();toast(error.message);return false;}
  })();
  try{return await legacySaving;}finally{legacySaving=null;}
}
$("saveProjectBtn").onclick = saveProjectAll;
document.addEventListener("keydown", e => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
    e.preventDefault();
    saveProjectAll();
  }
});
document.addEventListener("input",()=>{if(legacyDirty())backupLegacyDraft();});
window.addEventListener("beforeunload",event=>{if(legacyDirty()){backupLegacyDraft();event.preventDefault();event.returnValue="";}});

$("deleteProjectBtn").onclick = async () => {
  if (!P) return;
  if (!confirm(`Delete project "${P.name}"? This removes its saved data.`)) return;
  await api("/api/projects/" + P.id, { method: "DELETE" });
  await loadProjects();
  toast("Deleted");
};

/* ---------------- song tab ---------------- */
async function saveTitleArtist() {
  if (!P) return;
  if(LineDanceMerge.equal(readLegacyForms().song,legacyFormBase?.song))return;
  const pid=P.id;if(await saveProjectAll()&&P?.id===pid)P.song=structuredClone(P.draft.song);
}
$("songTitle").onblur = saveTitleArtist;
$("songArtist").onblur = saveTitleArtist;

$("setPathBtn").onclick = async () => {
  if (!P) return toast("Create a project first");
  try {
    const s = await api(`/api/projects/${P.id}/song-path`, {
      method: "POST", body: { path: $("songPath").value } });
    P.song = s;
    P.analysis = null;
    P.alignment = null;
    P.phrase = null;
    P.dance = {};
    $("songStatus").textContent = `Using: ${s.filename}`;
    $("audio").src = `/api/projects/${P.id}/audio`;
    renderAnalysis();
    renderAlignment(null);
    renderTempoGate();
    resetLyricMoveDraft();
    toast("Song set — now Analyze");
  } catch (e) { toast(e.message); }
};
const AUDIO_FILE_RE = /\.(mp3|wav|m4a|flac|ogg|aac)$/i;

async function uploadSongFile(file) {
  if (!P) return toast("Create a project first");
  if (!file) return;
  if (!AUDIO_FILE_RE.test(file.name || "")) {
    return toast("Choose an audio file: MP3, WAV, M4A, FLAC, OGG, or AAC");
  }
  const fd = new FormData();
  fd.append("file", file);
  const pid=P.id, token=legacyOpenRequest;
  try {
    const r = await fetch(`/api/projects/${pid}/song-upload`, { method: "POST", body: fd });
    if (!r.ok) {
      let message = "Upload failed";
      try { message = (await r.json()).detail || message; } catch (_) { /* use fallback */ }
      return toast(message);
    }
    const uploaded=await r.json();
    if(P?.id!==pid||token!==legacyOpenRequest)return;
    P.song = uploaded;
    P.analysis = null;
    P.alignment = null;
    P.phrase = null;
    P.dance = {};
    $("songStatus").textContent = `Using: ${P.song.filename}`;
    $("audio").src = `/api/projects/${P.id}/audio`;
    renderAnalysis();
    renderAlignment(null);
    renderTempoGate();
    resetLyricMoveDraft();
    toast("Song added - ready to analyze");
  } catch (e) { toast("Upload failed - make sure the app is running"); }
}

$("songFile").onchange = async e => {
  await uploadSongFile(e.target.files[0]);
  e.target.value = "";
};

const dropZone = $("fileDropZone");
let dropDepth = 0;
dropZone.onclick = () => $("songFile").click();
dropZone.onkeydown = e => {
  if (e.key === "Enter" || e.key === " ") {
    e.preventDefault();
    $("songFile").click();
  }
};
dropZone.addEventListener("dragenter", e => {
  e.preventDefault();
  dropDepth += 1;
  dropZone.classList.add("is-dragging");
});
dropZone.addEventListener("dragover", e => {
  e.preventDefault();
  e.dataTransfer.dropEffect = "copy";
});
dropZone.addEventListener("dragleave", e => {
  e.preventDefault();
  dropDepth = Math.max(0, dropDepth - 1);
  if (!dropDepth) dropZone.classList.remove("is-dragging");
});
dropZone.addEventListener("drop", async e => {
  e.preventDefault();
  dropDepth = 0;
  dropZone.classList.remove("is-dragging");
  await uploadSongFile(e.dataTransfer.files[0]);
});

$("analyzeBtn").onclick = async () => {
  if (!P) return toast("Create a project first");
  markLyricMoveDraftStale("Song analysis is being rebuilt. Rebuild the lyric-guided draft when analysis finishes.");
  try { await api(`/api/projects/${P.id}/analyze`, { method: "POST" }); }
  catch (e) { return toast(e.message); }
  $("analyzeStatus").textContent = "Starting analysis...";
  pollAnalysis(P.id);
};
async function pollAnalysis(pid) {
  if(P?.id!==pid)return;
  let st;try{st=await api(`/api/projects/${pid}/analysis-status`);}catch(error){if(P?.id===pid)toast(error.message);return;}
  if(P?.id!==pid)return;
  $("analyzeStatus").textContent = st.message || st.status;
  if (st.status === "running") {
    setTimeout(()=>pollAnalysis(pid), 1000);
  } else if (st.status === "done") {
    const fresh=await api("/api/projects/" + pid);if(P?.id!==pid)return;P=fresh;
    renderAnalysis();
    renderTempoGate();
    drawWave();
    markLyricMoveDraftStale("The beat analysis changed. Rebuild the lyric-guided draft before loading it.");
    toast("Analysis complete");
  } else if (st.status === "error") {
    $("analyzeStatus").textContent = "Error: " + st.message;
  }
}
function renderAnalysis() {
  const a = P && P.analysis;
  $("analysisCard").style.display = a ? "" : "none";
  if (!a) return;
  $("bpmValue").textContent = a.bpm;
  const conf = $("bpmConfidence");
  conf.textContent = a.bpm_confidence;
  conf.className = "chip " + a.bpm_confidence;
  $("bpmNotes").innerHTML = (a.bpm_confidence_notes || [])
    .map(n => "• " + esc(n)).join("<br>");
  const m = a.methods || {};
  $("methodsTable").innerHTML = `
    <tr><td>Autocorrelation</td><td>${m.autocorrelation ?? "—"}</td></tr>
    <tr><td>Beat tracker (median IBI)</td><td>${m.beat_tracker_median_ibi ?? "—"}</td></tr>
    <tr><td>Tempogram peak</td><td>${m.tempogram_peak ?? "—"}</td></tr>
    <tr><td>Windowed median</td><td>${m.windowed_median ?? "—"}
      ${m.windowed_spread ? `(spread ${m.windowed_spread[0]}–${m.windowed_spread[1]})` : ""}</td></tr>
    <tr><td>Beat jitter</td><td>${m.ibi_jitter_pct ?? "—"}%</td></tr>
    <tr><td>Duration</td><td>${fmtTime(a.duration)}</td></tr>
    <tr><td>Seconds per bar</td><td>${a.seconds_per_bar}</td></tr>`;
  const ow = $("octaveWarn");
  if (a.octave_alternates && a.octave_alternates.length) {
    ow.style.display = "";
    ow.textContent = "⚠ Octave ambiguity: " +
      a.octave_alternates.map(x => x.bpm + " BPM").join(", ") +
      " scores nearly as well. Confirm which grid the floor will count — both baselines are legitimate.";
  } else ow.style.display = "none";
  const dw = $("driftWarn");
  if (a.drift) {
    dw.style.display = "";
    dw.textContent = `⚠ Tempo drift: ${a.drift.first_half_bpm} → ${a.drift.second_half_bpm} BPM (${a.drift.drift_pct}%). A fixed count sheet can't phrase a drifting grid.`;
  } else dw.style.display = "none";
  $("candidatesBox").textContent = "Candidates: " + (a.candidates || [])
    .slice(0, 5).map(c => `${c.bpm} (${c.score})`).join("  ·  ");
}

function renderTempoGate() {
  const gate = $("tempoGate");
  const toggle = $("experimentalToggle");
  const check = $("genExperimental");
  const bpm = Number(P && P.analysis && P.analysis.bpm);
  if (!Number.isFinite(bpm) || bpm <= 0) {
    gate.textContent = "Tempo has not been measured yet. You can sketch a dance, but analyse the song before publishing.";
    toggle.style.display = "none";
    check.checked = false;
    return;
  }
  if (bpm > 132) {
    gate.textContent = `${bpm.toFixed(0)} BPM is above the validated 132 BPM range. Generation is available only in experimental/manual-review mode.`;
    gate.className = "notes flag warn";
    toggle.style.display = "";
    return;
  }
  gate.textContent = `${bpm.toFixed(0)} BPM is within the validated generation range (up to 132 BPM).`;
  gate.className = "notes";
  toggle.style.display = "none";
  check.checked = false;
}

/* ---------------- waveform ---------------- */
function loadBoundariesFromSections() {
  boundaries = [];
  labels = [];
  const secs = (P && P.sections) || [];
  if (secs.length) {
    for (const s of secs) { boundaries.push(s.start); labels.push(s.label); }
    boundaries.push(secs[secs.length - 1].end);
  }
}
function sectionsFromBoundaries() {
  const out = [];
  for (let i = 0; i + 1 < boundaries.length; i++) {
    out.push({ label: labels[i] || `Section ${i + 1}`,
               start: +boundaries[i].toFixed(4), end: +boundaries[i + 1].toFixed(4) });
  }
  return out;
}
function nextSectionLabel() {
  const used = new Set(labels.filter(Boolean).map(label => label.trim().toLowerCase()));
  let number = 1;
  while (used.has(`section ${number}`)) number++;
  return `Section ${number}`;
}
function insertSectionBoundary(time) {
  const snapped = snapTime(time);
  if (boundaries.some(boundary => Math.abs(boundary - snapped) < .15)) return false;
  let index = 0;
  while (index < boundaries.length && boundaries[index] < snapped) index++;
  boundaries.splice(index, 0, snapped);
  // A boundary opens the section to its right. Give that new section a real,
  // editable name instead of leaving a mysterious blank table row.
  if (boundaries.length >= 2 && index < boundaries.length - 1) {
    labels.splice(index, 0, nextSectionLabel());
  } else if (boundaries.length >= 2) {
    labels.push(nextSectionLabel());
  }
  return true;
}
function snapTime(t) {
  const a = P && P.analysis;
  if (!a || !$("snapChk").checked) return t;
  const db = a.downbeat_times;
  if (!db || !db.length) return t;
  let best = db[0];
  for (const d of db) if (Math.abs(d - t) < Math.abs(best - t)) best = d;
  return best;
}
const SEC_COLORS = ["#ff7a1a33", "#4da3ff33", "#6fce6f33", "#ffcf5c33",
                    "#c77dff33", "#ff6b5e33", "#4dd6c133", "#ff9ecb33"];
const MAX_WAVE_ZOOM = 12;
function updateWaveZoomControls() {
  const ready = Boolean(P && P.analysis);
  $("waveZoomReadout").textContent = `${Math.round(waveZoom * 100)}%`;
  $("zoomInBtn").disabled = !ready || waveZoom >= MAX_WAVE_ZOOM;
  $("zoomOutBtn").disabled = !ready || waveZoom <= 1;
  $("resetZoomBtn").disabled = !ready || waveZoom === 1;
}
function setWaveZoom(nextZoom) {
  if (!P || !P.analysis) return toast("Analyze the song first so there is a waveform to zoom");
  const duration = P.analysis.duration;
  const audio = $("audio");
  const focusTime = Math.max(0, Math.min(duration,
    Number.isFinite(audio.currentTime) ? audio.currentTime : duration / 2));
  waveZoom = Math.max(1, Math.min(MAX_WAVE_ZOOM, nextZoom));
  drawWave();
  const viewport = $("waveViewport");
  const focusX = focusTime / duration * $("wave").clientWidth;
  viewport.scrollLeft = Math.max(0, Math.min(
    focusX - viewport.clientWidth / 2,
    $("wave").clientWidth - viewport.clientWidth
  ));
  updateWaveZoomControls();
}
function resetWaveZoom() {
  if (waveZoom === 1) return;
  waveZoom = 1;
  drawWave();
  $("waveViewport").scrollLeft = 0;
  updateWaveZoomControls();
}
function drawWave() {
  const cv = $("wave");
  const a = P && P.analysis;
  const viewport = $("waveViewport");
  const viewportWidth = viewport.clientWidth || 900;
  const W = Math.max(320, Math.round(viewportWidth * waveZoom));
  cv.style.width = `${W}px`;
  cv.style.minWidth = `${W}px`;
  cv.width = W * devicePixelRatio;
  cv.height = 180 * devicePixelRatio;
  const ctx = cv.getContext("2d");
  ctx.scale(devicePixelRatio, devicePixelRatio);
  ctx.clearRect(0, 0, W, 180);
  ctx.fillStyle = "#0d0a07";
  ctx.fillRect(0, 0, W, 180);
  if (!a) {
    ctx.fillStyle = "#5a4f43";
    ctx.font = "14px sans-serif";
    ctx.fillText("Run Analyze on the Song tab to see the waveform.", 20, 95);
    updateWaveZoomControls();
    return;
  }
  const dur = a.duration;
  const x = t => t / dur * W;
  // sections
  const secs = sectionsFromBoundaries();
  secs.forEach((s, i) => {
    ctx.fillStyle = SEC_COLORS[i % SEC_COLORS.length];
    ctx.fillRect(x(s.start), 0, x(s.end) - x(s.start), 180);
    ctx.fillStyle = "#efe6da";
    ctx.font = "11px sans-serif";
    ctx.fillText(s.label, x(s.start) + 4, 14);
  });
  // waveform
  const wf = a.waveform;
  ctx.strokeStyle = "#ff7a1a";
  ctx.lineWidth = 1;
  ctx.beginPath();
  const n = wf.maxs.length;
  for (let i = 0; i < n; i++) {
    const px = i / n * W;
    const y1 = 90 - wf.maxs[i] * 70;
    const y2 = 90 - wf.mins[i] * 70;
    ctx.moveTo(px, y1);
    ctx.lineTo(px, y2);
  }
  ctx.stroke();
  // beats + downbeats
  if (W / a.beat_times.length > 3) {
    ctx.strokeStyle = "#3a312855";
    ctx.beginPath();
    for (const t of a.beat_times) { ctx.moveTo(x(t), 160); ctx.lineTo(x(t), 180); }
    ctx.stroke();
  }
  ctx.strokeStyle = "#a8988a88";
  ctx.beginPath();
  for (const t of a.downbeat_times) { ctx.moveTo(x(t), 150); ctx.lineTo(x(t), 180); }
  ctx.stroke();
  // boundaries
  boundaries.forEach((b, i) => {
    ctx.strokeStyle = "#ffb04d";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(x(b), 0);
    ctx.lineTo(x(b), 180);
    ctx.stroke();
  });
  // playhead
  const audio = $("audio");
  if (audio.duration) {
    ctx.strokeStyle = "#ffffffcc";
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(x(audio.currentTime), 0);
    ctx.lineTo(x(audio.currentTime), 180);
    ctx.stroke();
  }
  updateWaveZoomControls();
}
function canvasTime(e) {
  const cv = $("wave");
  const r = cv.getBoundingClientRect();
  const frac = (e.clientX - r.left) / r.width;
  return Math.max(0, Math.min(1, frac)) * (P.analysis ? P.analysis.duration : 0);
}
function hitBoundary(e) {
  if (!P || !P.analysis) return -1;
  const cv = $("wave");
  const r = cv.getBoundingClientRect();
  const pxPerSec = r.width / P.analysis.duration;
  const t = canvasTime(e);
  for (let i = 0; i < boundaries.length; i++) {
    if (Math.abs(boundaries[i] - t) * pxPerSec < 6) return i;
  }
  return -1;
}
$("wave").addEventListener("mousedown", e => {
  if (!P || !P.analysis) return;
  const hit = hitBoundary(e);
  if (hit >= 0 && !e.shiftKey) { dragIdx = hit; return; }
  const t = canvasTime(e);
  if (e.shiftKey) {
    insertSectionBoundary(t);
    renderSectionsTable();
    drawWave();
  } else {
    const audio = $("audio");
    audio.currentTime = t;
    drawWave();
  }
});
window.addEventListener("mousemove", e => {
  if (dragIdx < 0) return;
  // Clamp between neighboring boundaries: crossing a neighbor would re-sort
  // the boundary array while labels stayed put, silently rebinding section
  // names to the wrong audio.
  let t = snapTime(canvasTime(e));
  const lo = dragIdx > 0 ? boundaries[dragIdx - 1] + 0.05 : 0;
  const hi = dragIdx < boundaries.length - 1
    ? boundaries[dragIdx + 1] - 0.05
    : (P.analysis ? P.analysis.duration : t);
  boundaries[dragIdx] = Math.min(hi, Math.max(lo, t));
  drawWave();
});
window.addEventListener("mouseup", () => {
  if (dragIdx >= 0) {
    dragIdx = -1;
    renderSectionsTable();
    drawWave();
  }
});
$("wave").addEventListener("dblclick", e => {
  const hit = hitBoundary(e);
  if (hit >= 0) {
    boundaries.splice(hit, 1);
    if (hit < labels.length) labels.splice(hit, 1);
    renderSectionsTable();
    drawWave();
  }
});
$("playBtn").onclick = () => {
  const audio = $("audio");
  if (audio.paused) { audio.play(); $("playBtn").textContent = "⏸ Pause"; }
  else { audio.pause(); $("playBtn").textContent = "▶ Play"; }
};
$("zoomInBtn").onclick = () => setWaveZoom(waveZoom * 1.5);
$("zoomOutBtn").onclick = () => setWaveZoom(waveZoom / 1.5);
$("resetZoomBtn").onclick = resetWaveZoom;
let waveResizeTimer = null;
window.addEventListener("resize", () => {
  clearTimeout(waveResizeTimer);
  waveResizeTimer = setTimeout(drawWave, 80);
});
(function animate() {
  const audio = $("audio");
  if (audio && !audio.paused) {
    $("timeReadout").textContent = fmtTime(audio.currentTime);
    if (document.querySelector('[data-tab="sections"]').classList.contains("active"))
      drawWave();
  }
  requestAnimationFrame(animate);
})();

/* ---------------- lyrics + sections table ---------------- */
$("saveLyricsBtn").onclick = async () => {
  if (!P) return;
  try {
    const r = await api(`/api/projects/${P.id}/lyrics`, { method: "PUT",
      body: { text: $("lyricsText").value } });
    P.lyric_sections = r.sections;
    P.lyrics_raw = $("lyricsText").value;
    P.alignment = null;
    renderLyricTags();
    renderAlignment(null);
    markLyricMoveDraftStale("The lyrics changed. Align or scan them, then rebuild the lyric-guided draft.");
    toast(r.sections.length ? `Saved ${r.sections.length} section names` : "Lyrics saved");
  } catch (e) { toast(e.message); }
};
function renderLyricTags() {
  const box = $("lyricTags");
  box.innerHTML = "";
  for (const s of (P && P.lyric_sections) || []) {
    const c = document.createElement("span");
    c.className = "chip";
    c.textContent = s.label;
    box.appendChild(c);
  }
}

function renderAlignment(alignment) {
  const card = $("alignmentCard");
  const summary = $("alignmentSummary");
  const badge = $("alignmentBadge");
  const list = $("captionList");
  const accept = $("acceptAlignmentBtn");
  const keep = $("keepManualMarkersBtn");
  if (!P) {
    card.style.display = "none";
    return;
  }
  card.style.display = "block";
  if (!alignment) {
    summary.textContent = "Scan the song to create a local transcription and editable section draft, or paste known lyrics for exact alignment.";
    badge.textContent = "Not aligned";
    list.innerHTML = "<div class='hint empty-state'>No timed lyric rows yet.</div>";
    accept.disabled = true;
    keep.disabled = true;
    accept.textContent = "Use suggested section markers";
    return;
  }

  const info = alignment.summary || {};
  const confidence = Math.round((info.confidence || 0) * 100);
  const suggested = alignment.suggested_sections || [];
  const autoScan = alignment.mode === "auto_scan" || alignment.mode === "scan";
  const reviewCount = suggested.filter(row => row.review_required).length;
  summary.textContent = autoScan
    ? `${info.timed_lines || 0} vocal lines were transcribed locally. ${suggested.length} editable section${suggested.length === 1 ? "" : "s"} drafted${reviewCount ? `; ${reviewCount} need label or boundary review` : ""}.`
    : `${info.timed_lines || 0} of ${info.lyric_lines || 0} lyric lines received a time. ${suggested.length} editable section marker${suggested.length === 1 ? "" : "s"} suggested.`;
  badge.textContent = alignment.manual_decision === "accepted_suggestions" ? "Suggestions in use" :
    alignment.manual_decision === "auto_assigned_scan" ? "Draft assigned · review" :
    alignment.manual_decision === "kept_manual_markers" ? "Manual markers kept" :
    autoScan ? `${confidence}% speech confidence · draft` : `${confidence}% word match`;
  const captions = alignment.captions || [];
  list.innerHTML = captions.length ? captions.map(row => {
    const timed = row.start != null && row.end != null;
    const time = timed ? `${fmtTime(row.start)} – ${fmtTime(row.end)}` : "Needs review";
    const score = timed ? `${Math.round((row.confidence || 0) * 100)}% ${autoScan ? "speech" : "match"}` : "No match";
    return `<button class="caption-row ${timed ? "" : "unmatched"}" ${timed ? `data-start="${row.start}"` : ""} type="button">
      <span class="caption-time">${time}</span>
      <span class="caption-copy"><b>${esc(row.label || "Lyrics")}</b><span>${esc(row.text)}</span></span>
      <span class="caption-score">${score}</span>
    </button>`;
  }).join("") : "<div class='hint empty-state'>No lyric lines were found in the pasted text.</div>";
  accept.disabled = !suggested.length;
  keep.disabled = false;
  accept.textContent = autoScan ? "Use scanned section draft" : "Use suggested section markers";
}

$("captionList").onclick = event => {
  const row = event.target.closest(".caption-row[data-start]");
  if (!row || !P) return;
  const time = Number(row.dataset.start);
  if (!Number.isFinite(time)) return;
  const audio = $("audio");
  audio.currentTime = time;
  $("timeReadout").textContent = fmtTime(time);
  drawWave();
};

function setAlignmentStatus(message) {
  $("alignStatus").textContent = message || "";
}

function stopAlignmentPolling() {
  clearTimeout(alignmentPollTimer);
  alignmentPollTimer = null;
  $("alignLyricsBtn").disabled = false;
  $("scanLyricsBtn").disabled = false;
}

async function resumeAlignmentPolling(pid) {
  clearTimeout(alignmentPollTimer);
  alignmentPollTimer = null;
  const status = await api(`/api/projects/${pid}/alignment-status`);
  if (!P || P.id !== pid || status.status !== "running") return;
  $("alignLyricsBtn").disabled = true;
  $("scanLyricsBtn").disabled = true;
  setAlignmentStatus(status.message || "Listening to the song...");
  pollAlignment(pid);
}

async function pollAlignment(pid) {
  try {
    const status = await api(`/api/projects/${pid}/alignment-status`);
    // A slower response from the previously open project must not stop the
    // polling timer or re-enable controls for the project now on screen.
    if (!P || P.id !== pid) return;
    setAlignmentStatus(status.message);
    if (status.status === "running") {
      alignmentPollTimer = setTimeout(() => pollAlignment(pid), 1000);
      return;
    }
    stopAlignmentPolling();
    if (status.status === "done") {
      const pendingForms=legacyDirty();
      P = await api(`/api/projects/${pid}`);
      if(pendingForms||legacyDirty()){
        renderAlignment(null);
        toast("Alignment finished. Your unsaved text and markers are retained; save to merge or review conflicts.");
        return;
      }
      $("lyricsText").value = P.lyrics_raw || "";
      renderLyricTags();
      renderAlignment(P.alignment);
      loadBoundariesFromSections();
      renderSectionsTable();
      drawWave();
      markLyricMoveDraftStale("Timed lyrics changed. Rebuild the lyric-guided draft before loading it.");
      const scanned = status.mode === "scan" || P.alignment?.mode === "auto_scan";
      toast(scanned
        ? (P.alignment?.manual_decision === "auto_assigned_scan"
          ? "Lyrics and a section draft were assigned — review the markers"
          : "Scanned lyrics are ready — your manual markers were preserved")
        : "Timed lyrics are ready to review");
    } else if (status.status === "error") {
      toast(status.message || "Lyric alignment could not finish");
    } else if (status.status === "stale" || status.status === "cancelled") {
      toast(status.message || "The lyric scan was discarded; nothing was changed");
    }
  } catch (e) {
    stopAlignmentPolling();
    setAlignmentStatus(e.message);
    toast(e.message);
  }
}

$("scanLyricsBtn").onclick = async () => {
  if (!P) return toast("Create a project first");
  if (!P.analysis) return toast("Analyze the audio first so lyrics can snap to the beat grid");
  markLyricMoveDraftStale("The song is being scanned again. Rebuild the lyric-guided draft when it finishes.");
  try {
    // Protect anything typed since the last save. The scan service will see
    // it as authored lyrics and will never replace it with machine text.
    if ($("lyricsText").value !== (P.lyrics_raw || "")) {
      const r = await api(`/api/projects/${P.id}/lyrics`, { method: "PUT",
        body: { text: $("lyricsText").value } });
      P.lyric_sections = r.sections;
      P.lyrics_raw = $("lyricsText").value;
      P.alignment = null;
      renderLyricTags();
      renderAlignment(null);
    }
    const job = await api(`/api/projects/${P.id}/scan-lyrics`, { method: "POST" });
    $("scanLyricsBtn").disabled = true;
    $("alignLyricsBtn").disabled = true;
    setAlignmentStatus(job.message || "Listening for lyrics...");
    pollAlignment(P.id);
  } catch (e) {
    stopAlignmentPolling();
    setAlignmentStatus(e.message);
    toast(e.message);
  }
};

$("alignLyricsBtn").onclick = async () => {
  if (!P) return toast("Create a project first");
  if (!$("lyricsText").value.trim()) return toast("Paste the song lyrics first");
  markLyricMoveDraftStale("The lyrics are being aligned again. Rebuild the lyric-guided draft when it finishes.");
  try {
    if ($("lyricsText").value !== (P.lyrics_raw || "")) {
      const r = await api(`/api/projects/${P.id}/lyrics`, { method: "PUT",
        body: { text: $("lyricsText").value } });
      P.lyric_sections = r.sections;
      P.lyrics_raw = $("lyricsText").value;
      P.alignment = null;
      renderLyricTags();
      renderAlignment(null);
    }
    const job = await api(`/api/projects/${P.id}/align-lyrics`, { method: "POST" });
    $("alignLyricsBtn").disabled = true;
    $("scanLyricsBtn").disabled = true;
    setAlignmentStatus(job.message || "Aligning lyrics...");
    pollAlignment(P.id);
  } catch (e) { toast(e.message); }
};

$("acceptAlignmentBtn").onclick = async () => {
  if (!P) return;
  try {
    const result = await api(`/api/projects/${P.id}/alignment/accept`, { method: "POST" });
    P.sections = result.sections;
    P.alignment = result.alignment;
    P.phrase = null;
    loadBoundariesFromSections();
    renderSectionsTable();
    renderAlignment(P.alignment);
    drawWave();
    toast("Suggested markers added — drag any boundary to refine it");
  } catch (e) { toast(e.message); }
};

$("keepManualMarkersBtn").onclick = async () => {
  if (!P) return;
  try {
    const result = await api(`/api/projects/${P.id}/alignment/keep-manual`, { method: "POST" });
    P.alignment = result.alignment;
    renderAlignment(P.alignment);
    toast("Your manual waveform markers were kept");
  } catch (e) { toast(e.message); }
};

$("autoLabelBtn").onclick = () => {
  const tags = (P && P.lyric_sections) || [];
  if (!tags.length) return toast("Save lyrics & tags first");
  for (let i = 0; i + 1 < boundaries.length; i++) {
    labels[i] = tags[i] ? tags[i].label : labels[i] || `Section ${i + 1}`;
  }
  renderSectionsTable();
  drawWave();
  toast("Labels applied in tag order");
};
function renderSectionsTable() {
  const secs = sectionsFromBoundaries();
  const tb = $("sectionsTable");
  if (!secs.length) {
    tb.innerHTML = "<tr><td class='hint'>No sections yet. Use Add section at playhead, or shift+click two points on the waveform.</td></tr>";
    return;
  }
  tb.innerHTML = "<tr><th>Section label</th><th>Start</th><th>End</th><th>Length</th><th></th></tr>" +
    secs.map((s, i) => `<tr>
      <td><input data-i="${i}" class="secLabel" value="${esc(s.label)}"></td>
      <td><input type="text" inputmode="decimal" spellcheck="false" class="secTime" data-i="${i}" data-edge="start" value="${fmtTime(s.start)}" aria-label="Start time for ${esc(s.label)}"></td>
      <td><input type="text" inputmode="decimal" spellcheck="false" class="secTime" data-i="${i}" data-edge="end" value="${fmtTime(s.end)}" aria-label="End time for ${esc(s.label)}"></td>
      <td class="mono">${(s.end - s.start).toFixed(1)}s</td>
      <td><button type="button" class="del" data-i="${i}" aria-label="Remove ${esc(s.label)}">Remove</button></td>
    </tr>`).join("");
  tb.querySelectorAll(".secLabel").forEach(inp => {
    inp.onchange = () => { labels[+inp.dataset.i] = inp.value; drawWave(); };
  });
  tb.querySelectorAll(".secTime").forEach(inp => {
    const commit = () => editSectionTime(+inp.dataset.i, inp.dataset.edge, inp.value);
    inp.onchange = commit;
    inp.onblur = commit;
    inp.onkeydown = event => {
      if (event.key === "Enter") {
        event.preventDefault();
        commit();
      }
    };
  });
  tb.querySelectorAll(".del").forEach(d => {
    d.onclick = () => {
      const i = +d.dataset.i;
      boundaries.splice(i, 1);
      labels.splice(i, 1);
      renderSectionsTable();
      drawWave();
    };
  });
}
function parseSectionTime(value) {
  const raw = String(value || "").trim();
  if (!raw) return Number.NaN;
  if (!raw.includes(":")) return Number(raw);
  const parts = raw.split(":");
  if (parts.length !== 2) return Number.NaN;
  const minutes = Number(parts[0]);
  const seconds = Number(parts[1]);
  if (!Number.isFinite(minutes) || !Number.isFinite(seconds) || minutes < 0 || seconds < 0 || seconds >= 60) {
    return Number.NaN;
  }
  return minutes * 60 + seconds;
}
function editSectionTime(sectionIndex, edge, value) {
  if (!P || !P.analysis) return;
  const boundaryIndex = sectionIndex + (edge === "end" ? 1 : 0);
  const time = parseSectionTime(value);
  const duration = P.analysis.duration;
  const minimum = boundaryIndex > 0 ? boundaries[boundaryIndex - 1] + .05 : 0;
  const maximum = boundaryIndex < boundaries.length - 1
    ? boundaries[boundaryIndex + 1] - .05
    : duration;
  if (!Number.isFinite(time) || time < minimum || time > maximum) {
    toast(`Enter a time between ${fmtTime(minimum)} and ${fmtTime(maximum)}`);
    renderSectionsTable();
    return;
  }
  boundaries[boundaryIndex] = time;
  renderSectionsTable();
  drawWave();
}
$("addSectionBtn").onclick = () => {
  if (!P || !P.analysis) return toast("Analyze the song first so a section has real timing");
  const duration = P.analysis.duration;
  const audio = $("audio");
  let start = snapTime(Math.max(0, Math.min(duration, audio.currentTime || 0)));
  if (boundaries.length < 2) {
    // The first click creates a complete, visible section. A lone marker is
    // not useful in the table, so make a 16-second draft around the playhead.
    let end = snapTime(Math.min(duration, start + 16));
    if (end <= start + .15) {
      start = Math.max(0, duration - 16);
      end = duration;
    }
    boundaries = [start, end];
    labels = [nextSectionLabel()];
    audio.currentTime = start;
    renderSectionsTable();
    drawWave();
    return toast("New section added — type its label in the table");
  }
  if (!insertSectionBoundary(start)) {
    return toast("Move the playhead between two boundaries, then add the section");
  }
  renderSectionsTable();
  drawWave();
  toast("New section added — type its label in the table");
};
$("saveSectionsBtn").onclick = async () => {
  if (!P) return;
  const secs = sectionsFromBoundaries();
  await api(`/api/projects/${P.id}/sections`, { method: "PUT",
    body: { sections: secs } });
  P.sections = secs;
  toast(`Saved ${secs.length} sections`);
};

/* ---------------- phrase check ---------------- */
$("phraseBtn").onclick = async () => {
  if (!P) return;
  const secs = sectionsFromBoundaries();
  try {
    const r = await api(`/api/projects/${P.id}/phrase-check`, { method: "POST",
      body: { sections: secs, pattern_len: +$("patternLen").value } });
    P.phrase = r;
    P.sections = secs;
    renderPhrase(r);
  } catch (e) { toast(e.message); }
};
function renderPhrase(r) {
  const st = $("phraseStatus"), fl = $("phraseFlags"),
        tb = $("phraseTable"), tot = $("phraseTotals");
  if (!r) { st.innerHTML = ""; fl.innerHTML = ""; tb.innerHTML = ""; tot.innerHTML = ""; return; }
  const musicMapLabels = {
    CLEAN: "MUSIC MAP READY - your markers are preserved and the dance runs continuously.",
    REVIEW: "MUSIC MAP READY - the technical beat grid needs an ear-check; nothing was moved.",
    UNCERTAIN: "MUSIC MAP KEPT - verify the count overlay by ear before relying on it."
  };
  const markerNote = offset => {
    if (!Number.isFinite(offset)) return "No beat-grid read";
    if (offset === 0) return "On detected beat";
    return `Marker kept (${Math.abs(offset)}ms ${offset > 0 ? "after" : "before"} beat)`;
  };
  st.innerHTML = `<div class="statusbanner ${r.status}">${musicMapLabels[r.status] || r.status}</div>`;
  fl.innerHTML = (r.flags || []).map(f =>
    `<div class="flag ${f.severity || "info"}">${esc(f.message)}</div>`).join("");
  tb.innerHTML = "<tr><th>Song section</th><th>Song counts</th><th>Dance entry</th><th>Dance exit</th><th>How the dance fits</th><th>Grid note</th></tr>" +
    (r.sections || []).map(s => `<tr>
      <td>${esc(s.label)}</td>
      <td class="mono">${s.measured_beats ?? "?"}</td>
      <td class="mono">${s.dance_start_count ? "Count " + s.dance_start_count : "--"}</td>
      <td class="mono">${s.dance_end_count ? "Count " + s.dance_end_count : "--"}</td>
      <td class="dance-cue">${esc(s.dance_cue || "Dance fit not built for this saved report.")}</td>
      <td class="grid-note">${markerNote(s.marker_offset_ms)}</td>
    </tr>`).join("");
  const fit = r.dance_fit || {};
  const tail = Number.isFinite(fit.tail_counts) ?
    ` It reaches dance count ${fit.ending_count} at the end of this map.` : "";
  tot.innerHTML = `<strong>Continuous dance fit:</strong> ${esc(fit.advice || "Your song sections are the map; a dance phrase may cross them.")}` +
    `${tail} <span class="fit-meta">Music map: ${(r.music_map || {}).markers_preserved ? "preserved" : "saved"} - ` +
    `Grid total: ${(r.totals || {}).measured ?? "?"} counts</span>`;
  return;
  const labelTxt = { CLEAN: "CLEAN — both passes agree, phrasing is regular",
    REVIEW: "REVIEW — counts work but there are flags to read",
    UNCERTAIN: "UNCERTAIN — do not publish; the flags name the seam" };
  st.innerHTML = `<div class="statusbanner ${r.status}">${labelTxt[r.status] || r.status}</div>`;
  fl.innerHTML = (r.flags || []).map(f =>
    `<div class="flag ${f.severity}">${esc(f.message)}</div>`).join("");
  tb.innerHTML = "<tr><th>Section</th><th>Clock beats</th><th>Grid beats</th><th>Nearest 8</th><th>Residual</th><th>Verdict</th></tr>" +
    (r.sections || []).map(s => `<tr>
      <td>${esc(s.label)}</td>
      <td class="mono">${s.forward_beats}</td>
      <td class="mono">${s.measured_beats}</td>
      <td class="mono">${s.round8}</td>
      <td class="mono">${s.residual >= 0 ? "+" + s.residual : s.residual}</td>
      <td>${s.agree ? (s.classification === "clean" ? "✅ clean" : "⚠ " + s.classification) : "❌ passes disagree"}</td>
    </tr>`).join("");
  const t = r.totals || {};
  tot.innerHTML = `Intro: ${r.intro ? r.intro.beats : "?"} beats (suggest ${r.intro ? r.intro.suggest : "?"}) ·
    Outro: ${r.outro_beats} beats ·
    Totals: clock ${t.forward} vs grid ${t.measured}` +
    (r.tiling ? ` · ${r.tiling.danced_beats} danced counts = ${r.tiling.repetitions} × ${r.tiling.pattern_len}-count pattern ${r.tiling.clean ? "✅" : "❌"}` : "");
}

/* ---------------- lyric-guided draft ---------------- */
function resetLyricMoveDraft() {
  LYRIC_MOVE_DRAFT = null;
  lyricMoveRequestToken += 1;
  $("lyricMoveBadge").className = "tutorial-badge empty";
  $("lyricMoveBadge").textContent = "NOT BUILT";
  $("lyricMoveStatus").textContent = "";
  $("lyricMoveSummary").innerHTML = "";
  $("lyricLockedCues").innerHTML = "";
  $("lyricMoveIssues").innerHTML = "";
  $("lyricMoveCandidates").innerHTML = "";
  $("lyricPassageControl").hidden = true;
  $("lyricPassageSelect").disabled = true;
  $("lyricPassageSelect").innerHTML = '<option value="">Choose after the first scan</option>';
}

function lyricPercent(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "";
  const percent = number <= 1 ? number * 100 : number;
  return `${Math.round(percent)}%`;
}

function lyricPassageOption(passage, index) {
  const label = passage.label || `Passage ${index + 1}`;
  const start = Number(passage.start), end = Number(passage.end);
  const time = Number.isFinite(start) && Number.isFinite(end)
    ? ` · ${fmtTime(start)}–${fmtTime(end)}` : "";
  const passageCounts = passage.locked_counts ?? passage.matched_counts;
  const locked = Number.isFinite(Number(passageCounts))
    ? ` · ${Number(passageCounts)} matched counts` : "";
  return `${label}${time}${locked}`;
}

function lyricPassageId(passage) {
  return String(passage?.id ?? passage?.passage_id ?? "");
}

function lyricMoveName(moveId, lead, draft, detection) {
  if (detection && detection.move_name) return detection.move_name;
  for (const candidate of (draft.candidates || [])) {
    const match = (candidate.moves || []).find(move =>
      move.move_id === moveId && (!lead || move.lead === lead));
    if (match && match.name) return match.name;
  }
  const cached = (STEPS || []).find(move =>
    move.move_id === moveId && (!lead || move.lead === lead));
  if (cached && cached.name) return cached.name;
  return String(moveId || "Unresolved move").replaceAll("_", " ");
}

function lyricCandidateCheck(candidate, draft) {
  const moves = candidate.moves || [];
  const settings = draft.settings || {};
  const summary = draft.summary || {};
  const expected = Number(summary.total_counts ?? settings.counts ?? $("genCounts").value);
  if (String(draft.status || "").toUpperCase() === "STALE")
    return { complete: false, reason: "This draft is stale; rebuild it first.", total: 0 };
  if (candidate.complete === false || candidate.valid === false || candidate.validation?.valid === false)
    return { complete: false, reason: "The server marked this candidate incomplete.", total: 0 };
  if (!moves.length)
    return { complete: false, reason: "No moves were assembled.", total: 0 };
  if (!Number.isFinite(expected) || expected <= 0)
    return { complete: false, reason: "The required count total is missing.", total: 0 };

  const startFoot = settings.start_foot || "R";
  let foot = startFoot, rotation = 0, position = 0;
  for (const move of moves) {
    const counts = Number(move.counts);
    if (!move.move_id || !["R", "L"].includes(move.lead) ||
        !Number.isInteger(counts) || counts <= 0 || !["R", "L", "F"].includes(move.start) ||
        !["R", "L", "SAME"].includes(move.end) || !Number.isFinite(Number(move.rot))) {
      return { complete: false, reason: "A move is missing its checked count, foot, or turn mechanics.", total: position };
    }
    const blockEnd = Math.min((Math.floor(position / 8) + 1) * 8, expected);
    if (position + counts > blockEnd)
      return { complete: false, reason: `A move crosses the count ${blockEnd} phrase boundary.`, total: position };
    if (![foot, "F"].includes(move.start))
      return { complete: false, reason: `Foot continuity breaks before ${move.name || move.move_id}.`, total: position };
    position += counts;
    if (move.end !== "SAME") foot = move.end;
    rotation = (rotation + Number(move.rot)) % 360;
  }
  rotation = (rotation + 360) % 360;
  const wall = String(settings.wall ?? $("genWall").value);
  const turnDir = settings.turn_dir || $("genTurnDir").value;
  const targetRotation = wall === "1" ? 0 : wall === "2" ? 180 : turnDir === "R" ? 90 : 270;
  if (position !== expected)
    return { complete: false, reason: `${position} of ${expected} counts are filled.`, total: position };
  if (foot !== startFoot)
    return { complete: false, reason: `The pattern ends with ${foot} free instead of ${startFoot}.`, total: position };
  if (rotation !== targetRotation)
    return { complete: false, reason: `Net turn is ${rotation}°, not the required ${targetRotation}°.`, total: position };
  return { complete: true, reason: "Complete and ready for manual review.", total: position };
}

function lyricCandidateRows(candidate) {
  const provenance = candidate.provenance || [];
  const byStart = new Map(provenance
    .filter(row => Number.isFinite(Number(row.start_count)))
    .map(row => [Number(row.start_count), row]));
  let position = 1;
  return (candidate.moves || []).map((move, index) => {
    const source = byStart.get(position) || provenance[index] || move.provenance || {};
    const kind = String(source.kind || move.source || "gap_fill").toLowerCase() === "lyric"
      ? "lyric" : "gap_fill";
    const row = { move, source, kind, start: position,
      end: position + Number(move.counts || 0) - 1 };
    position = row.end + 1;
    return row;
  });
}

function renderLyricMoveDraft(draft) {
  const status = String(draft.status || "REVIEW").toUpperCase();
  const badge = $("lyricMoveBadge");
  badge.className = `tutorial-badge ${["READY", "REVIEW", "STALE", "BLOCKED"].includes(status) ? status : "REVIEW"}`;
  badge.textContent = status;
  $("lyricMoveStatus").textContent = status === "STALE"
    ? (draft.stale_reason || "The song, lyrics, or settings changed. Rebuild this draft before using it.")
    : status === "BLOCKED" ? "No safe lyric-guided candidate could be completed. Review the notes below."
    : "Review every lyric match and filled move before loading a candidate into Manual Build.";

  const passages = draft.passages || [];
  const passageSelect = $("lyricPassageSelect");
  const selectedId = String(draft.ui_selected_passage_id || draft.selected_passage_id || "");
  if (passages.length) {
    $("lyricPassageControl").hidden = false;
    passageSelect.disabled = false;
    passageSelect.innerHTML = passages.map((passage, index) =>
      `<option value="${esc(lyricPassageId(passage))}">${esc(lyricPassageOption(passage, index))}</option>`).join("");
    if (passages.some(passage => lyricPassageId(passage) === selectedId))
      passageSelect.value = selectedId;
  } else {
    $("lyricPassageControl").hidden = true;
    passageSelect.disabled = true;
  }
  const selectedPassage = passages.find(passage =>
    lyricPassageId(passage) === String(passageSelect.value || draft.selected_passage_id)) || passages[0];
  const activePassageId = selectedPassage ? lyricPassageId(selectedPassage) : selectedId;
  const summary = draft.summary || {};
  const totalCounts = summary.total_counts ?? draft.settings?.counts ?? "—";
  const anchoredMoves = summary.anchored_moves ?? summary.locked_moves ?? (draft.anchors || []).length;
  const anchoredCounts = Number(summary.anchored_counts ?? summary.locked_counts ?? 0);
  let filledCounts = summary.filled_counts;
  if (filledCounts == null) {
    const numericTotal = Number(totalCounts);
    if ((draft.candidates || []).length && Number.isFinite(numericTotal)) {
      filledCounts = Math.max(0, numericTotal - anchoredCounts);
    } else {
      filledCounts = (draft.gaps || [])
        .filter(gap => gap.filled === true || String(gap.status || "").toLowerCase() === "filled")
        .reduce((total, gap) => total + (Number(gap.counts) || 0), 0);
    }
  }
  const selectedCopy = selectedPassage
    ? `<div class="lyric-selected-passage"><b>Selected passage:</b> ${esc(selectedPassage.label || "Instruction passage")}` +
      `${Number.isFinite(Number(selectedPassage.start)) && Number.isFinite(Number(selectedPassage.end))
        ? ` · ${esc(fmtTime(Number(selectedPassage.start)))}–${esc(fmtTime(Number(selectedPassage.end)))}` : ""}` +
      `${selectedPassage.recommended ? " · recommended match" : ""}</div>` : "";
  $("lyricMoveSummary").innerHTML =
    `<div class="statusbanner ${status === "READY" ? "CLEAN" : status}">${status === "STALE" ? "STALE — rebuild before loading" : status === "BLOCKED" ? "BLOCKED — no complete safe draft" : "REVIEW — lyrics guided this draft; you stay in control"}</div>` +
    selectedCopy +
    `<div class="lyric-summary-grid">
      <div class="lyric-summary-stat"><strong>${esc(anchoredMoves)}</strong><span>lyric-locked moves</span></div>
      <div class="lyric-summary-stat"><strong>${esc(anchoredCounts)}</strong><span>lyric-supported counts</span></div>
      <div class="lyric-summary-stat"><strong>${esc(filledCounts)}</strong><span>compatible fill counts</span></div>
      <div class="lyric-summary-stat"><strong>${esc(totalCounts)}</strong><span>pattern counts</span></div>
    </div>`;

  const selectedDetections = (draft.detections || []).filter(row =>
    !row.passage_id || !activePassageId || String(row.passage_id) === activePassageId);
  const detections = new Map(selectedDetections.map(row => [row.id ?? row.detection_id, row]));
  const locked = $("lyricLockedCues");
  locked.className = "lyric-review-box";
  const cueRows = (draft.anchors || []).map(anchor => {
    const detection = detections.get(anchor.detection_id ?? anchor.id) || {};
    const counts = Number(anchor.counts ?? detection.counts ?? 0);
    const start = Number(anchor.start_count);
    const countLabel = Number.isFinite(start)
      ? (counts > 1 ? `${start}–${start + counts - 1}` : `${start}`) : "Review";
    const sourceText = anchor.lyric_text || anchor.source_text || detection.text || "Matched lyric cue";
    const confidence = lyricPercent(anchor.confidence ?? detection.confidence);
    return `<div class="lyric-cue-row">
      <span class="lyric-cue-count">Count ${esc(countLabel)}</span>
      <span class="lyric-cue-copy"><b>${esc(lyricMoveName(anchor.move_id, anchor.lead, draft, detection))}</b><small>“${esc(sourceText)}”</small></span>
      <span class="lyric-confidence">${esc(confidence || "review")}</span>
    </div>`;
  }).join("");
  locked.innerHTML = `<h4>Locked from the lyrics</h4><div class="lyric-cue-list">${cueRows || '<p class="hint">No lyric phrase was specific enough to lock a move.</p>'}</div>`;

  const issueHost = $("lyricMoveIssues");
  issueHost.className = "lyric-review-box";
  const issueRows = [];
  if (status === "STALE" && draft.stale_reason)
    issueRows.push({ code: "STALE", message: draft.stale_reason, severity: "error" });
  for (const issue of (draft.issues || []))
    issueRows.push(typeof issue === "string" ? { message: issue } : issue);
  const selectedUnresolved = (draft.unresolved || []).filter(row =>
    !row.passage_id || !activePassageId || String(row.passage_id) === activePassageId);
  for (const unresolved of selectedUnresolved)
    issueRows.push({ code: "UNRESOLVED LYRIC", message: `${unresolved.text || "Lyric cue"}: ${unresolved.message || unresolved.reason || "needs a human choice"}`, severity: "warn" });
  issueHost.innerHTML = `<h4>Ambiguities &amp; checks</h4><div class="lyric-issue-list">` +
    (issueRows.length ? issueRows.map(issue => {
      const severity = issue.severity === "error" ? "error" : issue.severity === "info" ? "info" : "warn";
      return `<div class="flag ${severity}">${issue.code ? `<b>${esc(issue.code)}:</b> ` : ""}${esc(issue.message || "Review this lyric cue.")}</div>`;
    }).join("") : '<p class="hint">No additional ambiguities were reported.</p>') + `</div>`;

  const candidateHost = $("lyricMoveCandidates");
  const candidates = draft.candidates || [];
  if (!candidates.length) {
    candidateHost.innerHTML = `<div class="warnbox">No complete candidate is available yet. ${$("lyricFillGaps").checked ? "Review the cue conflicts above." : "Turn on gap filling and rebuild, or finish the pattern manually."}</div>`;
    return;
  }
  candidateHost.innerHTML = candidates.map((candidate, index) => {
    const check = lyricCandidateCheck(candidate, draft);
    const blocks = [];
    for (const row of lyricCandidateRows(candidate)) {
      const number = Math.floor((row.start - 1) / 8) + 1;
      let block = blocks[blocks.length - 1];
      if (!block || block.number !== number) {
        block = { number, rows: [] };
        blocks.push(block);
      }
      block.rows.push(row);
    }
    const moveHtml = blocks.map(block => `<div class="lyric-block"><b>Counts ${(block.number - 1) * 8 + 1}–${block.number * 8}</b><ul class="lyric-move-list">` +
      block.rows.map(row => {
        const sourceText = row.source.lyric_text || row.source.source_text;
        return `<li class="lyric-move-row"><span class="provenance-chip ${row.kind === "lyric" ? "lyric" : "gap-fill"}">${row.kind === "lyric" ? "Lyric" : "Fill"}</span><span><b>${esc(row.start === row.end ? row.start : `${row.start}–${row.end}`)} · ${esc(row.move.name || row.move.move_id)}</b>${sourceText ? `<small>“${esc(sourceText)}”</small>` : ""}</span></li>`;
      }).join("") +
      `</ul></div>`).join("");
    const quality = candidate.quality || {};
    const qualityCopy = quality.score != null
      ? `<div class="cand-quality"><b>${esc(quality.score)}/100 · ${esc(quality.label || "Review draft")}</b><small>${esc(quality.publication_note || "Floor-test before saving.")}</small></div>` : "";
    return `<article class="lyric-candidate-card ${check.complete ? "" : "incomplete"}">
      <div class="lyric-candidate-heading"><h4>Lyric draft ${index + 1}</h4><span>${esc(check.total)} counts · ${esc(candidate.net_rot ?? "?")}° · ${esc(candidate.walls ?? "?")} wall${candidate.walls === 1 ? "" : "s"}</span></div>
      ${qualityCopy}${moveHtml}
      <div class="lyric-candidate-footer"><p class="notes">${esc(check.reason)}</p><button type="button" class="btn small ${check.complete ? "primary" : ""}" data-lyric-candidate="${index}" ${check.complete ? "" : "disabled"}>Load into Manual Build</button></div>
    </article>`;
  }).join("");
  candidateHost.querySelectorAll("[data-lyric-candidate]").forEach(button => {
    button.onclick = () => loadLyricCandidateIntoEditor(Number(button.dataset.lyricCandidate));
  });
}

function renderLyricMoveFailure(message, stale = false) {
  const badge = $("lyricMoveBadge");
  badge.className = `tutorial-badge ${stale ? "STALE" : "BLOCKED"}`;
  badge.textContent = stale ? "STALE" : "BLOCKED";
  $("lyricMoveStatus").textContent = stale
    ? "The source changed while this draft was being built. Nothing was loaded or saved."
    : "The lyric-guided draft could not be built. Nothing was changed.";
  $("lyricMoveSummary").innerHTML = "";
  $("lyricLockedCues").innerHTML = "";
  $("lyricMoveIssues").className = "lyric-review-box";
  $("lyricMoveIssues").innerHTML = `<h4>${stale ? "Rebuild required" : "Could not build"}</h4><div class="flag ${stale ? "error" : "warn"}">${esc(message)}</div>`;
  $("lyricMoveCandidates").innerHTML = "";
}

function markLyricMoveDraftStale(reason) {
  if (!LYRIC_MOVE_DRAFT) return;
  LYRIC_MOVE_DRAFT = {
    ...LYRIC_MOVE_DRAFT,
    status: "STALE",
    stale_reason: reason,
    ui_selected_passage_id: $("lyricPassageSelect").value,
  };
  renderLyricMoveDraft(LYRIC_MOVE_DRAFT);
}

async function loadLyricCandidateIntoEditor(index) {
  const draft = LYRIC_MOVE_DRAFT;
  const candidate = draft && (draft.candidates || [])[index];
  if (!candidate) return toast("That lyric-guided candidate is no longer available");
  const check = lyricCandidateCheck(candidate, draft);
  if (!check.complete) return toast(check.reason);
  await ensureSteps();
  const moves = (candidate.moves || []).map(move => ({ move_id: move.move_id, lead: move.lead }));
  const missing = moves.find(item => !stepInfo(item.move_id, item.lead));
  if (missing) return toast(`Move ${missing.move_id} is not available in the current library`);
  const settings = draft.settings || {};
  seq = moves;
  $("edCounts").value = String(settings.counts ?? $("genCounts").value);
  $("edWall").value = String(settings.wall ?? $("genWall").value);
  $("edTurnDir").value = settings.turn_dir || $("genTurnDir").value;
  $("editorDraftNotice").hidden = false;
  renderSequence();
  document.querySelector('.tab[data-tab="editor"]').click();
  toast("Lyric-guided draft loaded for review — it has not been saved");
}

$("lyricMoveDraftBtn").onclick = async () => {
  if (!P) return toast("Create or open a project first");
  if (!P.alignment) return renderLyricMoveFailure("Scan or align the lyrics first so the app has timed words to review.");
  const projectId = P.id;
  const token = ++lyricMoveRequestToken;
  const button = $("lyricMoveDraftBtn");
  const passageId = $("lyricPassageControl").hidden ? "" : $("lyricPassageSelect").value;
  const body = {
    level: $("genLevel").value,
    wall: $("genWall").value,
    turn_dir: $("genTurnDir").value,
    counts: +$("genCounts").value,
    seed: +$("genSeed").value,
    k: +$("genK").value,
    allow_sync: $("genSync").checked,
    experimental_mode: $("genExperimental").checked,
    publication_mode: $("genPolish").checked,
    include_custom_moves: $("genCustom").checked,
    fill_gaps: $("lyricFillGaps").checked,
  };
  if (passageId) body.passage_id = passageId;
  button.disabled = true;
  button.textContent = "Building review draft…";
  $("lyricMoveBadge").className = "tutorial-badge empty";
  $("lyricMoveBadge").textContent = "BUILDING";
  $("lyricMoveStatus").textContent = "Reading the timed lyrics and checking count, foot, and wall compatibility…";
  $("lyricMoveCandidates").innerHTML = "";
  try {
    const response = await api(`/api/projects/${projectId}/lyric-moves/draft`, { method: "POST", body });
    if (!P || P.id !== projectId || token !== lyricMoveRequestToken) return;
    const draft = response && response.draft ? response.draft : response;
    LYRIC_MOVE_DRAFT = draft || {};
    P.lyric_move_draft = LYRIC_MOVE_DRAFT;
    renderLyricMoveDraft(LYRIC_MOVE_DRAFT);
    if (String(LYRIC_MOVE_DRAFT.status || "").toUpperCase() === "STALE")
      toast("The draft is stale — rebuild it before loading a candidate");
    else toast(`${(LYRIC_MOVE_DRAFT.candidates || []).length} lyric-guided draft${(LYRIC_MOVE_DRAFT.candidates || []).length === 1 ? "" : "s"} ready to review`);
  } catch (error) {
    if (!P || P.id !== projectId || token !== lyricMoveRequestToken) return;
    const returned = error.data && (error.data.draft || (error.data.status ? error.data : null));
    if (returned) {
      LYRIC_MOVE_DRAFT = returned;
      P.lyric_move_draft = LYRIC_MOVE_DRAFT;
      renderLyricMoveDraft(returned);
    } else {
      const code = String(error.data?.error || error.data?.code || "").toUpperCase();
      renderLyricMoveFailure(error.message, code === "STALE" || error.status === 409 && code.includes("STALE"));
    }
    toast(error.message);
  } finally {
    if (P && P.id === projectId && token === lyricMoveRequestToken) {
      button.disabled = false;
      button.textContent = "Build from lyric moves";
    }
  }
};

$("lyricPassageSelect").onchange = () =>
  markLyricMoveDraftStale("A different instruction passage is selected. Build again to review its lyric moves.");
$("lyricFillGaps").onchange = () =>
  markLyricMoveDraftStale("The gap-filling choice changed. Build again before loading a candidate.");
for (const id of ["genLevel", "genWall", "genTurnDir", "genCounts", "genSeed", "genK",
                  "genSync", "genPolish", "genCustom", "genExperimental"]) {
  $(id).addEventListener("change", () =>
    markLyricMoveDraftStale("Generation settings changed. Build the lyric-guided draft again before loading it."));
}

/* ---------------- generate ---------------- */
$("generateBtn").onclick = async () => {
  if (!P) return;
  $("genError").innerHTML = "";
  try {
    const r = await api(`/api/projects/${P.id}/generate`, { method: "POST",
      body: {
        level: $("genLevel").value, wall: $("genWall").value,
        turn_dir: $("genTurnDir").value, counts: +$("genCounts").value,
        seed: +$("genSeed").value, k: +$("genK").value,
        allow_sync: $("genSync").checked,
        experimental_mode: $("genExperimental").checked,
        publication_mode: $("genPolish").checked,
        include_custom_moves: $("genCustom").checked,
      } });
    P = await api("/api/projects/" + P.id);
    renderCandidates();
    toast(`Generated ${r.candidates.length} candidate${r.candidates.length > 1 ? "s" : ""}`);
  } catch (e) {
    const d = e.data || {};
    $("genError").innerHTML = `<div class="errbox"><b>${esc(d.error || "Error")}</b>: ${esc(d.message || e.message)}</div>`;
  }
};
$("manualBuildBtn").onclick = () => document.querySelector('.tab[data-tab="editor"]').click();
$("autoBuildBtn").onclick = () => document.querySelector('.tab[data-tab="generate"]').click();
function groupBlocks(moves) {
  const blocks = [];
  let pos = 0, cur = null;
  for (const m of moves) {
    const bi = Math.floor(pos / 8);
    if (!cur || cur.n !== bi + 1) { cur = { n: bi + 1, items: [] }; blocks.push(cur); }
    cur.items.push(m.name);
    pos += m.counts;
  }
  return blocks;
}
function renderCandidates() {
  const box = $("candidates");
  const d = (P && P.dance) || {};
  const cands = d.candidates || [];
  box.innerHTML = "";
  cands.forEach((c, i) => {
    const div = document.createElement("div");
    div.className = "cand" + ((d.chosen ?? 0) === i && d.source !== "custom" ? " chosen" : "");
    const quality = c.quality || {};
    const strengths = (quality.strengths || []).join(" · ");
    const cautions = (quality.cautions || []).join(" · ");
    div.innerHTML = `<h3>Candidate ${i + 1} ${((d.chosen ?? 0) === i && d.source !== "custom") ? "· CHOSEN" : ""}</h3>` +
      groupBlocks(c.moves).map(b =>
        `<div class="blk"><b>Counts ${(b.n - 1) * 8 + 1}–${b.n * 8}</b><ul>` +
        b.items.map(x => `<li>${esc(x)}</li>`).join("") + "</ul></div>").join("") +
      `<div class="notes">net rotation ${c.net_rot}° → ${c.walls} wall${c.walls > 1 ? "s" : ""}</div>`;
    if (quality.score != null) {
      const summary = `<div class="cand-quality"><b>${quality.score}/100 · ${esc(quality.label || "Draft")}</b>` +
        `${strengths ? `<span>${esc(strengths)}</span>` : ""}` +
        `${cautions ? `<span class="caution">Edit: ${esc(cautions)}</span>` : ""}` +
        `<small>Signature opportunity: ${esc(quality.signature_opportunity || "choose one in the editor")}</small></div>`;
      div.querySelector("h3").insertAdjacentHTML("afterend", summary);
    }
    div.onclick = async () => {
      await api(`/api/projects/${P.id}/dance`, { method: "PUT",
        body: { source: "generated", chosen: i } });
      P.dance.chosen = i;
      P.dance.source = "generated";
      renderCandidates();
      toast(`Candidate ${i + 1} chosen`);
    };
    box.appendChild(div);
  });
  if (!cands.length)
    box.innerHTML = "<p class='hint'>No candidates yet — set the options and Generate.</p>";
}

/* ---------------- editor ---------------- */
async function ensureSteps() {
  if (!STEPS) STEPS = await api("/api/steps");
  return STEPS;
}
async function renderLibrary() {
  await ensureSteps();
  const q = $("libFilter").value.toLowerCase();
  const abOnly = $("libABOnly").checked;
  const customOnly = $("libCustomOnly").checked;
  const level = $("libLevel").value;
  const box = $("library");
  box.innerHTML = "";
  for (const s of STEPS) {
    if (abOnly && !s.ab_safe) continue;
    if (LEVEL_RANK[s.level] > LEVEL_RANK[level]) continue;
    if (customOnly && !s.move_id.startsWith("custom-")) continue;
    if (q && !s.name.toLowerCase().includes(q)) continue;
    // free-foot fillers resolve their foot automatically — show them once
    if (s.start === "F" && s.lead === "L") continue;
    const div = document.createElement("div");
    div.className = "lib-item";
    div.innerHTML = `<span>${esc(s.name)}</span>
      <span class="meta">${s.counts}ct · ${s.rot ? s.rot + "°" : "—"} · ${s.start}→${s.end === "SAME" ? "=" : s.end} · ${s.level}</span>`;
    div.onclick = () => {
      seq.push({ move_id: s.move_id, lead: s.lead });
      renderSequence();
    };
    box.appendChild(div);
  }
}
$("libFilter").oninput = renderLibrary;
$("libABOnly").onchange = renderLibrary;
$("libLevel").onchange = renderLibrary;
$("libCustomOnly").onchange = renderLibrary;

async function refreshMoveLibrary() {
  try {
    const [summary, custom] = await Promise.all([
      api("/api/moves/summary"), api("/api/moves/custom"),
    ]);
    $("librarySummary").textContent = `${summary.buildable_moves} buildable moves (${summary.built_in_moves} built-in, ${summary.custom_moves} yours) plus a ${summary.reference_glossary}-term reference glossary. ${summary.note}`;
    const list = $("customMovesList");
    list.innerHTML = "";
    if (!custom.length) {
      list.innerHTML = "<p class='hint'>No custom moves yet. Add one manually or import a completed move list.</p>";
      return;
    }
    for (const move of custom) {
      const row = document.createElement("div");
      row.className = "custom-move-row";
      row.innerHTML = `<span><strong>${esc(move.name)}</strong> <span class="meta">${esc(move.counts)}ct · ${esc(move.start)}→${esc(move.end)} · ${esc(move.level)}${move.in_generator ? " · auto-ready" : " · editor only"}</span></span>`;
      const remove = document.createElement("button");
      remove.className = "btn small danger";
      remove.type = "button";
      remove.textContent = "Remove";
      remove.onclick = async () => {
        if (!confirm(`Remove custom move "${move.name}" from your library?`)) return;
        try {
          await api(`/api/moves/custom/${encodeURIComponent(move.id)}`, { method: "DELETE" });
          STEPS = null;
          await renderLibrary();
          refreshMoveLibrary();
          toast("Custom move removed");
        } catch (err) { toast(err.message); }
      };
      row.appendChild(remove);
      list.appendChild(row);
    }
  } catch (err) {
    $("librarySummary").textContent = err.message;
  }
}

$("customMoveForm").onsubmit = async event => {
  event.preventDefault();
  const status = $("customMoveStatus");
  status.textContent = "Adding move...";
  const body = {
    name: $("customMoveName").value.trim(), counts: +$("customMoveCounts").value,
    start: $("customMoveStart").value, end: $("customMoveEnd").value,
    rotation: +$("customMoveRotation").value, level: $("customMoveLevel").value,
    travel: $("customMoveTravel").value, family: $("customMoveFamily").value.trim() || null,
    instructions: $("customMoveInstructions").value.trim(), sync: $("customMoveSync").checked,
    in_generator: $("customMoveGenerator").checked,
  };
  try {
    await api("/api/moves/custom", { method: "POST", body });
    event.target.reset();
    $("customMoveCounts").value = 2;
    $("customMoveLevel").value = "I";
    status.textContent = "Custom move added to your editor library.";
    STEPS = null;
    await renderLibrary();
    refreshMoveLibrary();
    toast("Custom move added");
  } catch (err) {
    status.textContent = err.message;
  }
};

$("importMovesBtn").onclick = async () => {
  const input = $("moveImportFile");
  const result = $("moveImportResult");
  const file = input.files && input.files[0];
  if (!file) return toast("Choose a move file first");
  const fd = new FormData();
  fd.append("file", file);
  result.innerHTML = "<p class='hint'>Reading move file...</p>";
  try {
    const response = await fetch("/api/moves/import", { method: "POST", body: fd });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || response.statusText);
    const accepted = data.accepted || [];
    const review = data.needs_review || [];
    result.innerHTML = `<div class="okbox">Imported ${accepted.length} of ${data.found} move row${data.found === 1 ? "" : "s"}.</div>` +
      (review.length ? `<div class="errbox">${review.length} row${review.length === 1 ? "" : "s"} need review. The app did not guess their mechanics.</div><ul class="import-review">${review.slice(0, 12).map(item => `<li><b>${esc(item.name)}</b>: ${esc(item.reason)}</li>`).join("")}${review.length > 12 ? `<li>…and ${review.length - 12} more</li>` : ""}</ul>` : "");
    input.value = "";
    STEPS = null;
    await renderLibrary();
    refreshMoveLibrary();
    toast(`${accepted.length} custom move${accepted.length === 1 ? "" : "s"} imported`);
  } catch (err) {
    result.innerHTML = `<div class="errbox">${esc(err.message)}</div>`;
  }
};

$("downloadMoveTemplateBtn").onclick = async () => {
  try {
    const template = await api("/api/moves/template");
    const blob = new Blob([JSON.stringify(template, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "line-dance-move-template.json";
    link.click();
    URL.revokeObjectURL(url);
  } catch (err) { toast(err.message); }
};

function stepInfo(move_id, lead) {
  return STEPS.find(s => s.move_id === move_id && s.lead === lead);
}
function renderSequence() {
  const ol = $("sequence");
  ol.innerHTML = "";
  let pos = 0;
  seq.forEach((it, i) => {
    const s = stepInfo(it.move_id, it.lead);
    const li = document.createElement("li");
    li.innerHTML = `<span>${pos + 1}–${pos + s.counts}: ${esc(s.name)}
        <span class="hint">(${s.start}→${s.end === "SAME" ? "=" : s.end}${s.rot ? ", " + s.rot + "°" : ""})</span></span>
      <span class="ctl">
        <button data-a="lead" data-i="${i}" title="flip lead foot">R/L</button>
        <button data-a="up" data-i="${i}">↑</button>
        <button data-a="dn" data-i="${i}">↓</button>
        <button data-a="rm" data-i="${i}">✕</button>
      </span>`;
    ol.appendChild(li);
    pos += s.counts;
  });
  ol.querySelectorAll("button").forEach(b => {
    b.onclick = () => {
      const i = +b.dataset.i;
      if (b.dataset.a === "rm") seq.splice(i, 1);
      if (b.dataset.a === "up" && i > 0) [seq[i - 1], seq[i]] = [seq[i], seq[i - 1]];
      if (b.dataset.a === "dn" && i < seq.length - 1) [seq[i + 1], seq[i]] = [seq[i], seq[i + 1]];
      if (b.dataset.a === "lead") seq[i].lead = seq[i].lead === "R" ? "L" : "R";
      renderSequence();
    };
  });
  clearTimeout(validateTimer);
  validateTimer = setTimeout(validateSeq, 250);
}
async function validateSeq() {
  const box = $("edValidation");
  if (!seq.length) { box.innerHTML = "<p class='hint'>Empty sequence.</p>"; return; }
  const r = await api("/api/validate", { method: "POST", body: {
    moves: seq, counts: +$("edCounts").value,
    wall: $("edWall").value, turn_dir: $("edTurnDir").value,
    bpm: P && P.analysis ? P.analysis.bpm : null } });
  const chips = `<div class="notes">${r.counts} counts · ends ${r.end_foot} free ·
    net ${r.net_rot}° → ${r.walls} wall${r.walls > 1 ? "s" : ""}</div>`;
  if (r.valid) box.innerHTML = `<div class="okbox">✅ Valid: counts, foot continuity and walls all close.</div>` + chips;
  else box.innerHTML = r.problems.map(p =>
    `<div class="flag error">${esc(p.message)}</div>`).join("") + chips;
}
$("edCounts").onchange = validateSeq;
$("edWall").onchange = validateSeq;
$("edTurnDir").onchange = validateSeq;
$("edClear").onclick = () => {
  seq = [];
  $("editorDraftNotice").hidden = true;
  renderSequence();
};
$("edLoadGenerated").onclick = async () => {
  await ensureSteps();
  const d = (P && P.dance) || {};
  let moves = null;
  if (d.source === "custom" && d.custom) moves = d.custom;
  else if (d.candidates && d.candidates.length)
    moves = d.candidates[d.chosen ?? 0].moves;
  if (!moves) return toast("No dance to load yet");
  seq = frozenLegacyMoves(moves, d.start_foot||"R");
  $("edCounts").value = d.counts || 32;
  $("edWall").value = d.wall || "2";
  $("edTurnDir").value = d.turn_dir || "L";
  $("editorDraftNotice").hidden = true;
  renderSequence();
};
$("edSaveBtn").onclick = async () => {
  if (!P) return;
  if (!seq.length) return toast("Sequence is empty");
  const r = await api(`/api/projects/${P.id}/dance`, { method: "PUT", body: {
    source: "custom", moves: seq, counts: +$("edCounts").value,
    wall: $("edWall").value, turn_dir: $("edTurnDir").value } });
  P = await api("/api/projects/" + P.id);
  $("editorDraftNotice").hidden = true;
  if (r.validation && !r.validation.valid)
    toast("Saved — but it FAILS validation; any export will carry a DRAFT banner");
  else toast("Saved as the project dance");
};

/* ---------------- tutorial blueprint ---------------- */
const TUTORIAL_CAMERAS = [
  ["rear_full", "Rear full body"],
  ["rear_wide", "Rear wide / travel"],
  ["feet_rear", "Rear feet close-up"],
  ["side_full", "Side full body"],
  ["overhead_feet", "Overhead foot path"],
];

function tutorialIssueMessage(issue) {
  if (typeof issue === "string") return issue;
  return issue && (issue.message || issue.code) || "Unknown tutorial check";
}

function tutorialCallout(segment) {
  return typeof segment.callout === "string"
    ? segment.callout : (segment.callout && segment.callout.text) || "";
}

function tutorialCamera(segment) {
  return typeof segment.camera === "string"
    ? segment.camera : (segment.camera && (segment.camera.primary || segment.camera.view || segment.camera.id)) || "rear_full";
}

function tutorialInstructionHtml(segment) {
  const lines = segment.instruction_lines || segment.lines || [];
  if (!lines.length) return `<span>${esc(segment.instruction || "No instruction line")}</span>`;
  return lines.map(line => {
    if (typeof line === "string") return `<span>${esc(line)}</span>`;
    const label = line.count_label || line.label || "";
    const copy = line.instruction || line.text || "";
    return `<span>${label ? `<b>${esc(label)}</b> ` : ""}${esc(copy)}</span>`;
  }).join("");
}

function setTutorialLinks(enabled) {
  const links = [
    ["tutorialTxtLink", "tutorial.txt"],
    ["tutorialCsvLink", "tutorial.csv"],
    ["tutorialJsonLink", "tutorial.json"],
  ];
  for (const [id, suffix] of links) {
    const link = $(id);
    if (enabled && P) {
      link.href = `/api/projects/${P.id}/${suffix}`;
      link.classList.remove("disabled-link");
      link.setAttribute("aria-disabled", "false");
    } else {
      link.removeAttribute("href");
      link.classList.add("disabled-link");
      link.setAttribute("aria-disabled", "true");
    }
  }
}

function renderTutorial(plan) {
  const badge = $("tutorialBadge");
  const statusBox = $("tutorialStatus");
  const table = $("tutorialTable");
  const summary = $("tutorialSummary");
  const walls = $("tutorialWalls");
  const save = $("saveTutorialBtn");
  if (!plan) {
    badge.className = "tutorial-badge empty";
    badge.textContent = "NOT BUILT";
    statusBox.innerHTML = `<div class="flag info">Choose a saved dance, then build its tutorial blueprint. Existing step-sheet work is not changed.</div>`;
    summary.innerHTML = `<p class="hint">No tutorial timing has been built for this project.</p>`;
    walls.innerHTML = "";
    table.innerHTML = `<tr><td class="hint">Build the blueprint to see count-locked movement, voice, and camera cues.</td></tr>`;
    save.disabled = true;
    setTutorialLinks(false);
    return;
  }

  const validation = plan.validation || {};
  const state = validation.status || plan.status || "REVIEW";
  const settings = plan.settings || {};
  const source = plan.source || {};
  badge.className = `tutorial-badge ${esc(state)}`;
  badge.textContent = state;
  $("tutorialLead").value = String(settings.callout_lead_counts || 2);
  $("tutorialVoice").value = settings.voice_name || "Georgia Belle";
  $("tutorialAnchor").value = source.anchor_source_seconds == null ? "" : source.anchor_source_seconds;
  $("tutorialTempoConfirmed").checked = !!settings.tempo_grid_confirmed;
  $("tutorialCountIn").value = settings.count_in || "Five, six, seven, eight";
  $("tutorialVoiceNotes").value = settings.voice_notes || "";
  $("tutorialProducerNotes").value = settings.producer_notes || "";

  const errors = validation.errors || [];
  const warnings = validation.warnings || [];
  const pending = validation.confirmation_pending == null
    ? (plan.segments || []).filter(x => !x.confirmed).length
    : validation.confirmation_pending;
  let notices = "";
  if (validation.ready) {
    notices += `<div class="okbox">READY — timing, dance source, calls, camera coverage, and every human review are current.</div>`;
  }
  if (errors.length) {
    notices += `<div class="errbox"><b>Blocked:</b><br>${errors.map(x => `• ${esc(tutorialIssueMessage(x))}`).join("<br>")}</div>`;
  }
  if (warnings.length) {
    notices += `<div class="warnbox"><b>Review:</b><br>${warnings.map(x => `• ${esc(tutorialIssueMessage(x))}`).join("<br>")}</div>`;
  }
  if (pending) {
    notices += `<div class="flag info">${pending} cue${pending === 1 ? "" : "s"} still need a human count/feet/call/camera check.</div>`;
  }
  statusBox.innerHTML = notices || `<div class="flag info">Blueprint built. Review each cue before production.</div>`;

  const dance = plan.dance || {};
  const segmentCount = (plan.segments || []).length;
  summary.innerHTML = `
    <div class="tutorial-stat"><strong>${esc(dance.total_counts || "—")}</strong><span>pattern counts</span></div>
    <div class="tutorial-stat"><strong>${esc(source.bpm || "—")}</strong><span>selected BPM</span></div>
    <div class="tutorial-stat"><strong>${segmentCount}</strong><span>movement cues</span></div>`;
  walls.innerHTML = (plan.wall_plan || []).map(pass => {
    const n = pass.pass || pass.number || "";
    const start = pass.start_facing || pass.facing_start || "—";
    const end = pass.end_facing || pass.facing_end || "—";
    return `<span class="wall-pass">Pass ${esc(n)} · ${esc(start)} → ${esc(end)}</span>`;
  }).join("");

  const cameraOptions = selected => TUTORIAL_CAMERAS.map(([id, label]) =>
    `<option value="${id}"${id === selected ? " selected" : ""}>${esc(label)}</option>`).join("");
  table.innerHTML = `<thead><tr><th>Counts</th><th>Song time</th><th>Exact footwork</th><th>Facing</th><th>GB callout</th><th>Camera</th><th>Checked</th><th>Review note</th></tr></thead><tbody>` +
    (plan.segments || []).map(segment => {
      const camera = tutorialCamera(segment);
      const facingStart = segment.facing_start || "—";
      const facingEnd = segment.facing_end || facingStart;
      const timecode = segment.start_timecode || segment.timecode || "—";
      return `<tr data-segment-id="${esc(segment.id)}">
        <td class="cue-count">${esc(segment.count_label || `${segment.start_count}-${segment.end_count}`)}</td>
        <td class="cue-time">${esc(timecode)}</td>
        <td class="cue-move"><strong>${esc(segment.move_name || segment.move_id)}</strong>${tutorialInstructionHtml(segment)}</td>
        <td class="cue-facing">${esc(facingStart)}${facingEnd !== facingStart ? ` → ${esc(facingEnd)}` : ""}</td>
        <td><input class="cue-callout" maxlength="120" value="${esc(tutorialCallout(segment))}"></td>
        <td><select class="cue-camera">${cameraOptions(camera)}</select>${segment.camera && segment.camera.secondary ? `<span class="field-hint">Insert: ${esc(segment.camera.secondary.replaceAll("_", " "))}</span>` : ""}${segment.camera && segment.camera.reason ? `<span class="field-hint">${esc(segment.camera.reason)}</span>` : ""}</td>
        <td class="cue-review"><input class="cue-confirmed" type="checkbox" aria-label="Cue checked"${segment.confirmed ? " checked" : ""}></td>
        <td><input class="cue-note" maxlength="240" value="${esc(segment.review_note || "")}" placeholder="optional"></td>
      </tr>`;
    }).join("") + `</tbody>`;
  save.disabled = !(plan.segments || []).length;
  setTutorialLinks(true);
}

async function refreshTutorial() {
  if (!P) return renderTutorial(null);
  const before=readLegacyForms().tutorial_edits;
  if(!LineDanceMerge.equal(before,legacyFormBase?.tutorial_edits))return toast("Unsaved tutorial edits retained. Save them before refreshing this blueprint.");
  try {
    const result = await api(`/api/projects/${P.id}/tutorial`);
    if(!LineDanceMerge.equal(before,readLegacyForms().tutorial_edits))return toast("Tutorial edits changed while loading; your edits are retained.");
    P.tutorial = result.tutorial || null;
    renderTutorial(P.tutorial);
    if(legacyBaseDraft)legacyBaseDraft.tutorial=structuredClone(P.tutorial);
    if(legacyFormBase){const current=readLegacyForms();if(current.tutorial_edits)legacyFormBase.tutorial_edits=current.tutorial_edits;else delete legacyFormBase.tutorial_edits;}
  } catch (err) {
    $("tutorialStatus").innerHTML = `<div class="errbox">${esc(err.message)}</div>`;
  }
}

$("buildTutorialBtn").onclick = async () => {
  if (!P) return toast("Open a project first");
  const button = $("buildTutorialBtn");
  button.disabled = true;
  try {
    const anchorRaw = $("tutorialAnchor").value.trim();
    const result = await api(`/api/projects/${P.id}/tutorial/build`, { method: "POST", body: {
      callout_lead_counts: +$("tutorialLead").value,
      voice_name: $("tutorialVoice").value.trim() || "Georgia Belle",
      anchor_seconds: anchorRaw === "" ? null : +anchorRaw,
      tempo_grid_confirmed: $("tutorialTempoConfirmed").checked,
      count_in: $("tutorialCountIn").value.trim() || "Five, six, seven, eight",
      voice_notes: $("tutorialVoiceNotes").value.trim(),
      producer_notes: $("tutorialProducerNotes").value.trim(),
    } });
    P.tutorial = result.tutorial;
    renderTutorial(P.tutorial);
    toast("Tutorial blueprint built — review each cue");
  } catch (err) {
    $("tutorialStatus").innerHTML = `<div class="errbox">${esc(err.message)}</div>`;
    toast(err.message);
  } finally {
    button.disabled = false;
  }
};

$("saveTutorialBtn").onclick = async () => {
  if(!P?.tutorial)return;
  if(await saveProjectAll()){P.tutorial=structuredClone(P.draft.tutorial);renderTutorial(P.tutorial);toast("Cue review saved with current provenance and timing.");}
};

/* ---------------- export ---------------- */
function loadMetaForm() {
  const m = (P && P.sheet_meta) || {};
  $("metaDanceTitle").value = m.dance_title || "";
  $("metaChoreo").value = m.choreographer || "";
  $("metaCountry").value = m.country || "";
  $("metaContact").value = m.contact || "";
  $("metaLevel").value = m.level_label || "";
  $("metaDesc").value = m.description || "";
  $("metaSig").value = m.signature_note || "";
  $("metaEnding").value = m.ending_note || "";
  $("metaYoutubeUrl").value = m.youtube_url || "";
  $("metaSheetUrl").value = m.sheet_url || "";
}
$("metaSaveBtn").onclick = async () => {
  if(!P)return;
  if(await saveProjectAll()){P.sheet_meta=structuredClone(P.draft.sheet_meta||{});refreshExport();}
};
async function refreshExport() {
  if (!P) return;
  $("txtLink").href = `/api/projects/${P.id}/sheet.txt`;
  $("htmlLink").href = `/api/projects/${P.id}/sheet.html`;
  $("pdfLink").href = `/api/projects/${P.id}/sheet.pdf`;
  try {
    const r = await api(`/api/projects/${P.id}/sheet.json`);
    const v = r.validation;
    $("sheetWarn").innerHTML = v && !v.valid
      ? `<div class="errbox">⚠ The current dance does not validate — fix it before publishing:<br>` +
        v.problems.map(p => "• " + esc(p.message)).join("<br>") + "</div>"
      : "";
    $("sheetFrame").src = `/api/projects/${P.id}/sheet.html?t=` + Date.now();
  } catch (e) {
    $("sheetWarn").innerHTML = `<div class="warnbox">${esc(e.message)}</div>`;
    $("sheetFrame").src = "about:blank";
  }
}
$("exportAllBtn").onclick = async () => {
  if (!P) return;
  try {
    const r = await api(`/api/projects/${P.id}/export-files`, { method: "POST" });
    $("exportResult").innerHTML =
      `Exported <b>${r.files.length}</b> files to <span class="mono">${esc(r.folder)}</span>` +
      "<br>" + r.files.map(esc).join(" · ");
    toast("Exported to folder");
  } catch (e) {
    $("exportResult").textContent = e.message;
    toast(e.message);
  }
};
$("publisherBtn").onclick = async () => {
  if (!P) return;
  try {
    const k = await api(`/api/projects/${P.id}/publish-kit`);
    $("publisherCard").style.display = "";
    $("pkTitle").value = k.youtube_title;
    $("pkYoutube").value = k.youtube_add_on;
    $("pkTags").value = k.hashtags;
    $("pkCopperComments").value = k.copperknob_comments;
    $("pkCopperList").innerHTML = (k.copperknob_checklist || [])
      .map(item => `<li>${esc(item)}</li>`).join("");
    $("pkBootList").innerHTML = (k.bootstepper_checklist || [])
      .map(item => `<li>${esc(item)}</li>`).join("");
  } catch (e) { toast(e.message); }
};
document.querySelectorAll(".copybtn").forEach(b => {
  b.onclick = () => {
    const el = $(b.dataset.copy);
    navigator.clipboard.writeText(el.value);
    toast("Copied");
  };
});

/* ---------------- boot ---------------- */
if (IS_FILE_PREVIEW) {
  $("fileMode").hidden = false;
} else {
  loadProjects().catch(e => {
    $("projectSelect").innerHTML = "<option>Unable to load projects</option>";
    $("projectSelect").disabled = true;
    $("openProjectBtn").disabled = true;
    toast(e.message);
  });
  // Settings are deliberately optional. A settings problem should never
  // interrupt opening or using the built-in generator.
  loadAISettings().catch(() => {});
}
