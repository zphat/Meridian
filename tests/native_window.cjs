// This attaches to the installed app's own WebView2, not a separate browser.
const {chromium}=require('playwright');
const {spawn,spawnSync}=require('node:child_process');
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
const {setTimeout:delay}=require('node:timers/promises');
const output=path.resolve('test-artifacts/native');
fs.mkdirSync(output,{recursive:true});
const root=path.join(process.env.LOCALAPPDATA,'Programs','Meridian');
const executable=path.join(root,'Meridian.exe');
(async()=>{
 let browser,page;
 const child=spawn(executable,[],{cwd:root,env:{...process.env,
   WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS:'--remote-debugging-port=19222 --remote-debugging-address=127.0.0.1',
 },stdio:['ignore','pipe','pipe']});
 child.stdout.on('data',x=>process.stdout.write(x));
 child.stderr.on('data',x=>process.stderr.write(x));
 try{
  let ready=false;
  for(let n=0;n<60;n++){
   if(child.exitCode!==null)throw Error('Native app exited with '+child.exitCode);
   try{const r=await fetch('http://127.0.0.1:19222/json/version');if(r.ok){ready=true;break;}}catch{}
   await delay(500);
  }
  assert.ok(ready,'WebView2 never initialized its browser process');
  browser=await chromium.connectOverCDP('http://127.0.0.1:19222');
  const context=browser.contexts()[0];
  page=context.pages()[0]||await context.waitForEvent('page',{timeout:10000});
  const errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  page.on('console',m=>{if(m.type()==='error')console.log('WEBVIEW CONSOLE:',m.text());});
  console.log('Native initial URL:',page.url());
  await page.locator('#heading').waitFor({state:'visible',timeout:20000});
  await page.waitForFunction(()=>document.querySelector('#auth-version')?.textContent!=='—');
  const state=await page.evaluate(()=>({url:location.href,title:document.title,width:innerWidth,height:innerHeight,
   background:getComputedStyle(document.body).backgroundColor,heading:document.querySelector('#heading').textContent,
   version:document.querySelector('#auth-version').textContent,emailVisible:document.querySelector('#email').getBoundingClientRect().width>100}));
  fs.writeFileSync(path.join(output,'state.json'),JSON.stringify(state,null,2));
  console.log('Native rendered state:',JSON.stringify(state));
  assert.ok(state.width>500&&state.height>300,'Native renderer has empty bounds');
  assert.ok(state.emailVisible,'Sign-in form is missing');
  assert.ok(!['rgba(0, 0, 0, 0)','rgb(255, 255, 255)'].includes(state.background),'Styles did not load');
  await page.locator('#email').fill('native-test@example.test');
  await page.locator('#password').fill('native-test-password');
  assert.equal(await page.locator('#email').inputValue(),'native-test@example.test');
  await page.screenshot({path:path.join(output,'sign-in.png')});
  await page.reload();await page.locator('#email').waitFor({state:'visible'});
  assert.deepEqual(errors,[]);
  console.log('PASS: installed native app renders styled, interactive sign-in and survives reload.');
 }catch(e){
  if(page){
   console.log('Native failure URL:',page.url());
   try{console.log('Native DOM:',(await page.content()).slice(0,6000));await page.screenshot({path:path.join(output,'failure.png'),timeout:5000});}catch{}
  }
  throw e;
 }finally{
  // /T closes the app-owned backend and WebView2 children as well.
  spawnSync('taskkill',['/PID',String(child.pid),'/T','/F']);
  if(browser)await browser.close().catch(()=>{});
  const log=path.join(process.env.LOCALAPPDATA,'Meridian','logs','startup.log');
  if(fs.existsSync(log)){fs.copyFileSync(log,path.join(output,'startup.log'));console.log(fs.readFileSync(log,'utf8').slice(-12000));}
 }
})().catch(e=>{console.error(e);process.exitCode=1;});
