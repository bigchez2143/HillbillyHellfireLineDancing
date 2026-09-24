/* Publish picker. The pack is already on this computer; these actions only open a site or copy the folder path. */
(function (root) {
  "use strict";

  function textOf(view) {
    return [view.note, view.copyLabel].concat(view.files.map(function (file) {
      return file.label + " " + file.name;
    }), view.destinations.map(function (item) {
      return item.name + " " + item.detail;
    })).join(" ");
  }

  function publishView(pack) {
    if (!pack || typeof pack.folder !== "string" || !pack.folder.trim() || !Array.isArray(pack.files) || !Array.isArray(pack.destinations)) {
      throw new Error("The publish pack was incomplete. Try Publish again.");
    }
    const files = pack.files.map(function (file) {
      if (!file || typeof file.label !== "string" || typeof file.name !== "string" || !file.name.trim()) {
        throw new Error("The publish pack was incomplete. Try Publish again.");
      }
      return {role: file.role, label: file.label, name: file.name};
    });
    if (!files.some(function (file) { return file.role === "pdf"; }) || !files.some(function (file) { return file.role === "portable"; })) {
      throw new Error("Publish needs both the step sheet and the portable draft. Try again.");
    }
    const destinations = pack.destinations.map(function (item) {
      let url;
      try { url = new URL(item.url); } catch { url = null; }
      if (!item || !url || url.protocol !== "https:" || url.username || url.password) {
        throw new Error("A website link was not ready. Try Publish again.");
      }
      return {id: item.id, name: item.name, detail: item.detail, url: url.href};
    });
    const view = {
      folder: pack.folder,
      note: typeof pack.note === "string" ? pack.note : "",
      files: files,
      destinations: destinations,
      copyLabel: "Copy folder"
    };
    return view;
  }

  function plainLanguage(view) {
    return textOf(view);
  }

  const api = {publishView: publishView, plainLanguage: plainLanguage};
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.LineDancePublish = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
