// Isolated backend fixture verifies both recommendation branches through the real page.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict');
(async()=>{
 assert.equal(process.env.QA_ACTION_FIXTURE,'1');
 const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
 try{
  const context=await browser.newContext({viewport:{width:1600,height:1050}});
  await context.addInitScript(token=>{localStorage.setItem('ramancloud_auth_token',token);localStorage.setItem('ramancloud_language','zh');},process.env.QA_FIXTURE_TOKEN);
  await context.route('**/api/**',async route=>{
   const u=new URL(route.request().url());const response=await route.fetch({url:process.env.QA_FIXTURE_API+u.pathname.slice(u.pathname.indexOf('/api/'))+u.search});await route.fulfill({response});
  });
  const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://127.0.0.1:5173/preprocessing/ai-analysis?task='+process.env.QA_FIXTURE_TASK);
  await page.locator('.welcome-screen.is-hidden').waitFor({state:'attached'});
  const workspace=page.locator('.ai-workspace'),select=workspace.getByLabel('方案生成方式',{exact:true});
  await select.waitFor();assert.equal(await select.inputValue(),'local_rules');
  let response=page.waitForResponse(r=>r.url().endsWith('/recommend'));
  await workspace.getByRole('button',{name:'生成预处理方案',exact:true}).click();
  let result=await response;assert.equal(result.request().postDataJSON().allow_ai,false);assert.equal((await result.json()).version.provider,'local_rules');
  await workspace.getByRole('button',{name:'重新推荐方案',exact:true}).waitFor();
  await select.selectOption('model');
  await workspace.getByText(/将所选波段的光谱采样数据/).waitFor();
  response=page.waitForResponse(r=>r.url().endsWith('/recommend'));
  await workspace.getByRole('button',{name:'重新推荐方案',exact:true}).click();result=await response;
  assert.equal(result.request().postDataJSON().allow_ai,true);const value=await result.json();
  assert.equal(value.version.provider,'ollama:fixture');
  assert.ok(value.version.steps.some(s=>s.method==='wtd'&&s.params.wavelet==='db2'&&s.params.level===2));
  await workspace.locator('select').filter({has:page.locator('option[value="wtd"]')}).waitFor();
  await page.screenshot({path:'logs/preprocess-model-mode.png'});
  assert.deepEqual(errors,[]);console.log('PASS default local rules, explicit model choice, paired data and editable model parameters');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
