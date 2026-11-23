/* Real preprocessing and exports, isolated database and QA services on 5001/5174. */
const {chromium}=require('playwright'),assert=require('assert/strict'),fs=require('fs/promises'),path=require('path'),{spawnSync}=require('child_process');
async function main(){
 const out=path.resolve(__dirname,'../../logs/spectrum-export-ui');await fs.mkdir(out,{recursive:true});
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH});
 const context=await browser.newContext({viewport:{width:1440,height:1050},locale:'zh-CN'});let page;
 try{
  const api='http://127.0.0.1:5001/api',ui='http://127.0.0.1:5174/preprocessing';
  const registration=await context.request.post(api+'/auth/register',{data:{username:'qa_export_'+Date.now(),password:'isolated-export-qa'}});assert.equal(registration.status(),200);
  const auth=(await registration.json()).data,headers={Authorization:'Bearer '+auth.token};
  async function req(route,data,method){const response=await context.request.fetch(api+route,{headers,data,method:method||(data?'POST':'GET')});assert.equal(response.status(),200,await response.text());return response.json();}
  const signal=Buffer.from('RamanShift(cm^-1)\tIntensity\n'+Array.from({length:120},(_,i)=>`${400+i*12.123456789}\t${10+i/10+Math.exp(-(((i-50)/5)**2))*50}`).join('\n'));
  const boundary='batch-export-qa',parts=[];
  for(const name of ['QA-export/a.txt','QA-export/sub/a.txt','QA-export/c.txt']) parts.push(Buffer.from(`--${boundary}\r\nContent-Disposition: form-data; name="paths"\r\n\r\n${name}\r\n--${boundary}\r\nContent-Disposition: form-data; name="files"; filename="a.txt"\r\nContent-Type: text/plain\r\n\r\n`),signal,Buffer.from('\r\n'));
  parts.push(Buffer.from(`--${boundary}--\r\n`));const uploaded=await context.request.post(api+'/ai-workflow-batches/upload',{headers:{...headers,'Content-Type':'multipart/form-data; boundary='+boundary},data:Buffer.concat(parts)});assert.equal(uploaded.status(),200,await uploaded.text());const batch=await uploaded.json();
  async function processTask(id){const version=(await req(`/ai-workflows/${id}/recommend`,{goal:'默认预处理',phase:'preprocess',allow_ai:false})).version;await req(`/ai-workflows/${id}/versions/${version.id}/execute`,{});for(let n=0;n<100;n++){const value=await req(`/ai-workflows/${id}/versions/${version.id}`);if(value.status==='completed')return value;assert.ok(['queued','running'].includes(value.status),value.error);await new Promise(resolve=>setTimeout(resolve,50));}throw Error('Processing timed out');}
  const first=await processTask(batch.items[0].workflow_id),second=await processTask(batch.items[1].workflow_id);
  await req('/analysis-runs/'+second.analysis_run_id,undefined,'DELETE'); // Completed trace retained, no result row.
  await req(`/ai-workflows/${batch.items[0].workflow_id}/recommend`,{goal:'新的待应用方案',phase:'preprocess',allow_ai:false}); // Must not export this draft.
  const project=(await req('/projects',{name:'QA export shared'})).data.project;
  await req(`/analysis-runs/${first.analysis_run_id}/warehouse`,{project_id:project.id,confirm_sharing:true});
  await context.addInitScript(token=>{localStorage.setItem('ramancloud_auth_token',token);localStorage.setItem('ramancloud_language','zh');localStorage.setItem('ramancloud_theme','light');},auth.token);
  page=await context.newPage();page.setDefaultTimeout(30000);const errors=[];page.on('pageerror',error=>errors.push(error.message));
  const open=async route=>{await page.goto(ui+route);await page.locator('.welcome-screen.is-hidden').waitFor({state:'attached'});};
  async function saveDownload(label,file){const event=page.waitForEvent('download');await page.getByRole('dialog').getByRole('button',{name:label,exact:true}).click();const download=await event;const target=path.join(out,file);await download.saveAs(target);return {target,bytes:await fs.readFile(target)};}
  function archive(target){const python=path.resolve(__dirname,'../../.venv/Scripts/python.exe');const result=spawnSync(python,['-c','import sys,zipfile,json,base64; z=zipfile.ZipFile(sys.argv[1]); assert z.testzip() is None; print(json.dumps({n:base64.b64encode(z.read(n)).decode() for n in z.namelist()}))',target]);assert.equal(result.status,0,result.stderr.toString());return Object.fromEntries(Object.entries(JSON.parse(result.stdout)).map(([key,value])=>[key,Buffer.from(value,'base64')]));}
  await open('/analysis-history?run='+first.analysis_run_id);await page.getByRole('heading',{name:'QA-export/a.txt',exact:true}).waitFor();
  await page.getByRole('button',{name:'导出',exact:true}).click();const singleTxt=await saveDownload('处理后光谱 TXT','single-processed.txt');const singlePng=await saveDownload('处理后光谱 PNG','single-processed.png');await page.getByRole('button',{name:'关闭',exact:true}).click();
  const before=(await req('/ai-workflows/'+batch.items[0].workflow_id)).versions.length;
  await page.getByRole('button',{name:'批量导出',exact:true}).click();
  const selected=page.getByRole('checkbox',{name:'选择 QA-export/a.txt',exact:true});assert.ok(await selected.isEnabled(),'Shared results must remain exportable');await selected.check();
  await page.getByRole('button',{name:'导出所选',exact:true}).click();await page.getByRole('dialog').getByRole('checkbox',{name:'原始光谱',exact:true}).check();await page.getByRole('dialog').getByRole('checkbox',{name:'PNG 图片',exact:true}).check();
  await page.screenshot({path:path.join(out,'export-options.png'),animations:'disabled'});
  const subset=archive((await saveDownload('下载 ZIP','history-selected.zip')).target),manifest=JSON.parse(subset['manifest.json']);
  assert.equal(manifest.spectra.length,1);assert.equal(manifest.spectra[0].version,1);assert.equal(Object.keys(subset).length,5);
  assert.ok(subset[manifest.spectra[0].files.find(name=>name.endsWith('processed_V1.txt'))].equals(singleTxt.bytes),'Single and batch TXT must match');
  assert.ok(subset[manifest.spectra[0].files.find(name=>name.endsWith('processed_V1.png'))].equals(singlePng.bytes),'Single and batch PNG must match');
  await page.getByRole('button',{name:'关闭',exact:true}).click();await page.getByRole('button',{name:'取消',exact:true}).click();
  await page.getByRole('button',{name:'导出批次 QA-export',exact:true}).click();await page.getByRole('dialog').getByRole('checkbox',{name:'PNG 图片',exact:true}).check();
  const whole=archive((await saveDownload('下载 ZIP','history-batch.zip')).target),wholeManifest=JSON.parse(whole['manifest.json']);
  assert.equal(wholeManifest.spectra.length,2);assert.equal(wholeManifest.skipped.length,1);assert.equal(Object.keys(whole).length,5);
  assert.equal(new Set(Object.keys(whole)).size,5);assert.ok(wholeManifest.spectra.some(item=>item.workflow_id===batch.items[1].workflow_id));
  for(const name of Object.keys(whole).filter(name=>name.endsWith('.png'))){assert.equal(whole[name].readUInt32BE(16),2400);assert.equal(whole[name].readUInt32BE(20),1440);}
  await page.getByRole('button',{name:'关闭',exact:true}).click();
  await open(`/ai-analysis?batch=${batch.id}&task=${batch.items[0].workflow_id}`);await page.getByRole('button',{name:'批量导出',exact:true}).waitFor();await page.getByRole('button',{name:'批量导出',exact:true}).click();
  const ai=archive((await saveDownload('下载 ZIP','ai-batch.zip')).target),aiManifest=JSON.parse(ai['manifest.json']);assert.equal(aiManifest.spectra.length,2);assert.equal(aiManifest.skipped.length,1);
  for(const item of aiManifest.spectra){const counterpart=wholeManifest.spectra.find(record=>record.workflow_id===item.workflow_id);assert.ok(counterpart);assert.equal(item.version_id,counterpart.version_id);assert.ok(ai[item.files[0]].equals(whole[counterpart.files.find(name=>name.endsWith('.txt'))]));}
  await page.getByRole('button',{name:'关闭',exact:true}).click();
  // Original-only export includes the unfinished spectrum; uncheck one file to export a subset.
  await page.getByRole('checkbox',{name:'选择光谱 QA-export/sub/a.txt',exact:true}).uncheck();
  await page.getByRole('button',{name:'批量导出',exact:true}).click();await page.getByRole('dialog').getByRole('checkbox',{name:'原始光谱',exact:true}).check();await page.getByRole('dialog').getByRole('checkbox',{name:'处理后光谱',exact:true}).uncheck();
  const originals=JSON.parse(archive((await saveDownload('下载 ZIP','originals-subset.zip')).target)['manifest.json']);assert.equal(originals.spectra.length,2);assert.equal(originals.skipped.length,0);assert.ok(originals.spectra.some(item=>item.workflow_id===batch.items[2].workflow_id));
  await page.setViewportSize({width:390,height:844});await page.screenshot({path:path.join(out,'export-mobile.png'),animations:'disabled'});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await page.getByRole('button',{name:'关闭',exact:true}).click();
  assert.equal((await req('/ai-workflows/'+batch.items[0].workflow_id)).versions.length,before);
  assert.equal((await req('/analysis-runs')).data.runs.some(run=>run.id===second.analysis_run_id),false);
  assert.deepEqual(errors,[]);console.log('SPECTRUM_EXPORT_UI_OK',JSON.stringify({twoPages:true,subset:true,txtPrecision:true,pngMatchesSingle:true,pngSize:[2400,1440],duplicateNames:true,shared:true,oldTrace:true,unfinishedSkipped:true,originalOnly:true,noMutation:true,mobile:true}));
 }catch(error){if(page){await page.screenshot({path:path.join(out,'error.png')}).catch(()=>{});await fs.writeFile(path.join(out,'error.txt'),await page.locator('body').innerText()).catch(()=>{});}throw error;}
 finally{await context.close();await browser.close();}
}
main().catch(error=>{console.error(error);process.exitCode=1;});
