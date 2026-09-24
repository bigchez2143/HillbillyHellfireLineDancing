/* Advanced drawer. Personal keys go to the local server only, and only when saved. */
(function (root) {
  "use strict";
  const KINDS = ["dances", "songs", "choreographers"];
  const WARNINGS = [
    "Advanced is optional. Leave it empty. Writing a dance, practice, Publish, and the song card all work with no keys.",
    "A personal key stays on this Windows account. It is not shared, it is not included in a dance export, and Publish does not ask for it. Publish still only saves a step sheet and a portable draft, then opens a website.",
    "BootStepper search uses a personal key from your own BootStepper account. Search is read-only. This app does not upload dances and does not keep a copy of BootStepper’s catalog.",
    "Bring your own AI is the same Optional AI settings as before. You pay that provider. This project is not billed."
  ];
  const SPOTIFY_NOTE = "A Spotify client id is not enabled. Policy for that connection is not cleared, so this screen does not ask for one. The song card still uses a share link only.";
  const KEY_NOTE_SAVED = "A personal key is saved on this computer. Leave the box blank to keep it.";
  const KEY_NOTE_EMPTY = "No BootStepper key is saved. The rest of the app works without one.";

  function keyPayload(apiKey) {
    const key = String(apiKey || "").trim();
    if (/[\u0000-\u001f\u007f]/.test(key) || /\s/.test(key)) throw new Error("Enter a personal key without spaces or line breaks.");
    if (key && (key.length < 8 || key.length > 512 || key.includes("://"))) {
      throw new Error("Paste the personal key itself, not a web address.");
    }
    return {api_key: key};
  }

  function searchPayload(kind, query) {
    const name = String(query || "").trim();
    if (!KINDS.includes(kind)) throw new Error("Choose dances, songs, or choreographers.");
    if (!name || name.length > 80 || /[\u0000-\u001f\u007f]/.test(name)) throw new Error("Enter a name to search for, up to 80 characters.");
    return {kind: kind, query: name};
  }

  function keyNote(status) {
    return status && status.bootstepper && status.bootstepper.api_key_configured ? KEY_NOTE_SAVED : KEY_NOTE_EMPTY;
  }

  function safeUrl(kind, value) {
    const prefix = "https://bootstepper.com/" + kind + "/";
    if (typeof value !== "string" || !value.startsWith(prefix)) return "";
    const id = value.slice(prefix.length);
    return /^[A-Za-z0-9]{6,64}$/.test(id) ? value : "";
  }

  function textList(value) {
    if (!Array.isArray(value)) return [];
    return value.filter(function (item) { return typeof item === "string" && item; }).slice(0, 8);
  }

  function presentItem(kind, item) {
    if (!item || typeof item !== "object") return null;
    if (kind === "dances") {
      const row = {
        title: String(item.title || ""),
        difficulty: String(item.difficulty || ""),
        counts: Number.isInteger(item.counts) ? item.counts : null,
        walls: Number.isInteger(item.walls) ? item.walls : null,
        choreographers: textList(item.choreographers),
        songs: textList(item.songs),
        url: safeUrl("dances", item.url)
      };
      return row.title ? row : null;
    }
    if (kind === "songs") {
      const row = {
        title: String(item.title || ""),
        artist: String(item.artist || ""),
        dance_count: Number.isInteger(item.dance_count) ? item.dance_count : null,
        url: safeUrl("songs", item.url)
      };
      return row.title ? row : null;
    }
    const row = {
      name: String(item.name || ""),
      country: String(item.country || ""),
      dance_count: Number.isInteger(item.dance_count) ? item.dance_count : null,
      url: safeUrl("choreographers", item.url)
    };
    return row.name ? row : null;
  }

  function presentResults(data) {
    const kind = data && KINDS.includes(data.kind) ? data.kind : "";
    const items = [];
    for (const item of (data && data.items) || []) {
      const row = presentItem(kind, item);
      if (row) items.push(row);
    }
    return {
      kind: kind,
      attribution: typeof data.attribution === "string" ? data.attribution : "",
      source: data && data.source === "https://bootstepper.com/" ? data.source : "https://bootstepper.com/",
      items: items
    };
  }

  function create(request) {
    const drawer = {
      status: null,
      results: null,
      message: "",
      async load() {
        this.status = await request("/api/settings/advanced");
        return this;
      },
      async saveKey(apiKey) {
        const body = keyPayload(apiKey);
        this.status = Object.assign({}, this.status, {bootstepper: await request("/api/settings/advanced/bootstepper", {method: "PUT", body: body})});
        this.message = body.api_key ? "Personal key saved on this computer. BootStepper was not contacted." : "Saved key kept. BootStepper was not contacted.";
        return this;
      },
      async forgetKey() {
        this.status = Object.assign({}, this.status, {bootstepper: await request("/api/settings/advanced/bootstepper/key", {method: "DELETE"})});
        this.results = null;
        this.message = "Saved BootStepper key forgotten on this computer.";
        return this;
      },
      async search(kind, query) {
        const body = searchPayload(kind, query);
        const data = await request("/api/settings/advanced/bootstepper/search", {method: "POST", body: body});
        this.results = presentResults(data);
        this.message = this.results.items.length ? "Search finished. Results stay on this screen." : "BootStepper returned no matches for that name.";
        return this;
      }
    };
    return drawer;
  }

  function mount(doc, request) {
    if (!doc || typeof request !== "function" || !doc.getElementById("advancedDrawer")) return null;
    const byId = function (id) { return doc.getElementById(id); };
    const drawer = create(request);
    const warnings = byId("advancedWarnings");
    if (warnings && !warnings.childElementCount) {
      for (const text of WARNINGS) {
        const paragraph = doc.createElement("p");
        paragraph.textContent = text;
        warnings.appendChild(paragraph);
      }
    }
    if (byId("spotifyLaterNote") && !byId("spotifyLaterNote").textContent) byId("spotifyLaterNote").textContent = SPOTIFY_NOTE;

    function setBusy(busy) {
      for (const id of ["bootstepperSave", "bootstepperForget", "bootstepperSearch"]) {
        if (byId(id)) byId(id).disabled = busy;
      }
    }
    function showStatus() {
      if (byId("bootstepperKeyNote")) byId("bootstepperKeyNote").textContent = keyNote(drawer.status);
      if (byId("bootstepperStatus")) byId("bootstepperStatus").textContent = drawer.message;
      const host = byId("bootstepperResults");
      if (!host) return;
      host.replaceChildren();
      const results = drawer.results;
      if (!results) return;
      if (results.attribution) {
        const note = doc.createElement("p");
        note.textContent = results.attribution;
        host.appendChild(note);
      }
      for (const item of results.items) {
        const article = doc.createElement("article");
        const title = doc.createElement("strong");
        title.textContent = item.title || item.name || "";
        article.appendChild(title);
        const detail = doc.createElement("p");
        const bits = [];
        if (item.difficulty) bits.push(item.difficulty);
        if (item.artist) bits.push(item.artist);
        if (item.country) bits.push(item.country);
        if (item.counts) bits.push(item.counts + " counts");
        if (item.walls) bits.push(item.walls + " walls");
        if (item.dance_count != null) bits.push(item.dance_count + " dances");
        if (item.choreographers && item.choreographers.length) bits.push(item.choreographers.join(", "));
        if (item.songs && item.songs.length) bits.push(item.songs.join("; "));
        detail.textContent = bits.join(" · ");
        article.appendChild(detail);
        if (item.url) {
          const link = doc.createElement("a");
          link.href = item.url;
          link.target = "_blank";
          link.rel = "noopener noreferrer";
          link.textContent = "Open on BootStepper";
          article.appendChild(link);
        }
        host.appendChild(article);
      }
    }
    async function refresh() {
      setBusy(true);
      try { await drawer.load(); drawer.message = keyNote(drawer.status); }
      catch (error) { drawer.message = error.message; }
      setBusy(false);
      showStatus();
    }
    const keyForm = byId("bootstepperKeyForm");
    if (keyForm) keyForm.addEventListener("submit", async function (event) {
      event.preventDefault();
      setBusy(true);
      try {
        await drawer.saveKey(byId("bootstepperKey").value);
        byId("bootstepperKey").value = "";
      } catch (error) { drawer.message = error.message; }
      setBusy(false);
      showStatus();
    });
    if (byId("bootstepperForget")) byId("bootstepperForget").addEventListener("click", async function () {
      setBusy(true);
      try { await drawer.forgetKey(); byId("bootstepperKey").value = ""; }
      catch (error) { drawer.message = error.message; }
      setBusy(false);
      showStatus();
    });
    const searchForm = byId("bootstepperSearchForm");
    if (searchForm) searchForm.addEventListener("submit", async function (event) {
      event.preventDefault();
      setBusy(true);
      try { await drawer.search(byId("bootstepperKind").value, byId("bootstepperQuery").value); }
      catch (error) { drawer.results = null; drawer.message = error.message; }
      setBusy(false);
      showStatus();
    });
    refresh();
    return drawer;
  }

  const api = {
    KINDS: KINDS,
    WARNINGS: WARNINGS,
    SPOTIFY_NOTE: SPOTIFY_NOTE,
    keyPayload: keyPayload,
    searchPayload: searchPayload,
    keyNote: keyNote,
    presentResults: presentResults,
    create: create,
    mount: mount
  };
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.LineDanceAdvanced = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
