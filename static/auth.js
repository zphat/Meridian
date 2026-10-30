'use strict';
(async function(){
  const form=document.querySelector('#form'), heading=document.querySelector('#heading'),description=document.querySelector('#description'),provider=document.querySelector('#provider'),submit=document.querySelector('#submit'),message=document.querySelector('#message');
  const codeForm=document.querySelector('#code-form'),codeBox=document.querySelector('#email-code'),codeSubmit=document.querySelector('#confirm-code'),codeMessage=document.querySelector('#code-message');
  const existingButton=document.querySelector('#show-existing-code');
  const pendingKey='meridian.pendingEmailCode';
  let mode='login', polling=null,activeChallenge=null;
  function storePending(challenge){
    try{sessionStorage.setItem(pendingKey,JSON.stringify({challenge,until:Date.now()+10*60*1000}));}catch(_){}
  }
  function readPending(){
    try{
      const value=JSON.parse(sessionStorage.getItem(pendingKey)||'null');
      if(value && typeof value.challenge==='string' && /^[A-Za-z0-9_-]{43}$/.test(value.challenge) && value.until>Date.now())return value;
      sessionStorage.removeItem(pendingKey);
    }catch(_){}
    return null;
  }
  function clearPending(){
    try{sessionStorage.removeItem(pendingKey);}catch(_){}
    activeChallenge=null;existingButton.hidden=true;
  }
  function showCode(challenge){
    activeChallenge=challenge;
    form.hidden=true;codeForm.hidden=false;
    existingButton.hidden=false;
    heading.textContent='Enter your verification code';
    description.textContent='Check the authorized inbox for your eight-digit code. No link needs to be opened.';
    codeMessage.textContent='Enter the code from your email here. It expires ten minutes after sending.';
    codeBox.focus();waitForEmailConfirmation(challenge);
  }
  function createChallenge(){
    const random=new Uint8Array(32);crypto.getRandomValues(random);
    return btoa(String.fromCharCode(...random)).replaceAll('+','-').replaceAll('/','_').replace(/=+$/,'');
  }
  function waitForEmailConfirmation(challenge){
    if(polling)clearInterval(polling);
    const until=Date.now()+10*60*1000;
    let busy=false;
    polling=setInterval(async()=>{
      if(busy)return;
      if(Date.now()>until){clearInterval(polling);polling=null;clearPending();codeForm.hidden=true;form.hidden=false;heading.textContent='Code expired';message.textContent='Your verification code has expired. Request a new one.';return;}
      busy=true;
      try{
        const r=await fetch('/api/auth/handoff',{method:'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',cache:'no-store',body:JSON.stringify({challenge})});
        if(r.ok){const state=await r.json();if(state.authenticated){clearInterval(polling);polling=null;location.replace('/');}}
      }catch(_){/* Retry while the local server is temporarily unavailable. */}
      finally{busy=false;}
    },1500);
  }
  try{
    const response=await fetch('/api/auth/status',{cache:'no-store'}),state=await response.json();
    if(state.authenticated){clearPending();location.replace('/');return;}
    const v=document.querySelector('#auth-version');if(v)v.textContent=state.version||'unknown';
    if(!state.configured){
      if(!state.local_setup){heading.textContent='Setup required on your PC';description.textContent='Initialize Meridian on the computer where it is installed before opening it remotely.';form.hidden=true;return;}
      mode='setup';heading.textContent='Set up private access';description.textContent='One-time setup: use the Proton inbox that should receive sign-in links, your access password, and your Resend API key. Nothing is committed to public source code.';
      document.querySelector('#resend_key').required=true;submit.textContent='Secure Meridian';
      document.querySelector('#password').autocomplete='new-password';
    }else{
      provider.hidden=true;submit.textContent='Email me an eight-digit code';
      const saved=readPending();
      if(saved){existingButton.hidden=false;showCode(saved.challenge);}
    }
  }catch(e){message.textContent='Authentication status unavailable.';form.hidden=true;return;}
  form.addEventListener('submit',async event=>{
    event.preventDefault();submit.disabled=true;message.className='';message.textContent='Checking…';
    const challenge=createChallenge();
    const data={email:form.elements.email.value.trim(),password:form.elements.password.value,challenge};
    if(mode==='setup')data.resend_key=form.elements.resend_key.value.trim();
    try{
      const response=await fetch(mode==='setup'?'/api/auth/setup':'/api/auth/request',{method:'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',body:JSON.stringify(data)});
      const obj=await response.json();
      if(!response.ok)throw new Error(obj.error||'Unable to complete request');
      if(mode==='setup'){
        mode='login';heading.textContent='Check your Proton inbox';description.textContent='Private access is configured and the first eight-digit verification code was sent. Enter it below to unlock Meridian.';
        provider.hidden=true;form.elements.resend_key.required=false;submit.textContent='Send another link';form.elements.resend_key.value='';
        message.className='good';message.textContent='Verification code sent. You can request another after the five-minute cooldown if needed.';
      }else{message.className='good';message.textContent='An eight-digit code has been sent to your authorized inbox. It expires in 10 minutes.';}
      storePending(challenge);
      codeBox.value='';
      showCode(challenge);
      form.elements.password.value='';
    }catch(e){
      const existing=readPending();
      if(existing){existingButton.hidden=false;message.textContent=(e.message||'Unable to send email')+' If you already received a code, use the button below.';}
      else message.textContent=e.message||'Unexpected error';
    }
    finally{submit.disabled=false;}
  });
  codeForm.addEventListener('submit',async event=>{
    event.preventDefault();
    if(!activeChallenge){codeMessage.textContent='Sign-in request expired. Request a new code.';return;}
    const code=codeBox.value.replace(/\s+/g,'');
    if(!/^[0-9]{8}$/.test(code)){codeMessage.textContent='Enter all eight digits from your email.';return;}
    codeSubmit.disabled=true;
    codeMessage.textContent='Verifying your email code…';
    try{
      const response=await fetch('/api/auth/confirm-code',{method:'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',cache:'no-store',body:JSON.stringify({challenge:activeChallenge,code})});
      const result=await response.json();
      if(!response.ok)throw Error(result.error||'Code could not be verified');
      if(polling){clearInterval(polling);polling=null;}
      clearPending();codeBox.value='';
      location.replace('/');
    }catch(error){codeMessage.textContent=error.message||'Unable to verify code.';}
    finally{codeSubmit.disabled=false;}
  });
  existingButton.addEventListener('click',()=>{const saved=readPending();if(saved)showCode(saved.challenge);else{existingButton.hidden=true;message.textContent='Your pending code expired; request a new one.';}});
  document.querySelector('#code-back').addEventListener('click',()=>{
    if(polling){clearInterval(polling);polling=null;}
    codeBox.value='';codeForm.hidden=true;form.hidden=false;
    heading.textContent='Sign in to Meridian';description.textContent='Your existing email code can still be entered below. You can request another only after the cooldown.';
    existingButton.hidden=!readPending();
    message.textContent='The previous code remains valid. You can return to it without sending another email.';
  });

})();