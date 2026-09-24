/* Basic community links. Names and websites only; nothing here is a sign-in or a key. */
(function (root) {
  "use strict";
  const MAX_LINKS = 40;
  const SECRET_QUERY = /^(api[_-]?key|access[_-]?token|refresh[_-]?token|token|secret|password|passwd|key|client[_-]?secret)$/i;

  function normalize(link) {
    const name = String(link && link.name || "").trim();
    const note = String(link && link.note || "").trim();
    const raw = String(link && link.url || "").trim();
    if (!name) throw new Error("Enter a name.");
    if (name.length > 80) throw new Error("The name is too long.");
    if (note.length > 160) throw new Error("The note is too long.");
    if (/[\u0000-\u001f\u007f]/.test(name + note + raw)) throw new Error("Use a normal name and website address.");
    let url;
    try { url = new URL(raw); } catch { throw new Error("Use a complete website address, starting with https://."); }
    if (url.protocol !== "https:" && url.protocol !== "http:") throw new Error("Use a complete website address, starting with https://.");
    if (url.username || url.password) throw new Error("That link includes a sign-in. Use the normal website address.");
    for (const key of url.searchParams.keys()) {
      if (SECRET_QUERY.test(key)) throw new Error("That link includes a key. Use the normal website address.");
    }
    const id = typeof link.id === "string" ? link.id : "";
    return {id: id, name: name, url: url.href, note: note};
  }

  function copyLink(link) {
    return {id: link.id, name: link.name, url: link.url, note: link.note || ""};
  }

  function create(request) {
    const shelf = {
      links: [],
      saved: false,
      warning: "",
      async load() {
        const data = await request("/api/settings/community");
        this.links = Array.isArray(data.links) ? data.links.map(copyLink) : [];
        this.saved = data.saved === true;
        this.warning = typeof data.warning === "string" ? data.warning : "";
        return this;
      },
      add(link) {
        const next = normalize(link);
        if (this.links.length >= MAX_LINKS) throw new Error("Remove a link before adding another.");
        if (this.links.some(function (item) { return item.url === next.url; })) throw new Error("That website is already in your list.");
        this.links = this.links.concat(next);
      },
      replace(id, link) {
        const next = normalize(Object.assign({}, link, {id: id}));
        if (!this.links.some(function (item) { return item.id === id; })) throw new Error("That link is no longer in the list.");
        if (this.links.some(function (item) { return item.id !== id && item.url === next.url; })) throw new Error("That website is already in your list.");
        this.links = this.links.map(function (item) { return item.id === id ? next : item; });
      },
      remove(id) {
        this.links = this.links.filter(function (item) { return item.id !== id; });
      },
      payload() {
        return {links: this.links.map(copyLink)};
      },
      async save() {
        const data = await request("/api/settings/community", {method: "PUT", body: this.payload()});
        this.links = data.links.map(copyLink);
        this.saved = true;
        this.warning = "";
        return this;
      },
      async reset() {
        const data = await request("/api/settings/community/reset", {method: "POST", body: {}});
        this.links = data.links.map(copyLink);
        this.saved = false;
        this.warning = "";
        return this;
      }
    };
    return shelf;
  }

  const api = {create: create, normalize: normalize, MAX_LINKS: MAX_LINKS};
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.LineDanceCommunity = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
