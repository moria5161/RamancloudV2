/* Isolated services; actual storage/preprocessing, synthetic model outputs. */
const {chromium}=require('playwright'),fs=require('fs/promises'),path=require('path'),assert=require('assert/strict');
async function main(){
 const out=path.resolve(__dirname,'../../logs/workspaces-ui');await fs.mkdir(out,{recursive:true});
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH});
 const context=await browser.newContext({viewport:{width:1500,height:1050},locale:'zh-CN'});let page;
 try{
  const api=process.env.RAMANCLOUD_TEST_API||'http://127.0.0.1:5001/api',ui=process.env.RAMANCLOUD_TEST_UI||'http://127.0.0.1:5174/preprocessing';
  const registration=await context.request.post(api+'/auth/register',{data:{username:'qa_workspace_'+Date.now(),password:'isolated-workspace-qa'}});assert.equal(registration.status(),200);
  const auth=(await registration.json()).data,headers={Authorization:'Bearer '+auth.token};
  async function req(route,data){const response=data===undefined?await context.request.get(api+route,{headers}):await context.request.post(api+route,{headers,data});assert.equal(response.status(),200,await response.text());return response.json();}
  const signal=Buffer.from('RamanShift(cm^-1)\tIntensity\n'+Array.from({length:401},(_,i)=>`${200+i*10}\t${10+i/50+Math.exp(-(((i-80)/8)**2))*60}`).join('\n'));
  const input={name:'qa-workspace.txt',mimeType:'text/plain',buffer:signal};
  async function source(slug){const response=await context.request.post(api+'/'+slug+'/sources/upload',{headers,multipart:{file:input}});assert.equal(response.status(),200,await response.text());return response.json();}
  async function waitJob(slug,id){for(let i=0;i<200;i++){const job=await req('/'+slug+'/jobs/'+id);if(!['queued','running'].includes(job.status)){assert.equal(job.status,'completed',job.error);return job;}await new Promise(resolve=>setTimeout(resolve,30));}throw Error('Job timeout');}
  await context.addInitScript(({token,id})=>{localStorage.setItem('ramancloud_auth_token',token);localStorage.setItem('ramancloud_language:'+id,'zh');localStorage.setItem('ramancloud_theme','light');},{token:auth.token,id:auth.user.id});
  await context.route('**/preprocessing/api/**',async route=>{
    const url=new URL(route.request().url());
    await route.fulfill({response:await route.fetch({url:api+url.pathname.replace('/preprocessing/api','')+url.search})});
  });
  page=await context.newPage();page.setDefaultTimeout(30000);const errors=[];page.on('pageerror',error=>errors.push(error.message));
  const active=()=>page.locator('[data-analysis-workspace]:not([hidden])');
  async function open(route){await page.goto(ui+route);await page.locator('.welcome-screen.is-hidden').waitFor({state:'attached'});}
  async function nav(label){await page.getByRole('link',{name:label,exact:true}).first().click();}
  await open('/');
  await page.locator('.home-branch-links').getByRole('link',{name:'光谱到结构',exact:true}).waitFor();
  const task=await req('/ai-workflows/source',{demo:'tutorial'});
  await open('/ai-analysis?task='+task.id);await active().getByLabel('起始波数',{exact:true}).fill('400');
  await nav('库匹配');await active().getByRole('heading',{name:'库匹配',exact:true}).waitFor();
  const qa=await page.evaluate(async()=>{const {currentQATask,screenContext}=await import('/preprocessing/src/components/qaContext.js');return {task:currentQATask(),screen:screenContext(false)};});assert.equal(qa.task,null);assert.equal(qa.screen.state.module,'库匹配');
  await nav('智能光谱处理');await active().getByLabel('起始波数',{exact:true}).waitFor();assert.equal(await active().getByLabel('起始波数',{exact:true}).inputValue(),'400');assert.ok(page.url().includes(task.id));
  await active().getByRole('button',{name:'新建分析',exact:true}).click();await page.waitForFunction(()=>document.querySelector('[data-analysis-workspace]:not([hidden]) [data-qa-task]')?.dataset.qaTask==='');assert.equal(new URL(page.url()).search,'');await req('/ai-workflows/'+task.id);
  await nav('库匹配');await active().locator('input[type=file]').setInputFiles(input);await active().getByText('qa-workspace.txt',{exact:true}).first().waitFor();
  await active().getByRole('checkbox',{name:'确认横轴为拉曼位移 cm⁻¹',exact:true}).check();await active().getByRole('checkbox',{name:'按模型流程预处理（AirNet + PEER）',exact:true}).uncheck();await active().getByLabel('库匹配候选数量',{exact:true}).selectOption('5');
  await nav('光谱到结构');await active().locator('input[placeholder*="C6H6"]').fill('C6H6');
  const newlyUploaded=await req('/ai-workflows/source',{demo:'bacteria'});
  await nav('混合物解析');await active().getByRole('tab',{name:'建立标准品模型',exact:true}).click();await active().getByLabel('标准品物质名称',{exact:true}).fill('QA ethanol');await active().getByLabel('SSnet 模型点数',{exact:true}).selectOption('1024');
  await nav('光谱到结构');assert.equal(await active().locator('input[placeholder*="C6H6"]').inputValue(),'C6H6');
  await nav('库匹配');assert.equal(await active().getByLabel('库匹配候选数量',{exact:true}).inputValue(),'5');assert.ok(await active().getByRole('checkbox',{name:'确认横轴为拉曼位移 cm⁻¹',exact:true}).isChecked());
  await active().getByRole('tab',{name:'预处理结果',exact:true}).click();await active().locator(`option[value="${newlyUploaded.id}"]`).waitFor({state:'attached'});await active().getByRole('tab',{name:'本地上传',exact:true}).click();
  // Delay the response to prove hidden-page completion cannot navigate away.
  await page.route('**/library-matching/jobs',async route=>{if(route.request().method()==='POST'){const response=await route.fetch({url:api+'/library-matching/jobs'});await new Promise(resolve=>setTimeout(resolve,450));await route.fulfill({response});}else await route.fallback();});
  await active().getByRole('button',{name:'开始库匹配',exact:true}).click();await nav('光谱到结构');await page.waitForTimeout(1700);assert.ok(page.url().includes('/structure-generation'));
  await nav('库匹配');await active().getByRole('group',{name:'库匹配候选',exact:true}).waitFor();const libraryId=new URL(page.url()).searchParams.get('job');assert.ok(libraryId);const library=await waitJob('library-matching',libraryId);
  await page.unroute('**/library-matching/jobs');
  await active().getByRole('button',{name:'新建分析',exact:true}).click();assert.equal(await active().getByLabel('库匹配候选数量',{exact:true}).inputValue(),'3');assert.equal(await active().locator('.sg-selected-source').count(),0);assert.equal(await active().locator('.lm-candidates').count(),0);
  await nav('混合物解析');assert.equal(await active().getByLabel('标准品物质名称',{exact:true}).inputValue(),'QA ethanol');assert.equal(await active().getByLabel('SSnet 模型点数',{exact:true}).inputValue(),'1024');
  await active().getByRole('button',{name:'新建分析',exact:true}).click();assert.equal(await active().getByRole('tab',{name:'解析混合谱',exact:true}).getAttribute('aria-selected'),'true');assert.equal(await active().getByLabel('标准品物质名称',{exact:true}).count(),0);
  await nav('高光谱处理');await active().getByRole('button',{name:'成像示例',exact:true}).click();await page.waitForFunction(()=>JSON.parse(document.querySelector('[data-analysis-workspace]:not([hidden]) [data-qa-state]').dataset.qaState).status==='loaded');const hyperState=await active().locator('[data-qa-state]').getAttribute('data-qa-state');
  await nav('光谱到结构');await nav('高光谱处理');assert.equal(await active().locator('[data-qa-state]').getAttribute('data-qa-state'),hyperState);
  await active().getByRole('button',{name:'新建分析',exact:true}).click();await page.waitForFunction(()=>JSON.parse(document.querySelector('[data-analysis-workspace]:not([hidden]) [data-qa-state]').dataset.qaState).status==='empty');
  const sgSource=await source('structure-generation');const structure=await waitJob('structure-generation',(await req('/structure-generation/jobs',{source_id:sgSource.id,unit_confirmed:true})).id);
  const mxSource=await source('ssnet');const model=await waitJob('ssnet',(await req('/ssnet/train',{name:'QA standard',standards:[{source_id:mxSource.id}],unit_confirmed:true,points:128,epochs:1,samples_per_epoch:32,rf_samples:32,trees:10})).id);
  const mixture=await waitJob('ssnet',(await req('/ssnet/predict',{source_id:mxSource.id,model_id:model.id,unit_confirmed:true})).id);
  const failed={...model,id:'test-failed-standard',name:'Failed standard',status:'failed',error:'Isolated standard training failure'};
  const queued={...model,id:'test-queued-standard',name:'Queued standard',status:'queued'};
  const ssnetRecords=/\/ssnet\/jobs(?:\/test-failed-standard)?$/;
  await page.route(ssnetRecords,async route=>{
    const pathname=new URL(route.request().url()).pathname;
    if(pathname.endsWith('/test-failed-standard')){await route.fulfill({json:failed});return;}
    const response=await route.fetch({url:api+'/ssnet/jobs'});
    await route.fulfill({json:[failed,queued,...await response.json()]});
  });
  await open('/spectral-unmixing?job='+failed.id);
  const trainingRecords=active().getByLabel('SSnet 任务记录',{exact:true});
  await trainingRecords.locator(`option[value="${model.id}"]`).waitFor({state:'attached'});
  assert.equal(await trainingRecords.locator(`option[value="${queued.id}"]`).count(),1);
  assert.equal(await trainingRecords.inputValue(),failed.id);
  await active().getByRole('alert').filter({hasText:failed.error}).waitFor();
  await active().getByRole('button',{name:'重新排队',exact:true}).waitFor();
  await trainingRecords.selectOption('');
  await trainingRecords.locator(`option[value="${failed.id}"]`).waitFor({state:'detached'});
  await page.unroute(ssnetRecords);
  await open('/structure-generation?job='+structure.id);await active().locator('.sg-candidate').nth(1).click();
  await nav('库匹配');await nav('光谱到结构');assert.equal(await active().locator('.sg-candidate').nth(1).getAttribute('aria-pressed'),'true');assert.ok(page.url().includes(structure.id));
  await active().getByRole('button',{name:'新建分析',exact:true}).click();await active().locator('input[placeholder*="C6H6"]').waitFor();assert.equal(await active().locator('input[placeholder*="C6H6"]').inputValue(),'');assert.equal(await active().locator('.sg-live-results').count(),0);
  await open('/analysis-history?run='+library.analysis_run_id);await page.locator('.history-model-result .lm-candidate').first().waitFor();assert.equal(await page.getByRole('button',{name:'叠加对比',exact:true}).count(),0);assert.ok(await page.locator('.dw-module-record .dw-record-type-icon').count());
  const before=await page.locator('.lm-comparison .js-plotly-plot').evaluate(plot=>plot.data[0].y);
  assert.equal(await page.locator('.dw-record-spectra .js-plotly-plot').count(),2);
  await page.locator('.lm-candidate').nth(1).click();await page.waitForTimeout(100);const after=await page.locator('.lm-comparison .js-plotly-plot').evaluate(plot=>plot.data[0].y);assert.notDeepEqual(before,after);await page.screenshot({path:path.join(out,'history-library.png'),animations:'disabled'});
  await page.getByRole('button',{name:'匹配设置',exact:true}).click();await page.getByRole('heading',{name:'匹配设置 · PeakNet',exact:true}).waitFor();
  await open('/analysis-history?run='+structure.analysis_run_id);
  await page.getByRole('heading',{name:structure.source_name+' · 光谱到结构',exact:true}).waitFor();
  assert.equal(await page.getByLabel('分析类型',{exact:true}).inputValue(),'structure_generation');
  await page.locator('.sg-candidate').nth(1).click();await page.locator('.sg-candidate-detail h3').getByText('C2H6O',{exact:true}).waitFor();assert.equal(await page.getByRole('button',{name:'原始',exact:true}).count(),0);assert.ok(await page.locator('.sg-candidate img').count());await page.screenshot({path:path.join(out,'history-structures.png'),animations:'disabled'});
  assert.equal(await page.locator('.dw-record-spectra .js-plotly-plot').count(),2);
  await page.getByRole('button',{name:'生成设置',exact:true}).click();await page.getByRole('heading',{name:'生成设置 · Vib2Mol',exact:true}).waitFor();
  await open('/analysis-history?run='+mixture.analysis_run_id);await page.locator('.history-mixture-result .js-plotly-plot').waitFor();assert.equal(await page.locator('.history-mixture-result .js-plotly-plot').evaluate(plot=>plot.data.length),3);await page.getByRole('button',{name:'估计背景',exact:true}).click();assert.equal(await page.locator('.history-mixture-result .js-plotly-plot').evaluate(plot=>plot.data.length),2);
  await page.locator('.dw-record-spectra .js-plotly-plot').waitFor();
  await page.getByRole('button',{name:'解析信息',exact:true}).click();await page.getByRole('heading',{name:'解析信息 · SSnet (U-Net ECA + Random Forest)',exact:true}).waitFor();
  await page.getByText('训练轮次',{exact:true}).waitFor();
  const wave=Array.from({length:80},(_,i)=>400+i*10),spectra=Array.from({length:4},(_,pixel)=>wave.map((x,i)=>30+pixel*40+i*.2+(pixel+1)*30*Math.exp(-(((i-35)/5)**2))));
  const steps=[{type:'denoise',method:'sg',params:{window_size:7,order:2}}];
  const single=(await req('/process',{wavenumber:wave,intensity:spectra[0],source_name:'QA single',steps,save_history:true})).data.analysis_run;
  async function checkSpectrum(runId) {
    await open('/analysis-history?run='+runId);
    const plot=page.locator('.dw-chart .js-plotly-plot');
    await plot.waitFor();
    const values=await plot.evaluate(chart=>chart.data.map(trace=>trace.y));
    assert.equal(values.length,2);
    assert.notDeepEqual(values[0],values[1]);
    await page.getByRole('button',{name:'处理过程',exact:true}).click();
    await page.getByRole('heading',{name:/降噪 · Savitzky-Golay/}).waitFor();
    assert.equal(await page.locator('.dw-step dd').first().textContent(),'7');
  }
  await checkSpectrum(single.id);
  const form=new FormData();
  for(const name of ['first.txt','second.txt']) {
    form.append('paths','history-test/'+name);
    form.append('files',new Blob([signal],{type:'text/plain'}),name);
  }
  const upload=await context.request.post(api+'/ai-workflow-batches/upload',{headers,multipart:form});
  assert.equal(upload.status(),200,await upload.text());
  const batch=await upload.json(),[first]=batch.items;
  const template=await req('/ai-workflows/'+first.workflow_id+'/versions',{steps,goal:'Verify batch run settings'});
  await req('/ai-workflow-batches/'+batch.id+'/execute',{template_workflow_id:first.workflow_id,template_version_id:template.id,workflow_ids:batch.items.map(item=>item.workflow_id)});
  let completed;
  for(let i=0;i<100;i++){
    completed=await req('/ai-workflow-batches/'+batch.id);
    if(!completed.active)break;
    await new Promise(resolve=>setTimeout(resolve,100));
  }
  assert.equal(completed.counts.completed,2);
  for(const item of completed.items) {
    const version=await req('/ai-workflows/'+item.workflow_id+'/versions/'+item.version_id);
    await checkSpectrum(version.analysis_run_id);
  }
  const cube=(await req('/process-hyperspectral',{wavenumber:wave,spectra,shape:[2,2,80],mode:'imaging',source_name:'QA cube',save_history:true,steps:[{type:'baseline',method:'airpls',params:{lam:10000,diff_order:2}}]})).data;
  const rid=cube.analysis_run.id;await open('/analysis-history?run='+rid);await page.locator('[data-hyper-role=original] .js-plotly-plot').waitFor();await page.locator('[data-hyper-role=processed] .js-plotly-plot').waitFor();
  const rawZ=await page.locator('[data-hyper-role=original] .js-plotly-plot').evaluate(plot=>plot.data[0].z),processedZ=await page.locator('[data-hyper-role=processed] .js-plotly-plot').evaluate(plot=>plot.data[0].z);assert.notDeepEqual(rawZ,processedZ);
  assert.deepEqual(await page.locator('.dw-hyper-images .js-plotly-plot').evaluateAll(plots=>plots.map(plot=>[plot.data[0].zmin,plot.data[0].zmax])),Array(2).fill([Math.min(...rawZ.flat(),...processedZ.flat()),Math.max(...rawZ.flat(),...processedZ.flat())]));
  const modes=page.getByRole('navigation',{name:'高光谱结果视图'});await modes.getByRole('button',{name:'原始',exact:true}).click();assert.equal(await page.locator('[data-hyper-role=processed]').count(),0);assert.deepEqual(await page.locator('[data-hyper-role=original] .js-plotly-plot').evaluate(plot=>plot.data[0].z),rawZ);
  await modes.getByRole('button',{name:'处理后',exact:true}).click();assert.equal(await page.locator('[data-hyper-role=original]').count(),0);assert.deepEqual(await page.locator('[data-hyper-role=processed] .js-plotly-plot').evaluate(plot=>plot.data[0].z),processedZ);
  await modes.getByRole('button',{name:'对比',exact:true}).click();await page.locator('[data-hyper-role=original] .js-plotly-plot').evaluate(plot=>plot.emit('plotly_click',{points:[{x:0,y:0}]}));await page.locator('.dw-pixel-result .js-plotly-plot').waitFor();await page.waitForFunction(()=>document.querySelector('.dw-pixel-result .js-plotly-plot')?.data?.length===2);await page.screenshot({path:path.join(out,'history-hyperspectral.png'),animations:'disabled'});
  await page.setViewportSize({width:390,height:844});await page.waitForTimeout(250);assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await page.screenshot({path:path.join(out,'history-mobile.png'),animations:'disabled'});
  await page.setViewportSize({width:1500,height:1050});
  const series=(await req('/process-hyperspectral',{wavenumber:wave,spectra,mode:'time_series',source_name:'QA time series',save_history:true,steps:[{type:'baseline',method:'airpls',params:{lam:10000,diff_order:2}}]})).data;
  await open('/analysis-history?run='+series.analysis_run.id);await page.locator('[data-hyper-role=original] .js-plotly-plot').waitFor();await page.locator('[data-hyper-role=processed] .js-plotly-plot').waitFor();
  const seriesRaw=await page.locator('[data-hyper-role=original] .js-plotly-plot').evaluate(plot=>plot.data[0].z),seriesProcessed=await page.locator('[data-hyper-role=processed] .js-plotly-plot').evaluate(plot=>plot.data[0].z);assert.notDeepEqual(seriesRaw,seriesProcessed);
  assert.equal(await page.getByLabel('成像波数',{exact:true}).count(),0);await page.getByRole('navigation',{name:'高光谱结果视图'}).getByRole('button',{name:'处理后',exact:true}).click();assert.equal(await page.locator('[data-hyper-role=original]').count(),0);
  await page.setViewportSize({width:390,height:844});await open('/analysis-history?run='+structure.analysis_run_id);await page.locator('.history-model-result .sg-candidate').first().waitFor();await page.waitForTimeout(150);assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await page.screenshot({path:path.join(out,'structure-mobile.png'),animations:'disabled'});
  await page.setViewportSize({width:1500,height:1050});
  await page.locator('.settings-trigger').click();
  await page.locator('.settings-popover').getByRole('button',{name:'English',exact:true}).click();
  await page.locator('.settings-trigger').click();
  await page.getByRole('heading',{name:structure.source_name+' · Spectrum to Structure',exact:true}).waitFor();
  await nav('Spectrum to Structure');
  await active().getByRole('heading',{name:'Spectrum to Structure',exact:true}).waitFor();
  assert.deepEqual(errors,[]);console.log('WORKSPACES_HISTORY_UI_OK',JSON.stringify({fiveWorkspaces:true,unfinishedPreserved:true,hiddenAsyncNavigation:true,completedCandidatePreserved:true,newAnalysisReset:true,activeQaOnly:true,libraryCandidates:true,structures:true,mixtureCurves:true,hyperspectralRoles:true,timeSeriesRoles:true,sharedColorScale:true,pixelComparison:true,mobile:true}));
 }catch(error){if(page){await page.screenshot({path:path.join(out,'error.png')}).catch(()=>{});await fs.writeFile(path.join(out,'error.txt'),await page.locator('body').innerText()).catch(()=>{});}throw error;}
 finally{await context.unrouteAll({behavior:'ignoreErrors'});await context.close();await browser.close();}
}
main().catch(error=>{console.error(error);process.exitCode=1;});
