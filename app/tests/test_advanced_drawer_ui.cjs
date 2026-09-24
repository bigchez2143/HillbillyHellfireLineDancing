'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {WARNINGS, SPOTIFY_NOTE, keyPayload, searchPayload, keyNote, presentResults, create} = require('../static/advanced-drawer.js');

const html = fs.readFileSync(path.join(__dirname, '../static/creator.html'), 'utf8');
const publish = html.slice(html.indexOf('id="publishDialog"'), html.indexOf('id="notice"'));
const drawer = html.slice(html.indexOf('id="advancedDrawer"'), html.indexOf('id="newDialog"'));

test('the Advanced drawer warns, folds in Optional AI, and does not collect a Spotify client id', () => {
  assert.match(drawer, /id="advancedDrawer" class="advanced"/);
  assert.match(drawer, /id="settingsAiBtn"/);
  assert.equal(WARNINGS.length, 4);
  for (const warning of WARNINGS) assert.ok(drawer.includes(warning));
  assert.match(drawer, /read-only/i);
  assert.match(drawer, /does not keep a copy/);
  assert.equal(SPOTIFY_NOTE, html.match(/id="spotifyLaterNote">([^<]+)/)[1]);
  assert.match(SPOTIFY_NOTE, /not enabled/);
  assert.equal((drawer.match(/<input/g) || []).length, 2);
  assert.match(drawer, /id="spotifyLaterNote"/);
  assert.doesNotMatch(drawer, /<input[^>]*(spotify|client)/i);
  assert.doesNotMatch(publish, /bootstepperKey|client id|api key/i);
  assert.doesNotMatch(publish, /\bAPI\b/);
});

test('a typed key is sent only when saving, and search never includes it', () => {
  assert.deepEqual(keyPayload('  '), {api_key: ''});
  assert.equal(keyPayload(' personal-key ').api_key, 'personal-key');
  assert.throws(() => keyPayload('https://example.com/?api_key=SECRET'), /web address/);
  assert.deepEqual(searchPayload('dances', ' cupid '), {kind: 'dances', query: 'cupid'});
  assert.throws(() => searchPayload('events', 'cupid'), /dances, songs, or choreographers/);
  const body = searchPayload('songs', 'shuffle');
  assert.equal(body.api_key, undefined);
  assert.equal(body.client_id, undefined);
});

test('search results keep a public summary and drop sheet, streaming, and key fields', () => {
  const view = presentResults({
    kind: 'dances',
    attribution: 'From BootStepper',
    source: 'https://bootstepper.com/',
    items: [{
      title: 'Cup of Practice',
      difficulty: 'Beginner',
      counts: 32,
      walls: 4,
      choreographers: ['Alex Example'],
      songs: ['Practice Song — Example Band'],
      url: 'https://bootstepper.com/dances/D4B57G68FMQH7MN',
      stepSheetBlobUrl: 'https://blobs.example/SECRET-SHEET',
      api_key: 'FAKE-BOOT-KEY',
      spotifyUrl: 'https://open.spotify.com/track/secret'
    }]
  });
  assert.deepEqual(Object.keys(view.items[0]).sort(), ['choreographers', 'counts', 'difficulty', 'songs', 'title', 'url', 'walls']);
  assert.equal(JSON.stringify(view).includes('SECRET'), false);
  assert.equal(JSON.stringify(view).includes('spotify'), false);
  assert.equal(presentResults({kind: 'dances', items: [{title: 'Bad link', url: 'javascript:alert(1)'}]}).items[0].url, '');
});

test('save, forget, and search talk only to the local advanced routes', async () => {
  const calls = [];
  let configured = false;
  const drawer = create(async (url, options) => {
    calls.push([url, options && options.method, options && options.body]);
    if (options && options.method === 'PUT') {
      configured = true;
      assert.equal(options.body.api_key, 'personal-key');
      return {api_key_configured: true, read_only: true, writes_enabled: false};
    }
    if (options && options.method === 'DELETE') {
      configured = false;
      return {api_key_configured: false, read_only: true, writes_enabled: false};
    }
    if (options && options.method === 'POST') {
      assert.equal(options.body.api_key, undefined);
      return {kind: 'dances', attribution: 'From BootStepper', source: 'https://bootstepper.com/', items: [{title: 'Cup of Practice', url: 'https://bootstepper.com/dances/D4B57G68FMQH7MN'}]};
    }
    return {bootstepper: {api_key_configured: configured, read_only: true, writes_enabled: false}, ai: {enabled: false}, spotify: {enabled: false, client_id_collected: false}};
  });
  await drawer.load();
  assert.equal(keyNote(drawer.status), 'No BootStepper key is saved. The rest of the app works without one.');
  await drawer.saveKey('personal-key');
  assert.match(drawer.message, /not contacted/);
  assert.equal(keyNote(drawer.status), 'A personal key is saved on this computer. Leave the box blank to keep it.');
  await drawer.search('dances', 'cupid');
  assert.equal(drawer.results.items[0].title, 'Cup of Practice');
  await drawer.forgetKey();
  assert.equal(drawer.results, null);
  assert.deepEqual(calls.map(call => [call[0], call[1]]), [
    ['/api/settings/advanced', undefined],
    ['/api/settings/advanced/bootstepper', 'PUT'],
    ['/api/settings/advanced/bootstepper/search', 'POST'],
    ['/api/settings/advanced/bootstepper/key', 'DELETE']
  ]);
});
