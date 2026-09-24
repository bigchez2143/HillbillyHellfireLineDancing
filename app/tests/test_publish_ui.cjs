'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const {publishView, plainLanguage} = require('../static/publish-ui.js');

const pack = {
  folder: 'C:\\Users\\Lee\\Dances\\Evening Practice',
  note: 'Your step sheet and portable draft are in a folder on this computer. Nothing was sent to a website.',
  files: [
    {role: 'pdf', name: 'Evening Practice - step sheet.pdf', label: 'Step sheet'},
    {role: 'portable', name: 'Evening Practice - portable draft.zip', label: 'Portable draft'}
  ],
  destinations: [
    {id: 'bootstepper', name: 'BootStepper', detail: 'Opens their add-a-dance page. You upload the step sheet there yourself.', url: 'https://bootstepper.com/dances/create'},
    {id: 'copperknob', name: 'CopperKnob', detail: 'Opens their contact page. You attach the step sheet there yourself.', url: 'https://www.copperknob.co.uk/contactus'},
    {id: 'linedance', name: 'LineDance.com', detail: 'Opens Submit a Dance. Sign in there if they ask, then upload the step sheet.', url: 'https://www.linedance.com/submit'}
  ]
};

test('the picker names both files and the three websites', () => {
  const view = publishView(pack);
  assert.deepEqual(view.files.map(file => file.role), ['pdf', 'portable']);
  assert.equal(view.copyLabel, 'Copy folder');
  assert.equal(view.folder, pack.folder);
  assert.deepEqual(view.destinations.map(item => item.url), [
    'https://bootstepper.com/dances/create',
    'https://www.copperknob.co.uk/contactus',
    'https://www.linedance.com/submit'
  ]);
  assert.doesNotMatch(plainLanguage(view), /\bAPI\b/i);
});

test('a pack missing the portable draft is not shown', () => {
  assert.throws(() => publishView({...pack, files: pack.files.slice(0, 1)}), /portable draft/);
});

test('a destination that is not a website is refused', () => {
  const bad = {...pack, destinations: [{...pack.destinations[0], url: 'javascript:alert(1)'}]};
  assert.throws(() => publishView(bad), /website/);
});
