const {chromium}=require(process.env.MERIDIAN_PLAYWRIGHT||'playwright');
const {spawn}=require('node:child_process');
const path=require('node:path');
const fs=require('node:fs');
const assert=require('node:assert/strict');
const output=process.env.MERIDIAN_TEST_OUTPUT||path.resolve('test-artifacts');
fs.mkdirSync(output,{recursive:true});
(async()=>{
 const server=spawn(process.env.PYTHON||'python',['tests/browser_server.py'],{cwd:path.resolve(__dirname,'..'),stdio:['ignore','pipe','pipe']});
 let errors='';server.stderr.on('data',x=>errors+=x);
 let browser;
 try{
  const port=await new Promise((resolve,reject)=>{server.stdout.once('data',x=>resolve(String(x).trim()));server.once('exit',()=>reject(Error(errors)));setTimeout(()=>reject(Error('Fixture server startup timed out: '+errors)),15000).unref();});
  browser=await chromium.launch({headless:true,channel:"chromium",args:['--no-sandbox']});
  const page=await browser.newPage({viewport:{width:1280,height:850}});
  const pageErrors=[];page.on('pageerror',e=>pageErrors.push(e.message));
  await page.goto('http://127.0.0.1:'+port);
  await page.locator('#resend_key').waitFor({state:'visible'});
  await page.locator('#email').fill('owner@example.test');
  await page.locator('#password').fill('owner-password');
  await page.locator('#resend_key').fill('re_fixture_email_key');
  await page.locator('#submit').click();
  await page.locator('#email-code').waitFor({state:'visible'});
  assert.match(await page.locator('#delivery-reference').textContent(),/fixture-email-reference/);
  await page.reload();await page.locator('#email-code').waitFor({state:'visible'});
  await page.locator('#email-code').fill('11111111');await page.locator('#confirm-code').click();
  await page.waitForFunction(()=>document.querySelector('#code-message').textContent.includes('Incorrect'));
  await page.locator('#email-code').fill('13572468');await page.locator('#confirm-code').click();
  await page.locator('#page h1').waitFor();
  await page.screenshot({path:path.join(output,'overview.png'),fullPage:true});
  const tile=page.locator('.stat-tile').first();await tile.evaluate(el=>el.setAttribute('data-preserved','yes'));
  await page.evaluate(()=>load(true));assert.equal(await tile.getAttribute('data-preserved'),'yes','unchanged responses must not rebuild the page');
  // Every page fits both a small desktop window and a phone width.
  for(const width of [1280,800,390]){
   await page.setViewportSize({width,height:850});
   for(const view of ['overview','latitude','longitude','sundial','activity','analytics','settings']){
    await page.evaluate(view=>{location.hash=view},view);
    await page.waitForFunction(view=>document.querySelector('#crumb-current').textContent.toLowerCase()===(view==='overview'?'overview':view),view);
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`${view} overflows at ${width}px`);
   }
  }
  await page.setViewportSize({width:1280,height:850});
  await page.evaluate(()=>location.hash='analytics');await page.locator('#analytics-project').waitFor();
  await page.locator('[data-analytics-days="30"]').click();
  await page.locator('#analytics-project').selectOption('sundial');
  assert.equal(await page.locator('#analytics-project').inputValue(),'sundial');
  await page.screenshot({path:path.join(output,'analytics.png'),fullPage:true});
  await page.evaluate(()=>location.hash='settings');await page.locator('[data-monitor-mode="quiet"]').waitFor();
  await page.locator('[data-monitor-mode="quiet"]').click();
  await page.waitForFunction(()=>document.querySelector('[data-monitor-mode="quiet"]').getAttribute('aria-pressed')==='true');
  await page.evaluate(()=>location.hash='overview');await page.locator('[data-modal="note"]').first().click();
  await page.locator('[name="title"]').fill('Browser regression note');await page.locator('[name="body"]').fill('Saved and verified without sending email.');
  await page.locator('#modal-form [type="submit"]').click();await page.locator('#modal-form').waitFor({state:'detached'});
  assert.ok(await page.evaluate(()=>model.notes.some(x=>x.title==='Browser regression note')));
  // A hidden dashboard should schedule no recurring UI requests.
  let polls=0;page.on('request',r=>{if(r.url().endsWith('/api/state'))polls++;});
  await page.clock.install();
  await page.evaluate(()=>{Object.defineProperty(document,'hidden',{configurable:true,get:()=>true});document.dispatchEvent(new Event('visibilitychange'));});
  const before=polls;await page.clock.runFor(65000);assert.equal(polls,before,'hidden app kept polling');
  await page.evaluate(()=>{Object.defineProperty(document,'hidden',{configurable:true,get:()=>false});document.dispatchEvent(new Event('visibilitychange'));});
  await page.locator('#lock-button').click();await page.locator('#heading').waitFor();
  assert.equal((await page.request.get('http://127.0.0.1:'+port+'/api/state')).status(),401);
  assert.deepEqual(pageErrors,[]);
  console.log('Browser checks passed: setup, code recovery, wrong/correct code, all routes at 3 widths, analytics filters, quiet mode, note save, unchanged-state reuse, hidden polling, lock.');
 }finally{if(browser)await browser.close();server.kill();}
})().catch(e=>{console.error(e);process.exitCode=1;});
