'use strict';
function githubSharedAlert(){
 const access=model.github_access||{},limited=access.state==='rate_limited',invalid=access.state==='invalid_token';
 const oldLimit=model.projects.some(p=>/rate limit|request allowance|requests are paused/i.test(p.github?.error||''));
 if(!limited&&!invalid&&!oldLimit)return null;
 return {project:'github',level:'info',settings:true,title:invalid?'GitHub token needs attention':limited?'GitHub refresh paused':'GitHub refresh can be retried',
  detail:invalid?'Replace or remove the rejected token in Settings. Your local workspace remains available.':limited?`GitHub asks Meridian to wait until ${shortDate(access.retry_at)}. Website checks continue and saved project data stays available.${access.authenticated?'':' An optional GitHub token provides a larger request allowance.'}`:'The previous GitHub allowance pause has ended. Use Refresh & check to collect current results.'};
}
function githubPanel(){
 const a=model.github_access||{},paused=['rate_limited','invalid_token'].includes(a.state),resetFuture=a.reset_at&&Date.parse(a.reset_at)>Date.now();
 return `<div class="panel github-panel"><div class="panel-header"><div><span class="small-label">READ-ONLY PROJECT ACCESS</span><h3>GitHub connection</h3></div>${pill(paused?'Needs attention':a.authenticated?'Token connected':'Public access',paused?'warn':a.authenticated?'good':'dim')}</div><p class="caption-line">Public access shares a small hourly allowance with other apps on your internet connection. A free, optional GitHub token raises the allowance. Meridian only reads project data.</p><div class="runtime-facts"><span>${ico('clock')} ${a.limit!=null&&resetFuture?`${fmt(a.remaining)} of ${fmt(a.limit)} requests remaining`:'Allowance updates on the next request'}</span>${a.retry_at?`<span>Retry after ${esc(shortDate(a.retry_at))}</span>`:a.reset_at&&resetFuture?`<span>Resets ${esc(shortDate(a.reset_at))}</span>`:''}</div><div class="page-actions">${a.source==='environment'?'<p class="caption-line">Configured through MERIDIAN_GITHUB_TOKEN on this computer.</p>':`<button class="primary-button" data-modal="github">${ico('git')} ${a.authenticated?'Replace token':'Connect GitHub token'}</button>${a.saved_token?'<button class="soft-button" data-remove-github>Remove saved token</button>':''}`}<a class="soft-button" href="https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens" target="_blank" rel="noreferrer">Token instructions ${ico('external')}</a></div><p class="caption-line">Recent responses are cached across restarts. Live goal checks still request fresh build evidence. Tokens stay in a private local credentials file and are excluded from workspace exports.</p></div>`;
}
function githubTokenFields(){
 return `<div class="subtle-card"><p class="caption-line">Create a fine-grained token with <strong>Public repositories (read-only)</strong> access. No write permissions are needed for these public projects. Give it a name such as Meridian and an expiration you are comfortable with.</p><a class="inline-link" href="https://github.com/settings/personal-access-tokens/new?name=Meridian&amp;description=Read+public+project+status&amp;expires_in=90" target="_blank" rel="noreferrer">Create token on GitHub ${ico('external')}</a></div><div class="field" style="margin-top:18px"><label for="github-token">GitHub personal access token</label><input id="github-token" name="token" type="password" autocomplete="off" spellcheck="false" required minlength="20" maxlength="255" placeholder="Paste the token here"></div><p class="caption-line">Paste it into this local window. Meridian tests the token before saving; a failed test preserves your existing setting.</p>`;
}
document.addEventListener('click',async e=>{
 const button=e.target.closest('[data-remove-github]');if(!button)return;
 button.disabled=true;
 try{await call('/settings/github','DELETE');await load(true);toast('Saved token removed. Public GitHub access is active.');}
 catch(error){toast(error.message,true);button.disabled=false;}
});
