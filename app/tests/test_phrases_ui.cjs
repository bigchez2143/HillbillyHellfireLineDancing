/* Async editor safety: stale previews must not insert into a changed dance. */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

function fixture(){
  const elements={phrasePreviewStatus:{textContent:''},phraseInsertBtn:{disabled:false},phrasePreviewDialog:{close(){this.closed=true;}}};
  const context={console,structuredClone,document:{querySelector(){return null;}},$:id=>elements[id],
    numeric:value=>{const parts=String(value??0).split('/');return Number(parts[0])/(parts.length>1?Number(parts[1]):1);},
    project:{id:'first-dance'},draft:{},changeVersion:0,part:{id:'A',moves:[{id:'existing',counts:8,text:'Existing'}]},
    selectedPart(){return context.part;},clone:structuredClone,notify(){},changes:0,
    change(action){context.changes++;action(context.draft);context.changeVersion++;},
    api:async()=>({moves:[{id:'fresh',duration_counts:'8',events:[{duration_counts:'8',text:'New'}]}],notice:'Inserted'})};
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../static/phrases-ui.js'),'utf8'),context);
  vm.runInContext('globalThis.testing={insert:insertPreviewedPhrase,duration:phraseDuration,preview:()=>{phrasePreview={id:"phrase-one",version:1,mirrored:false,context:phraseContext(),position:"end"};}}',context);
  return {context,elements};
}

(async()=>{
  let {context,elements}=fixture();
  assert.equal(context.testing.duration({events:[{duration_counts:'1/3'},{offset_counts:'1/3',duration_counts:'23/3'}]}),8);
  assert.equal(context.testing.duration({definition:{counts:{numerator:16,denominator:2}}}),8);
  assert.ok(Number.isNaN(context.testing.duration({move_id:'unresolved'})));
  context.testing.preview();context.project={id:'another-dance'};
  await context.testing.insert();
  assert.equal(context.changes,0);assert.match(elements.phrasePreviewStatus.textContent,/dance changed/);

  ({context,elements}=fixture());
  let finish;
  context.api=()=>new Promise(resolve=>{finish=resolve;});
  context.testing.preview();const pending=context.testing.insert();
  context.part={id:'B',moves:[]};context.changeVersion++;
  finish({moves:[{id:'wrong-dance'}]});await pending;
  assert.equal(context.changes,0);assert.deepEqual(context.part.moves,[]);
  assert.match(elements.phrasePreviewStatus.textContent,/dance changed/);

  ({context,elements}=fixture());
  context.testing.preview();await context.testing.insert();
  assert.equal(context.changes,1);assert.equal(context.part.moves[1].id,'fresh');
  assert.equal(elements.phrasePreviewDialog.closed,true);
  console.log('Phrase UI checks passed: exact duration display, stale preview, in-flight dance changes and independent insertion.');
})().catch(error=>{console.error(error);process.exitCode=1;});
