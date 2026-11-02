/* Pure calculations shared by the dashboard and its regression checks. */
(function(root){
 'use strict';
 function downloadGrowth(rows,days,project='all',now=Date.now()){
  const end=new Date(now).toISOString().slice(0,10);
  const start=new Date(Date.parse(end+'T00:00:00Z')-(days-1)*86400000).toISOString().slice(0,10);
  const previous=new Map(),totals=new Map();let comparisons=0,resets=0,gaps=0;
  for(const row of [...rows].sort((a,b)=>a.date.localeCompare(b.date))){
   if(project!=='all'&&row.project!==project)continue;
   const key=JSON.stringify([row.project,row.release_tag,row.asset]),old=previous.get(key);
   const total=Number(row.total);if(!Number.isFinite(total)||total<0)continue;
   if(row.date>=start&&row.date<=end&&old&&old.date>=start&&old.date<row.date){
    if(total>=old.total){
     totals.set(row.date,(totals.get(row.date)||0)+total-old.total);comparisons++;
     if(Date.parse(row.date)-Date.parse(old.date)>86400000)gaps++;
    }else resets++;
   }
   previous.set(key,{date:row.date,total});
  }
  return {total:comparisons?[...totals.values()].reduce((a,b)=>a+b,0):null,comparisons,resets,gaps,
   dates:Array.from({length:days},(_,i)=>{const date=new Date(Date.parse(start+'T00:00:00Z')+i*86400000).toISOString().slice(0,10);return {date,value:totals.has(date)?totals.get(date):null};})};
 }
 function localDay(value=Date.now(),timeZone){
  const date=new Date(value);if(!Number.isFinite(date.getTime()))return '';
  if(timeZone){const parts=new Intl.DateTimeFormat('en-US',{timeZone,year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(date);return ['year','month','day'].map(type=>parts.find(p=>p.type===type).value).join('-');}
  return `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`;
 }
 function goalDays(goals,now=Date.now(),timeZone){
  const day=localDay(now,timeZone),active=[],today=[],history=[];
  for(const goal of goals){if(goal.state!=='done')active.push(goal);else if(goal.completed_at&&localDay(goal.completed_at,timeZone)===day)today.push(goal);else history.push(goal);}
  const recent=(a,b)=>String(b.completed_at||'').localeCompare(String(a.completed_at||''));
  return {day,active,today:today.sort(recent),history:history.sort(recent)};
 }
 const api={downloadGrowth,localDay,goalDays};
 if(typeof module!=='undefined')module.exports=api;else root.MeridianMetrics=api;
})(typeof globalThis!=='undefined'?globalThis:this);
