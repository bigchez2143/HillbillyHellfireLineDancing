/* Song card. A Spotify link opens or copies. Rehearsal uses a local file or the metronome. */
(function (root) {
  "use strict";
  const TYPES = new Set(["track", "album", "playlist", "episode", "artist", "show"]);
  const ID = /^[0-9A-Za-z]{22}$/;
  const SHORT = /^[0-9A-Za-z_-]{2,80}$/;
  const SECRET_QUERY = /^(api[_-]?key|access[_-]?token|refresh[_-]?token|token|secret|password|passwd|key|client[_-]?id|client[_-]?secret|code)$/i;
  const SHARE_HOSTS = new Set(["open.spotify.com", "www.open.spotify.com", "play.spotify.com", "www.play.spotify.com"]);
  const SHORT_HOSTS = new Set(["spotify.link", "www.spotify.link"]);
  const PASTE = "Paste a Spotify song, album, or playlist link.";
  const CONNECT = "Paste the share link from Spotify. This app does not connect to Spotify.";
  const KEY = "That link includes a key. Paste the normal share link.";
  const help = {
    intro: "Add an optional local audio file for the beat. A Spotify link is for sharing and opening the song.",
    card: "A Spotify link is for sharing and opening the song. A local audio file is optional and is what this app uses for BPM, rehearsal, and teaching. The link does not play with the dance.",
    link: "Song, album, and playlist links are for sharing and opening. They do not load into rehearsal, and this app does not sign in to Spotify.",
    local: "This file stays on this computer. BPM and rehearsal use it when you add one. It is separate from the Spotify link.",
    localEmpty: "No local file yet. Rehearsal uses the metronome until you add one.",
    practiceLocal: "Rehearsal plays your local audio file. The Spotify link is only for sharing and opening the song.",
    practiceMetronome: "Rehearsal uses the metronome. The Spotify link is only for sharing and opening the song."
  };

  function normalizeSpotifyUrl(value) {
    if (value == null) return "";
    if (typeof value !== "string") throw new Error(PASTE);
    const raw = value.trim();
    if (!raw) return "";
    if (raw.length > 2048 || /[\u0000-\u001f\u007f]/.test(raw)) throw new Error(PASTE);
    const uri = raw.match(/^spotify:([a-z]+):([0-9A-Za-z]{22})$/i);
    if (raw.toLowerCase().startsWith("spotify:")) {
      if (!uri || !TYPES.has(uri[1].toLowerCase())) throw new Error(PASTE);
      return `https://open.spotify.com/${uri[1].toLowerCase()}/${uri[2]}`;
    }
    let url;
    try { url = new URL(raw); } catch { throw new Error(PASTE); }
    if (url.protocol !== "https:" || url.username || url.password || (url.port && url.port !== "443")) throw new Error(PASTE);
    const host = url.hostname.toLowerCase();
    if (!SHARE_HOSTS.has(host) && !SHORT_HOSTS.has(host) && (host === "spotify.com" || host.endsWith(".spotify.com"))) throw new Error(CONNECT);
    for (const key of url.searchParams.keys()) {
      if (SECRET_QUERY.test(key)) throw new Error(KEY);
    }
    if (SHORT_HOSTS.has(host)) {
      const segment = url.pathname.replace(/^\/+|\/+$/g, "");
      if (segment.includes("/") || !SHORT.test(segment)) throw new Error(PASTE);
      return `https://spotify.link/${segment}`;
    }
    if (!SHARE_HOSTS.has(host)) throw new Error(PASTE);
    let segments = url.pathname.split("/").filter(Boolean);
    while (segments.length && (segments[0].toLowerCase() === "embed" || segments[0].toLowerCase().startsWith("intl-"))) segments.shift();
    if (segments.length !== 2 || !TYPES.has(segments[0].toLowerCase()) || !ID.test(segments[1])) throw new Error(PASTE);
    return `https://open.spotify.com/${segments[0].toLowerCase()}/${segments[1]}`;
  }

  function localMediaPath(song) {
    const path = song && typeof song.path === "string" ? song.path.trim().replace(/^"|"$/g, "") : "";
    if (!path) return "";
    const lowered = path.toLowerCase();
    if (lowered.startsWith("http://") || lowered.startsWith("https://") || lowered.startsWith("spotify:") || lowered.startsWith("file:")) return "";
    return path;
  }

  function rehearsalPlan(song, spotifyUrl) {
    let openUrl = "";
    try { openUrl = normalizeSpotifyUrl(spotifyUrl || ""); } catch { openUrl = ""; }
    const path = localMediaPath(song);
    if (path) return {kind: "local", path: path, openUrl: openUrl, playsSpotify: false, note: help.practiceLocal};
    return {kind: "metronome", path: "", openUrl: openUrl, playsSpotify: false, note: help.practiceMetronome};
  }

  function playbackUrl(projectId, song, spotifyUrl) {
    if (rehearsalPlan(song, spotifyUrl).kind !== "local") return "";
    if (typeof projectId !== "string" || !/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(projectId)) return "";
    return `/api/projects/${encodeURIComponent(projectId)}/audio`;
  }

  const api = {
    help: help,
    PASTE: PASTE,
    CONNECT: CONNECT,
    KEY: KEY,
    normalizeSpotifyUrl: normalizeSpotifyUrl,
    localMediaPath: localMediaPath,
    rehearsalPlan: rehearsalPlan,
    playbackUrl: playbackUrl
  };
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.LineDanceSongCard = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
