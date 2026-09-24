/* Optional BYO connection settings. All requests go to the local app server. */
(function(root,factory){
  const exported=factory();
  if(typeof module==='object'&&module.exports)module.exports=exported;
  else{root.LineDanceAIConnection=exported;exported.mount({document:root.document,request:(path,options)=>root.api(path,options)});}
})(typeof globalThis!=='undefined'?globalThis:this,function(){
  'use strict';
  const TEST_PROMPT='Connection test only. Reply with OK.';
  const PRESETS={
    openai:{label:'OpenAI',provider:'openai_compatible',base_url:'https://api.openai.com/v1'},
    anthropic:{label:'Anthropic',provider:'anthropic_messages',base_url:'https://api.anthropic.com/v1'},
    compatible:{label:'Other OpenAI-compatible provider / local model',provider:'openai_compatible',base_url:''},
    custom:{label:'Custom connection (adapter not available)',provider:'custom',base_url:''}
  };
  const blank=()=>({enabled:false,provider:'openai_compatible',base_url:'',model:'',timeout_seconds:60,api_key:''});
  function fields(value){return {enabled:!!value.enabled,provider:String(value.provider||'openai_compatible'),base_url:String(value.base_url||'').trim().replace(/\/+$/,''),model:String(value.model||'').trim(),timeout_seconds:Number(value.timeout_seconds)};}
  function presetFor(value){
    if(value.provider==='custom')return 'custom';
    if(value.provider==='anthropic_messages')return 'anthropic';
    return fields(value).base_url==='https://api.openai.com/v1'?'openai':'compatible';
  }
  function payload(form){
    const result=fields(form);
    if(!['openai_compatible','anthropic_messages','custom'].includes(result.provider))throw new Error('Choose a supported connection type.');
    if(result.model.length>160)throw new Error('Keep the model name under 160 characters.');
    if(!Number.isInteger(result.timeout_seconds)||result.timeout_seconds<5||result.timeout_seconds>180)throw new Error('Use a whole-number timeout from 5 to 180 seconds.');
    if(result.base_url){
      let url;try{url=new URL(result.base_url);}catch{throw new Error('Enter a full API address, beginning with https://.');}
      if(!['http:','https:'].includes(url.protocol)||url.username||url.password||url.search||url.hash)throw new Error('Use an HTTP or HTTPS API address without credentials, query parameters or fragments.');
      if(url.protocol==='http:'&&!['localhost','127.0.0.1','[::1]'].includes(url.hostname))throw new Error('Use HTTPS except for a model running on this computer.');
    }
    const key=String(form.api_key||'').trim();if(key)result.api_key=key;
    return result;
  }
  class Connection {
    constructor(request,onChange=()=>{}){this.request=request;this.onChange=onChange;this.session=0;this.version=0;this.saved=null;this.form=blank();this.loaded=false;this.busy=false;this.message='';this.tested=null;this.failed=null;}
    emit(){this.onChange();}
    dirty(){return !!String(this.form.api_key||'').trim()||!this.saved||JSON.stringify(fields(this.form))!==JSON.stringify(fields(this.saved));}
    setForm(form){this.form={...blank(),...form};this.version++;this.tested=null;this.failed=null;this.message='Connection edits are not saved. Saving does not contact your provider.';this.emit();}
    adopt(info){
      if(!info||typeof info.connection_fingerprint!=='string'||!/^[a-f0-9]{64}$/.test(info.connection_fingerprint))throw new Error('The saved connection could not be identified. Reload settings before testing.');
      this.saved={...fields(info),api_key_configured:!!info.api_key_configured,configured:!!info.configured,ready:!!info.ready,authentication:info.authentication,endpoint:String(info.endpoint||''),connection_fingerprint:info.connection_fingerprint};
      this.form={...fields(this.saved),api_key:''};this.loaded=true;this.version++;this.tested=null;this.failed=null;
    }
    ready(){return this.loaded&&!this.busy&&!this.dirty()&&this.saved.ready&&this.saved.provider!=='custom'&&!!this.saved.endpoint;}
    status(){
      if(!this.loaded)return 'Saved settings have not loaded.';
      if(this.dirty())return 'Unsaved connection changes — save before testing.';
      if(!this.saved.enabled)return 'AI is off. All normal dance tools remain available.';
      if(this.saved.provider==='custom')return 'Saved for later. This connection needs an adapter and cannot be tested or used by the assistant yet.';
      if(!this.saved.ready)return 'Setup is incomplete. Enter an API address, model name and the required key, then save.';
      if(this.failed===this.saved.connection_fingerprint)return 'Last connection test failed. Review the error below and retry.';
      return this.tested===this.saved.connection_fingerprint?'Connection test passed in this session. This does not validate any choreography.':'Connection saved and ready to test. It has not been tested in this session.';
    }
    async load(){
      const session=++this.session;this.busy=true;this.loaded=false;this.form.api_key='';this.message='Loading saved connection…';this.emit();
      try{const info=await this.request('/api/creator/ai/connection');if(session!==this.session)return;this.adopt(info);this.message='Settings loaded locally. No provider request was made.';}
      catch(error){if(session===this.session)this.message=error.message;}
      finally{if(session===this.session){this.busy=false;this.emit();}}
    }
    async mutate(method,path,body){
      if(!this.loaded||this.busy)throw new Error('Wait for the saved connection to load.');
      const session=this.session;this.busy=true;this.tested=null;this.failed=null;this.message=method==='DELETE'?'Forgetting the saved key…':'Saving connection locally…';this.emit();
      let saved=false;
      try{
        await this.request(path,{method,...(body?{body}:{})});saved=true;
        if(session!==this.session)return;
        this.form.api_key='';
        const info=await this.request('/api/creator/ai/connection');if(session!==this.session)return;
        this.adopt(info);this.message=method==='DELETE'?'Saved key forgotten. No provider request was made.':'Connection saved locally. No provider request was made.';
      }catch(error){if(session===this.session){if(saved)this.loaded=false;this.message=(saved?'The change was saved, but settings could not be refreshed. Reload before continuing. ':'')+error.message;}}
      finally{if(session===this.session){this.busy=false;this.emit();}}
    }
    save(){return this.mutate('PUT','/api/settings/ai',payload(this.form));}
    forget(){if(this.dirty())throw new Error('Save or discard your connection edits before forgetting the saved key.');if(!this.saved?.api_key_configured)throw new Error('There is no saved key to forget.');return this.mutate('DELETE','/api/settings/ai/key');}
    review(){if(!this.ready())throw new Error('Save a ready connection before testing.');return {session:this.session,version:this.version,fingerprint:this.saved.connection_fingerprint,endpoint:this.saved.endpoint,prompt:TEST_PROMPT};}
    async test(review){
      if(!this.ready()||!review||review.session!==this.session||review.version!==this.version||review.fingerprint!==this.saved.connection_fingerprint)throw new Error('The connection changed. Review the saved test destination again.');
      const session=this.session;this.busy=true;this.failed=null;this.message='Sending the small connection test…';this.emit();
      try{
        const result=await this.request('/api/creator/ai/test',{method:'POST',body:{confirmed:true,expected_connection_fingerprint:review.fingerprint}});
        if(session!==this.session)return;
        if(this.version!==review.version||this.dirty()||result.connection_fingerprint!==this.saved.connection_fingerprint){this.message='The connection changed. This test result does not apply to the current settings.';return;}
        if(result.ok!==true)throw new Error('The connection test did not succeed. Review the saved settings.');
        this.tested=review.fingerprint;this.failed=null;this.message='Connection test succeeded. No project data was sent.';
      }catch(error){if(session===this.session){this.tested=null;this.failed=this.version===review.version&&!this.dirty()&&this.saved.connection_fingerprint===review.fingerprint?review.fingerprint:null;this.message=this.failed?error.message:'The connection changed. This test result does not apply to the current settings.';}}
      finally{if(session===this.session){this.busy=false;this.emit();}}
    }
    close(){this.session++;this.version++;this.form.api_key='';this.saved=null;this.loaded=false;this.busy=false;this.tested=null;this.failed=null;this.emit();}
  }
  function mount({document:doc,request}){
    if(!doc||typeof request!=='function')return null;
    const byId=id=>doc.getElementById(id);
    doc.body.insertAdjacentHTML('beforeend',`<dialog id="creatorAiConnection" class="ai-connection-dialog" aria-labelledby="creatorAiTitle"><form id="creatorAiForm"><div class="ai-connection-heading"><div><span class="eyebrow">YOUR OPTIONAL CONNECTION</span><h2 id="creatorAiTitle">Bring your own AI.</h2></div><button id="creatorAiClose" type="button">Close</button></div><p>Use your own provider account and pay any provider charges directly. AI is optional; your dance editor, local music tools, practice and exports work without it.</p><fieldset id="creatorAiFields"><legend>Connection settings</legend><label class="check-label"><input id="creatorAiEnabled" type="checkbox"> Enable this AI connection</label><label>Provider preset<select id="creatorAiPreset">${Object.entries(PRESETS).map(([key,value])=>`<option value="${key}">${value.label}</option>`).join('')}</select></label><p id="creatorAiPresetHelp"></p><label>API address<input id="creatorAiAddress" type="url" autocomplete="off" spellcheck="false" placeholder="https://api.example.com/v1"></label><label>Model name<input id="creatorAiModel" maxlength="160" autocomplete="off" spellcheck="false" placeholder="Enter a model available on your account"></label><div class="ai-connection-grid"><label>API key<input id="creatorAiKey" type="password" autocomplete="new-password" spellcheck="false" placeholder="Enter a key, or leave blank to keep the saved key"></label><label>Timeout (seconds)<input id="creatorAiTimeout" type="number" min="5" max="180" step="1" value="60"></label></div><p id="creatorAiKeyNote"></p></fieldset><p class="ai-connection-state" id="creatorAiState" role="status" aria-live="polite"></p><p id="creatorAiMessage" role="status" aria-live="polite"></p><div class="actions"><button id="creatorAiSave" class="primary">Save connection</button><button id="creatorAiReview" type="button">Review connection test</button><button id="creatorAiForget" type="button">Forget saved key</button><button id="creatorAiReload" type="button">Reload saved settings</button></div></form><section id="creatorAiTestReview" class="ai-connection-review" hidden aria-labelledby="creatorAiTestTitle"><h3 id="creatorAiTestTitle">Review this test</h3><p>Your saved connection will receive one small request. Your provider may charge your account.</p><dl><dt>Exact destination</dt><dd id="creatorAiDestination"></dd><dt>Only message sent</dt><dd><code>Connection test only. Reply with OK.</code></dd></dl><p>No song, audio, lyrics, project summary, conversation history or system prompt is sent. Authentication uses the saved key when your connection requires one.</p><div class="actions"><button id="creatorAiSendTest" type="button" class="primary">Send this test</button><button id="creatorAiCancelTest" type="button">Cancel test</button></div></section><section id="creatorAiForgetReview" class="ai-connection-review" hidden><h3>Forget this saved key?</h3><p>The app will remove its local key. This does not cancel your provider account or revoke a key at the provider.</p><div class="actions"><button id="creatorAiConfirmForget" type="button">Forget key now</button><button id="creatorAiCancelForget" type="button">Keep key</button></div></section><details class="ai-connection-help"><summary>What the assistant can receive</summary><p>To use Ask AI, switch to Advanced, open Creator Studio, then choose Generate &amp; follow lyrics.</p><p>A later Ask AI request can send your typed prompt, recent conversation messages, and a project summary if you choose to include it. Audio files are not sent automatically. Review the assistant’s context choice before sending.</p><p>Keys are protected for your Windows account and excluded from dance projects, backups and exports. Connecting here does not install a local model or include shared AI credits. BootStepper search uses a separate personal key in the Advanced drawer. It is not sent to this AI provider.</p></details><div class="ai-connection-links"><a href="https://developers.openai.com/api/reference/overview" target="_blank" rel="noopener noreferrer">OpenAI API help ↗</a><a href="https://platform.claude.com/docs/en/api/overview" target="_blank" rel="noopener noreferrer">Anthropic API help ↗</a></div></dialog>`);
    const dialog=byId('creatorAiConnection');let review=null,renderedSession=-1,renderedVersion=-1;
    const connection=new Connection(request,render);
    const inputs=['creatorAiEnabled','creatorAiPreset','creatorAiAddress','creatorAiModel','creatorAiKey','creatorAiTimeout'];
    function formValue(){return {enabled:byId('creatorAiEnabled').checked,provider:PRESETS[byId('creatorAiPreset').value].provider,base_url:byId('creatorAiAddress').value,model:byId('creatorAiModel').value,api_key:byId('creatorAiKey').value,timeout_seconds:byId('creatorAiTimeout').value};}
    function hideReviews(){review=null;byId('creatorAiTestReview').hidden=true;byId('creatorAiForgetReview').hidden=true;}
    function render(){
      const state=connection;
      if(renderedSession!==state.session||renderedVersion!==state.version){
        const values=state.form;byId('creatorAiEnabled').checked=values.enabled;
        byId('creatorAiPreset').value=presetFor(values);byId('creatorAiAddress').value=values.base_url;
        byId('creatorAiModel').value=values.model;byId('creatorAiKey').value=values.api_key;byId('creatorAiTimeout').value=values.timeout_seconds;
        renderedSession=state.session;renderedVersion=state.version;
      }
      byId('creatorAiFields').disabled=!state.loaded||state.busy;
      byId('creatorAiSave').disabled=!state.loaded||state.busy;
      byId('creatorAiReview').disabled=!state.ready();
      byId('creatorAiForget').disabled=!state.loaded||state.busy||state.dirty()||!state.saved?.api_key_configured;
      byId('creatorAiReload').disabled=state.busy;
      byId('creatorAiReload').textContent=state.loaded&&state.dirty()?'Discard connection edits and reload':'Reload saved settings';
      byId('creatorAiClose').textContent=state.loaded&&state.dirty()?'Close without saving':'Close';
      byId('creatorAiSendTest').disabled=state.busy||!state.ready();byId('creatorAiCancelTest').disabled=state.busy;
      byId('creatorAiConfirmForget').disabled=byId('creatorAiCancelForget').disabled=state.busy;
      byId('creatorAiState').textContent=state.status();byId('creatorAiMessage').textContent=state.message;
      const changedTarget=state.saved&&(fields(state.form).provider!==state.saved.provider||fields(state.form).base_url!==state.saved.base_url);
      byId('creatorAiKeyNote').textContent=changedTarget?'Changing the provider or API address clears the old saved key when you save. Enter the key for this destination.':state.saved?.authentication==='none_local'?'This local OpenAI-compatible connection does not require a key.':state.saved?.api_key_configured?'A key is saved securely. Leave this field blank to keep it for the same provider and address.':'No key is saved. Enter your provider’s key. A compatible local model may allow no key.';
      byId('creatorAiPresetHelp').textContent=state.form.provider==='custom'?'Custom settings can be saved, but an adapter is not available. This option cannot run the assistant or a connection test.':'Presets fill in the API address. Enter your own model name; available models depend on your account. A ChatGPT or Claude app subscription does not by itself configure an API connection here.';
    }
    function edit(){hideReviews();connection.setForm(formValue());}
    for(const id of inputs)byId(id).addEventListener(id==='creatorAiPreset'||id==='creatorAiEnabled'?'change':'input',()=>{
      if(id==='creatorAiPreset'){
        const preset=PRESETS[byId(id).value];byId('creatorAiAddress').value=preset.base_url;byId('creatorAiModel').value='';byId('creatorAiKey').value='';
      }else if(id==='creatorAiAddress')byId('creatorAiKey').value='';
      edit();
    });
    byId('creatorAiForm').onsubmit=async event=>{event.preventDefault();hideReviews();try{await connection.save();}catch(error){connection.message=error.message;render();}};
    byId('creatorAiReload').onclick=()=>{hideReviews();connection.load();};
    byId('creatorAiReview').onclick=()=>{try{review=connection.review();byId('creatorAiDestination').textContent=review.endpoint;byId('creatorAiTestReview').hidden=false;byId('creatorAiForgetReview').hidden=true;byId('creatorAiSendTest').focus();}catch(error){connection.message=error.message;render();}};
    byId('creatorAiCancelTest').onclick=hideReviews;
    byId('creatorAiSendTest').onclick=async()=>{try{await connection.test(review);}catch(error){connection.message=error.message;}hideReviews();render();};
    byId('creatorAiForget').onclick=()=>{hideReviews();byId('creatorAiForgetReview').hidden=false;byId('creatorAiConfirmForget').focus();};
    byId('creatorAiCancelForget').onclick=hideReviews;
    byId('creatorAiConfirmForget').onclick=async()=>{try{await connection.forget();}catch(error){connection.message=error.message;}hideReviews();render();};
    byId('creatorAiClose').onclick=()=>dialog.close();
    dialog.addEventListener('close',()=>{hideReviews();connection.close();byId('creatorAiKey').value='';});
    function open(){hideReviews();if(!dialog.open)dialog.showModal();return connection.load();}
    for(const id of ['aiSetupBtn','settingsAiBtn'])if(byId(id))byId(id).onclick=open;
    render();return {open,connection};
  }
  return {Connection,PRESETS,TEST_PROMPT,fields,payload,presetFor,mount};
});
