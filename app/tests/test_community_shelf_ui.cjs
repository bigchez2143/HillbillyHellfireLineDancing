'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const {create, normalize} = require('../static/community-shelf.js');

test('a new link is a name and website, and a key in the address is refused', () => {
  assert.equal(normalize({name: ' Thursday class ', url: 'https://example.com/class', note: ' Studio '}).name, 'Thursday class');
  assert.throws(() => normalize({name: 'Class', url: 'https://example.com/?api_key=SECRET'}), /key/);
  assert.throws(() => normalize({name: 'Class', url: 'javascript:alert(1)'}), /https/);
});

test('add, edit, and remove round-trip through local settings without extra fields', async () => {
  const calls = [];
  let stored = {saved: false, links: [{id: 'bootstepper', name: 'BootStepper', url: 'https://bootstepper.com/', note: 'Dances'}]};
  const shelf = create(async (path, options) => {
    calls.push([path, options && options.method, options && options.body]);
    if (options && options.method === 'PUT') {
      stored = {saved: true, links: options.body.links.map((link, index) => ({...link, id: link.id || 'link-' + (index + 1)}))};
      return stored;
    }
    if (options && options.method === 'POST') {
      stored = {saved: false, links: [{id: 'bootstepper', name: 'BootStepper', url: 'https://bootstepper.com/', note: 'Dances'}]};
      return stored;
    }
    return stored;
  });
  await shelf.load();
  shelf.add({name: 'Studio', url: 'https://example.com/studio', note: 'Thursday', api_key: 'DO-NOT-SEND'});
  assert.deepEqual(Object.keys(shelf.payload().links[1]).sort(), ['id', 'name', 'note', 'url']);
  assert.equal(shelf.payload().links[1].api_key, undefined);
  await shelf.save();
  assert.equal(calls[1][0], '/api/settings/community');
  assert.equal(calls[1][1], 'PUT');
  shelf.replace('link-2', {name: 'Beginners', url: 'https://example.com/beginners', note: ''});
  await shelf.save();
  assert.equal(shelf.links[1].name, 'Beginners');
  shelf.remove('link-2');
  await shelf.save();
  assert.equal(shelf.links.length, 1);
  await shelf.reset();
  assert.equal(shelf.saved, false);
  assert.equal(calls.at(-1)[0], '/api/settings/community/reset');
});
