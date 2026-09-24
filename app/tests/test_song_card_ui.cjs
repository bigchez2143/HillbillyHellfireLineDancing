'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const card = require('../static/song-card.js');

const TRACK = 'Aa1Bb2Cc3Dd4Ee5Ff6Gg7H';
const PLAYLIST = '37i9dQZF1DXcBWIGoYBM5M';
const root = path.resolve(__dirname, '..', '..');

test('share links become a canonical address and keys are refused', () => {
  assert.equal(card.normalizeSpotifyUrl(`https://open.spotify.com/track/${TRACK}?si=share`), `https://open.spotify.com/track/${TRACK}`);
  assert.equal(card.normalizeSpotifyUrl(`https://open.spotify.com/embed/playlist/${PLAYLIST}`), `https://open.spotify.com/playlist/${PLAYLIST}`);
  assert.equal(card.normalizeSpotifyUrl(`spotify:album:${TRACK}`), `https://open.spotify.com/album/${TRACK}`);
  assert.equal(card.normalizeSpotifyUrl('https://spotify.link/AbCd12'), 'https://spotify.link/AbCd12');
  assert.equal(card.normalizeSpotifyUrl('  '), '');
  assert.throws(() => card.normalizeSpotifyUrl('https://www.youtube.com/watch?v=dQw4w9WgXcQ'), new RegExp(card.PASTE));
  assert.throws(() => card.normalizeSpotifyUrl(`https://api.spotify.com/v1/tracks/${TRACK}?client_id=SECRET`), new RegExp(card.CONNECT));
  assert.throws(() => card.normalizeSpotifyUrl(`https://open.spotify.com/track/${TRACK}?client_id=SECRET`), new RegExp(card.KEY));
  for (const message of [card.PASTE, card.CONNECT, card.KEY]) assert.doesNotMatch(message, /SECRET|client id|API/i);
});

test('rehearsal plays a local file and the link stays share-only', () => {
  const link = `https://open.spotify.com/track/${TRACK}`;
  const quiet = card.rehearsalPlan({path: null}, link);
  assert.equal(quiet.kind, 'metronome');
  assert.equal(quiet.playsSpotify, false);
  assert.equal(quiet.openUrl, link);
  assert.equal(card.playbackUrl('evening-practice', {path: null}, link), '');

  const local = card.rehearsalPlan({path: 'C:\\Music\\practice.wav'}, link);
  assert.equal(local.kind, 'local');
  assert.equal(local.playsSpotify, false);
  assert.equal(local.path, 'C:\\Music\\practice.wav');
  const playback = card.playbackUrl('evening-practice', {path: 'C:\\Music\\practice.wav'}, link);
  assert.equal(playback, '/api/projects/evening-practice/audio');
  assert.doesNotMatch(playback, /spotify/i);

  const disguised = card.rehearsalPlan({path: link}, '');
  assert.equal(disguised.kind, 'metronome');
  assert.equal(card.playbackUrl('evening-practice', {path: link}, link), '');
});

test('the song card copy is on the page and does not promise a connection', () => {
  const html = fs.readFileSync(path.join(root, 'app', 'static', 'creator.html'), 'utf8');
  const music = html.split('data-page="music"', 2)[1].split('data-page="practice"', 2)[0];
  const practice = html.split('id="practiceSource"', 2)[1].split('</p>', 2)[0];
  const visible = music + practice;
  for (const [key, sentence] of Object.entries(card.help)) {
    if (key === "practiceLocal") continue;
    assert.ok(visible.includes(sentence), sentence);
  }
  assert.equal(card.rehearsalPlan({path: "C:\\Music\\practice.wav"}, "").note, card.help.practiceLocal);
  assert.match(visible, /Open Spotify link/);
  assert.match(visible, /Copy link/);
  assert.doesNotMatch(visible, /\b(API|client id|client secret|oauth|sync|iframe|embed|web playback)\b/i);
  const creator = fs.readFileSync(path.join(root, 'app', 'static', 'creator.js'), 'utf8');
  assert.match(creator, /LineDanceSongCard\.playbackUrl/);
  assert.doesNotMatch(creator, /musicAudio\.src\s*=\s*[^;\n]*spotify/i);
});
