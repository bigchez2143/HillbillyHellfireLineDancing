const assert=require('node:assert/strict');
const t=require('../static/move-timing.js');
assert.equal(t.label(0),'1');assert.equal(t.label('1/2'),'1&');
assert.equal(t.label('3/2'),'2&');assert.equal(t.label('1/4'),'1e');
assert.equal(t.label('3/4'),'1a');assert.equal(t.label('2/3'),'1+2/3');
// Dorothy's late syncopation must remain 2&, not be moved to 1&.
assert.equal(t.practice(1.6,1.5,8),'2&');
assert.equal(t.practice(2.2,1.5,8),'3');
assert.equal(t.practice(8.6,8.5,8),'1&');
assert.equal(t.practice(6.8,6.5,6),'1&');
assert.equal(t.facing('45'),'Facing 1:30 (45°)');
assert.equal(t.facing('-90'),'Facing 9:00 (270°)');
assert.equal(t.facing(null),'Facing needs review');
assert.equal(t.facing('unknown'),'Facing needs review');
// Wizard R takes weight on R, so a following free-foot scuff must use L.
assert.equal(t.endingFreeFoot([{events:[{support_after:'R'},{support_after:'L'},{support_after:'R'}]}],'R'),'L');
assert.equal(t.endingFreeFoot([{events:[{support_after:'unknown'}]}],'R'),null);
assert.equal(t.endingFreeFoot([{events:[{support_after:'R'}]},{end:'SAME'}],'R'),'L');
assert.equal(t.endingFreeFoot([{events:[{support_after:'R'},{support_after:'same'}]}],'R'),'L');
console.log('Move timing presentation regressions passed.');
