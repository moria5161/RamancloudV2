/* Run only against the isolated QA service on 5001/5174. Uses real storage/deletion. */
const {chromium} = require('playwright');
const assert = require('assert/strict');
const fs = require('fs/promises');
const path = require('path');
async function main() {
  const out = path.resolve(__dirname, '../../logs/records-selection-ui');
  await fs.mkdir(out, {recursive:true});
  const browser = await chromium.launch({headless:true, executablePath:process.env.CHROME_PATH});
  const context = await browser.newContext({viewport:{width:1440,height:1000},locale:'zh-CN'});
  let page;
  try {
    const api = 'http://127.0.0.1:5001/api', ui = 'http://127.0.0.1:5174/preprocessing';
    const registered = await context.request.post(api+'/auth/register', {data:{username:'qa_selection_'+Date.now(),password:'isolated-records-qa'}});
    assert.equal(registered.status(),200);
    const auth = (await registered.json()).data, headers = {Authorization:'Bearer '+auth.token};
    async function req(route,data,method) {
      const response = await context.request.fetch(api+route,{method:method || (data ? 'POST':'GET'),headers,data});
      assert.equal(response.status(),200,await response.text());
      return response.json();
    }
    const signal = Buffer.from('RamanShift(cm^-1)\tIntensity\n'+Array.from({length:100},(_,i)=>`${400+i*10}\t${10+i/10+Math.exp(-(((i-40)/4)**2))*20}`).join('\n'));
    async function upload(name) {
      const response = await context.request.post(api+'/ai-workflows/upload',{headers,multipart:{file:{name,mimeType:'text/plain',buffer:signal}}});
      assert.equal(response.status(),200,await response.text()); return response.json();
    }
    async function processTask(task) {
      const version = (await req('/ai-workflows/'+task.id+'/recommend',{goal:'默认预处理',phase:'preprocess',allow_ai:false})).version;
      await req(`/ai-workflows/${task.id}/versions/${version.id}/execute`,{});
      for (let i=0;i<100;i++) {
        const state = await req(`/ai-workflows/${task.id}/versions/${version.id}`);
        if (state.status==='completed') return state;
        assert.ok(['queued','running'].includes(state.status),state.error);
        await new Promise(resolve=>setTimeout(resolve,50));
      }
      throw new Error('QA preprocessing timed out');
    }
    const a=await upload('single-a.txt'), b=await upload('single-b.txt'), shared=await upload('shared.txt'), draft=await upload('draft.txt');
    await processTask(a); const latestA=await processTask(a); await processTask(b); const protectedRun=await processTask(shared);
    const project=(await req('/projects',{name:'QA selection shared'})).data.project;
    await req(`/analysis-runs/${protectedRun.analysis_run_id}/warehouse`,{project_id:project.id,confirm_sharing:true});
    const boundary='records-selection-batch', pieces=[];
    for (const name of ['batch-a.txt','batch-b.txt','notes.txt']) {
      pieces.push(Buffer.from(`--${boundary}\r\nContent-Disposition: form-data; name="paths"\r\n\r\nQA-batch/${name}\r\n--${boundary}\r\nContent-Disposition: form-data; name="files"; filename="${name}"\r\nContent-Type: text/plain\r\n\r\n`),name==='notes.txt'?Buffer.from('invalid input'):signal,Buffer.from('\r\n'));
    }
    pieces.push(Buffer.from(`--${boundary}--\r\n`));
    const uploaded=await context.request.post(api+'/ai-workflow-batches/upload',{headers:{...headers,'Content-Type':'multipart/form-data; boundary='+boundary},data:Buffer.concat(pieces)});
    assert.equal(uploaded.status(),200,await uploaded.text());const batch=await uploaded.json();
    const batchResult=await processTask({id:batch.items[0].workflow_id});
    await context.addInitScript(token=>{localStorage.setItem('ramancloud_auth_token',token);localStorage.setItem('ramancloud_language','zh');localStorage.setItem('ramancloud_theme','light');},auth.token);
    page=await context.newPage(); page.setDefaultTimeout(30000);
    const errors=[]; page.on('pageerror',error=>errors.push(error.message));
    async function open(route='/analysis-history') {await page.goto(ui+route);await page.locator('.welcome-screen.is-hidden').waitFor({state:'attached'});await page.getByRole('button',{name:'批量删除',exact:true}).waitFor();await page.locator('.dw-history-list').getByRole('button').first().waitFor();}
    const list=()=>page.locator('.dw-history-list');
    const state=label=>page.getByRole('navigation',{name:'记录状态'}).getByRole('button',{name:label,exact:true});
    await open();
    assert.equal(await list().getByText('QA-batch/batch-a.txt',{exact:true}).count(),0);
    assert.equal(await page.getByRole('button',{name:'失败 / 已停止',exact:true}).count(),0);
    assert.equal(await page.getByRole('button',{name:'文件夹批次',exact:true}).count(),0);
    await state('未处理').click(); await list().getByText('draft.txt',{exact:true}).waitFor();assert.equal(await list().getByText('single-a.txt',{exact:true}).count(),0);
    await state('已处理').click();await list().getByText('single-a.txt',{exact:true}).waitFor();assert.equal(await list().getByText('draft.txt',{exact:true}).count(),0);
    await state('全部').click();await page.getByRole('button',{name:'批量处理',exact:true}).click();await list().getByText('QA-batch/batch-a.txt',{exact:true}).waitFor();
    await page.screenshot({path:path.join(out,'batch-records.png'),animations:'disabled'});
    await state('未处理').click();await list().getByText('QA-batch/batch-b.txt',{exact:true}).waitFor();assert.equal(await list().getByText('QA-batch/batch-a.txt',{exact:true}).count(),0);
    await list().getByText('QA-batch/notes.txt',{exact:true}).waitFor();
    await state('已处理').click();await list().getByText('QA-batch/batch-a.txt',{exact:true}).waitFor();assert.equal(await list().getByText('QA-batch/batch-b.txt',{exact:true}).count(),0);
    for (const type of ['hyperspectral','mixture_analysis','library_matching','structure_generation']) {
      await page.getByLabel('分析类型',{exact:true}).selectOption(type);
      assert.equal(await page.getByRole('navigation',{name:'单光谱处理方式'}).count(),0);
    }
    await open('/analysis-history?run='+batchResult.analysis_run_id);await page.getByRole('heading',{name:'QA-batch/batch-a.txt',exact:true}).waitFor();
    assert.equal(await page.getByRole('button',{name:'批量处理',exact:true}).getAttribute('aria-pressed'),'true');
    // Reproduce a real legacy batch: saved row removed, completed trace retained.
    await req('/analysis-runs/'+batchResult.analysis_run_id,undefined,'DELETE');
    await open();await page.getByRole('button',{name:'批量处理',exact:true}).click();await state('已处理').click();
    await list().getByRole('button',{name:/QA-batch\/batch-a.txt/}).click();
    await page.getByRole('heading',{name:'QA-batch/batch-a.txt',exact:true}).waitFor();
    await page.waitForFunction(()=>document.querySelector('.js-plotly-plot')?.data?.some(trace=>trace.name==='处理后'));
    assert.deepEqual(await page.locator('.js-plotly-plot').first().evaluate(plot=>plot.data.find(trace=>trace.name==='处理后').y),batchResult.trace.at(-1).after.intensity);
    assert.equal((await req('/analysis-runs')).data.runs.some(run=>run.id===batchResult.analysis_run_id),false);
    await page.screenshot({path:path.join(out,'completed-trace-record.png'),animations:'disabled'});
    await open('/analysis-history?run='+latestA.analysis_run_id);await page.getByRole('heading',{name:'single-a.txt',exact:true}).waitFor();
    await page.getByRole('button',{name:'批量删除',exact:true}).click();
    assert.ok(await page.getByRole('checkbox',{name:'选择 shared.txt',exact:true}).isDisabled());
    await page.getByRole('checkbox',{name:'选择 single-a.txt',exact:true}).check();
    await page.screenshot({path:path.join(out,'selection-desktop.png'),animations:'disabled'});
    page.once('dialog',async dialog=>{assert.match(dialog.message(),/2 条结果版本/);await dialog.dismiss();});
    await page.getByRole('button',{name:'删除所选',exact:true}).click();
    assert.equal((await req('/analysis-runs')).data.runs.filter(run=>run.result.ai_workflow_id===a.id).length,2);
    page.once('dialog',dialog=>dialog.accept());await page.getByRole('button',{name:'删除所选',exact:true}).click();await page.getByText('已删除 2 条记录',{exact:true}).waitFor();
    let all=(await req('/analysis-runs')).data.runs;
    assert.equal(all.filter(run=>run.result.ai_workflow_id===a.id).length,0);
    assert.ok(all.some(run=>run.result.ai_workflow_id===b.id));
    assert.ok(all.some(run=>run.id===protectedRun.analysis_run_id));
    await req('/ai-workflows/'+batch.items[0].workflow_id);
    // Deleting completed records retains their original workflow/source.
    await req('/ai-workflows/'+a.id);
    await page.getByRole('button',{name:'批量删除',exact:true}).click();
    await page.getByRole('checkbox',{name:'选择 single-b.txt',exact:true}).check();
    await page.getByRole('checkbox',{name:'选择 draft.txt',exact:true}).check();
    page.once('dialog',dialog=>dialog.accept());await page.getByRole('button',{name:'删除所选',exact:true}).click();await page.getByText('已删除 2 条记录',{exact:true}).waitFor();
    all=(await req('/analysis-runs')).data.runs;assert.equal(all.some(run=>run.result.ai_workflow_id===b.id),false);
    assert.equal((await context.request.get(api+'/ai-workflows/'+draft.id,{headers})).status(),404);
    await page.getByRole('button',{name:'批量处理',exact:true}).click();await state('未处理').click();
    await page.getByRole('button',{name:'批量删除',exact:true}).click();await page.getByRole('checkbox',{name:'全选当前筛选记录',exact:true}).check();
    assert.equal(await page.getByRole('checkbox',{name:'选择 QA-batch/batch-b.txt',exact:true}).isChecked(),true);
    await state('已处理').click();assert.equal(await page.getByRole('button',{name:'删除所选',exact:true}).isDisabled(),true);
    await page.setViewportSize({width:390,height:844});await page.screenshot({path:path.join(out,'selection-mobile.png'),animations:'disabled'});
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    await page.setViewportSize({width:1440,height:1000});await state('全部').click();
    await page.getByRole('checkbox',{name:'全选当前筛选记录',exact:true}).check();
    const blockedMember=`**/ai-workflow-batches/${batch.id}/items/${batch.items[0].workflow_id}`;
    await page.route(blockedMember,async route=>{
      if (route.request().method()==='DELETE') await route.fulfill({status:409,contentType:'application/json',body:JSON.stringify({detail:'QA concurrent share protection'})});
      else await route.continue();
    });
    page.once('dialog',dialog=>dialog.accept());await page.getByRole('button',{name:'删除所选',exact:true}).click();
    await page.getByText('已删除 2 条记录，1 条未删除',{exact:true}).waitFor();
    await req('/ai-workflows/'+batch.items[0].workflow_id);
    assert.equal((await context.request.get(api+'/ai-workflows/'+batch.items[1].workflow_id,{headers})).status(),404);
    await page.unroute(blockedMember);
    page.once('dialog',dialog=>dialog.dismiss());await page.getByRole('button',{name:'删除批次 QA-batch',exact:true}).click();await req('/ai-workflow-batches/'+batch.id);
    page.once('dialog',dialog=>dialog.accept());await page.getByRole('button',{name:'删除批次 QA-batch',exact:true}).click();await page.getByText('暂无符合条件的记录',{exact:true}).waitFor();
    assert.equal((await context.request.get(api+'/ai-workflow-batches/'+batch.id,{headers})).status(),404);
    const sharedAsset=await req(`/analysis-runs/${protectedRun.analysis_run_id}/warehouse`,{project_id:project.id,confirm_sharing:true});
    const derived=await req('/ai-workflows/source',{dataset_id:sharedAsset.dataset_id});
    await page.goto(ui+'/projects?project='+project.id);await page.getByRole('tab',{name:'共享结果',exact:true}).click();
    page.once('dialog',dialog=>dialog.accept());await page.getByRole('button',{name:'取消共享',exact:true}).click();
    await page.getByRole('button',{name:'取消共享',exact:true}).waitFor({state:'detached'});
    assert.equal((await req('/analysis-runs/'+protectedRun.analysis_run_id)).data.run.is_shared,false);
    await req('/ai-workflows/'+derived.id);
    await open('/analysis-history?run='+protectedRun.analysis_run_id);await page.getByRole('button',{name:'批量删除',exact:true}).click();
    await page.getByRole('checkbox',{name:'选择 shared.txt',exact:true}).check();
    page.once('dialog',dialog=>dialog.accept());await page.getByRole('button',{name:'删除所选',exact:true}).click();await page.getByText('已删除 1 条记录',{exact:true}).waitFor();
    assert.equal((await context.request.get(api+'/analysis-runs/'+protectedRun.analysis_run_id,{headers})).status(),404);
    await req('/ai-workflows/'+derived.id);
    assert.deepEqual(errors,[]);
    console.log('RECORDS_SELECTION_UI_OK',JSON.stringify({singleBatchSeparated:true,allModules:true,deepLinks:true,subsetDeletion:true,allVersions:true,cancel:true,sharedProtection:true,filteredSelectAll:true,partialFailure:true,completedTraces:true,invalidFiles:true,wholeBatchDeletion:true,unshareReferencedResult:true,mobile:true}));
  } catch(error) {
    if(page){await page.screenshot({path:path.join(out,'error.png')}).catch(()=>{});await fs.writeFile(path.join(out,'error.txt'),await page.locator('body').innerText()).catch(()=>{});}throw error;
  } finally {await context.close();await browser.close();}
}
main().catch(error=>{console.error(error);process.exitCode=1;});
