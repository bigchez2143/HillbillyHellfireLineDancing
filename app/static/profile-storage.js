/* Isolate browser drafts and preferences when a restored profile reuses project IDs. */
(function(root){
  'use strict';
  function create(storage,profile){
    if(!profile||typeof profile.profile_id!=='string'||!/^[a-zA-Z0-9_-]{1,100}$/.test(profile.profile_id))throw new Error('The application profile could not be identified.');
    const key=name=>'ldc.profile.'+profile.profile_id+'.'+name;
    function get(name){
      let value=storage.getItem(key(name));
      if(value===null&&profile.can_migrate_legacy_browser_state){
        const old='ldc.'+name;value=storage.getItem(old);
        if(value!==null){storage.setItem(key(name),value);storage.removeItem(old);}
      }
      if(value===null&&Object.prototype.hasOwnProperty.call(profile.browser_preferences||{},name)){
        const saved=profile.browser_preferences[name];value=typeof saved==='string'?saved:JSON.stringify(saved);storage.setItem(key(name),value);
      }
      return value;
    }
    return {key,get,set:(name,value)=>storage.setItem(key(name),value),remove:name=>storage.removeItem(key(name))};
  }
  const api={create};if(typeof module==='object'&&module.exports)module.exports=api;else root.LineDanceProfileStorage=api;
})(typeof globalThis!=='undefined'?globalThis:this);
