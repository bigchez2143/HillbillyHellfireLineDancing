"use strict";
const assert=require("node:assert/strict"),fs=require("node:fs"),vm=require("node:vm"),path=require("node:path");
const source=fs.readFileSync(path.join(__dirname,"../static/app.js"),"utf8");
const merge=require("../static/draft-merge.js");
const nodes=new Map(), storage=new Map();
const node=id=>{if(!nodes.has(id))nodes.set(id,{value:"",checked:false,querySelectorAll:()=>[]});return nodes.get(id);};
const context=vm.createContext({structuredClone,LineDanceMerge:merge,$:node,Object,JSON,console,
 localStorage:{setItem:(k,v)=>storage.set(k,v),getItem:k=>storage.get(k),removeItem:k=>storage.delete(k)},toast:()=>{},
 sectionsFromBoundaries:()=>[{start:0,end:8,label:"Verse"}],renderSequence:()=>{},renderSectionsTable:()=>{},loadBoundariesFromSections:()=>{},renderTutorial:()=>{}});
vm.runInContext('var P={id:"A"},legacyOpenRequest=1,legacyRevision=1,legacyBaseDraft={},legacyFormBase=null,legacySaving=null,legacyLoadedSeq="[]",seq=[],boundaries=[],STEPS=[];',context);
vm.runInContext(source.slice(source.indexOf("/* Legacy draft state:"),source.indexOf("/* End legacy draft state. */")),context);
const fixtureMove={move_id:"custom-old",lead:"R",name:"Original",counts:4,start:"R",end:"R",rot:0,lines:[{beats:4,text:"Frozen instruction"}]};
context.fixtureMove=fixtureMove;
vm.runInContext('P.draft_move_snapshots={"custom-old":{variants:{R:structuredClone(fixtureMove)}}};STEPS=[{...fixtureMove,lines:[{beats:4,text:"Changed live instruction"}]}];seq=[{move_id:"custom-old",lead:"R"}];legacyBaseDraft={song:{title:"Old",artist:"Original artist"},sheet_meta:{description:"Original note",unexposed:"Retain me"},editor:{moves:structuredClone(seq),counts:4,wall:"1",turn_dir:"L"},choreography:{parts:[{id:"A",moves:[structuredClone(fixtureMove)]}],routine:[{id:"r",part_id:"A",repeat:1}]}};',context);
node("songTitle").value="Old";node("songArtist").value="Original artist";node("metaDesc").value="Original note";node("edCounts").value="4";node("edWall").value="1";node("edTurnDir").value="L";
vm.runInContext('legacyFormBase=readLegacyForms();',context);
node("metaDesc").value="Local note";
let local=vm.runInContext('legacyLocalDraft()',context);
const remote=structuredClone(context.legacyBaseDraft);remote.song.artist="Other window artist";
const result=merge.merge(context.legacyBaseDraft,local,remote);
assert.deepEqual(result.conflicts,[]);assert.equal(result.value.song.artist,"Other window artist");assert.equal(result.value.sheet_meta.description,"Local note");assert.equal(result.value.sheet_meta.unexposed,"Retain me");
vm.runInContext('seq.push({...fixtureMove,id:"extra"});',context);
local=vm.runInContext('legacyLocalDraft()',context);
assert.equal(local.choreography.parts[0].moves[0].lines[0].text,"Frozen instruction");
vm.runInContext('legacyBaseDraft.choreography.routine[0].repeat=2;',context);
assert.throws(()=>vm.runInContext('legacyLocalDraft()',context),/main choreography editor/);
vm.runInContext('legacyBaseDraft.choreography.routine[0].repeat=1;seq=structuredClone(legacyFormBase.editor.moves);',context);

// Execute the production API helper against a delayed response, without a
// browser or network: an old-project completion must never reach its caller.
vm.runInContext(source.slice(source.indexOf("async function api("),source.indexOf("/* Legacy draft state:")),context);
let resolveResponse,fetches=0;
context.fetch=()=>{fetches++;return new Promise(resolve=>resolveResponse=resolve);};
context.IS_FILE_PREVIEW=false;
(async()=>{
 const pending=vm.runInContext('api("/api/projects/A/analyze",{method:"POST"})',context);
 vm.runInContext('P={id:"B"};legacyOpenRequest++;',context);
 resolveResponse({ok:true,json:async()=>({status:"done"})});
 await assert.rejects(pending,error=>error.code==="STALE_PROJECT_RESPONSE");assert.equal(context.P.id,"B");assert.equal(fetches,1);
 const productionApi=context.api;
 context.saveProjectAll=async()=>{context.legacyRevision=7;return true;};
 let guardedBody;
 context.fetch=async(url,options)=>{guardedBody=JSON.parse(options.body);return {ok:true,json:async()=>({sections:[]})};};
 await productionApi("/api/projects/B/lyrics",{method:"PUT",body:{text:"Synthetic text"}});
 assert.equal(guardedBody.expected_revision,7);assert.equal(guardedBody.text,"Synthetic text");

 // Execute production main Save: latest remote fields merge while another
 // local keystroke during PUT remains dirty and recoverable afterwards.
 vm.runInContext('P={id:"A",draft:{}};legacyOpenRequest=3;legacySaving=null;',context);
 vm.runInContext(source.slice(source.indexOf("async function saveProjectAll()"),source.indexOf('$("saveProjectBtn").onclick = saveProjectAll;')),context);
 let resolvePut,putBody;
 context.api=async(url,options)=>{
   if(!options)return {document_revision:3,draft:structuredClone(remote)};
   putBody=options.body;
   return new Promise(resolve=>resolvePut=resolve);
 };
 const saving=vm.runInContext('saveProjectAll()',context);
 await new Promise(resolve=>setImmediate(resolve));
 assert.equal(putBody.expected_revision,3);assert.equal(putBody.draft.song.artist,"Other window artist");assert.equal(putBody.draft.sheet_meta.description,"Local note");
 node("metaDesc").value="Typed while saving";
 resolvePut({document_revision:4,draft:structuredClone(putBody.draft)});
 assert.equal(await saving,true);assert.equal(vm.runInContext('legacyDirty()',context),true);assert(storage.has("ldc.legacyRecovery.A"));
 console.log("PASS: actual legacy form delta/save merge, frozen definitions, irregular-graph protection, late response cancellation and in-flight edits");
})().catch(error=>{console.error(error);process.exitCode=1;});
