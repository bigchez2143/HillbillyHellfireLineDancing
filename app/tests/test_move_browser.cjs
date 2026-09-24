const assert=require('node:assert/strict');
const test=require('node:test'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const m=require('../static/move-browser-model.js');
const core=[{move_id:'vine',lead:'R',name:'Right vine',level:'B',family:'vine'},{move_id:'vine',lead:'L',name:'Left vine',level:'B',family:'vine'},{move_id:'wizard',lead:'R',name:'Wizard',aliases:['Dorothy'],definition_hash:'abc',level:'I',group:'Locking'}];
const users=[{id:'user-test',name:'My step',difficulty:'Intermediate'},{id:'user-old',name:'Old step',deleted:true}];
const refs=[{id:'reference-0',name:'BPM',category:'concept',level:'Beginner'}];
const rows=m.index(core,users,refs);
assert.equal(m.filter(rows).length,3);
assert.equal(m.filter(rows,{query:'Dorothy'})[0].data.move_id,'wizard');
assert.deepEqual(m.filter(rows,{tab:'glossary'}).map(x=>x.name),['BPM']);
assert.equal(m.filter(rows,{tab:'personal',archived:true}).length,2);
assert.equal(m.filter(rows,{difficulty:'INT'})[0].name,'My step');
assert.equal(m.filter(rows,{favoritesOnly:true,favorites:['expansion:wizard']})[0].name,'Wizard');
assert.equal(m.index(core,[],[],'L')[0].name,'Left vine');
assert.equal(m.turn('-90'),'¼ turn left');assert.equal(m.turn('360'),'Full turn right');
assert.equal(m.turn(null),'Not specified');assert.equal(m.turn('-90',true),'-90°');
console.log('PASS: unified move search, aliases, personal/reference separation, levels, favorites, mirroring selection and plain turn labels');

const legacy=[{move_id:'custom-my-rock',lead:'R',name:'My right rock',level:'B',family:'rock',counts:4,lines:[{beats:2,text:'Rock and recover'},{beats:2,text:'Side and touch'}]},{move_id:'custom-my-rock',lead:'L',name:'My left rock',level:'B',family:'rock',counts:4,lines:[{beats:2,text:'Mirrored rock and recover'},{beats:2,text:'Mirrored side and touch'}]}];
test('older custom moves belong to My moves while core, expansion and references remain separate',()=>{
  const all=m.index([...core,...legacy],users,refs);
  const mine=m.filter(all,{tab:'personal'});
  assert.deepEqual(mine.map(r=>r.name),['My right rock','My step']);
  const old=mine.find(r=>r.kind==='legacy');assert.equal(old.key,'core:custom-my-rock');
  assert.equal(old.data,legacy[0]);assert.equal(m.isPersonal(old),true);
  assert.deepEqual(m.filter(all,{tab:'glossary'}).map(r=>r.name),['BPM']);
  assert.equal(m.filter(all,{favoritesOnly:true,favorites:['core:custom-my-rock']})[0],old);
  assert.equal(m.filter(all,{tab:'personal',archived:true}).length,3);
  assert.equal(m.filter(m.index([...core,...legacy],users,refs,'L'),{tab:'personal'}).find(r=>r.kind==='legacy').name,'My left rock');
});

test('personal preview accumulates implicit exact counts without changing saved events',()=>{
  const move={events:[{id:'first',duration_counts:'1',text:'Step'},{id:'second',duration_counts:'1/2',text:'Lock'},{id:'third',duration_counts:'.5',text:'Step',extra:{retain:true}}]};
  const before=structuredClone(move),preview=m.previewRows(move);
  assert.deepEqual(preview.map(r=>r.label),['1','2','2&']);
  assert.deepEqual(preview.map(r=>r.offset_counts),['0','1','3/2']);
  assert.deepEqual(move,before);assert.equal(Object.hasOwn(move.events[1],'offset_counts'),false);
  const thirds=m.previewRows({events:[{duration_counts:'1/3'},{duration_counts:'1/3'},{duration_counts:'1/3'},{duration_counts:'1'}]});
  assert.deepEqual(thirds.map(r=>r.label),['1','1+1/3','1+2/3','2']);
  const tenths=m.previewRows({events:Array.from({length:31},()=>({duration_counts:'.1'}))});
  assert.equal(tenths[30].offset_counts,'3');assert.equal(tenths[30].label,'4');
});

test('personal preview preserves explicit offsets and does not guess after unknown timing',()=>{
  const result=m.previewRows({events:[{text:'Unknown span'},{duration_counts:'1'},{offset_counts:'3/2',duration_counts:'1/2'},{duration_counts:'1'},{offset_counts:null,duration_counts:'1'}]});
  assert.deepEqual(result.map(r=>r.label),['1','Unspecified','2&','3','Unspecified']);
  assert.equal(m.previewRows({events:[{offset_counts:'1/0',duration_counts:'1'}]})[0].label,'Unspecified');
});

test('core previews show accumulated ranges and known syncopation rather than repeated durations',()=>{
  assert.deepEqual(m.previewRows(legacy[0]).map(r=>r.label),['1–2','3–4']);
  const move={lines:[{beats:2,sync:true,text:'Shuffle'},{beats:1,text:'Step'},{beats:1,text:'Touch'}]};
  assert.deepEqual(m.previewRows(move).map(r=>r.label),['1&2','3','4']);
  assert.equal(m.previewRows({lines:[{beats:4,sync:true,text:'An older written combination'}]})[0].label,'1–4 (syncopated)');
});

test('readable family labels retain stable filter keys and singular counts are grammatical',()=>{
  assert.equal(m.familyLabel('backlock'),'Back locking step');assert.equal(m.familyLabel('point_side'),'Side point');
  assert.equal(m.familyLabel('my_private_family'),'My private family');
  assert.equal(m.familyLabel('Wizard / Dorothy'),'Wizard / Dorothy');
  const rows=m.index([{move_id:'back_lock',lead:'R',name:'Lock',family:'backlock'}],[],[]);
  assert.equal(rows[0].family,'backlock');
  assert.equal(m.filter(rows,{query:'Back locking',family:'backlock'}).length,1);
  assert.equal(m.durationLabel(1),'1 count');assert.equal(m.durationLabel('2/2'),'2/2 count');
  assert.equal(m.durationLabel('1/2'),'1/2 counts');assert.equal(m.durationLabel(null),'Counts not set');
  assert.equal(m.quantity(1,'move'),'1 move');assert.equal(m.quantity(1,'personal move'),'1 personal move');
  assert.equal(m.quantity(1,'favorite'),'1 favorite');assert.equal(m.quantity(0,'favorite'),'0 favorites');
});

const source=fs.readFileSync(path.join(__dirname,'../static/move-browser.js'),'utf8');
const stars=()=>[{disabled:false},{disabled:false}];
function favoriteHarness(){
  const context=vm.createContext({buttons:stars(),console,errors:[],document:{},renderMoveChoices:()=>{},notify:message=>context.errors.push(message)});
  context.document.querySelectorAll=()=>context.buttons;
  context.renderUnifiedBrowser=()=>{context.buttons=stars();context.buttons.forEach(b=>b.disabled=context.favoriteBusy);};
  vm.runInContext('var favoriteBusy=false,favoriteChange=0,browserFavorites=[];',context);
  vm.runInContext(source.slice(source.indexOf('function updateFavoriteControls'),source.indexOf('async function archiveBrowserMove')),context);
  return context;
}
test('favorite controls disable during the actual request and all reenable after success',async()=>{
  const context=favoriteHarness();let resolve,calls=0;
  context.api=()=>{calls++;return new Promise(r=>resolve=r);};
  const pending=context.toggleBrowserFavorite('core:vine');
  assert.ok(context.buttons.every(b=>b.disabled));
  await context.toggleBrowserFavorite('core:another');assert.equal(calls,1);
  resolve({favorites:['core:vine']});await pending;
  assert.ok(context.buttons.every(b=>!b.disabled));assert.deepEqual(context.browserFavorites,['core:vine']);
});
test('favorite controls reenable after failure without changing saved favorite state',async()=>{
  const context=favoriteHarness();let reject;
  context.api=()=>new Promise((_,r)=>reject=r);
  const pending=context.toggleBrowserFavorite('core:vine');assert.ok(context.buttons.every(b=>b.disabled));
  reject(new Error('Storage is busy'));await pending;
  assert.ok(context.buttons.every(b=>!b.disabled));assert.deepEqual([...context.browserFavorites],[]);
  assert.deepEqual(context.errors,['Storage is busy']);
});
test('late initial preference response cannot overwrite a completed favorite change',async()=>{
  const context=favoriteHarness();let finishPreferences,started;
  const requestStarted=new Promise(resolve=>started=resolve);
  context.creatorReady=Promise.resolve();context.loadUserMoves=async()=>{};context.renderCatalog=async()=>{};
  context.api=async endpoint=>endpoint.endsWith('/preferences')?new Promise(r=>{finishPreferences=r;started();}):{favorites:['core:vine']};
  vm.runInContext(source.slice(source.indexOf('async function loadMoveBrowser()'),source.lastIndexOf('loadMoveBrowser();')),context);
  const initial=context.loadMoveBrowser();await requestStarted;
  await context.toggleBrowserFavorite('core:vine');finishPreferences({favorites:[]});await initial;
  assert.deepEqual(context.browserFavorites,['core:vine']);
});

test('actual personal insertion asks for the previewed immutable version and clones its snapshot',async()=>{
  const target={moves:[]};let finishSnapshot,requested;
  const context=vm.createContext({draft:{choreography:{start:{free_foot:'R'}}},project:{id:'dance-a'},activePart:'A',changeVersion:1,libraryRoot:'/api/creator/library',clone:structuredClone,uid:()=> 'new-instance',selectedPart:()=>target,change:operation=>operation(),showView:()=>{},notify:()=>{},requestStillCurrent:()=>true});
  context.api=endpoint=>{requested=endpoint;return new Promise(r=>finishSnapshot=r);};
  vm.runInContext(source.slice(source.indexOf('async function addBrowserMove('),source.indexOf("$('browserPreviewClose')")),context);
  const preview={kind:'user',data:{id:'move-123',version:3,duration_counts:'2',events:[{duration_counts:'2'}]}};
  const pending=context.addBrowserMove(preview);
  assert.equal(requested,'/api/creator/library/records/move-123/snapshot?version=3');
  const frozen={snapshot_id:'move-123@3',library_version:3,name:'Saved version three',events:[{id:'old-event',duration_counts:'2',text:'Frozen cue'}]};
  finishSnapshot(frozen);await pending;
  assert.equal(target.moves[0].library_version,3);assert.equal(target.moves[0].id,'new-instance');
  frozen.events[0].text='Changed elsewhere';assert.equal(target.moves[0].events[0].text,'Frozen cue');
});

test('actual render offers the older manager in Basic without personal edit/archive routes',()=>{
  const nodes=new Map();const node=id=>{if(!nodes.has(id))nodes.set(id,{value:'',checked:false,querySelectorAll:()=>[]});return nodes.get(id);};
  for(const id of ['unifiedMoveFamily','unifiedMoveLevel'])node(id).value='all';node('unifiedMoveLead').value='R';
  const context=vm.createContext({$:node,MoveBrowserModel:m,moves:[...core,...legacy],userMoveLibrary:users,catalog:refs,document:{querySelectorAll:()=>[]},escapeHtml:value=>String(value??''),packDurationLabel:()=> '2 counts'});
  vm.runInContext('var browserTab="personal",browserPage=0,browserRows=[],browserFavorites=[],favoriteBusy=true;',context);
  vm.runInContext(source.slice(source.indexOf('function indexedBrowserRows'),source.indexOf('function updateFavoriteControls')),context);
  context.renderUnifiedBrowser();
  assert.match(node('browserResults').innerHTML,/My older move/);
  assert.match(node('browserResults').innerHTML,/data-browser-legacy="core:custom-my-rock"/);
  assert.doesNotMatch(node('browserResults').innerHTML,/data-browser-(?:edit|archive)="core:custom-my-rock"/);
  assert.match(node('browserResults').innerHTML,/data-browser-star="core:custom-my-rock" disabled/);
  assert.equal(node('browserLeadLabel').hidden,false);
});
