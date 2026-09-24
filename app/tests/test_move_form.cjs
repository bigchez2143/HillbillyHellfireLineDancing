'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {Model, mount, onsetToOffset, offsetToOnset, exactCount} = require('../static/move-form.js');
const original = () => [
  {id:'kept-1',offset_counts:'0/2',duration_counts:'2/2',text:'Step right',support_before:'L',support_after:'R',rotation_deg:0,notes:{author:'Synthetic fixture',flags:['keep']},future_extension:{nested:[1,null,'x']}},
  {id:'kept-2',duration_counts:'.5',text:'Recover left',support_before:'R',support_after:'L',rotation_deg:'0/1',facing_before_deg:'315/1'},
  {id:'kept-3',offset_counts:'3/2',duration_counts:'1/2',text:'Step right',support_before:'L',support_after:'R',rotation_deg:'0'}
];

test('no-op preserves exact fields, IDs, omitted offsets, types, and caller data', () => {
  const events=original(), model=new Model({events,duration:'2/1'});
  assert.deepEqual(model.views().map(r=>r.onset),['1','2','2&']);
  assert.deepEqual(model.read(),{events,duration_counts:'2/1'});
  assert.equal(model.isDirty(),false);
  model.patch(1,'text','New teaching cue');
  const expected=original();expected[1].text='New teaching cue';
  assert.deepEqual(model.read().events,expected);
  assert.deepEqual(events,original());
});

test('unknown and absent weight/turn data are never inferred by viewing or saving', () => {
  const events=[{id:'unknown',duration_counts:'4',text:'Provisional cue',support_before:null,support_after:'unknown',rotation_deg:null,custom_fact:'retain'}];
  const model=new Model({events,duration:4});
  assert.equal(model.views()[0].support_before,'unknown');
  assert.deepEqual(model.read().events,events);
  assert.ok(model.inspect().warnings.some(w=>w.includes('unverified')));
  const absent=new Model({events:[{text:'Hold',duration_counts:'1'}],duration:'1'});
  assert.deepEqual(absent.read().events,[{text:'Hold',duration_counts:'1'}]);
});

test('new row has exact timing and explicitly unknown support without a guessed turn', () => {
  const model=new Model();model.add();
  const [event]=model.read('1').events;
  assert.ok(event.id);assert.equal(event.offset_counts,'0');assert.equal(event.duration_counts,'1');
  assert.equal(event.support_before,'unknown');assert.equal(event.support_after,'unknown');
  assert.equal(Object.hasOwn(event,'rotation_deg'),false);
  assert.equal(Object.hasOwn(event,'facing_before_deg'),false);
});

test('count label conversion preserves Dorothy 1, 2, 2& and arbitrary rational counts', () => {
  for(const [onset,offset]of [['1','0'],['2','1'],['2&','3/2'],['7/4','3/4'],['4/3','1/3'],['1.25','1/4']]) assert.equal(onsetToOffset(onset),offset);
  for(const offset of ['0','3/2','1/3','3/4','99999']) assert.equal(onsetToOffset(offsetToOnset(offset)),offset);
  for(const invalid of ['0','-1','&','2&&','1/0','NaN','Infinity']) assert.throws(()=>onsetToOffset(invalid));
  assert.equal(exactCount('0.100000000000000001'),'100000000000000001/1000000000000000000');
});

test('decimal durations accumulate exactly and a declared total is never silently changed', () => {
  const events=Array.from({length:30},(_,i)=>({id:`t${i}`,duration_counts:'0.1',text:'Synthetic tenth'}));
  const model=new Model({events,duration:'3'});
  assert.equal(model.inspect().span,'3');assert.equal(model.read().duration_counts,'3');
  assert.throws(()=>model.read('4'),/cover 3 counts.*declares 4/);
  assert.deepEqual(model.events,events);
});

test('real bundled variants all roundtrip, including provisional unknown models', () => {
  const pack=JSON.parse(fs.readFileSync(path.join(__dirname,'../../data/expanded-moves.json'),'utf8'));
  for(const move of pack.moves){
    const model=new Model({events:move.events,duration:move.duration_counts});
    assert.deepEqual(model.read().events,move.events,move.id);
  }
  const dorothy=pack.moves.find(m=>m.group==='Wizard / Dorothy');
  assert.ok(dorothy);
  assert.deepEqual(new Model({events:dorothy.events,duration:dorothy.duration_counts}).views().map(v=>v.onset),['1','2','2&']);
});

test('explicit gaps and overlaps explain which onset to correct', () => {
  const model=new Model({events:original(),duration:'2'});
  model.patch(1,'onset','2&');
  assert.throws(()=>model.read(),/Row 2 starts at 2&; expected 2/);
  model.patch(1,'onset','2');assert.deepEqual(model.read().events[1].offset_counts,'1');
  model.patch(2,'onset','2');assert.throws(()=>model.read(),/Row 3 starts at 2; expected 2&/);
});

test('plain weight and turn edits preserve every unrelated event field', () => {
  const model=new Model({events:original(),duration:'2'}), expected=original();
  model.patch(0,'support_before','both');model.patch(0,'rotation_deg','-90');
  expected[0].support_before='both';expected[0].rotation_deg='-90';
  assert.deepEqual(model.read().events,expected);
  model.patch(0,'rotation_deg','');delete expected[0].rotation_deg;
  assert.deepEqual(model.read().events,expected);
  assert.throws(()=>model.patch(0,'support_after','any'),/supported weight/);
  assert.throws(()=>model.patch(0,'id','replacement'),/not editable/);
});

test('reordering and removal keep IDs/details and reflow exact durations', () => {
  const model=new Model({events:original(),duration:'2'});
  model.move(2,-1);
  assert.deepEqual(model.events.map(e=>e.id),['kept-1','kept-3','kept-2']);
  assert.deepEqual(model.events.map(e=>e.offset_counts),['0','1','3/2']);
  assert.equal(model.events[2].duration_counts,'.5');
  assert.deepEqual(model.events[0].future_extension,original()[0].future_extension);
  model.remove(0);
  assert.deepEqual(model.events.map(e=>e.offset_counts),['0','1/2']);
  assert.throws(()=>model.read('2'),/cover 1 counts.*declares 2/);
  assert.equal(model.read('1').events.length,2);
});

test('unknown-duration reorder fails without partial mutation; unknown timings survive no-op', () => {
  const events=[{id:'unknown',text:'Unknown span'},{id:'known',offset_counts:'1',duration_counts:'1',text:'Step'}];
  const model=new Model({events,duration:'2'});
  assert.deepEqual(model.read().events,events);
  assert.throws(()=>model.move(1,-1),/every row a duration/);
  assert.deepEqual(model.events,events);
  assert.throws(()=>model.add(),/Resolve.*timing/);
  model.patch(1,'duration_counts','4');
  assert.throws(()=>model.read('2'),/at least 5 counts.*declares 2/);
});

test('JSON changes require valid objects, preserve extras, and cannot be silently overwritten by rows', () => {
  const model=new Model({events:original(),duration:'2'});
  model.setJson('[bad');
  assert.throws(()=>model.read(),/JSON changes are not valid/);assert.equal(model.jsonDraft,'[bad');
  assert.deepEqual(model.events,original());
  assert.throws(()=>model.patch(0,'text','Lost edit'),/Apply JSON/);
  assert.throws(()=>model.setEnabled(false),/Apply your JSON/);
  assert.throws(()=>model.reflow(),/Apply JSON/);
  model.setJson(JSON.stringify([{id:'a',duration_counts:'2',text:'JSON cue',extra:{nested:true}}]));
  assert.deepEqual(model.read().events,[{id:'a',duration_counts:'2',text:'JSON cue',extra:{nested:true}}]);
  model.setJson('[null]');assert.throws(()=>model.applyJson(),/count-row objects/);
  model.discardJson();assert.equal(model.read().events[0].text,'JSON cue');
});

test('description only needs an explicit clear and enabled empty timing cannot be saved', () => {
  const model=new Model({events:original(),duration:'2'});
  assert.throws(()=>model.setEnabled(false),/Remove the count rows explicitly/);
  assert.deepEqual(model.events,original());
  model.clear();assert.deepEqual(model.read().events,[]);
  model.setEnabled(true);assert.throws(()=>model.read(),/Add a count row/);
});

// Small DOM harness exercises the mounted production form without a browser,
// network or dependency. It covers event wiring and state preservation; it is
// not a layout or accessibility certification.
class Element {
  constructor(tag,doc){this.tagName=tag.toUpperCase();this.ownerDocument=doc;this.children=[];this.attrs={};this.events={};this.value='';this.hidden=false;this.disabled=false;this.classes=new Set();this.classList={add:v=>this.classes.add(v),remove:v=>this.classes.delete(v),toggle:(v,on)=>on?this.classes.add(v):this.classes.delete(v)};}
  setAttribute(k,v){this.attrs[k]=String(v);if(k==='hidden')this.hidden=true;if(k==='value')this.value=String(v);}
  removeAttribute(k){delete this.attrs[k];}
  append(...children){this.children.push(...children);}
  replaceChildren(...children){this.children=children;}
  addEventListener(k,f){(this.events[k]??=[]).push(f);}
  dispatch(k){for(const f of this.events[k]||[])f({target:this});}
  focus(){this.ownerDocument.activeElement=this;}
  querySelector(selector){const row=selector.match(/^\[data-row="(\d+)"\] input$/);if(row){const el=find(this,n=>n.attrs['data-row']===row[1]);return el&&find(el,n=>n.tagName==='INPUT');}throw new Error('Harness selector unsupported: '+selector);}
}
function find(node,predicate){if(predicate(node))return node;for(const child of node.children){const found=find(child,predicate);if(found)return found;}return null;}
function ui(events=original(),duration='2'){
  const doc={createElement:tag=>new Element(tag,doc)},container=new Element('div',doc);
  const mounted=mount(container,{events,duration});
  return {container,mounted,field:(name,row=0)=>find(find(container,n=>n.attrs['data-row']===String(row)),n=>n.attrs['data-field']===name),button:text=>find(container,n=>n.tagName==='BUTTON'&&n.textContent===text),mode:find(container,n=>n.attrs['aria-label']==='Move timing mode'),json:find(container,n=>n.attrs['aria-label']==='Exact event JSON')};
}
function input(node,value){node.value=value;node.dispatch('input');}
function change(node,value){node.value=value;node.dispatch('change');}

test('mounted no-op is lossless and editing a cue leaves metadata/IDs/fractions intact', () => {
  const form=ui();assert.deepEqual(form.mounted.read().events,original());
  input(form.field('text',1),'A clearer cue');
  const expected=original();expected[1].text='A clearer cue';
  assert.deepEqual(form.mounted.read().events,expected);
});

test('invalid count typing remains visible, blocks save/mode switch, and cannot be lost in JSON', () => {
  const form=ui();const onset=form.field('onset');input(onset,'2/');
  assert.equal(onset.attrs['aria-invalid'],'true');assert.equal(form.json.disabled,true);
  assert.throws(()=>form.mounted.read(),/Row 1/);
  change(form.mode,'description');assert.equal(form.mode.value,'timed');assert.equal(onset.value,'2/');
  input(onset,'1');assert.equal(form.json.disabled,false);assert.deepEqual(form.mounted.read().events[0].offset_counts,'0');
});

test('mounted JSON application is explicit and pending malformed text survives a failed save', () => {
  const form=ui();input(form.json,'[bad');
  assert.equal(find(form.container,n=>n.classes?.has('no')||n.attrs.class==='move-form-rows').disabled,true);
  assert.throws(()=>form.mounted.read(),/JSON changes are not valid/);assert.equal(form.json.value,'[bad');
  form.button('Keep count rows instead').dispatch('click');
  assert.deepEqual(form.mounted.read().events,original());
  const edited=original();edited[0].text='From JSON';edited[0].custom='retained';
  input(form.json,JSON.stringify(edited));form.button('Apply JSON changes').dispatch('click');
  assert.deepEqual(form.mounted.read().events,edited);
});

test('mounted description switch asks before clearing and keeping rows preserves them', () => {
  const form=ui();change(form.mode,'description');assert.throws(()=>form.mounted.read(),/remove or keep/);
  form.button('Keep count rows').dispatch('click');assert.deepEqual(form.mounted.read().events,original());
  change(form.mode,'description');form.button('Remove all count rows').dispatch('click');
  assert.deepEqual(form.mounted.read().events,[]);assert.equal(form.mode.value,'description');
});

test('mounted plain-language turns and weights map to mechanics only when chosen', () => {
  const form=ui();const turn=find(form.container,n=>n.attrs['aria-label']==='Turn during action 1');
  change(turn,'90');change(form.field('support_after'),'both');
  assert.equal(form.mounted.read().events[0].rotation_deg,'90');
  assert.equal(form.mounted.read().events[0].support_after,'both');
  const newTurn=find(form.container,n=>n.attrs['aria-label']==='Turn during action 1');change(newTurn,'');
  assert.equal(Object.hasOwn(form.mounted.read().events[0],'rotation_deg'),false);
});

test('mounted total check does not rewrite the declared count and reset changes record cleanly', () => {
  const form=ui();form.mounted.setDuration('4');assert.throws(()=>form.mounted.read(),/declares 4/);
  form.mounted.setValue({events:[],duration:null});assert.deepEqual(form.mounted.read(),{events:[],duration_counts:null});assert.equal(form.mounted.isDirty(),false);
  change(form.mode,'timed');form.button('Add count row').dispatch('click');
  assert.equal(form.mounted.read('1').events[0].support_before,'unknown');
});

test('valid JSON with a bad total stays visible as rows after blocked Save', () => {
  const form=ui();const events=[{id:'json-edited',duration_counts:'4',text:'New four-count cue',unexposed:'keep'}];
  input(form.json,JSON.stringify(events));
  assert.throws(()=>form.mounted.read(),/cover 4 counts.*declares 2/);
  assert.equal(form.field('text').value,'New four-count cue');
  assert.equal(form.field('duration_counts').value,'4');
  assert.equal(find(form.container,n=>n.attrs.class==='move-form-pending').hidden,true);
  form.mounted.setDuration('4');assert.deepEqual(form.mounted.read().events,events);
});
