/* Count-by-count personal move editing. Pure model also runs under Node. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.LineDanceMoveForm = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const copy = value => JSON.parse(JSON.stringify(value));
  const own = (obj, key) => Object.prototype.hasOwnProperty.call(obj, key);
  const gcd = (a, b) => { a = a < 0n ? -a : a; while (b) [a, b] = [b, a % b]; return a; };
  function fraction(n, d = 1n) {
    if (!d) throw new Error('A fraction cannot have a zero denominator.');
    if (d < 0n) { n = -n; d = -d; }
    const g = gcd(n, d); return {n: n / g, d: d / g};
  }
  function parse(value) {
    const s = String(value ?? '').trim();
    if (s.length > 80) throw new Error('Use a shorter number or exact fraction.');
    let m = s.match(/^([+-]?\d+)\s*\/\s*(\d+)$/);
    if (m) return fraction(BigInt(m[1]), BigInt(m[2]));
    m = s.match(/^([+-]?)(\d*)(?:\.(\d+))?$/);
    if (!m || (!m[2] && !m[3])) throw new Error('Use a number or exact fraction, such as 1/2.');
    const d = 10n ** BigInt((m[3] || '').length);
    return fraction((m[1] === '-' ? -1n : 1n) * BigInt((m[2] || '0') + (m[3] || '')), d);
  }
  const add = (a, b) => fraction(a.n * b.d + b.n * a.d, a.d * b.d);
  const sub = (a, b) => fraction(a.n * b.d - b.n * a.d, a.d * b.d);
  const compare = (a, b) => a.n * b.d < b.n * a.d ? -1 : a.n * b.d > b.n * a.d ? 1 : 0;
  const exact = f => f.d === 1n ? String(f.n) : `${f.n}/${f.d}`;
  const zero = () => fraction(0n);
  function bounded(value, {positive = false, signed = false} = {}) {
    const f = parse(value);
    if ((!signed && f.n < 0n) || (positive && f.n <= 0n) || compare(f, fraction(100000n)) > 0 || compare(f, fraction(-100000n)) < 0) {
      throw new Error(positive ? 'Enter a positive duration, up to 100000 counts.' : 'This value is outside the supported range.');
    }
    return f;
  }
  function onsetToOffset(value) {
    const s = String(value).trim();
    const m = s.match(/^(\d+)\s*&$/);
    const onset = m ? add(parse(m[1]), fraction(1n, 2n)) : parse(s);
    const offset = sub(onset, fraction(1n));
    return exact(bounded(exact(offset)));
  }
  function offsetToOnset(value) {
    const onset = add(parse(value), fraction(1n));
    if (onset.d === 2n && onset.n > 0n) return `${onset.n / 2n}&`;
    return exact(onset);
  }
  function checkEvents(events) {
    if (!Array.isArray(events) || events.length > 512 || events.some(e => !e || typeof e !== 'object' || Array.isArray(e))) {
      throw new Error('Use a JSON array with at most 512 count-row objects.');
    }
    return copy(events);
  }
  const supports = {
    support_before: [['unknown', 'Not sure yet'], ['L', 'Weight on left'], ['R', 'Weight on right'], ['both', 'Weight on both'], ['neither', 'Neither foot (in the air)'], ['any', 'Any starting weight']],
    support_after: [['unknown', 'Not sure yet'], ['L', 'Weight on left'], ['R', 'Weight on right'], ['both', 'Weight on both'], ['neither', 'Neither foot (in the air)'], ['same', 'Keep the same weight']]
  };
  const turns = [['', 'Not sure yet'], ['0', 'No turn'], ['90', 'Quarter turn right'], ['-90', 'Quarter turn left'], ['180', 'Half turn right'], ['-180', 'Half turn left'], ['270', 'Three-quarter turn right'], ['-270', 'Three-quarter turn left'], ['360', 'Full turn right'], ['-360', 'Full turn left'], ['custom', 'Other turn (degrees)']];
  let nextId = 0;
  function eventId() { return 'event-' + (typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : `${Date.now().toString(36)}-${++nextId}`); }
  class Model {
    constructor({events = [], duration = null} = {}) { this.reset({events, duration}); }
    reset({events = [], duration = null}) {
      this.events = checkEvents(events); this.duration = duration; this.enabled = events.length > 0;
      this.jsonDraft = null; this.baseline = JSON.stringify({events: this.events, duration, enabled: this.enabled});
    }
    isDirty() { return this.jsonDraft !== null || this.baseline !== JSON.stringify({events: this.events, duration: this.duration, enabled: this.enabled}); }
    setJson(text) { this.jsonDraft = text; }
    applyJson() {
      if (this.jsonDraft === null) return;
      let parsed;
      try { parsed = JSON.parse(this.jsonDraft); } catch { throw new Error('JSON changes are not valid yet. Fix them or choose Keep count rows.'); }
      this.events = checkEvents(parsed); this.enabled = parsed.length > 0; this.jsonDraft = null;
    }
    discardJson() { this.jsonDraft = null; }
    setEnabled(enabled) {
      if (this.jsonDraft !== null) throw new Error('Apply your JSON changes or keep the count rows before changing timing mode.');
      if (!enabled && this.events.length) throw new Error('Remove the count rows explicitly before using description only.');
      this.enabled = enabled;
    }
    clear() { this.events = []; this.jsonDraft = null; this.enabled = false; }
    views() {
      let cursor = zero();
      return this.events.map(event => {
        let offset = null, span = null;
        try { offset = own(event, 'offset_counts') && event.offset_counts != null ? bounded(event.offset_counts) : cursor; } catch { /* Keep the authored value visible. */ }
        try { if (event.duration_counts != null) span = bounded(event.duration_counts); } catch { /* Inspected below. */ }
        cursor = offset && span ? add(offset, span) : null;
        let turn = '';
        if (event.rotation_deg != null) {
          try { const numeric = exact(parse(event.rotation_deg)); turn = turns.some(([v]) => v === numeric) ? numeric : 'custom'; } catch { turn = 'custom'; }
        }
        return {
          onset: offset ? offsetToOnset(exact(offset)) : (event.offset_counts == null ? '' : String(event.offset_counts)),
          duration_counts: event.duration_counts == null ? '' : String(event.duration_counts),
          text: event.text == null ? '' : String(event.text),
          support_before: event.support_before ?? 'unknown', support_after: event.support_after ?? 'unknown',
          turn, rotation_deg: event.rotation_deg == null ? '' : String(event.rotation_deg),
          facing_before_deg: event.facing_before_deg == null ? '' : String(event.facing_before_deg),
          facing_after_deg: event.facing_after_deg == null ? '' : String(event.facing_after_deg)
        };
      });
    }
    patch(index, field, value) {
      if (this.jsonDraft !== null) throw new Error('Apply JSON changes before editing the rows.');
      const event = this.events[index];
      if (!event) throw new Error('This count row is no longer available.');
      if (field === 'onset') event.offset_counts = onsetToOffset(value);
      else if (field === 'duration_counts') {
        if (String(value).trim() === '') delete event.duration_counts;
        else event.duration_counts = exact(bounded(value));
      } else if (field === 'text') event.text = value;
      else if (supports[field]) {
        if (!supports[field].some(([v]) => v === value)) throw new Error('Choose a supported weight description.');
        event[field] = value;
      } else if (['rotation_deg', 'facing_before_deg', 'facing_after_deg'].includes(field)) {
        if (String(value).trim() === '') delete event[field];
        else event[field] = exact(bounded(value, {signed: true}));
      } else throw new Error('This field is not editable in the count form.');
    }
    inspect(duration = this.duration) {
      const errors = [], warnings = []; let cursor = zero(), maximum = zero(), known = true;
      this.events.forEach((event, i) => {
        let offset = cursor, span = null;
        try { if (event.offset_counts != null) offset = bounded(event.offset_counts); } catch (e) { errors.push(`Row ${i + 1} start: ${e.message}`); offset = null; }
        try { if (event.duration_counts != null) span = bounded(event.duration_counts); } catch (e) { errors.push(`Row ${i + 1} duration: ${e.message}`); }
        if (offset && cursor && compare(offset, cursor)) errors.push(`Row ${i + 1} starts at ${offsetToOnset(exact(offset))}; expected ${offsetToOnset(exact(cursor))}. Adjust the start or add an explicit hold.`);
        if (!offset || !span) { known = false; warnings.push(`Row ${i + 1} has unspecified timing.`); }
        cursor = offset && span ? add(offset, span) : null;
        if (cursor && compare(cursor, maximum) > 0) maximum = cursor;
        if (!event.support_before || event.support_before === 'unknown' || !event.support_after || event.support_after === 'unknown' || event.rotation_deg == null) warnings.push(`Row ${i + 1} has unverified weight or turn information.`);
        for (const field of ['rotation_deg', 'facing_before_deg', 'facing_after_deg']) {
          if (event[field] != null) try { bounded(event[field], {signed: true}); } catch (e) { errors.push(`Row ${i + 1} ${field.replaceAll('_', ' ')}: ${e.message}`); }
        }
      });
      let declared = null;
      try { if (duration != null && String(duration).trim() !== '') declared = bounded(duration); } catch (e) { errors.push(`Move counts: ${e.message}`); }
      if (declared && this.events.length && (known ? compare(maximum, declared) !== 0 : compare(maximum, declared) > 0)) errors.push(`Count rows cover ${known ? '' : 'at least '}${exact(maximum)} counts, but the move declares ${exact(declared)}. Update Counts or the rows; neither is changed automatically.`);
      return {errors, warnings, span: known && this.events.length ? exact(maximum) : null, declared: declared ? exact(declared) : null};
    }
    reflow() {
      if (this.jsonDraft !== null) throw new Error('Apply JSON changes before changing row timing.');
      const spans = this.events.map(e => {
        if (e.duration_counts == null) throw new Error('Give every row a duration before placing the rows back to back.');
        return bounded(e.duration_counts);
      });
      let cursor = zero();
      this.events.forEach((event, i) => { event.offset_counts = exact(cursor); cursor = add(cursor, spans[i]); });
    }
    add() {
      if (this.jsonDraft !== null) throw new Error('Apply your JSON changes before adding a row.');
      if (this.events.length >= 512) throw new Error('A move can contain at most 512 count rows.');
      const state = this.inspect(null);
      if (this.events.length && (state.span === null || state.errors.length)) throw new Error('Resolve the existing row timing before adding the next count.');
      this.enabled = true;
      this.events.push({id: eventId(), offset_counts: state.span || '0', duration_counts: '1', text: '', support_before: 'unknown', support_after: 'unknown'});
    }
    remove(index) {
      if (this.jsonDraft !== null) throw new Error('Apply JSON changes before removing a row.');
      if (!this.events[index]) throw new Error('This count row is no longer available.');
      const state = this.inspect(null); this.events.splice(index, 1);
      if (state.span !== null && !state.errors.length) this.reflow();
    }
    move(index, delta) {
      if (this.jsonDraft !== null) throw new Error('Apply JSON changes before reordering rows.');
      const target = index + delta;
      if (!this.events[index] || !this.events[target]) return;
      // Validate before mutation so an unknown duration cannot cause a partial reorder.
      this.events.forEach(e => { if (e.duration_counts == null) throw new Error('Give every row a duration before reordering.'); bounded(e.duration_counts); });
      const event = this.events.splice(index, 1)[0]; this.events.splice(target, 0, event); this.reflow();
    }
    read(duration = this.duration) {
      this.applyJson(); this.duration = duration;
      const result = this.inspect(duration);
      if (this.enabled && !this.events.length) throw new Error('Add a count row, or choose Description only.');
      if (!this.enabled && this.events.length) throw new Error('Remove the count rows explicitly before using description only.');
      if (result.errors.length) throw new Error(result.errors.join(' '));
      return {events: copy(this.events), duration_counts: duration == null || String(duration).trim() === '' ? null : duration};
    }
  }

  function mount(container, options = {}) {
    if (!container || !container.ownerDocument) throw new Error('Provide a move-editor container.');
    const doc = container.ownerDocument, model = new Model(options), invalid = new Map();
    let destroyed = false;
    function el(tag, text, attrs = {}) {
      const node = doc.createElement(tag); if (text != null) node.textContent = text;
      for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
      return node;
    }
    function button(text, handler, attrs = {}) { const node = el('button', text, {type: 'button', ...attrs}); node.addEventListener('click', handler); return node; }
    function notify() { if (typeof options.onChange === 'function') options.onChange(); }
    container.classList.add('move-form');
    const label = el('label', 'How would you like to describe the timing?');
    const mode = el('select', null, {'aria-label': 'Move timing mode'});
    for (const [value, text] of [['description', 'Description only'], ['timed', 'Count by count']]) mode.append(el('option', text, {value}));
    label.append(mode); container.append(label);
    const intro = el('p', 'Leave anything you do not know unspecified. Weight means the foot carrying your weight, not the foot that moves.');
    container.append(intro);
    const confirmation = el('div', null, {class: 'move-form-confirm', hidden: ''});
    confirmation.append(el('p', 'Description only removes all timed rows when you save. Your written explanation and teaching media stay in place.'));
    confirmation.append(button('Remove all count rows', () => { model.clear(); invalid.clear(); confirmation.hidden = true; render(); notify(); mode.focus(); }));
    confirmation.append(button('Keep count rows', () => { confirmation.hidden = true; mode.value = 'timed'; mode.focus(); }));
    container.append(confirmation);
    const summary = el('p', null, {class: 'move-form-summary', role: 'status', 'aria-live': 'polite'}); container.append(summary);
    const timed = el('div'); container.append(timed);
    const help = el('p', 'Start counts at 1. Use 2& for the half beat after 2, or an exact fraction such as 7/4. Duration is time held: 1, 1/2 or 1/4 count.'); timed.append(help);
    const fieldset = el('fieldset', null, {class: 'move-form-rows'}); fieldset.append(el('legend', 'Count rows')); timed.append(fieldset);
    const rowList = el('div'); fieldset.append(rowList);
    const rowActions = el('div', null, {class: 'actions'}); timed.append(rowActions);
    function action(operation, focusIndex) {
      if (invalid.size) { summary.textContent = 'Fix the highlighted field before changing the row order.'; return; }
      try { operation(); render(); notify(); if (focusIndex != null) rowList.querySelector(`[data-row="${focusIndex}"] input`)?.focus(); }
      catch (error) { summary.textContent = error.message; }
    }
    const addButton = button('Add count row', () => action(() => model.add(), model.events.length));
    const reflowButton = button('Place rows back to back', () => action(() => model.reflow(), 0));
    rowActions.append(addButton, reflowButton);
    timed.append(el('p', 'Moving or removing a row closes its gap when timing is known. Reordering keeps each action’s duration. Review the Counts total above after these changes.'));
    const jsonDetails = el('details', null, {class: 'advanced move-form-json'}); jsonDetails.append(el('summary', 'Advanced: exact event JSON'));
    jsonDetails.append(el('p', 'Count starts in JSON are zero-based offset_counts. Extra event fields are kept. Apply JSON changes before continuing with the rows.'));
    const jsonLabel = el('label', 'Event JSON');
    const json = el('textarea', null, {rows: '8', spellcheck: 'false', 'aria-label': 'Exact event JSON'}); jsonLabel.append(json); jsonDetails.append(jsonLabel); container.append(jsonDetails);
    const pending = el('div', null, {class: 'move-form-pending', hidden: ''});
    pending.append(el('p', 'JSON changes are waiting. Count-row editing is paused so neither version is lost.'));
    pending.append(button('Apply JSON changes', () => { try { model.applyJson(); invalid.clear(); render(); notify(); } catch (e) { summary.textContent = e.message; } }));
    pending.append(button('Keep count rows instead', () => { model.discardJson(); render(); notify(); })); container.append(pending);
    function refresh() {
      const state = model.inspect();
      const details = [...invalid.values(), ...state.errors];
      const timing = model.enabled ? (state.span === null ? 'Some row timing is unspecified.' : `Rows cover ${state.span} counts.${state.declared === null ? ' No total is entered in Counts.' : ` Move total: ${state.declared}.`}`) : 'Description only: weight and turn checks remain unverified.';
      summary.textContent = details.length ? details.join(' ') : timing + (state.warnings.length && model.enabled ? ' Some weight, turn or timing information remains unverified.' : '');
      summary.classList.toggle('has-error', details.length > 0);
      pending.hidden = model.jsonDraft === null; fieldset.disabled = model.jsonDraft !== null;
      addButton.disabled = reflowButton.disabled = model.jsonDraft !== null;
      json.disabled = invalid.size > 0;
      if (model.jsonDraft === null) json.value = JSON.stringify(model.events, null, 2);
    }
    function render() {
      if (destroyed) return;
      mode.value = model.enabled ? 'timed' : 'description'; timed.hidden = !model.enabled; rowList.replaceChildren();
      model.views().forEach((view, index) => {
        const row = el('fieldset', null, {class: 'move-form-row', 'data-row': String(index)}); row.append(el('legend', `Action ${index + 1}`));
        const fields = el('div', null, {class: 'move-form-grid'}); row.append(fields);
        const control = (parent, title, field, choices = null, attrs = {}) => {
          const wrapper = el('label', title), node = el(choices ? 'select' : field === 'text' ? 'textarea' : 'input', null, {'data-field': field, ...attrs});
          if (choices) {
            for (const [value, text] of choices) node.append(el('option', text, {value}));
            if (!choices.some(([value]) => value === String(view[field]))) node.append(el('option', `Unrecognized value: ${String(view[field])}`, {value: String(view[field])}));
          }
          node.value = view[field]; wrapper.append(node); parent.append(wrapper);
          node.addEventListener(choices ? 'change' : 'input', () => {
            const key = `${index}:${field}`;
            try { model.patch(index, field, node.value); invalid.delete(key); node.removeAttribute('aria-invalid'); }
            catch (error) { invalid.set(key, `Row ${index + 1}, ${title}: ${error.message}`); node.setAttribute('aria-invalid', 'true'); }
            refresh(); notify();
          });
          return node;
        };
        control(fields, 'Starts on count', 'onset', null, {placeholder: '1 or 2&'});
        control(fields, 'Lasts (counts)', 'duration_counts', null, {placeholder: '1 or 1/2'});
        control(row, 'What happens?', 'text', null, {rows: '2', placeholder: 'Step right to the side'});
        const weights = el('div', null, {class: 'move-form-grid'}); row.append(weights);
        control(weights, 'Weight before', 'support_before', supports.support_before);
        control(weights, 'Weight after', 'support_after', supports.support_after);
        const turnLabel = el('label', 'Turn during this action'), turn = el('select', null, {'aria-label': `Turn during action ${index + 1}`});
        for (const [value, text] of turns) turn.append(el('option', text, {value}));
        turn.value = view.turn; turnLabel.append(turn); row.append(turnLabel);
        const custom = el('div'); const degrees = control(custom, 'Other turn in degrees (positive right, negative left)', 'rotation_deg', null, {placeholder: '45 or -45'}); custom.hidden = view.turn !== 'custom'; row.append(custom);
        turn.addEventListener('change', () => {
          custom.hidden = turn.value !== 'custom';
          if (turn.value === 'custom') { degrees.focus(); return; }
          model.patch(index, 'rotation_deg', turn.value); degrees.value = turn.value;
          invalid.delete(`${index}:rotation_deg`); degrees.removeAttribute('aria-invalid'); refresh(); notify();
        });
        const advanced = el('details', null, {class: 'advanced move-form-facing'}); advanced.append(el('summary', 'Advanced: absolute facing'));
        advanced.append(el('p', 'Optional degrees relative to the room: front 0, right 90, back 180, left 270. Leave blank if not fixed.'));
        control(advanced, 'Facing before (degrees)', 'facing_before_deg'); control(advanced, 'Facing after (degrees)', 'facing_after_deg'); row.append(advanced);
        const actions = el('div', null, {class: 'actions'});
        const up = button('Move up', () => action(() => model.move(index, -1), index - 1), {'aria-label': `Move action ${index + 1} earlier`}); up.disabled = index === 0;
        const down = button('Move down', () => action(() => model.move(index, 1), index + 1), {'aria-label': `Move action ${index + 1} later`}); down.disabled = index === model.events.length - 1;
        actions.append(up, down, button('Remove row', () => action(() => model.remove(index), Math.max(0, index - 1)), {'aria-label': `Remove action ${index + 1}`})); row.append(actions); rowList.append(row);
      });
      refresh();
    }
    mode.addEventListener('change', () => {
      if (invalid.size) { mode.value = model.enabled ? 'timed' : 'description'; summary.textContent = 'Fix the highlighted field before changing timing mode.'; return; }
      try { model.setEnabled(mode.value === 'timed'); confirmation.hidden = true; render(); notify(); }
      catch (e) { if (mode.value === 'description' && model.events.length && model.jsonDraft === null) { confirmation.hidden = false; mode.value = 'timed'; } else { mode.value = model.enabled ? 'timed' : 'description'; summary.textContent = e.message; } }
    });
    json.addEventListener('input', () => { model.setJson(json.value); refresh(); notify(); });
    render();
    return {
      setValue(value) { model.reset(value); invalid.clear(); confirmation.hidden = true; render(); },
      setDuration(value) { model.duration = value; refresh(); },
      read(duration = model.duration) {
        if (invalid.size) throw new Error([...invalid.values()].join(' '));
        if (!confirmation.hidden) throw new Error('Choose whether to remove or keep the count rows first.');
        // Valid JSON can still have a count mismatch. Show those newly applied
        // rows even when Save is blocked, keeping the form and model identical.
        try { return model.read(duration); } finally { render(); }
      },
      isDirty() { return invalid.size > 0 || !confirmation.hidden || model.isDirty(); },
      destroy() { destroyed = true; container.replaceChildren(); container.classList.remove('move-form'); }
    };
  }
  return {Model, mount, onsetToOffset, offsetToOnset, exactCount: value => exact(parse(value))};
});
