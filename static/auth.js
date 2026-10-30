'use strict';
(async function(){
  const form=document.querySelector('#form'), heading=document.querySelector('#heading'),description=document.querySelector('#description'),provider=document.querySelector('#provider'),submit=document.querySelector('#submit'),message=document.querySelector('#message');
  let mode='login';
  try{
    const response=await fetch('/api/auth/status',{cache:'no-store'}),state=await response.json();
    if(state.authenticated){location.replace('/');return;}
    if(!state.configured){
      if(!state.local_setup){heading.textContent='Setup required on your PC';description.textContent='Initialize Meridian on the computer where it is installed before opening it remotely.';form.hidden=true;return;}
      mode='setup';heading.textContent='Set up private access';description.textContent='One-time setup: use the Proton inbox that should receive sign-in links, your access password, and your Resend API key. Nothing is committed to public source code.';
      document.querySelector('#resend_key').required=true;submit.textContent='Secure Meridian';
      document.querySelector('#password').autocomplete='new-password';
    }else provider.hidden=true;
  }catch(e){message.textContent='Authentication status unavailable.';form.hidden=true;return;}
  form.addEventListener('submit',async event=>{
    event.preventDefault();submit.disabled=true;message.className='';message.textContent='Checking…';
    const data={email:form.elements.email.value.trim(),password:form.elements.password.value};
    if(mode==='setup')data.resend_key=form.elements.resend_key.value.trim();
    try{
      const response=await fetch(mode==='setup'?'/api/auth/setup':'/api/auth/request',{method:'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',body:JSON.stringify(data)});
      const obj=await response.json();
      if(!response.ok)throw new Error(obj.error||'Unable to complete request');
      if(mode==='setup'){
        mode='login';heading.textContent='Check your Proton inbox';description.textContent='Private access is configured and the first one-time sign-in link has been sent. Open it on this computer or through Tailscale.';
        provider.hidden=true;submit.textContent='Send another link';form.elements.resend_key.value='';
        message.className='good';message.textContent='Sign-in link sent. You may request another after the five-minute cooldown if needed.';
      }else{message.className='good';message.textContent='Check your authorized inbox. The link expires in 10 minutes.';}
      form.elements.password.value='';
    }catch(e){message.textContent=e.message||'Unexpected error';}
    finally{submit.disabled=false;}
  });
})();