/* Isolated service on 5001/5174, real preprocessing, no model recommendation. */
const {chromium}=require('playwright'), fs=require('fs/promises'), path=require('path'), assert=require('assert/strict');
async function main(){
 const out=path.resolve(__dirname,'../../logs/records-flow-ui');await fs.mkdir(out,{recursive:true});
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH});
 const context=await browser.newContext({viewport:{width:1440,height:1050},locale:'zh-CN'});let page;
 try{
  const api='http://127.0.0.1:5001/api',ui='http://127.0.0.1:5174/preprocessing';
  const registration=await context.request.post(api+'/auth/register',{data:{username:'qa_records_'+Date.now(),password:'isolated-records-qa'}});assert.equal(registration.status(),200);
  const auth=(await registration.json()).data,headers={Authorization:'Bearer '+auth.token};
  async function req(route,data){const r=data===undefined?await context.request.get(api+route,{headers}):await context.request.post(api+route,{headers,data});assert.equal(r.status(),200,await r.text());return r.json();}
  const project=(await req('/projects',{name:'QA unified records'})).data.project;
  const task=await req('/ai-workflows/source',{demo:'tutorial'});
  await context.addInitScript(token=>{localStorage.setItem('ramancloud_auth_token',token);localStorage.setItem('ramancloud_language','zh');localStorage.setItem('ramancloud_theme','light');},auth.token);
  page=await context.newPage();page.setDefaultTimeout(30000);const errors=[];page.on('pageerror',error=>errors.push(error.message));
  const open=async route=>{await page.goto(ui+route);await page.locator('.welcome-screen.is-hidden').waitFor({state:'attached'});};
  await open('/ai-analysis?task='+task.id);
  assert.equal(await page.locator('.ai-sources').count(),0);assert.equal(await page.locator('.ai-workflow-stages button').count(),3);
  assert.equal(await page.getByText('保存与下载',{exact:true}).count(),0);
  await page.getByRole('button',{name:'生成预处理方案',exact:true}).click();await page.getByRole('button',{name:'开始处理',exact:true}).click();
  await page.getByText('已记录 · 查看分析记录',{exact:true}).waitFor();
  const detail=await req('/ai-workflows/'+task.id),version=await req('/ai-workflows/'+task.id+'/versions/'+detail.versions.at(-1).id);
  assert.equal(version.status,'completed');const runId=version.analysis_run_id;
  await page.screenshot({path:path.join(out,'result-desktop.png'),animations:'disabled'});
  async function exported(label,name){await page.getByRole('button',{name:'导出',exact:true}).click();const dialog=page.getByRole('dialog');await dialog.waitFor();const event=page.waitForEvent('download');await dialog.getByRole('button',{name:label,exact:true}).click();const download=await event;const target=path.join(out,name);await download.saveAs(target);await dialog.getByRole('button',{name:'关闭',exact:true}).click();return fs.readFile(target);}
  const processed=await exported('处理后光谱 TXT','processed-workspace.txt');
  const rows=processed.toString().trim().split('\n').slice(1).map(row=>row.split('\t').map(Number));
  rows.forEach(([x,y],i)=>{assert.equal(x,version.trace.at(-1).after.wavenumber[i]);assert.equal(y,version.trace.at(-1).after.intensity[i]);});
  const png=await exported('处理后光谱 PNG','processed-workspace.png');assert.equal(png.readUInt32BE(16),2400);assert.equal(png.readUInt32BE(20),1440);
  await page.getByRole('button',{name:'共享到项目',exact:true}).click();await page.getByLabel('目标项目',{exact:true}).selectOption(project.id);
  await page.getByRole('button',{name:'确认共享',exact:true}).click();await page.getByRole('dialog').waitFor({state:'detached'});
  await open('/analysis-history?run='+runId);await page.getByRole('heading',{name:'tutorial_raman.txt',exact:true}).waitFor();
  assert.deepEqual(await exported('处理后光谱 TXT','processed-history.txt'),processed);
  assert.deepEqual(await exported('处理后光谱 PNG','processed-history.png'),png);
  await page.screenshot({path:path.join(out,'records-desktop.png'),animations:'disabled'});
  await open('/projects?project='+project.id);await page.getByRole('tab',{name:'共享结果',exact:true}).click();await page.getByRole('link',{name:'打开结果',exact:true}).first().click();
  await page.getByRole('heading',{name:'tutorial_raman.txt',exact:true}).waitFor();assert.ok(page.url().includes(runId));
  assert.deepEqual(await exported('处理后光谱 TXT','processed-project.txt'),processed);
  const runs=(await req('/analysis-runs')).data.runs;assert.equal(runs.filter(run=>run.result.ai_workflow_id===task.id).length,1);
  const extra=await req('/ai-workflows/source',{demo:'bacteria'});
  await open('/analysis-history');await page.getByRole('button',{name:'未处理',exact:true}).click();
  await page.getByRole('link',{name:'继续处理',exact:true}).click();assert.ok(page.url().includes(extra.id));
  await page.getByRole('button',{name:'生成预处理方案',exact:true}).waitFor();
  await page.screenshot({path:path.join(out,'upload-desktop.png'),animations:'disabled'});
  await open('/ai-analysis?task='+task.id+'&version='+version.id);await page.getByRole('button',{name:'继续调整',exact:true}).click();
  await page.getByLabel('调整反馈',{exact:true}).fill('峰变弱了，减小平滑窗口，其他步骤保持不变');
  await page.getByRole('button',{name:'导出',exact:true}).click();assert.ok(await page.getByRole('button',{name:'处理后光谱 TXT',exact:true}).isDisabled());await page.getByRole('button',{name:'关闭',exact:true}).click();
  await page.getByRole('button',{name:'更新方案并预览',exact:true}).click();await page.getByRole('button',{name:'应用修改',exact:true}).click();
  await page.getByText('已记录 · 查看分析记录',{exact:true}).waitFor();
  await page.setViewportSize({width:390,height:844});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await page.screenshot({path:path.join(out,'result-mobile.png'),animations:'disabled'});
  await page.getByRole('button',{name:'导出',exact:true}).click();await page.screenshot({path:path.join(out,'export-mobile.png'),animations:'disabled'});await page.getByRole('button',{name:'关闭',exact:true}).click();
  await open('/analysis-history');await page.screenshot({path:path.join(out,'records-mobile.png'),animations:'disabled'});
  await page.setViewportSize({width:1440,height:1050});
  const boundary='qa-records-folder';const parts=[];const content='RamanShift(cm^-1)\tIntensity\n'+Array.from({length:80},(_,i)=>`${400+i*15}\t${10+Math.sin(i/5)+i/4}`).join('\n');
  for(const name of ['a.txt','b.txt']){parts.push(`--${boundary}\r\nContent-Disposition: form-data; name="paths"\r\n\r\nQA-folder/${name}\r\n`);parts.push(`--${boundary}\r\nContent-Disposition: form-data; name="files"; filename="${name}"\r\nContent-Type: text/plain\r\n\r\n${content}\r\n`);}parts.push(`--${boundary}--\r\n`);
  const uploaded=await context.request.post(api+'/ai-workflow-batches/upload',{headers:{...headers,'Content-Type':'multipart/form-data; boundary='+boundary},data:Buffer.from(parts.join(''))});assert.equal(uploaded.status(),200,await uploaded.text());const batch=await uploaded.json();
  await open('/analysis-history');await page.getByRole('button',{name:'批量处理',exact:true}).click();await page.getByRole('link',{name:'打开批量处理',exact:true}).first().click();
  await page.waitForURL(url=>url.searchParams.get('task')===batch.items[0].workflow_id);await page.getByRole('button',{name:'生成预处理方案',exact:true}).click();
  const batchStarted=page.waitForResponse(response=>response.url().endsWith('/ai-workflow-batches/'+batch.id+'/execute')&&response.request().method()==='POST');
  await page.getByRole('button',{name:/按当前方案批量处理/}).click();const started=await batchStarted;assert.equal(started.status(),200,await started.text());let finished;
  for(let i=0;i<120;i++){finished=await req('/ai-workflow-batches/'+batch.id);if(!finished.active)break;await page.waitForTimeout(100);}assert.equal(finished.counts.completed,2);
  const pending=await req('/analysis-records/tasks');assert.equal(pending.batches.find(item=>item.id===batch.id).counts.completed,2);
  const before=(await req('/ai-workflows')).length;
  const signal='RamanShift(cm^-1)\tIntensity\n'+Array.from({length:401},(_,i)=>`${200+i*10}\t${10+Math.exp(-(((i-80)/10)**2))*80}`).join('\n');
  const moduleJobs=[];
  for(const slug of ['library-matching','structure-generation','ssnet']){
   const sourceUpload=await context.request.post(api+'/'+slug+'/sources/upload',{headers,multipart:{file:{name:'qa-reference.txt',mimeType:'text/plain',buffer:Buffer.from(signal)}}});assert.equal(sourceUpload.status(),200,await sourceUpload.text());const source=await sourceUpload.json();let created;
   if(slug==='ssnet'){
    const training=await req('/ssnet/train',{name:'QA records model',standards:[{source_id:source.id}],unit_confirmed:true,points:128,epochs:1,samples_per_epoch:32,rf_samples:32,trees:10});let trained;
    for(let i=0;i<120;i++){trained=await req('/ssnet/jobs/'+training.id);if(!['queued','running'].includes(trained.status))break;await page.waitForTimeout(100);}assert.equal(trained.status,'completed',trained.error);
    created=await req('/ssnet/predict',{source_id:source.id,model_id:trained.id,unit_confirmed:true});
   }else created=await req('/'+slug+'/jobs',{source_id:source.id,unit_confirmed:true,...(slug==='library-matching'?{preprocessing_mode:'prepared'}:{})});
   let job;for(let i=0;i<120;i++){job=await req('/'+slug+'/jobs/'+created.id);if(!['queued','running'].includes(job.status))break;await page.waitForTimeout(100);}assert.equal(job.status,'completed',job.error);assert.ok(job.analysis_run_id);
   await open('/'+(slug==='ssnet'?'spectral-unmixing':slug)+'?job='+job.id);await page.getByText('已自动记录',{exact:true}).waitFor();assert.equal(await page.getByRole('button',{name:'保存分析结果',exact:true}).count(),0);
   moduleJobs.push(job);
  }
  assert.equal((await req('/ai-workflows')).length,before);
  const all=(await req('/analysis-runs')).data.runs;for(const job of moduleJobs)assert.equal(all.filter(run=>run.id===job.analysis_run_id).length,1);
  assert.deepEqual(errors,[]);console.log('RECORDS_FLOW_UI_OK',JSON.stringify({stages:3,noTaskSidebar:true,automaticRecord:true,sameTxtAndPng:true,sharedResultSameRecord:true,draftResume:true,refinementApplied:true,mobile:true,errors}));
 }catch(error){if(page){await page.screenshot({path:path.join(out,'error.png')}).catch(()=>{});await fs.writeFile(path.join(out,'error-text.txt'),await page.locator('body').innerText()).catch(()=>{});}throw error;}
 finally{await context.close();await browser.close();}
}
main().catch(error=>{console.error(error);process.exitCode=1;});
