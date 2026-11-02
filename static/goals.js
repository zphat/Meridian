'use strict';
const goalCheckLabels={verified:'Verified',failed:'Still failing',blocked:'Unable to verify',manual:'Hands-on check',not_checked:'Not checked'};
const goalCheckTones={verified:'good',failed:'bad',blocked:'warn',manual:'dim',not_checked:'dim'};
let goalDialogReturn=null;
function goalCheckState(g){return g.check?.state||(g.rule?.kind==='manual'?'manual':'not_checked');}
function goalRuleLabel(g){
 const rule=g.rule||{kind:'manual'},p=project(g.project);
 if(rule.kind==='site')return 'Endpoint: '+(p?.sites.find(s=>s.url===rule.target)?.label||rule.target);
 if(rule.kind==='build')return 'Current-commit workflow: '+(gh(p).workflows?.find(r=>String(r.workflow_id)===rule.target)?.name||rule.target);
 if(rule.kind==='uptime')return 'Sync health + latest scheduled monitor';
 return 'Hands-on acceptance checklist';
}
function goalCard(g,actions=true){
 const report=model.verification_report||{},state=goalCheckState(g),checking=model.busy&&report.state==='running'&&(!report.goal_id||report.goal_id===g.id)&&(!report.project||report.project===g.project);
 return `<article class="work-row goal-row" data-goal-id="${g.id}"><button class="work-ring ${g.state==='done'?'done':''}" aria-label="${g.state==='done'?'Reopen goal':'Mark goal complete manually'}" title="${g.state==='done'?'Reopen':'Mark complete after your own test'}" data-goal-state="${g.id}" data-state="${g.state==='done'?'todo':'done'}">${ico('check','tickbox')}</button><div class="work-main"><button class="goal-title ${g.state==='done'?'done':''}" data-review-goal="${g.id}">${esc(g.title)}</button>${g.description?`<p class="goal-description">${esc(g.description)}</p>`:''}<div class="work-caption"><span>${esc(labels[g.project])}</span><span>${esc(g.category)}</span><span>${esc(g.priority)} priority</span>${g.state==='doing'?'<span>In progress</span>':''}</div><div class="goal-check-line">${pill(checking?'Checking…':goalCheckLabels[state],checking?'warn':goalCheckTones[state])}<span>${g.check?.checked_at?'Checked '+ago(g.check.checked_at):g.state==='done'?'Marked done manually':g.rule?.kind==='manual'?'See the acceptance checklist':'Ready for a live check'}</span></div>${g.check?`<p class="goal-check-summary">${esc(g.check.summary)}</p>`:''}${actions?`<div class="goal-actions"><button class="soft-button" data-prompt-project="${g.project}" data-prompt-goal="${g.id}">${ico('code')} Repair prompt</button><button class="soft-button" data-check-goal="${g.id}" ${model.busy?'disabled':''}>${ico('refresh')} ${checking?'Checking…':'Check again'}</button><button class="text-action" data-review-goal="${g.id}">Details & evidence</button><button class="text-action" data-edit-goal="${g.id}" aria-label="Edit ${esc(g.title)}">${ico('edit')} Edit</button></div>`:''}</div></article>`;
}
function verificationBanner(pid=null){
 const r=model.verification_report||{},checks=goals(pid).filter(g=>g.check),running=model.busy&&r.state==='running';
 if(r.state==='idle'&&!checks.length)return `<div class="verification-banner"><div>${ico('shield')}<div><strong>Work from evidence</strong><p>Open a repair prompt, make the fix, then check again. Verifiable goals complete automatically; device tests show exactly what to confirm.</p></div></div><button class="soft-button" data-check-project="${pid||''}" ${model.busy?'disabled':''}>${ico('refresh')} Check ${pid?'project':'all goals'}</button></div>`;
 const count=Object.fromEntries(['verified','failed','blocked','manual'].map(s=>[s,checks.filter(g=>g.check.state===s).length]));
 const latest=checks.map(g=>g.check.checked_at).sort().at(-1);
 return `<div class="verification-banner ${running?'checking':''}" role="status"><div>${ico(running?'refresh':'shield')}<div><strong>${running?'Refreshing evidence and checking goals…':r.state==='error'?'Checks could not finish':'Latest goal checks'}</strong><p>${running?'The results will update here automatically.':r.state==='error'?esc(r.summary):`${count.verified} verified · ${count.failed} still failing · ${count.blocked} unable to verify · ${count.manual} hands-on${latest?' · '+esc(ago(latest)):''}`}</p>${!running&&r.reopened?`<p>${r.reopened} previously verified goal${r.reopened===1?' was':'s were'} reopened after a failed check.</p>`:''}</div></div><button class="soft-button" data-check-project="${pid||''}" ${model.busy?'disabled':''}>${ico('refresh')} ${running?'Checking…':'Check again'}</button></div>`;
}
function goalEvidence(g){
 const state=goalCheckState(g);
 return `<div class="goal-evidence-box"><div class="panel-header"><strong>${esc(goalRuleLabel(g))}</strong>${pill(goalCheckLabels[state],goalCheckTones[state])}</div><p>${esc(g.check?.summary||(g.rule?.kind==='manual'?'This goal needs the hands-on checks below. Meridian will not mark it verified from unrelated build or endpoint results.':'Run Check again to collect fresh evidence for this goal.'))}</p>${g.check?.checked_at?`<p class="caption-line">Last checked ${esc(shortDate(g.check.checked_at))}${g.completed_at?' · Completed '+esc(shortDate(g.completed_at))+' ('+(g.completion_source==='verified'?'verified':'manual')+')':''}</p>`:''}${(g.check?.evidence||[]).map(e=>`<div class="goal-evidence-row">${pill(goalCheckLabels[e.state]||e.state,goalCheckTones[e.state]||'dim')}<div><strong>${esc(e.label)}</strong><p>${esc(e.detail)}</p>${e.commit?`<small>Commit ${esc(e.commit.slice(0,12))}</small>`:''}${e.url?`<a class="inline-link" href="${href(e.url)}" target="_blank" rel="noreferrer">Open evidence ${ico('external')}</a>`:''}</div></div>`).join('')}</div>`;
}
function closeGoalDialog(){
 document.querySelector('#goal-review-backdrop')?.remove();document.querySelector('#prompt-backdrop')?.remove();
 if(model)render();
 if(goalDialogReturn?.isConnected)goalDialogReturn.focus();else document.querySelector('#refresh-button')?.focus();
}
function showGoalReview(id){
 const g=model.goals.find(g=>g.id===id);if(!g)return;
 goalDialogReturn=document.activeElement;
 document.querySelector('#goal-review-backdrop')?.remove();
 const host=document.createElement('div');host.className='modal-backdrop';host.id='goal-review-backdrop';host.dataset.goalId=id;
 host.innerHTML=`<section class="modal goal-dialog" role="dialog" aria-modal="true" aria-labelledby="goal-review-title"><div class="modal-header"><div><span class="eyebrow">${esc(labels[g.project])} / GOAL</span><h2 id="goal-review-title">${esc(g.title)}</h2><p>${esc(g.description)}</p></div><button class="icon-btn" data-close-goal-dialog aria-label="Close goal details">${ico('close')}</button></div><div id="goal-evidence">${goalEvidence(g)}</div><h3>Suggested approach</h3><ol class="goal-plan">${(g.guidance?.approach||[]).map(t=>`<li>${esc(t)}</li>`).join('')}</ol><h3>What counts as finished</h3><ul class="goal-acceptance">${(g.guidance?.acceptance||[]).map(t=>`<li>${esc(t)}</li>`).join('')}</ul><div class="modal-footer goal-footer"><button class="soft-button" data-prompt-project="${g.project}" data-prompt-goal="${g.id}">${ico('code')} Repair prompt</button><button class="primary-button" data-check-goal="${g.id}" ${model.busy?'disabled':''}>${ico('refresh')} Check again</button><button class="text-action" data-goal-manual="${g.id}">${g.state==='done'?'Reopen goal':'I tested it — mark done'}</button></div></section>`;
 document.body.append(host);host.querySelector('button').focus();
}
function syncGoalDialog(){const host=document.querySelector('#goal-review-backdrop');if(!host)return;const g=model.goals.find(g=>g.id===Number(host.dataset.goalId));if(g)host.querySelector('#goal-evidence').innerHTML=goalEvidence(g);}
function makeRepairPrompt(pid,goalId=null,siteIndex=null){
 const p=project(pid);if(!p)return '';
 const data=gh(p),site=siteIndex===null?null:p.sites[Number(siteIndex)],task=goalId?model.goals.find(x=>x.id===goalId&&x.project===pid):site?null:recommendations(pid)[0];
 const plan=task?.guidance||(site?{approach:['Reproduce the failing request to '+site.url+' and record its HTTP status, response and timing.','Inspect DNS, HTTPS certificate coverage, routing, deployment status and the endpoint implementation; identify which layer fails.','Repair the cause while preserving authentication and the expected response contract.','Test the deployed endpoint and related navigation or health workflow, then repeat the probe from Meridian.'],acceptance:['The exact endpoint returns the expected successful status and content.','The deployed fix is verified with timestamped request and workflow evidence.']}:{approach:['Reproduce the current failure, trace its cause, make a focused fix, then test the installed or deployed result.'],acceptance:['The original failure is resolved and relevant regression checks pass.']});
 const focus=site?`Investigate ${site.label}: ${site.url}`:task?.title||`Review ${p.name}'s unresolved failures`;
 const list=(a)=>a.map((s,i)=>`${i+1}. ${s}`).join('\n');
 const evidence=p.sites.map(s=>`- ${s.label} — ${s.url}: ${s.status?(s.status.success?'probe passed':'probe failed'):'not checked'}; HTTP ${s.status?.status??'unknown'}; checked ${s.status?.checked_at||'never'}${s.status?.error?'; '+s.status.error:''}`).join('\n');
 const ci=data.ci,monitor=data.uptime_workflow;
 const issues=(data.issues||[]).slice(0,4).map(i=>`- #${i.number} ${i.title}: ${i.url}`).join('\n');
 const results=task?.check?.evidence?.map(e=>`- ${e.label}: ${e.state} — ${e.detail}${e.url?'\n  Evidence: '+e.url:''}`).join('\n');
 return `Maintain ${p.name}: https://github.com/${p.repository}\n\nGOAL\n${focus}\n${task?.description||''}\n\nFirst confirm whether this is still a problem on the current version. If it is already resolved, provide the exact supporting evidence instead of changing working code.\n\nLATEST COLLECTED EVIDENCE — verify freshness before relying on it\nPublished release: ${releaseTag(p)}${data.release?.html_url?' — '+data.release.html_url:''}\nGitHub last fetched: ${p.github?.checked_at||'never'}${p.github?.error?' (refresh warning: '+p.github.error+')':''}\nDefault-branch commit: ${data.head_sha||'not collected'}\n${evidence}\nBuild: ${ci?.name||'unknown'} — ${ci?.conclusion||ci?.status||'unknown'}; run ${ci?.created_at||'unknown'}${ci?.html_url?'\n'+ci.html_url:''}\n${monitor?'Scheduled monitor: '+(monitor.conclusion||monitor.status)+'; run '+monitor.created_at+'\n'+(monitor.html_url||'')+'\n':''}${task?'Selected verification: '+goalRuleLabel(task)+'\nLast goal result: '+(task.check?.summary||'Not checked')+'\n':''}${results||''}\n${issues?'\nRELATED REPOSITORY CONTEXT (not proof of completion)\n'+issues+'\n':''}\nINVESTIGATION AND IMPLEMENTATION\n${list(plan.approach)}\n\nACCEPTANCE CHECKS\n${list(plan.acceptance)}\n${task?.rule?.kind&&task.rule.kind!=='manual'?'3. Rerun the selected Meridian verification: '+goalRuleLabel(task)+'. Report its exact source URL, timestamp and commit where relevant.\n':''}\nPreserve existing features, local data, privacy and lightweight background behavior. Read the repository instructions, inspect the relevant implementation, reproduce the failure and make a focused repair. Add a regression check for the failing behavior. Test the actual installed or deployed artifact where the problem occurs; a window existing or an unrelated green build does not prove the feature works. Do not expose keys, passwords, private backup contents or other secrets.\n\nDELIVERABLE\nReport the root cause (or why no fix was needed), files changed, exact tests and results, version/commit tested, and links to workflow/artifact evidence. Update project status with verified progress. Clearly list anything that still needs real-device or private-server access, with the shortest concrete checklist to finish it. Do not mark those checks complete without evidence.`;
}
function showPromptModal(msg){
 goalDialogReturn=document.activeElement;document.querySelector('#goal-review-backdrop')?.remove();document.querySelector('#prompt-backdrop')?.remove();
 const d=document.createElement('div');d.className='modal-backdrop';d.id='prompt-backdrop';
 d.innerHTML=`<section class="modal goal-dialog" role="dialog" aria-modal="true" aria-labelledby="prompt-title"><div class="modal-header"><div><h2 id="prompt-title">Your repair prompt</h2><p>Review the context, investigation plan and acceptance checks, then copy it into your coding conversation.</p></div><button class="icon-btn" data-close-goal-dialog aria-label="Close prompt">${ico('close')}</button></div><textarea class="prompt-text" readonly aria-label="Repair prompt"></textarea><p class="caption-line">Prepared locally from this goal and collected evidence. No AI subscription or API call is needed.</p><div class="modal-footer"><span id="prompt-copy-status" role="status"></span><button class="soft-button" data-select-prompt>Select all</button><button class="primary-button" data-copy-prompt>${ico('code')} Copy prompt</button></div></section>`;
 document.body.append(d);const box=d.querySelector('textarea');box.value=msg;box.focus();box.setSelectionRange(0,0);box.scrollTop=0;
}
async function copyRepairPrompt(pid,goalId=null,siteIndex=null){showPromptModal(makeRepairPrompt(pid,goalId,siteIndex));}
async function checkGoals(goalId=null,pid=null){
 closeGoalDialog();
 try{const r=await call('/goals/check','POST',{goal_id:goalId,project:pid||undefined});toast(r.started?'Refreshing evidence; results will update automatically.':'A refresh is already running.');await load(true);}
 catch(e){toast(e.message,true);}
}
function verificationFields(goal,pid){
 const rule=goal?.rule||{kind:'manual',target:''};
 return `<div class="goal-rule-fields"><div class="field"><label for="verification-kind">How should Meridian verify this goal?</label><select id="verification-kind" name="verification_kind"><option value="manual" ${rule.kind==='manual'?'selected':''}>Hands-on checklist</option><option value="site" ${rule.kind==='site'?'selected':''}>A monitored endpoint responds correctly</option><option value="build" ${rule.kind==='build'?'selected':''}>A named workflow passes on the current commit</option>${project(pid)?.sites.some(s=>s.type==='health')?`<option value="uptime" ${rule.kind==='uptime'?'selected':''}>Sync endpoint + scheduled monitor both pass</option>`:''}</select></div><div id="verification-target-fields">${verificationTarget(rule.kind,pid,rule.target)}</div><p class="caption-line">A passing automatic check completes the goal; a later failed check reopens it. Choose a check that actually proves this goal. Device behavior and private backup restores need hands-on evidence.</p></div>`;
}
function verificationTarget(kind,pid,selected=''){
 const p=project(pid);let choices=[];
 if(kind==='site')choices=p?.sites.map(s=>[s.url,s.label+' — '+s.url])||[];
 if(kind==='build')choices=gh(p).workflows?.map(r=>[String(r.workflow_id),r.name])||[];
 if(!['site','build'].includes(kind))return '<input type="hidden" name="verification_target" value="">';
 return `<div class="field"><label for="verification-target">${kind==='site'?'Endpoint':'Workflow'}</label><select id="verification-target" name="verification_target" required><option value="">${choices.length?'Choose the check':'Refresh GitHub first to load workflows'}</option>${choices.map(([id,name])=>`<option value="${esc(id)}" ${id===selected?'selected':''}>${esc(name)}</option>`).join('')}</select></div>`;
}
document.addEventListener('click',async e=>{
 const b=e.target.closest('[data-review-goal],[data-check-goal],[data-check-project],[data-close-goal-dialog],[data-copy-prompt],[data-goal-manual]');
 if(!b){if(['goal-review-backdrop','prompt-backdrop'].includes(e.target.id))closeGoalDialog();return;}
 if(b.disabled)return;
 if(b.hasAttribute('data-review-goal'))showGoalReview(Number(b.dataset.reviewGoal));
 else if(b.hasAttribute('data-check-goal'))await checkGoals(Number(b.dataset.checkGoal));
 else if(b.hasAttribute('data-check-project'))await checkGoals(null,b.dataset.checkProject);
 else if(b.hasAttribute('data-close-goal-dialog'))closeGoalDialog();
 else if(b.hasAttribute('data-goal-manual')){const g=model.goals.find(x=>x.id===Number(b.dataset.goalManual));closeGoalDialog();if(g)await setGoal(g.id,g.state==='done'?'todo':'done');}
 else if(b.hasAttribute('data-copy-prompt')){
  const box=document.querySelector('#prompt-backdrop textarea');
  try{await navigator.clipboard.writeText(box.value);$('#prompt-copy-status').textContent='Copied';b.textContent='Copied';}
  catch{box.focus();box.select();$('#prompt-copy-status').textContent='Text selected. Press Ctrl+C to copy.';}
 }
});
document.addEventListener('change',e=>{
 if(!modalSpec||modalSpec.type!=='goal')return;
 const kind=$('#verification-kind');if(!kind)return;
 if(e.target.matches('#verification-kind, select[name="project"]')){
  const pid=$('#modal-form [name="project"]').value;
  if(e.target.name==='project'){$('.goal-rule-fields').outerHTML=verificationFields(null,pid);return;}
  $('#verification-target-fields').innerHTML=verificationTarget(kind.value,pid);
 }
});
document.addEventListener('keydown',e=>{
 const dialog=document.querySelector('#goal-review-backdrop, #prompt-backdrop');if(!dialog)return;
 if(e.key==='Escape'){e.preventDefault();closeGoalDialog();return;}
 if(e.key==='Tab'){
  const items=[...dialog.querySelectorAll('button:not([disabled]),textarea,a[href]')].filter(el=>el.getClientRects().length),first=items[0],last=items.at(-1);
  if(e.shiftKey&&document.activeElement===first){e.preventDefault();last?.focus();}
  else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first?.focus();}
 }
});
