// Isolated HTTP fixtures test conversation order and the plan execution controls.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.CHROME_PATH||'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
 try{
  const context=await browser.newContext({viewport:{width:1440,height:1000}});
  await context.addInitScript(()=>localStorage.setItem('ramancloud_auth_token','timeline-fixture'));
  let sequence=0,replies=0,executions=0,clarifyNext=false;const plans=new Map();
  await context.route('**/api/**',async route=>{
   const request=route.request(),path=new URL(request.url()).pathname;
   if(path.endsWith('/auth/me'))return route.fulfill({json:{data:{user:{id:'fixture',username:'fixture',role:'user'}}}});
   if(path.endsWith('/account/preferences'))return route.fulfill({json:{language:'zh'}});
   if(path.endsWith('/assistant/config'))return route.fulfill({json:{provider:'ollama',model:'fixture'}});
   if(path.endsWith('/qa-assistant/reply'))return route.fulfill({contentType:'application/x-ndjson',body:[{type:'delta',text:`建议${++replies}：采用 SG 去噪，然后校正基线。\n`+'检查曲线和峰形。\n'.repeat(25)},{type:'done'}].map(x=>JSON.stringify(x)).join('\n')+'\n'});
   if(path.endsWith('/actions/catalog'))return route.fulfill({json:{operations:[],pipeline_registry:[],parameter_rules:{}}});
   if(path.endsWith('/qa-assistant/plans')){
    if(request.method()==='GET')return route.fulfill({json:[]});
    if(clarifyNext){clarifyNext=false;return route.fulfill({json:{clarification:'请明确新的处理目标。'}});}
    const match=request.postDataBuffer().toString().match(/name="payload"\r\n\r\n([^\r]+)/);
    const payload=JSON.parse(match[1]);
    const plan={id:`plan-${++sequence}`,revision:1,status:'draft',title:`方案${sequence}`,summary:'SG 去噪，保留峰形',source_name:'测试光谱',context_key:payload.context_key,steps:[{action:'preprocess',label:'去噪',params:{}}]};
    plans.set(plan.id,plan);return route.fulfill({json:plan});
   }
   const match=path.match(/\/qa-assistant\/plans\/(plan-\d+)(\/execute)?$/);
   if(match){
    const plan=plans.get(match[1]);
    if(match[2]){executions++;plan.status='queued';}
    else if(plan.status==='queued')plan.status='completed';
    return route.fulfill({json:plan});
   }
   return route.fulfill({json:{data:{}}});
  });
  const page=await context.newPage(),errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.goto((process.env.E2E_UI_URL||'http://127.0.0.1:5173/preprocessing')+'/contributors');
  await page.locator('.welcome-screen.is-hidden').waitFor({state:'attached'});
  await page.evaluate(()=>{
   document.addEventListener('qa-read-execution-input',event=>{event.detail.value={module:'contributors',inputs:{source:{workflow_id:'fixture'}},files:[],locked:false};});
   document.dispatchEvent(new Event('qa-execution-input-changed'));
  });
  const panel=page.locator('.qa-panel'),input=panel.getByLabel('问答消息');
  async function send(text){await input.fill(text);await panel.getByRole('button',{name:/^(发送|重试发送)$/}).click();await page.waitForFunction(()=>!document.querySelector('.qa-composer textarea').disabled&&!document.querySelector('.qa-composer textarea').value);}
  await send('请帮我用 SG 去噪，保留峰形');
  await panel.getByRole('button',{name:'生成运行方案',exact:true}).click();
  await panel.locator('[data-plan-id="plan-1"]').waitFor();
  clarifyNext=true;
  await panel.getByRole('button',{name:'生成运行方案',exact:true}).click();
  await panel.getByRole('alert').filter({hasText:'请明确新的处理目标。'}).waitFor();
  assert.equal(await panel.locator('[data-plan-id="plan-1"]').getByRole('button',{name:'一键运行',exact:true}).count(),0,'a clarification preserves the timeline but retires the previous draft');
  await send('请继续调整基线校正');
  const order=await panel.locator('.qa-messages > .qa-message,.qa-messages > .qa-plan-card').evaluateAll(nodes=>nodes.map(n=>n.textContent));
  assert.ok(order[2].includes('方案1'));assert.ok(order[3].includes('继续调整基线'));
  await panel.getByRole('button',{name:'生成运行方案',exact:true}).click();
  const second=panel.locator('[data-plan-id="plan-2"]');await second.waitFor();
  assert.equal(await panel.locator('.qa-plan-card').count(),2);
  assert.equal(await panel.locator('[data-plan-id="plan-1"]').getByRole('button',{name:'一键运行',exact:true}).count(),0);
  await second.getByRole('button',{name:'一键运行',exact:true}).click();
  await panel.locator('.qa-messages').evaluate(n=>{n.scrollTop=0;n.dispatchEvent(new Event('scroll',{bubbles:true}));});
  await second.getByText('已完成',{exact:true}).waitFor();assert.equal(executions,1);
  assert.ok(await panel.locator('.qa-messages').evaluate(n=>n.scrollTop)<5,'progress polling preserves the reading position');
  await send('请帮我解读处理后的峰形');
  const ids=await panel.locator('.qa-messages > .qa-message,.qa-messages > .qa-plan-card').evaluateAll(nodes=>nodes.map(n=>n.dataset.planId||n.textContent));
  assert.equal(ids[2],'plan-1');assert.equal(ids[5],'plan-2');assert.ok(ids[6].includes('处理后的峰形'));
  await panel.locator('.qa-messages').evaluate(n=>{n.scrollTop=0;});await page.waitForTimeout(150);
  // Opening older parameters must not force the reader back to the newest answer.
  await panel.locator('[data-plan-id="plan-1"] summary').click();await page.waitForTimeout(150);
  assert.ok(await panel.locator('.qa-messages').evaluate(n=>n.scrollTop)<1000);
  assert.deepEqual(errors,[]);console.log('PASS chronological cards, replacement, one-click execution and later discussion');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
