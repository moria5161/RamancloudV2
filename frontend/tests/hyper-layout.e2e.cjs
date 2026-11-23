/* Actual hyperspectral demo + SG processing; isolated QA database on 5001/5174. */
const {chromium}=require('playwright'),assert=require('assert/strict'),fs=require('fs/promises'),path=require('path');
async function main(){
 const out=path.resolve(__dirname,'../../logs/hyper-layout-ui');await fs.mkdir(out,{recursive:true});
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH});
 const context=await browser.newContext({viewport:{width:1600,height:1050},locale:'zh-CN'});let page;
 try{
  const api=process.env.RAMANCLOUD_TEST_API||'http://127.0.0.1:5001/api',ui=process.env.RAMANCLOUD_TEST_UI||'http://127.0.0.1:5174/preprocessing';
  const registered=await context.request.post(api+'/auth/register',{data:{username:'qa_hyper_layout_'+Date.now(),password:'isolated-hyper-qa'}});assert.equal(registered.status(),200);const auth=(await registered.json()).data,headers={Authorization:'Bearer '+auth.token};
  await context.addInitScript(({token,id})=>{localStorage.setItem('ramancloud_auth_token',token);localStorage.setItem('ramancloud_language:'+id,'zh');localStorage.setItem('ramancloud_theme','light');},{token:auth.token,id:auth.user.id});
  await context.route('**/preprocessing/api/**',async route=>{
    const url=new URL(route.request().url());
    await route.fulfill({response:await route.fetch({url:api+url.pathname.replace('/preprocessing/api','')+url.search})});
  });
  page=await context.newPage();page.setDefaultTimeout(30000);const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.goto(ui+'/hyperspectral');await page.locator('.welcome-screen.is-hidden').waitFor({state:'attached'});
  const active=page.locator('[data-analysis-workspace]:not([hidden])');
  const button=active.getByRole('button',{name:'新建分析',exact:true});
  const buttonShape=await button.evaluate(node=>{const icon=node.querySelector('svg').getBoundingClientRect(),label=node.querySelector('span').getBoundingClientRect();return {height:node.getBoundingClientRect().height,display:getComputedStyle(node).display,delta:Math.abs((icon.top+icon.height/2)-(label.top+label.height/2))};});
   assert.ok(['flex','inline-flex'].includes(buttonShape.display));assert.ok(buttonShape.height<=36);assert.ok(buttonShape.delta<=2);
  await page.screenshot({path:path.join(out,'toolbar.png'),animations:'disabled'});
  await active.getByRole('button',{name:'成像示例',exact:true}).click();await page.waitForFunction(()=>JSON.parse(document.querySelector('[data-analysis-workspace]:not([hidden]) [data-qa-state]').dataset.qaState).status==='loaded');
   const slider=active.locator('input[type=range]').first();const min=Number(await slider.getAttribute('min')),max=Number(await slider.getAttribute('max'));const selected=Math.min(max,min+Math.max(0,Math.round(1616-min)));
   const sliceDone=page.waitForResponse(response=>response.url().includes('/hyperspectral-slice/')&&response.status()===200);sliceDone.catch(()=>{});await slider.fill(String(selected));await sliceDone;
  await active.getByRole('button',{name:'去噪',exact:true}).click();
  const response=page.waitForResponse(response=>response.url().endsWith('/process-hyperspectral')&&response.request().method()==='POST');await active.getByRole('button',{name:'运行流程',exact:true}).click();const processedResponse=await response;assert.equal(processedResponse.status(),200,await processedResponse.text());const processed=(await processedResponse.json()).data;
  assert.ok(Math.abs(processed.preview_wavenumber-selected)<10);
  await active.getByRole('link',{name:'已保存分析记录',exact:true}).waitFor();
  await page.waitForFunction(()=>{const p=document.querySelector('[data-analysis-workspace]:not([hidden]) .js-plotly-plot');return p?.data?.filter(trace=>trace.type==='heatmap').length===2;});
  const live=await active.locator('.js-plotly-plot').first().evaluate(plot=>plot.data.map(trace=>({z:trace.z,zmin:trace.zmin,zmax:trace.zmax,colorscale:trace.colorscale})));
  assert.equal(live.length,2);assert.equal(live[0].zmin,live[1].zmin);assert.equal(live[0].zmax,live[1].zmax);
  await page.screenshot({path:path.join(out,'workspace.png'),animations:'disabled'});
  await active.getByRole('link',{name:'已保存分析记录',exact:true}).click();assert.ok(page.url().includes('run='+processed.analysis_run.id));assert.ok(page.url().includes('wavenumber='));
  const history=page.locator('.history-hyperspectral-result');await history.locator('[data-hyper-role=processed] .js-plotly-plot').waitFor();
  const previews=await history.locator('.dw-hyper-images .js-plotly-plot').evaluateAll(plots=>plots.map(plot=>({z:plot.data[0].z,zmin:plot.data[0].zmin,zmax:plot.data[0].zmax,colorscale:plot.data[0].colorscale})));
  function nearMatrix(actual,expected){assert.equal(actual.length,expected.length);for(let y=0;y<actual.length;y++){assert.equal(actual[y].length,expected[y].length);for(let x=0;x<actual[y].length;x++)assert.ok(Math.abs(actual[y][x]-expected[y][x])<=1e-5,`Value mismatch at ${x},${y}`);}}
  for(let i=0;i<2;i++){nearMatrix(previews[i].z,live[i].z);assert.ok(Math.abs(previews[i].zmin-live[i].zmin)<=1e-5);assert.ok(Math.abs(previews[i].zmax-live[i].zmax)<=1e-5);assert.deepEqual(previews[i].colorscale,live[i].colorscale);}
  async function checkGeometry(){
    await history.locator('[data-hyper-role=processed] .js-plotly-plot').waitFor();
    const boxes=await history.evaluate(node=>{
      const mean=node.querySelector(':scope > .sized-plot'),wave=node.querySelector('.dw-hyper-wave'),images=node.querySelector('.dw-hyper-images');
      const rect=n=>{const r=n.getBoundingClientRect();return {top:r.top,bottom:r.bottom,height:r.height,width:r.width};};
      return {mean:rect(mean),wave:rect(wave),images:rect(images),plots:[...node.querySelectorAll('.sized-plot')].map(host=>({host:rect(host),svg:rect(host.querySelector('.svg-container'))}))};
    });
    assert.ok(boxes.mean.height>=309,JSON.stringify(boxes));assert.ok(boxes.wave.top>=boxes.mean.bottom-1,JSON.stringify(boxes));assert.ok(boxes.images.top>=boxes.wave.bottom-1,JSON.stringify(boxes));
    for(const plot of boxes.plots){assert.ok(plot.svg.bottom<=plot.host.bottom+2,JSON.stringify(plot));assert.ok(plot.svg.top>=plot.host.top-1,JSON.stringify(plot));}
  }
  await checkGeometry();
  for(let cycle=0;cycle<4;cycle++)for(const tab of ['处理过程','数据与文件']){await page.getByRole('navigation',{name:'分析详情'}).getByRole('button',{name:tab,exact:true}).click();await page.getByRole('navigation',{name:'分析详情'}).getByRole('button',{name:'结果总览',exact:true}).click();await checkGeometry();}
  await page.screenshot({path:path.join(out,'history-after-tab-cycles.png'),animations:'disabled'});
  await page.setViewportSize({width:390,height:844});await page.waitForTimeout(180);await checkGeometry();assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await page.screenshot({path:path.join(out,'history-mobile.png'),animations:'disabled'});
  await page.getByRole('link',{name:'高光谱处理',exact:true}).first().click();await button.waitFor();await page.waitForTimeout(100);assert.ok((await button.boundingBox()).height<=36);assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await page.setViewportSize({width:1600,height:1050});
  await active.locator('.hyper-import-settings > summary').click();
  await active.getByLabel('数据模式',{exact:true}).selectOption('time_series');
  const seriesWave=Array.from({length:530},(_,i)=>1400-i);
  const table=['\t'+seriesWave.join('\t'),...Array.from({length:260},(_,row)=>[row,...seriesWave.map(x=>row*1000+x)].join('\t'))].join('\n');
  const uploaded=page.waitForResponse(r=>r.url().endsWith('/upload-hyperspectral')&&r.status()===200);
  await active.locator('input[type=file]').setInputFiles({name:'sampled-series.txt',mimeType:'text/plain',buffer:Buffer.from(table)});
  const series=(await (await uploaded).json()).data;
  await active.getByText('热图为抽样预览，点击采集行可查看该位置的完整光谱。',{exact:true}).waitFor();
  const sourcePlot=active.locator('.js-plotly-plot').first();
  await page.waitForFunction(()=>document.querySelector('[data-analysis-workspace]:not([hidden]) .js-plotly-plot')?._ev?.listenerCount('plotly_click')>0);
  const axes=await sourcePlot.evaluate(plot=>({x:plot.data[0].x,y:plot.data[0].y}));
  assert.equal(axes.x.length,512);assert.equal(axes.y.length,128);
  assert.deepEqual(axes.x,series.preview_x);assert.deepEqual(axes.y,series.preview_y);
  const selectedIndex=axes.y[80];
  assert.ok(selectedIndex>128);
  await sourcePlot.scrollIntoViewIfNeeded();
  const cell=await sourcePlot.evaluate((plot,index)=>{
    const bounds=plot.getBoundingClientRect(), {xaxis,yaxis}=plot._fullLayout;
    return {x:bounds.left+xaxis._offset+xaxis.l2p(plot.data[0].x[250]),y:bounds.top+yaxis._offset+yaxis.l2p(index)};
  },selectedIndex);
  const spectrumRequest=page.waitForResponse(r=>r.url().includes('/hyperspectral-spectrum/')&&new URL(r.url()).searchParams.get('index')===String(selectedIndex));
  await page.mouse.click(cell.x,cell.y);
  const row=(await (await spectrumRequest).json()).data;
  assert.equal(row.index,selectedIndex);assert.deepEqual(row.intensity,seriesWave.map(x=>selectedIndex*1000+x));
  await active.getByRole('button',{name:'去噪',exact:true}).click();
  const seriesProcessed=page.waitForResponse(r=>r.url().endsWith('/process-hyperspectral')&&r.status()===200);
  await active.getByRole('button',{name:'运行流程',exact:true}).click();
  const processedSeries=(await (await seriesProcessed).json()).data;
  assert.deepEqual(processedSeries.shape,[260,530]);
  await active.getByRole('link',{name:'已保存分析记录',exact:true}).click();
  const savedSeries=page.locator('[data-hyper-role=processed] .js-plotly-plot');
  await savedSeries.waitFor();
  assert.deepEqual(await savedSeries.evaluate(plot=>plot.data[0].y),axes.y);
  assert.deepEqual(errors,[]);console.log('HYPER_LAYOUT_UI_OK',JSON.stringify({toolbar:true,savedSlice:true,sameMatrices:true,samePalette:true,sameScale:true,tabCycles:8,noOverlap:true,mobile:true,cachedWorkspace:true}));
 }catch(error){if(page){await page.screenshot({path:path.join(out,'error.png')}).catch(()=>{});await fs.writeFile(path.join(out,'error.txt'),await page.locator('body').innerText()).catch(()=>{});}throw error;}
 finally{await context.close();await browser.close();}
}
main().catch(error=>{console.error(error);process.exitCode=1;});
