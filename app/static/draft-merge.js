/* Pure three-way merge. Ordered arrays are indivisible editing decisions. */
(function (root) {
  "use strict";
  const absent = Symbol("absent");
  const object = value => value !== null && typeof value === "object" && !Array.isArray(value);
  const copy = value => value === absent ? absent : structuredClone(value);
  function equal(left, right) {
    if (left === right) return true;
    if (left === absent || right === absent) return false;
    if (Array.isArray(left) || Array.isArray(right)) return Array.isArray(left) && Array.isArray(right) && left.length === right.length && left.every((item, index) => equal(item, right[index]));
    if (!object(left) || !object(right)) return false;
    const keys = Object.keys(left);
    return keys.length === Object.keys(right).length && keys.every(key => Object.prototype.hasOwnProperty.call(right, key) && equal(left[key], right[key]));
  }
  function merge(base, local, remote) {
    const conflicts = [];
    function visit(before, mine, theirs, path) {
      if (equal(mine, before)) return copy(theirs);
      if (equal(theirs, before) || equal(mine, theirs)) return copy(mine);
      if ((before === absent || object(before)) && object(mine) && object(theirs)) {
        if(before === absent)before = {};
        const value = {};
        for (const key of new Set([...Object.keys(before), ...Object.keys(mine), ...Object.keys(theirs)])) {
          const get = source => Object.prototype.hasOwnProperty.call(source, key) ? source[key] : absent;
          const child = visit(get(before), get(mine), get(theirs), path + "/" + key.replace(/~/g, "~0").replace(/\//g, "~1"));
          if (child !== absent) Object.defineProperty(value, key, {value: child, enumerable: true, configurable: true, writable: true});
        }
        return value;
      }
      conflicts.push(path || "/");
      return copy(theirs);
    }
    return {value: visit(base, local, remote, ""), conflicts};
  }
  const api = Object.freeze({merge, equal});
  root.LineDanceMerge = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
