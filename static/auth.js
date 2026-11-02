'use strict';
(async function(){
  const $=s=>document.querySelector(s);
  const form=$('#form'),heading=$('#heading'),description=$('#description'),provider=$('#provider'),submit=$('#submit'),message=$('#message');
  const codeForm=$('#code-form'),codeBox=$('#email-code'),codeSubmit=$('#confirm-code'),codeMessage=$('#code-message'),existingButton=$('#show-existing-code');
  const pendingKey='meridian.pendingEmailCode',cooldownKey='meridian.emailCooldown';
  let mode='login',polling=null,active=null,sending=false,cooldownTimer=null;
  const stored=(key)=>{try{return JSON.parse(sessionStorage.getItem(key)||'null');}catch(_){return null;}};
  const save=(key,value)=>{try{sessionStorage.setItem(key,JSON.stringify(value));}catch(_){}};
  function readPending(){
    const p=stored(pendingKey);
    return p && /^[A-Za-z0-9_-]{43}$/.test(p.challenge||'') && p.until>Date.now()?p:null;
  }
  function clearPending(){try{sessionStorage.removeItem(pendingKey);}catch(_){}active=null;existingButton.hidden=true;}
  function stopPolling(){clearTimeout(polling);polling=null;}
  function updateCooldown(){
    clearTimeout(cooldownTimer);
    const remaining=Math.max(0,Math.ceil(((stored(cooldownKey)||0)-Date.now())/1000));
    submit.disabled=sending||remaining>0;
    submit.textContent=sending?'Sending…':remaining>0?`Request another in ${remaining>=3600?Math.ceil(remaining/3600)+'h':remaining>=60?Math.ceil(remaining/60)+'m':remaining+'s'}`:mode==='setup'?'Set up and email my code':'Email me an eight-digit code';
    if(remaining>0&&!document.hidden)cooldownTimer=setTimeout(updateCooldown,remaining>60?10000:1000);
  }
  function setCooldown(seconds){if(seconds>0)save(cooldownKey,Date.now()+seconds*1000);updateCooldown();}
  function showLogin(){
    stopPolling();codeForm.hidden=true;form.hidden=false;existingButton.hidden=!readPending();
    heading.textContent='Sign in to Meridian';
    description.textContent='Use your authorized email and password, then enter the code from your inbox.';
    updateCooldown();
  }
  function expire(){clearPending();showLogin();message.textContent='Your code expired. Request a new one when the countdown finishes.';}
  async function poll(){
    stopPolling();if(!active)return;
    if(active.until<=Date.now()){expire();return;}
    if(document.hidden)return;
    try{
      const r=await fetch('/api/auth/handoff',{method:'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',cache:'no-store',body:JSON.stringify({challenge:active.challenge})});
      if(r.ok&&(await r.json()).authenticated){clearPending();location.replace('/');return;}
    }catch(_){/* The service may briefly restart during an upgrade. */}
    if(active)polling=setTimeout(poll,3000);
  }
  function showCode(p){
    active=p;form.hidden=true;codeForm.hidden=false;
    heading.textContent='Check your inbox';
    description.textContent='Enter the eight-digit code in this window. You can leave the email links alone.';
    codeMessage.textContent='Resend accepted the email. Check spam if it has not arrived. The code expires ten minutes after sending.';
    $('#delivery-reference').textContent=p.emailId?'Email reference: '+p.emailId:'';
    codeBox.focus();poll();
  }
  function createChallenge(){const bytes=new Uint8Array(32);crypto.getRandomValues(bytes);return btoa(String.fromCharCode(...bytes)).replaceAll('+','-').replaceAll('/','_').replace(/=+$/,'');}
  async function post(path,data){
    const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',cache:'no-store',body:JSON.stringify(data)});
    const result=await r.json();
    if(!r.ok){const e=Error(result.error||'Request failed. Please try again.');e.retryAfter=result.retry_after||0;throw e;}
    return result;
  }
  try{
    const response=await fetch('/api/auth/status',{cache:'no-store'});
    if(!response.ok)throw Error('Status unavailable');
    const state=await response.json();$('#auth-version').textContent=state.version||'unknown';
    if(state.authenticated){clearPending();location.replace('/');return;}
    if(!state.configured){
      clearPending();save(cooldownKey,0);
      if(!state.local_setup){heading.textContent='Set up on your PC';description.textContent='Open Meridian on the computer where it is installed to complete initial setup.';form.hidden=true;return;}
      mode='setup';heading.textContent='Set up private access';
      description.textContent='Use the inbox registered to your Resend account, choose an access password, and enter your Sending access API key.';
      $('#resend_key').required=true;$('#password').autocomplete='new-password';
    }else{
      provider.hidden=true;$('#email-settings').hidden=!state.local_setup;
      const pending=readPending();if(pending)showCode(pending);
    }
    updateCooldown();
  }catch(_){message.textContent='Cannot reach Meridian. Close and reopen the app to reconnect.';form.hidden=true;return;}
  form.addEventListener('submit',async e=>{
    e.preventDefault();if(sending||submit.disabled)return;sending=true;updateCooldown();message.className='';message.textContent='Contacting the email service…';
    const challenge=createChallenge();
    const data={email:form.elements.email.value.trim(),password:form.elements.password.value,challenge};
    if(mode==='setup')data.resend_key=$('#resend_key').value.trim();
    else if($('#replacement-key').value.trim())data.resend_key=$('#replacement-key').value.trim();
    try{
      const result=await post(mode==='setup'?'/api/auth/setup':'/api/auth/request',data);
      mode='login';provider.hidden=true;$('#resend_key').required=false;$('#resend_key').value='';$('#replacement-key').value='';$('#email-settings').hidden=false;
      form.elements.password.value='';$('#password').autocomplete='current-password';
      const p={challenge,until:result.expires_at?result.expires_at*1000:Date.now()+600000,emailId:result.email_id||''};
      save(pendingKey,p);setCooldown(result.retry_after||60);codeBox.value='';showCode(p);
    }catch(err){
      setCooldown(err.retryAfter);message.textContent=err.message;existingButton.hidden=!readPending();
    }finally{sending=false;updateCooldown();}
  });
  codeBox.addEventListener('input',()=>{codeBox.value=codeBox.value.replace(/\D/g,'').slice(0,8);});
  codeForm.addEventListener('submit',async e=>{
    e.preventDefault();if(!active||active.until<=Date.now()){expire();return;}
    const code=codeBox.value.replace(/\s+/g,'');if(!/^\d{8}$/.test(code)){codeMessage.textContent='Enter all eight digits from the email.';return;}
    stopPolling();codeSubmit.disabled=true;codeMessage.textContent='Verifying…';
    try{await post('/api/auth/confirm-code',{challenge:active.challenge,code});clearPending();codeBox.value='';location.replace('/');}
    catch(err){codeMessage.textContent=err.message;poll();}
    finally{codeSubmit.disabled=false;}
  });
  existingButton.addEventListener('click',()=>{const p=readPending();if(p)showCode(p);else expire();});
  $('#code-back').addEventListener('click',()=>{showLogin();message.textContent=readPending()?'Your existing code still works. Return to it below without sending another email.':'';});
  document.addEventListener('visibilitychange',()=>{updateCooldown();if(document.hidden)stopPolling();else if(!codeForm.hidden)poll();});
  window.addEventListener('pagehide',()=>{stopPolling();clearTimeout(cooldownTimer);});
  document.documentElement.dataset.meridianReady='auth';
})();
