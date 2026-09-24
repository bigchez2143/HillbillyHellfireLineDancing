'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const {Connection,PRESETS,TEST_PROMPT,payload,presetFor,mount}=require('../static/ai-connection-ui.js');
const fingerprint='a'.repeat(64),otherFingerprint='b'.repeat(64);
const settings=(extra={})=>({enabled:true,provider:'openai_compatible',base_url:'https://api.openai.com/v1',model:'user-entered-model',timeout_seconds:60,api_key_configured:true,configured:true,ready:true,authentication:'api_key',endpoint:'https://api.openai.com/v1/chat/completions',connection_fingerprint:fingerprint,test_status:'not_tested',...extra});

test('opening only reads local settings and never copies a returned credential into state',async()=>{
  const calls=[],connection=new Connection(async(...args)=>{calls.push(args);return settings({api_key:'DO-NOT-COPY',private_history:'DO-NOT-COPY'});});
  assert.equal(calls.length,0);await connection.load();
  assert.deepEqual(calls,[['/api/creator/ai/connection']]);assert.equal(connection.ready(),true);
  assert.equal(connection.saved.api_key,undefined);assert.equal(connection.form.api_key,'');
  assert.equal(connection.saved.private_history,undefined);assert.match(connection.status(),/has not been tested/);
});
test('preset addresses and manual model names map to the supported adapters',()=>{
  assert.equal(PRESETS.openai.base_url,'https://api.openai.com/v1');assert.equal(PRESETS.anthropic.provider,'anthropic_messages');
  assert.equal(presetFor(settings()),'openai');assert.equal(presetFor(settings({base_url:'http://localhost:8080/v1'})),'compatible');
  assert.equal(presetFor(settings({provider:'custom'})),'custom');
  assert.equal(Object.hasOwn(PRESETS.openai,'model'),false);
});
test('save payload allowlists settings, omits a blank key, and sends an explicitly entered key only locally',()=>{
  const input={...settings(),api_key:'',song:'PRIVATE',history:['PRIVATE'],project_id:'PRIVATE'};
  assert.deepEqual(payload(input),{enabled:true,provider:'openai_compatible',base_url:'https://api.openai.com/v1',model:'user-entered-model',timeout_seconds:60});
  assert.equal(payload({...input,api_key:' synthetic-test-key '}).api_key,'synthetic-test-key');
  for(const base_url of ['http://remote.example/v1','https://user:pass@example.com','https://example.com/v1?token=secret','https://example.com/v1#fragment'])assert.throws(()=>payload({...input,base_url}));
  assert.equal(payload({...input,base_url:'http://[::1]:8080/v1'}).base_url,'http://[::1]:8080/v1');
});
test('explicit save writes local settings, refreshes fingerprint, clears typed key and never tests',async()=>{
  const calls=[];let current=settings();
  const connection=new Connection(async(path,options)=>{calls.push([path,options]);if(options?.method==='PUT'){current=settings({...options.body,api_key:undefined,connection_fingerprint:otherFingerprint});return current;}return current;});
  await connection.load();connection.setForm({...connection.form,model:'another-user-model',api_key:'synthetic-key'});
  assert.equal(connection.ready(),false);await connection.save();
  assert.deepEqual(calls.map(c=>c[0]),['/api/creator/ai/connection','/api/settings/ai','/api/creator/ai/connection']);
  assert.equal(calls[1][1].body.api_key,'synthetic-key');assert.equal(connection.form.api_key,'');
  assert.equal(connection.saved.connection_fingerprint,otherFingerprint);assert.equal(connection.tested,null);
});
test('failed save keeps typed edits for retry, but close clears key and stale requests cannot repopulate it',async()=>{
  const connection=new Connection(async(path,options)=>{if(options)throw new Error('Local storage is unavailable');return settings();});
  await connection.load();connection.setForm({...connection.form,api_key:'synthetic-retry-key'});await connection.save();
  assert.equal(connection.form.api_key,'synthetic-retry-key');assert.match(connection.message,/Local storage/);
  connection.close();assert.equal(connection.form.api_key,'');assert.equal(connection.loaded,false);
});
test('successful save followed by refresh failure cannot enable a test for old settings',async()=>{
  let reads=0;const connection=new Connection(async(path,options)=>{if(options)return {};if(++reads>1)throw new Error('Read failed');return settings();});
  await connection.load();connection.setForm({...connection.form,api_key:'synthetic-key'});await connection.save();
  assert.equal(connection.form.api_key,'');assert.equal(connection.loaded,false);assert.equal(connection.ready(),false);
  assert.match(connection.message,/change was saved.*Reload/);
});
test('only the explicitly reviewed fingerprint is posted; no prompt/project/history payload is accepted',async()=>{
  const calls=[];const connection=new Connection(async(path,options)=>{calls.push([path,options]);return options?{ok:true,connection_fingerprint:fingerprint}:settings();});
  await connection.load();const review=connection.review();
  assert.equal(review.endpoint,'https://api.openai.com/v1/chat/completions');assert.equal(review.prompt,TEST_PROMPT);
  assert.equal(TEST_PROMPT,'Connection test only. Reply with OK.');assert.equal(calls.length,1);
  await connection.test(review);
  assert.deepEqual(calls[1],['/api/creator/ai/test',{method:'POST',body:{confirmed:true,expected_connection_fingerprint:fingerprint}}]);
  assert.equal(connection.tested,fingerprint);assert.match(connection.status(),/test passed in this session/);
});
test('editing after review blocks the request and editing during a test invalidates its result',async()=>{
  let posts=0,finish;const connection=new Connection(async(path,options)=>{if(options){posts++;return new Promise(resolve=>finish=resolve);}return settings();});
  await connection.load();const oldReview=connection.review();connection.setForm({...connection.form,model:'Changed'});
  await assert.rejects(connection.test(oldReview),/connection changed/);assert.equal(posts,0);
  await connection.load();const pending=connection.test(connection.review());
  connection.setForm({...connection.form,model:'Changed while waiting'});finish({ok:true,connection_fingerprint:fingerprint});await pending;
  assert.equal(connection.tested,null);assert.match(connection.message,/does not apply/);
});
test('another connection fingerprint or a safe provider failure never produces success',async()=>{
  let fail=false;const connection=new Connection(async(path,options)=>{if(!options)return settings();if(fail)throw new Error('The provider rejected this model.');return {ok:true,connection_fingerprint:otherFingerprint};});
  await connection.load();await connection.test(connection.review());assert.equal(connection.tested,null);
  fail=true;await connection.test(connection.review());assert.equal(connection.tested,null);assert.match(connection.message,/rejected this model/);
  assert.equal(connection.failed,fingerprint);assert.equal(connection.status(),'Last connection test failed. Review the error below and retry.');
  connection.setForm({...connection.form,model:'A corrected model'});assert.equal(connection.failed,null);assert.match(connection.status(),/Unsaved connection changes/);
  await connection.load();assert.equal(connection.failed,null);assert.match(connection.status(),/has not been tested/);
});
test('closing and reopening ignores an older settings response',async()=>{
  const pending=[];const connection=new Connection(()=>new Promise(resolve=>pending.push(resolve)));
  const first=connection.load();connection.close();const second=connection.load();
  pending[1](settings({model:'New opening',connection_fingerprint:otherFingerprint}));await second;
  pending[0](settings({model:'Old opening'}));await first;
  assert.equal(connection.form.model,'New opening');assert.equal(connection.saved.connection_fingerprint,otherFingerprint);
});
test('disconnected, incomplete and unsupported custom configurations cannot be tested',async()=>{
  for(const config of [settings({enabled:false,ready:false}),settings({ready:false,api_key_configured:false}),settings({provider:'custom',ready:true})]){
    const connection=new Connection(async()=>config);await connection.load();assert.equal(connection.ready(),false);assert.throws(()=>connection.review(),/Save a ready connection/);
  }
  const local=new Connection(async()=>settings({base_url:'http://localhost:8000/v1',endpoint:'http://localhost:8000/v1/chat/completions',api_key_configured:false,authentication:'none_local'}));
  await local.load();assert.equal(local.ready(),true);
});
test('forgetting a saved key is explicit and refreshes disconnected state',async()=>{
  const calls=[];let forgotten=false;
  const connection=new Connection(async(path,options)=>{calls.push([path,options]);if(options?.method==='DELETE')forgotten=true;return settings(forgotten?{api_key_configured:false,ready:false}:{});});
  await connection.load();assert.equal(calls.length,1);await connection.forget();
  assert.equal(calls[1][0],'/api/settings/ai/key');assert.equal(calls[1][1].method,'DELETE');assert.equal(connection.saved.api_key_configured,false);assert.equal(connection.ready(),false);
});

// Narrow DOM fixture checks actual button wiring. No browser or provider calls.
class Node {
  constructor(){this.value='';this.checked=false;this.disabled=false;this.hidden=false;this.open=false;this.listeners={};}
  addEventListener(type,handler){(this.listeners[type]??=[]).push(handler);}
  dispatch(type){for(const handler of this.listeners[type]||[])handler({target:this});}
  showModal(){this.open=true;}close(){this.open=false;this.dispatch('close');}focus(){}
}
function mounted(request){
  const nodes=new Map([['aiSetupBtn',new Node()],['settingsAiBtn',new Node()]]);
  const doc={body:{insertAdjacentHTML(_where,html){for(const match of html.matchAll(/id="([^"]+)"/g))nodes.set(match[1],new Node());}},getElementById:id=>nodes.get(id)};
  const instance=mount({document:doc,request});return {...instance,node:id=>nodes.get(id)};
}
test('mounted modal replaces both navigation buttons and opening never sends a provider request',async()=>{
  const calls=[];const ui=mounted(async(...args)=>{calls.push(args);return settings();});
  assert.equal(calls.length,0);await ui.node('settingsAiBtn').onclick();
  assert.equal(ui.node('creatorAiConnection').open,true);assert.deepEqual(calls,[['/api/creator/ai/connection']]);
  assert.equal(ui.node('creatorAiReview').disabled,false);assert.equal(ui.node('creatorAiKey').value,'');
  ui.node('creatorAiKey').value='synthetic-key';ui.node('creatorAiKey').dispatch('input');assert.equal(ui.node('creatorAiReview').disabled,true);
  ui.node('creatorAiClose').onclick();assert.equal(ui.node('creatorAiKey').value,'');assert.equal(ui.node('creatorAiConnection').open,false);
});
test('mounted test review shows exact destination and makes no call until Send this test',async()=>{
  const calls=[];const ui=mounted(async(path,options)=>{calls.push([path,options]);return options?{ok:true,connection_fingerprint:fingerprint}:settings();});
  await ui.open();ui.node('creatorAiReview').onclick();
  assert.equal(ui.node('creatorAiTestReview').hidden,false);assert.equal(ui.node('creatorAiDestination').textContent,'https://api.openai.com/v1/chat/completions');assert.equal(calls.length,1);
  await ui.node('creatorAiSendTest').onclick();assert.equal(calls.length,2);assert.equal(calls[1][0],'/api/creator/ai/test');
  assert.match(ui.node('creatorAiMessage').textContent,/succeeded/);
});
test('mounted provider changes clear typed key and model without saving or contacting the provider',async()=>{
  const calls=[];const ui=mounted(async(...args)=>{calls.push(args);return settings();});await ui.open();
  ui.node('creatorAiKey').value='synthetic-key';ui.node('creatorAiKey').dispatch('input');
  ui.node('creatorAiPreset').value='anthropic';ui.node('creatorAiPreset').dispatch('change');
  assert.equal(ui.node('creatorAiAddress').value,'https://api.anthropic.com/v1');assert.equal(ui.node('creatorAiKey').value,'');assert.equal(ui.node('creatorAiModel').value,'');
  assert.equal(calls.length,1);assert.equal(ui.node('creatorAiReview').disabled,true);assert.match(ui.node('creatorAiKeyNote').textContent,/clears the old saved key/);
});
