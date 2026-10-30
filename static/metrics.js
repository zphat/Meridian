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
 const api={downloadGrowth};
 if(typeof module!=='undefined')module.exports=api;else root.MeridianMetrics=api;
})(typeof globalThis!=='undefined'?globalThis:this);
