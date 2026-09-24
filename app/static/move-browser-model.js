/* Pure indexing/filtering for the library and compact editor picker. */
(function(root){
  'use strict';
  const levels={AB:'Absolute Beginner',B:'Beginner',I:'Improver',INT:'Intermediate',A:'Advanced'};
  function level(value){return levels[value]||value||'Unspecified';}
  function familyLabel(value){
    const labels={jazzbox:'Jazz box',steptouch:'Step touch',toestrut:'Toe strut',sidetogether:'Side together',walkback:'Walk back',kbc:'Kick-ball-change',crossrock:'Cross rock',crossshuffle:'Cross shuffle',backlock:'Back locking step',heelgrind:'Heel grind',fullturn:'Full turn',rollingvine:'Rolling vine',point_side:'Side point',stomp_weighted:'Stomp with weight'};
    const text=labels[value]||String(value||'Other').replaceAll('_',' ').replaceAll('-',' ');
    return text.charAt(0).toUpperCase()+text.slice(1);
  }
  const quantity=(value,singular,plural=singular+'s')=>`${value} ${value===1?singular:plural}`;
  function durationLabel(value){
    if(value===null||value===undefined)return 'Counts not set';
    const parsed=count(value);
    return `${value} ${parsed&&parsed.n===parsed.d?'count':'counts'}`;
  }
  const isPersonal=row=>row.kind==='user'||row.kind==='legacy';
  function index(builtins,personal,references,lead='R'){
    const rows=builtins.filter(m=>m.lead===lead).map(m=>({
      // Keep the existing core:* favorite key for legacy custom definitions.
      // Their ownership label is independent from that persistence namespace.
      key:(m.definition_hash?'expansion:':'core:')+m.move_id,
      kind:m.definition_hash?'expansion':String(m.move_id).startsWith('custom-')?'legacy':'core',
      name:m.name,aliases:m.aliases||[],level:level(m.level),family:m.group||m.family||'Other',data:m
    }));
    for(const m of personal)rows.push({key:'user:'+m.id,kind:'user',name:m.name,aliases:m.aliases||[],level:level(m.difficulty),family:'Personal moves',deleted:!!m.deleted,data:m});
    references.forEach((m,i)=>rows.push({key:'reference:'+(m.id||'reference-'+i),kind:'reference',name:m.name,aliases:m.aliases||[],level:level(m.level),family:(m.category||'Glossary').replaceAll('_',' '),data:{...m,referenceId:m.id||'reference-'+i}}));
    return rows;
  }
  function filter(rows,{query='',tab='moves',difficulty='all',family='all',favoritesOnly=false,favorites=[],archived=false}={}){
    const q=query.trim().toLocaleLowerCase(),stars=new Set(favorites);
    return rows.filter(r=>(tab==='glossary'?r.kind==='reference':tab==='personal'?isPersonal(r):r.kind!=='reference')&&(!r.deleted||archived)&&(difficulty==='all'||r.level===level(difficulty))&&(family==='all'||r.family===family)&&(!favoritesOnly||stars.has(r.key))&&`${r.name} ${r.aliases.join(' ')} ${r.family} ${familyLabel(r.family)}`.toLocaleLowerCase().includes(q)).sort((a,b)=>a.name.localeCompare(b.name)||a.key.localeCompare(b.key));
  }
  function rational(n,d=1n){if(!d)throw new Error('Invalid count');let a=n,b=d;while(b)[a,b]=[b,a%b];return {n:n/a,d:d/a};}
  function count(value){
    if(value===null||value===undefined)return null;
    const s=String(value).trim();if(s.length>80)return null;
    const f=s.match(/^(\d+)\s*\/\s*(\d+)$/),d=s.match(/^(\d*)(?:\.(\d+))?$/);
    try{
      if(f)return rational(BigInt(f[1]),BigInt(f[2]));
      if(d&&(d[1]||d[2]))return rational(BigInt((d[1]||'0')+(d[2]||'')),10n**BigInt((d[2]||'').length));
    }catch{}return null;
  }
  const plus=(a,b)=>a&&b?rational(a.n*b.d+b.n*a.d,a.d*b.d):null;
  const exact=f=>f?(f.d===1n?String(f.n):`${f.n}/${f.d}`):null;
  function countLabel(offset){
    if(!offset)return 'Unspecified';
    const whole=offset.n/offset.d,remainder=offset.n%offset.d;
    if(!remainder)return String(whole+1n);
    const suffix=remainder*4n===offset.d?'e':remainder*2n===offset.d?'&':remainder*4n===offset.d*3n?'a':null;
    return suffix?`${whole+1n}${suffix}`:`${whole+1n}+${exact(rational(remainder,offset.d))}`;
  }
  function previewRows(move){
    const explicit=Array.isArray(move.events)&&move.events.length>0;
    const rows=explicit?move.events:move.lines||[];let cursor=rational(0n);
    return rows.map(row=>{
      const start=explicit&&Object.prototype.hasOwnProperty.call(row,'offset_counts')?count(row.offset_counts):cursor;
      const duration=count(explicit?row.duration_counts:row.beats);
      let label=countLabel(start);
      if(!explicit&&start&&duration&&start.d===1n&&duration.d===1n&&duration.n>1n){
        label=row.sync&&duration.n===2n?`${start.n+1n}&${start.n+2n}`:`${start.n+1n}–${start.n+duration.n}${row.sync?' (syncopated)':''}`;
      }
      cursor=plus(start,duration);
      return {row,label,offset_counts:exact(start),duration_counts:exact(duration)};
    });
  }
  function turn(value,advanced=false){
    if(value===null||value===undefined||value==='')return 'Not specified';
    const bits=String(value).split('/'),angle=Number(bits[0])/(bits.length===2?Number(bits[1]):1);
    if(!Number.isFinite(angle))return 'Not specified';
    if(advanced)return angle+'°';
    if(angle===0)return 'No turn';
    const amount={45:'⅛',90:'¼',135:'⅜',180:'½',225:'⅝',270:'¾',315:'⅞',360:'Full'}[Math.abs(angle)]||Math.abs(angle)+'°';
    return `${amount} turn ${angle<0?'left':'right'}`;
  }
  const api={index,filter,level,turn,isPersonal,previewRows,familyLabel,quantity,durationLabel};
  if(typeof module==='object'&&module.exports)module.exports=api;else root.MoveBrowserModel=api;
})(typeof globalThis!=='undefined'?globalThis:this);
