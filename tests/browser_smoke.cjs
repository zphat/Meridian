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
  browser=await chromium.launch({headless:true,channel:"chromium",executablePath:process.env.MERIDIAN_CHROME_EXECUTABLE,args:['--no-sandbox']});
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
  await page.waitForFunction(()=>model.notes.some(x=>x.title==='Browser regression note'));
  // Fresh verification completes only matching goals, and a regression reopens them.
  await page.evaluate(()=>location.hash='sundial');
  const goalId=await page.evaluate(()=>model.goals.find(g=>g.title==='Diagnose repeated sync-server uptime-check failures').id);
  const card=()=>page.locator(`[data-goal-id="${goalId}"]`);
  await card().locator('[data-prompt-goal]').click();
  const prompt=await page.locator('#prompt-backdrop textarea').inputValue();
  assert.equal(await page.locator('#prompt-backdrop textarea').evaluate(el=>el.scrollTop),0,'Prompt should open at the beginning');
  for(const text of ['INVESTIGATION AND IMPLEMENTATION','ACCEPTANCE CHECKS','exact failed step','scheduled health workflow','https://github.com/'])assert.ok(prompt.includes(text),`Missing repair context: ${text}`);
  await page.screenshot({path:path.join(output,'repair-prompt.png')});
  await page.locator('[data-copy-prompt]').click();
  assert.match(await page.locator('#prompt-copy-status').textContent(),/Copied|Text selected/);
  await page.keyboard.press('Escape');
  await card().locator('[data-check-goal]').click();
  await page.waitForFunction(id=>model.goals.find(g=>g.id===id).check?.state==='verified'&&!model.busy,goalId);
  assert.equal(await page.evaluate(id=>model.goals.find(g=>g.id===id).completion_source,goalId),'verified');
  await page.locator('.completed-list summary').click();
  await card().locator('[data-review-goal]').first().click();
  assert.equal(await page.locator('.goal-evidence-row').count(),2);
  assert.match(await page.locator('#goal-evidence').textContent(),/Verified|both pass/);
  for(const width of [1280,800,390]){
   await page.setViewportSize({width,height:850});
   assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`Goal evidence overflows at ${width}px`);
  }
  await page.screenshot({path:path.join(output,'goal-evidence-mobile.png')});
  await page.keyboard.press('Escape');
  await page.setViewportSize({width:1280,height:850});
  await page.request.post('http://127.0.0.1:'+port+'/__test/checks/fail');
  await page.locator('[data-check-project="sundial"]').click();
  await page.waitForFunction(id=>model.goals.find(g=>g.id===id).check?.state==='failed'&&!model.busy,goalId);
  assert.equal(await page.evaluate(id=>model.goals.find(g=>g.id===id).state,goalId),'todo');
  assert.match(await page.locator('.verification-banner').textContent(),/reopened/);
  assert.match(await card().textContent(),/Still failing|Reopened/);
  await card().locator('[data-review-goal]').first().click();
  assert.match(await page.locator('#goal-evidence').textContent(),/HTTP 503/);
  await page.screenshot({path:path.join(output,'goal-evidence.png')});
  await page.keyboard.press('Escape');
  await page.request.post('http://127.0.0.1:'+port+'/__test/checks/pass');
  await page.locator('#refresh-button').click();
  await page.waitForFunction(()=>!model.busy&&model.goals.every(g=>g.check));
  const hardware=await page.evaluate(()=>model.goals.find(g=>g.title==='Verify macOS recording, permissions and export on real hardware'));
  assert.equal(hardware.check.state,'manual');assert.notEqual(hardware.state,'done');
  // The rule editor persists an explicitly chosen, current-commit workflow.
  await page.locator('[data-modal="goal"]').first().click();
  await page.locator('[name="title"]').fill('Verify packaged application build');
  await page.locator('#verification-kind').selectOption('build');
  await page.locator('#verification-target').selectOption('7');
  await page.locator('#modal-form [type="submit"]').click();
  await page.locator('#modal-form').waitFor({state:'detached'});
  await page.waitForFunction(()=>model.goals.some(g=>g.title==='Verify packaged application build'));
  const custom=await page.evaluate(()=>model.goals.find(g=>g.title==='Verify packaged application build'));
  assert.deepEqual(custom.rule,{kind:'build',target:'7'});
  await page.locator(`[data-goal-id="${custom.id}"] [data-check-goal]`).click();
  await page.waitForFunction(id=>model.goals.find(g=>g.id===id).check?.state==='verified'&&!model.busy,custom.id);
  await page.screenshot({path:path.join(output,'goals.png'),fullPage:true});
  await page.reload();await page.locator('#page h1').waitFor();
  assert.equal(await page.evaluate(id=>model.goals.find(g=>g.id===id).check.state,custom.id),'verified');
  // A hidden dashboard should schedule no recurring UI requests.
  let polls=0;page.on('request',r=>{if(r.url().endsWith('/api/state'))polls++;});
  await page.clock.install();
  await page.evaluate(()=>{Object.defineProperty(document,'hidden',{configurable:true,get:()=>true});document.dispatchEvent(new Event('visibilitychange'));});
  const before=polls;await page.clock.runFor(65000);assert.equal(polls,before,'hidden app kept polling');
  await page.evaluate(()=>{Object.defineProperty(document,'hidden',{configurable:true,get:()=>false});document.dispatchEvent(new Event('visibilitychange'));});
  await page.locator('#lock-button').click();await page.locator('#heading').waitFor();
  assert.equal((await page.request.get('http://127.0.0.1:'+port+'/api/state')).status(),401);
  assert.deepEqual(pageErrors,[]);
  console.log('Browser checks passed: setup, code recovery, wrong/correct code, all routes at 3 widths, analytics filters, quiet mode, note save, detailed repair prompt and copy, fresh verification, regression reopening, evidence modals, manual-check honesty, rule editing, persisted results, unchanged-state reuse, hidden polling, lock.');
 }finally{if(browser)await browser.close();server.kill();}
})().catch(e=>{console.error(e);process.exitCode=1;});
