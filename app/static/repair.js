/* Sound Repair Studio client.  All audio processing stays in the local server. */
const $ = (selector) => document.querySelector(selector);
const state = { project: null, poller: null, info: null, activeTab: "song" };
const audio = $("#originalAudio");
const previewMode = window.location.protocol === "file:";

async function api(path, options = {}) {
  if (previewMode) {
    throw new Error("This is a visual preview. Start app/run.bat to use song repair.");
  }
  const response = await fetch(path, options);
  if (!response.ok) {
    let message = "Something went wrong.";
    try { message = (await response.json()).detail || message; } catch (_) { /* friendly fallback */ }
    throw new Error(message);
  }
  const contentType = response.headers.get("content-type") || "";
  return contentType.includes("application/json") ? response.json() : response;
}

function setStatus(element, message = "", kind = "") {
  element.textContent = message;
  element.className = `status ${kind}`;
}

function clock(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) return "--:--";
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${(seconds % 60).toFixed(1).padStart(4, "0")}`;
}

function cacheBusted(url) { return `${url}${url.includes("?") ? "&" : "?"}v=${Date.now()}`; }

function currentId() { return state.project && state.project.id; }

function hasAudio() { return Boolean(state.project && state.project.song && state.project.song.path); }

function showTab(tab) {
  state.activeTab = tab;
  document.querySelectorAll(".studio-tab").forEach((button) => {
    const active = button.dataset.tab === tab;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
  });
  document.querySelectorAll("[data-panel]").forEach((panel) => {
    const isOutput = panel.dataset.panel === "export";
    const available = !isOutput || Boolean(state.info && state.info.last_output);
    panel.hidden = panel.dataset.panel !== tab || !available;
  });
}

function wireTabs() {
  document.querySelectorAll(".studio-tab").forEach((button) => {
    button.addEventListener("click", () => showTab(button.dataset.tab));
  });
  showTab(state.activeTab);
}

async function refreshProjects(selectId) {
  const projects = await api("/api/projects");
  const select = $("#projectSelect");
  select.innerHTML = "";
  for (const project of projects) {
    const option = document.createElement("option");
    option.value = project.id;
    option.textContent = project.name || project.id;
    select.append(option);
  }
  if (!projects.length) return null;
  const wanted = selectId || currentId() || projects[0].id;
  select.value = projects.some((project) => project.id === wanted) ? wanted : projects[0].id;
  await loadProject(select.value);
  return projects;
}

async function createProject(name) {
  const project = await api("/api/projects", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, title: name, artist: "" }),
  });
  await refreshProjects(project.id);
  setStatus($("#songStatus"), "New repair project ready. Add the song you want to fix.");
}

async function loadProject(id) {
  if (!id) return;
  stopPolling();
  state.project = await api(`/api/projects/${encodeURIComponent(id)}`);
  const song = state.project.song || {};
  $("#projectSelect").value = state.project.id;
  $("#songTitle").value = song.title || "";
  $("#songArtist").value = song.artist || "";
  $("#songFile").value = "";
  if (song.path) {
    audio.src = cacheBusted(`/api/projects/${state.project.id}/audio`);
    setStatus($("#songStatus"), `${song.filename || "Song"} is loaded.`);
  } else {
    audio.removeAttribute("src"); audio.load();
    setStatus($("#songStatus"), "Choose a song to begin.");
    $("#scrubber").max = 0; $("#duration").textContent = "--:--";
  }
  await refreshRepairInfo();
}

async function refreshRepairInfo() {
  if (!currentId()) return;
  state.info = await api(`/api/projects/${currentId()}/repair`);
  const separation = state.info.separation || { stems: [] };
  renderStems(separation.stems || []);
  const hasStems = separation.stems && separation.stems.length;
  $("#separateBtn").disabled = !hasAudio();
  $("#renderBtn").disabled = !hasStems;
  $("#repairStem").disabled = !hasStems;
  if (hasStems) {
    setStatus($("#renderStatus"), "Choose a matching earlier phrase, mark the gap, then make the repaired mix.");
  } else if (hasAudio()) {
    setStatus($("#renderStatus"), "Split the song first so there is a clean component to restore.");
  }
  const output = state.info.last_output;
  if (output) {
    const outputUrl = `/api/projects/${currentId()}/repair/output`;
    $("#repairedAudio").src = cacheBusted(outputUrl);
    $("#downloadMix").href = outputUrl;
    const render = state.info.last_render || {};
    const matching = render.time_stretched ? "The reference was time-matched to the missing passage and " : "The matching phrase was ";
    $("#renderSummary").textContent = `${matching}blended into the original full mix using the ${render.stem || "selected"} stem. Compare it here, then download the WAV when it feels right.`;
  }
  showTab(state.activeTab);
}

function renderStems(stems) {
  const grid = $("#stemGrid");
  grid.innerHTML = "";
  const select = $("#repairStem");
  const selected = select.value;
  select.innerHTML = "";
  if (!stems.length) {
    grid.innerHTML = '<p class="empty-stems">Your editable stems will appear here after separation.</p>';
    select.append(new Option("Split the song to choose a stem", ""));
    return;
  }
  for (const stem of stems) {
    const card = document.createElement("article");
    card.className = "stem-card";
    card.innerHTML = `<b>${stem.name}</b><small>${stem.detail}</small><a href="/api/projects/${encodeURIComponent(currentId())}/repair/stems/${encodeURIComponent(stem.id)}">Download WAV ↓</a>`;
    grid.append(card);
    select.append(new Option(stem.name, stem.id));
  }
  if ([...select.options].some((option) => option.value === selected)) select.value = selected;
  else if ([...select.options].some((option) => option.value === "drums")) select.value = "drums";
}

async function uploadSong(file) {
  if (!file) return;
  if (!currentId()) await createProject("Song repair");
  setStatus($("#songStatus"), `Loading ${file.name}…`, "working");
  const form = new FormData(); form.append("file", file);
  try {
    await api(`/api/projects/${currentId()}/song-upload`, { method: "POST", body: form });
    state.project = await api(`/api/projects/${currentId()}`);
    audio.src = cacheBusted(`/api/projects/${currentId()}/audio`);
    setStatus($("#songStatus"), `${file.name} is loaded. Split it when you are ready.`, "");
    await refreshProjects(currentId());
  } catch (error) { setStatus($("#songStatus"), error.message, "error"); }
}

async function saveSongDetails() {
  if (!currentId()) return;
  try {
    await api(`/api/projects/${currentId()}/meta`, {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: $("#songTitle").value.trim(), artist: $("#songArtist").value.trim() }),
    });
    state.project = await api(`/api/projects/${currentId()}`);
    setStatus($("#songStatus"), "Song details saved.");
  } catch (error) { setStatus($("#songStatus"), error.message, "error"); }
}

function startPolling(kind) {
  stopPolling();
  const statusElement = kind === "separation" ? $("#separationStatus") : $("#renderStatus");
  const tick = async () => {
    try {
      const job = await api(`/api/projects/${currentId()}/repair/status`);
      const statusKind = job.status === "error" ? "error" : job.status === "running" ? "working" : "";
      setStatus(statusElement, job.message || "Working…", statusKind);
      if (job.status === "done" || job.status === "error" || job.status === "stale") {
        stopPolling();
        if (job.status === "done") {
          await refreshRepairInfo();
          setStatus(statusElement, job.message || "Ready.");
        }
        $("#separateBtn").disabled = !hasAudio();
        return;
      }
    } catch (error) { setStatus(statusElement, error.message, "error"); stopPolling(); }
  };
  tick();
  state.poller = window.setInterval(tick, 1300);
}

function stopPolling() { if (state.poller) window.clearInterval(state.poller); state.poller = null; }

async function separate() {
  if (!hasAudio()) { setStatus($("#separationStatus"), "Load a song first.", "error"); return; }
  try {
    $("#separateBtn").disabled = true;
    await api(`/api/projects/${currentId()}/repair/separate`, { method: "POST" });
    startPolling("separation");
  } catch (error) { setStatus($("#separationStatus"), error.message, "error"); $("#separateBtn").disabled = false; }
}

function renderValues() {
  return {
    stem: $("#repairStem").value,
    source_start: Number($("#sourceStart").value), source_end: Number($("#sourceEnd").value),
    target_start: Number($("#targetStart").value), target_end: Number($("#targetEnd").value),
    fade_ms: Number($("#fadeMs").value), gain_db: Number($("#gainDb").value),
  };
}

async function renderRepair() {
  const body = renderValues();
  if (!body.stem || !Number.isFinite(body.source_start) || !Number.isFinite(body.source_end) || !Number.isFinite(body.target_start) || !Number.isFinite(body.target_end)) {
    setStatus($("#renderStatus"), "Enter all four time points in seconds.", "error"); return;
  }
  if (body.source_end <= body.source_start || body.target_end <= body.target_start) {
    setStatus($("#renderStatus"), "Each selection needs a start time before its end time.", "error"); return;
  }
  try {
    $("#renderBtn").disabled = true;
    await api(`/api/projects/${currentId()}/repair/render`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    startPolling("render");
  } catch (error) { setStatus($("#renderStatus"), error.message, "error"); $("#renderBtn").disabled = false; }
}

function setPoint(id) { $("#" + id).value = audio.currentTime.toFixed(2); }

function wireAudio() {
  audio.addEventListener("loadedmetadata", () => {
    $("#scrubber").max = audio.duration || 0;
    $("#duration").textContent = clock(audio.duration);
  });
  audio.addEventListener("timeupdate", () => {
    $("#scrubber").value = audio.currentTime;
    $("#playhead").textContent = clock(audio.currentTime);
  });
  $("#scrubber").addEventListener("input", (event) => {
    audio.currentTime = Number(event.target.value); $("#playhead").textContent = clock(audio.currentTime);
  });
}

function wireInterface() {
  $("#projectSelect").addEventListener("change", (event) => loadProject(event.target.value));
  $("#newProjectBtn").addEventListener("click", () => $("#newProjectDialog").showModal());
  $("#cancelProjectBtn").addEventListener("click", () => $("#newProjectDialog").close());
  $("#newProjectForm").addEventListener("submit", async (event) => {
    event.preventDefault(); const name = $("#newProjectName").value.trim(); if (!name) return;
    $("#newProjectDialog").close(); $("#newProjectName").value = ""; await createProject(name);
  });
  $("#songFile").addEventListener("change", (event) => uploadSong(event.target.files[0]));
  $("#saveSongBtn").addEventListener("click", saveSongDetails);
  $("#separateBtn").addEventListener("click", separate);
  $("#renderBtn").addEventListener("click", renderRepair);
  document.querySelectorAll(".set-time").forEach((button) => button.addEventListener("click", () => setPoint(button.dataset.target)));
  const zone = $("#dropZone");
  ["dragenter", "dragover"].forEach((name) => zone.addEventListener(name, (event) => { event.preventDefault(); zone.classList.add("dragging"); }));
  ["dragleave", "drop"].forEach((name) => zone.addEventListener(name, (event) => { event.preventDefault(); zone.classList.remove("dragging"); }));
  zone.addEventListener("drop", (event) => uploadSong(event.dataTransfer.files[0]));
}

async function boot() {
  wireAudio(); wireInterface(); wireTabs();
  if (previewMode) {
    $("#fileMode").hidden = false;
    setStatus($("#songStatus"), "Preview mode — start app/run.bat to upload and repair a song.");
    return;
  }
  try {
    const projects = await api("/api/projects");
    if (!projects.length) await createProject("Song repair");
    else await refreshProjects();
  } catch (error) { setStatus($("#songStatus"), `Could not load the repair workspace: ${error.message}`, "error"); }
}

boot();
