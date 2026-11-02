const {downloadGrowth}=require('../static/metrics.js');
const assert=require('node:assert/strict');
const row=(date,total,asset='app.exe',release_tag='v1')=>({date,total,asset,release_tag,project:'latitude'});
const now=Date.parse('2026-10-30T12:00:00Z');
let result=downloadGrowth([row('2026-10-28',100),row('2026-10-29',110),row('2026-10-30',115)],7,'all',now);
assert.equal(result.total,15);assert.equal(result.dates[0].value,null);
result=downloadGrowth([row('2026-10-29',100),row('2026-10-30',10,'app.exe','v2')],7,'all',now);
assert.equal(result.total,null,'new release baseline is not growth');
result=downloadGrowth([row('2026-10-29',100),row('2026-10-30',5)],7,'all',now);
assert.equal(result.total,null);assert.equal(result.resets,1);
result=downloadGrowth([row('2026-10-23',90),row('2026-10-30',110)],7,'all',now);
assert.equal(result.total,null,'increase spanning outside selected period is not attributed to it');
result=downloadGrowth([row('2026-10-25',10),row('2026-10-30',30)],7,'all',now);
assert.equal(result.total,20);assert.equal(result.gaps,1);
assert.equal(downloadGrowth([row('2026-10-29',2),row('2026-10-30',4)],7,'sundial',now).total,null);
console.log('Analytics calculation checks passed.');

const {goalDays,localDay}=require('../static/metrics.js');
const tz='America/Chicago';
const goals=[{id:1,state:'done',completed_at:'2026-11-01T05:01:00Z'},
 {id:2,state:'done',completed_at:'2026-11-02T01:00:00Z'},
 {id:3,state:'done',completed_at:'2026-11-01T04:59:00Z'},
 {id:4,state:'done',completed_at:null},{id:5,state:'doing'}];
// The fall-back day is 25 hours long; UTC midnight is still yesterday locally.
let days=goalDays(goals,Date.parse('2026-11-02T05:59:00Z'),tz);
assert.equal(days.day,'2026-11-01');assert.deepEqual(days.today.map(g=>g.id),[2,1]);
assert.deepEqual(days.history.map(g=>g.id),[3,4]);assert.equal(days.active.length,1);
days=goalDays(goals,Date.parse('2026-11-02T06:01:00Z'),tz);
assert.equal(days.today.length,0);assert.equal(days.history.length,4);
assert.equal(goals[0].state,'done','Day rollover must not mutate goal completion');
assert.equal(localDay('2026-11-01T20:00:00Z','Asia/Tokyo'),'2026-11-02');
console.log('Local-day goal history checks passed, including midnight, DST and undated legacy completions.');
