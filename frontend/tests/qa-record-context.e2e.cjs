/* Real permissions and stored spectra on isolated 5001/5174; synthetic model tokens. */
const {chromium}=require('playwright'),assert=require('assert/strict'),fs=require('fs/promises'),path=require('path');
async function main(){
 const out=path.resolve(__dirname,'../../logs/qa-record-context-ui');await fs.mkdir(out,{recursive:true});
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH});
 const context=await browser.newContext({viewport:{width:1440,height:1000},locale:'zh-CN'});let page;
 try{
  const api='http://127.0.0.1:5001/api',ui='http://127.0.0.1:5174/preprocessing';
  const registered=await context.request.post(api+'/auth/register',{data:{username:'qa_qa_context_'+Date.now(),password:'isolated-qa-context'}});assert.equal(registered.status(),200);const auth=(await registered.json()).data,headers={Authorization:'Bearer '+auth.token};
  async function req(route,data){const r=data===undefined?await context.request.get(api+route,{headers}):await context.request.post(api+route,{headers,data});assert.equal(r.status(),200,await r.text());return r.json();}
  const task=await req('/ai-workflows/source',{demo:'tutorial'}),planned=await req('/ai-workflows/'+task.id+'/recommend',{goal:'默认预处理',phase:'preprocess',allow_ai:false});
  let version=planned.version;await req('/ai-workflows/'+task.id+'/versions/'+version.id+'/execute',{});
  for(let i=0;i<100;i++){version=await req('/ai-workflows/'+task.id+'/versions/'+version.id);if(!['queued','running','previewing'].includes(version.status))break;await new Promise(r=>setTimeout(r,50));}assert.equal(version.status,'completed');
  const project=(await req('/projects',{name:'QA assistant context'})).data.project;await req('/analysis-runs/'+version.analysis_run_id+'/warehouse',{project_id:project.id,confirm_sharing:true});
  await context.addInitScript(token=>{localStorage.setItem('ramancloud_auth_token',token);localStorage.setItem('ramancloud_language','zh');localStorage.setItem('ramancloud_theme','light');},auth.token);
  page=await context.newPage();page.setDefaultTimeout(30000);const errors=[];page.on('pageerror',error=>errors.push(error.message));
  async function open(route){await page.goto(ui+route);await page.locator('.welcome-screen.is-hidden').waitFor({state:'attached'});}
  await open('/ai-analysis?task='+task.id+'&version='+version.id);
  let panel=page.locator('.qa-panel');await panel.waitFor();await panel.locator('.qa-consent input').check();
  async function ask(text){const count=await panel.locator('.qa-copy').count(),response=page.waitForResponse(r=>/\/qa-assistant\/(reply|preprocessing-turn)$/.test(r.url())&&r.request().method()==='POST');await panel.getByLabel('问答消息').fill(text);await panel.getByRole('button',{name:'发送',exact:true}).click();const r=await response;assert.equal(r.status(),200);await page.waitForFunction(n=>document.querySelectorAll('.qa-copy').length===n+1&&!document.querySelector('.qa-composer textarea').disabled,count);return {body:r.request().postDataBuffer(),answer:await panel.locator('.qa-answer').last().innerText()};}
  const current=await ask('解释当前处理结果');assert.ok(current.body.includes(Buffer.from(task.id)));assert.ok(current.answer.includes('[comparison]'));const currentEvidence=await req('/qa-assistant/context/'+task.id+'?version_id='+version.id);
  await open('/analysis-history?run='+version.analysis_run_id);await page.locator('[data-qa-run]').waitFor();
  await page.waitForFunction(id=>document.querySelector('[data-qa-run]')?.dataset.qaRun===id,version.analysis_run_id);
  assert.equal(await panel.count(),0);
  const savedEvidence=await req('/qa-assistant/records/'+version.analysis_run_id+'/context');assert.equal(savedEvidence.run_id,version.analysis_run_id);assert.deepEqual(savedEvidence.comparison.after,currentEvidence.comparison.after);
  await page.screenshot({path:path.join(out,'qa-record-desktop.png'),animations:'disabled'});
  await open('/projects?project='+project.id);await page.getByRole('tab',{name:'共享结果',exact:true}).click();await page.getByRole('button',{name:/预览 tutorial_raman.txt/}).click();
  const state=JSON.parse(await page.locator('[data-qa-state]').getAttribute('data-qa-state'));assert.equal(state.section,'共享结果');assert.ok(state.selected_file.filename);assert.equal(state.selected_file.data_kind,'processed');
  await page.setViewportSize({width:390,height:844});assert.equal(await page.locator('.qa-panel, .qa-launch').count(),0);
  await page.screenshot({path:path.join(out,'qa-project-mobile.png'),animations:'disabled'});
  assert.deepEqual(errors,[]);console.log('QA_RECORD_CONTEXT_OK',JSON.stringify({taskEvidence:true,recordEvidence:true,sameStatistics:true,projectSelection:true,assistantHiddenOutsideAnalysis:true,noRealModelCalls:true}));
 }catch(error){if(page){await page.screenshot({path:path.join(out,'error.png')}).catch(()=>{});await fs.writeFile(path.join(out,'error-text.txt'),await page.locator('body').innerText()).catch(()=>{});}throw error;}
 finally{await context.close();await browser.close();}
}
main().catch(error=>{console.error(error);process.exitCode=1;});
