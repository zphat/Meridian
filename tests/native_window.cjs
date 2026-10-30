// Attach to the installed app's WebView2; never launch a substitute browser.
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
const log=path.join(process.env.LOCALAPPDATA,'Meridian','logs','startup.log');
const published=process.env.MERIDIAN_TEST_PUBLISHED==='1';
const readLog=()=>fs.existsSync(log)?fs.readFileSync(log,'utf8'):'';
function cleanup(){
 // Only this disposable runner's installed Meridian processes; no broad
 // Python or Edge process matching.
 spawnSync('powershell.exe',['-NoProfile','-Command',`$root=Join-Path $env:LOCALAPPDATA 'Programs/Meridian';$paths=@((Join-Path $root 'Meridian.exe'),(Join-Path $root 'runtime/python.exe'));Get-CimInstance Win32_Process | Where-Object {$_.ExecutablePath -in $paths} | ForEach-Object {Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue}`]);
}
async function waitExit(child,timeout=10000){
 const until=Date.now()+timeout;
 while(child.exitCode===null&&child.signalCode===null){if(Date.now()>until)throw Error('Native app did not close');await delay(100);}
}
async function nativeCheck(label,{retry=false,fullFlow=false}={}){
 let browser,page;
 const logStart=readLog().length;
 const child=spawn(executable,[],{cwd:root,env:{...process.env,WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS:'--remote-debugging-port=19222 --remote-debugging-address=127.0.0.1'},stdio:['ignore','pipe','pipe']});
 child.stderr.on('data',x=>process.stderr.write(x));
 try{
  let connected=false;
  for(let n=0;n<50;n++){
   if(child.exitCode!==null)throw Error('Native app exited before displaying its interface');
   try{const r=await fetch('http://127.0.0.1:19222/json/version');if(r.ok){connected=true;break;}}catch{}
   await delay(400);
  }
  assert.ok(connected,'Native WebView2 debugging endpoint did not initialize');
  browser=await chromium.connectOverCDP('http://127.0.0.1:19222');
  const context=browser.contexts()[0];
  page=context.pages()[0]||await context.waitForEvent('page',{timeout:10000});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.locator('#heading').waitFor({state:'visible',timeout:22000});
  await page.waitForFunction(()=>document.querySelector('#auth-version')?.textContent!=='—');
  const state=await page.evaluate(()=>({url:location.href,width:innerWidth,height:innerHeight,background:getComputedStyle(document.body).backgroundColor,heading:document.querySelector('#heading').textContent,version:document.querySelector('#auth-version').textContent,emailVisible:document.querySelector('#email').getBoundingClientRect().width>100}));
  console.log(label,JSON.stringify(state));
  fs.writeFileSync(path.join(output,label+'.json'),JSON.stringify(state,null,2));
  assert.ok(state.width>500&&state.height>300,'Native renderer has empty bounds');
  assert.ok(state.emailVisible,'Sign-in form is missing');
  assert.ok(!['rgba(0, 0, 0, 0)','rgb(255, 255, 255)'].includes(state.background),'Styles did not load');
  await page.locator('#email').fill('native-test@example.test');
  await page.locator('#password').fill('native-test-password');
  assert.equal(await page.locator('#email').inputValue(),'native-test@example.test');
  await page.screenshot({path:path.join(output,label+'.png')});
  if(fullFlow){
   await page.locator('#resend_key').fill('re_native_fixture_key');
   await page.locator('#submit').click();
   await page.locator('#email-code').waitFor({state:'visible'});
   await page.locator('#email-code').fill('13572468');
   await page.locator('#confirm-code').click();
   await page.locator('#page h1').waitFor();
   for(const route of ['overview','analytics','settings']){
    await page.evaluate(x=>location.hash=x,route);
    await page.waitForFunction(x=>document.querySelector('#crumb-current').textContent.toLowerCase()===x,route);
   }
   await page.screenshot({path:path.join(output,'native-dashboard.png')});
   await page.locator('#lock-button').click();await page.locator('#heading').waitFor();
  }
  await page.reload();await page.locator('#email').waitFor({state:'visible'});
  if(!published){
   for(let n=0;n<30&&!readLog().slice(logStart).includes('interface ready');n++)await delay(100);
   const launchLog=readLog().slice(logStart);
   assert.match(launchLog,/interface ready/,'App never acknowledged a rendered interface');
   assert.ok(!launchLog.includes('deadline reached'),'Normal start used browser fallback');
   if(retry)assert.match(launchLog,/retrying navigation/,'Simulated blank did not exercise retry');
  }
  assert.deepEqual(errors,[]);
  spawnSync('powershell.exe',['-NoProfile','-Command',`(Get-Process -Id ${child.pid}).CloseMainWindow() | Out-Null`]);
  await waitExit(child);
  console.log('PASS:',label,'styled interactive native interface, reload and normal close');
 }catch(e){
  if(page){try{console.log('Failure URL:',page.url());console.log((await page.content()).slice(0,2000));await page.screenshot({path:path.join(output,label+'-failure.png'),timeout:5000});}catch{}}
  throw e;
 }finally{
  if(child.exitCode===null)spawnSync('taskkill',['/PID',String(child.pid),'/T','/F']);
  if(browser)await browser.close().catch(()=>{});
  fs.writeFileSync(path.join(output,label+'.log'),readLog().slice(logStart));
 }
}
(async()=>{
 cleanup();await delay(700);
 for(let i=1;i<=5;i++)await nativeCheck('launch-'+i);
 if(!published){
  cleanup();await delay(700);
  const fixture=spawn(path.join(root,'runtime/python.exe'),[path.resolve('tests/native_server.py'),root,'1'],{stdio:['ignore','pipe','pipe']});
  let fixtureOutput='';fixture.stdout.on('data',x=>fixtureOutput+=x);fixture.stderr.on('data',x=>process.stderr.write(x));
  try{
   for(let n=0;n<60&&!fixtureOutput.includes('Ready');n++){if(fixture.exitCode!==null)throw Error('Native fixture exited');await delay(100);}
   assert.match(fixtureOutput,/Ready/);
   await nativeCheck('blank-document-recovery',{retry:true,fullFlow:true});
   console.log('PASS: automatically recovered blank navigation, then native setup, email code, dashboard routes and lock.');
  }finally{fixture.kill();await waitExit(fixture);}
 }
})().catch(e=>{console.error(e);process.exitCode=1;}).finally(()=>{cleanup();fs.writeFileSync(path.join(output,'startup.log'),readLog());});
