// Requires an explicitly isolated fixture backend. No live user data or real model calls.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict');
(async()=>{
 assert.equal(process.env.QA_ACTION_FIXTURE,'1');
 const browser=await chromium.launch({executablePath:process.env.CHROME_PATH||'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
 const context=await browser.newContext({viewport:{width:1536,height:1050}});
 try{
  const api=process.env.QA_FIXTURE_API,token=process.env.QA_FIXTURE_TOKEN,ui=process.env.E2E_UI_URL||'http://127.0.0.1:5173/preprocessing';
  await context.addInitScript(t=>{localStorage.setItem('ramancloud_auth_token',t);localStorage.setItem('ramancloud_language','zh');},token);
  await context.route('**/api/**',async route=>{
   const u=new URL(route.request().url());
   try{const r=await route.fetch({url:api+u.pathname.slice(u.pathname.indexOf('/api/'))+u.search,timeout:120000});await route.fulfill({response:r});}
   catch(e){await route.abort().catch(()=>{});}
  });
  const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));page.setDefaultTimeout(30000);
  const open=async path=>{await page.goto(ui+path);await page.locator('.qa-panel').waitFor();await page.locator('.welcome-screen.is-hidden').waitFor({state:'attached'});};
  const panel=page.locator('.qa-panel');
  async function generate(goal){
   await panel.locator('.qa-consent input').check();await panel.getByLabel('问答消息').fill(goal);
   const turn=page.waitForResponse(r=>r.url().endsWith('/qa-assistant/preprocessing-turn')&&r.request().method()==='POST');
   await panel.getByRole('button',{name:'生成预处理方案',exact:true}).click();
   const response=await turn;assert.equal(response.status(),200,await response.text());
   const {kind,plan}=await response.json();assert.equal(kind,'plan');
   await panel.locator(`[data-plan-id="${plan.id}"]`).waitFor();
   return plan;
  }
  async function run({units=false,sharing=false}={}){
   const card=panel.getByRole('region',{name:'可运行方案'});
   if(units)await card.getByRole('checkbox',{name:/确认所选光谱横轴/}).check();
   if(sharing)await card.getByRole('checkbox',{name:/向当前项目成员共享/}).check();
   const sent=page.waitForResponse(r=>r.url().endsWith('/execute')&&r.url().includes('/qa-assistant/plans/'));
   await card.getByRole('button',{name:'一键运行',exact:true}).click();const response=await sent;
   assert.equal(response.status(),200,await response.text());
   await page.waitForFunction(()=>document.querySelector('.qa-plan-heading span')?.textContent==='已完成',{},{timeout:60000});
   assert.equal(await card.getByRole('button',{name:'一键运行',exact:true}).count(),0);
   return card;
  }
  await open('/ai-analysis?task='+process.env.QA_FIXTURE_TASK);
  await page.waitForFunction(()=>document.querySelector('[data-qa-task]')?.dataset.qaTask);
  await panel.locator('.qa-consent input').check();
  await panel.getByLabel('问答消息').fill('你好');
  assert.equal(await panel.getByRole('button',{name:'生成运行方案',exact:true}).count(),0);
  await panel.getByLabel('问答消息').fill('');
  assert.equal(await panel.getByRole('button',{name:'发送',exact:true}).isDisabled(),true);
  await generate('温和降噪');
  assert.equal(await panel.locator('.qa-plan-card details').count(),0);
  assert.equal(await panel.getByRole('button',{name:'一键运行',exact:true}).isVisible(),true);
  const card=panel.getByRole('region',{name:'可运行方案'});
  await card.getByRole('region',{name:'查看/修改算法与参数'}).locator('select').first().selectOption('sg');
  await card.getByLabel('窗口大小（奇数）',{exact:true}).fill('7');
  await page.locator('nav a[href="/preprocessing/library-matching"]').click();
  assert.equal(await card.count(),0);
  await page.locator('nav a[href="/preprocessing/ai-analysis"]').click();
  await card.waitFor();
  await run();
  assert.equal(await card.locator('.qa-plan-result').count(),1);
  await page.screenshot({path:'logs/qa-actions-preprocessing.png'});

  await page.setViewportSize({width:390,height:844});await page.getByRole('button',{name:'打开 AI 问答助手'}).click();
  const box=await panel.boundingBox();assert.ok(box.x>=0&&box.width<=390);
  await page.screenshot({path:'logs/qa-actions-mobile.png'});
  assert.deepEqual(errors,[]);
  console.log('PASS real preprocessing input, editable plan, plan visibility and responsive card');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
