/* Presentation of exact compiler counts; this does not infer choreography. */
(function(root){
  'use strict';
  function number(value){const p=String(value).split('/');return Number(p[0])/(p.length===2?Number(p[1]):1);}
  function label(value){
    const n=number(value);if(!Number.isFinite(n))return '?';
    if(n<0)return 'pickup '+Math.abs(n);
    const whole=Math.floor(n),part=n-whole;
    for(const [fraction,suffix]of [[0,''],[.25,'e'],[.5,'&'],[.75,'a']])if(Math.abs(part-fraction)<1e-8)return String(whole+1)+suffix;
    for(const [fraction,suffix]of [[1/3,'1/3'],[2/3,'2/3']])if(Math.abs(part-fraction)<1e-8)return String(whole+1)+'+'+suffix;
    return String(whole+1)+'+'+String(Math.round(part*10000)/10000);
  }
  function practice(position,eventStart,group=8){
    const pos=Math.max(0,number(position)),start=number(eventStart),size=number(group)||8;
    return Math.floor(pos)===Math.floor(start)?label(((start%size)+size)%size):String(Math.floor(pos%size)+1);
  }
  function facing(value){
    if(value===null||value===undefined||!Number.isFinite(number(value)))return 'Facing needs review';
    const angle=((number(value)%360)+360)%360,minutes=Math.round(angle*2)%720;
    return `Facing ${Math.floor(minutes/60)||12}:${String(minutes%60).padStart(2,'0')} (${angle}°)`;
  }
  function endingFreeFoot(moves,initial){
    let free=['R','L'].includes(initial)?initial:null;
    for(const move of moves){
      if(Array.isArray(move.events)&&move.events.length){
        for(const event of move.events){
          if(event.support_after==='same')continue;
          free={R:'L',L:'R'}[event.support_after]||null;
        }
      }else if(move.end!=='SAME')free=['R','L'].includes(move.end)?move.end:null;
    }
    return free;
  }
  const api={number,label,practice,facing,endingFreeFoot};
  if(typeof module==='object'&&module.exports)module.exports=api;
  else root.MoveTiming=api;
})(typeof globalThis!=='undefined'?globalThis:this);
