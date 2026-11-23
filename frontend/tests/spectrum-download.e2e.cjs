/* Run against the isolated QA services on 5001/5174, never the user's database. */
const { chromium } = require('playwright');
const fs = require('fs/promises'), path = require('path'), assert = require('assert/strict');

async function main() {
  const out = path.resolve(__dirname, '../../logs/spectrum-download-ui');
  await fs.mkdir(out, {recursive: true});
  const browser = await chromium.launch({headless: true, executablePath: process.env.CHROME_PATH});
  const context = await browser.newContext({viewport: {width: 1440, height: 1050}, locale: 'zh-CN'});
  let page;
  try {
    const api = 'http://127.0.0.1:5001/api';
    const res = await context.request.post(api + '/auth/register', {data: {username: 'qa_image_' + Date.now(), password: 'isolated-spectrum-image-qa'}});
    assert.equal(res.status(), 200); const auth = (await res.json()).data;
    const headers = {Authorization: 'Bearer ' + auth.token};
    async function request(route, data) {
      const res = data === undefined ? await context.request.get(api + route, {headers}) : await context.request.post(api + route, {headers, data});
      assert.equal(res.status(), 200, await res.text()); return res.json();
    }
    const task = await request('/ai-workflows/source', {demo: 'tutorial'});
    const planned = await request('/ai-workflows/' + task.id + '/recommend', {goal: '默认预处理', phase: 'preprocess', allow_ai: false});
    let version = planned.version;
    await request('/ai-workflows/' + task.id + '/versions/' + version.id + '/execute', {});
    for (let attempt = 0; attempt < 100; attempt++) {
      version = await request('/ai-workflows/' + task.id + '/versions/' + version.id);
      if (!['queued', 'running', 'previewing'].includes(version.status)) break;
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    assert.equal(version.status, 'completed', version.error);
    await context.addInitScript(token => {
      localStorage.setItem('ramancloud_auth_token', token);
      localStorage.setItem('ramancloud_language', 'zh');
      localStorage.setItem('ramancloud_theme', 'dark');
    }, auth.token);
    page = await context.newPage(); page.setDefaultTimeout(30000);
    const errors = []; page.on('pageerror', error => errors.push(error.message));
    await page.goto('http://127.0.0.1:5174/preprocessing/ai-analysis?task=' + task.id + '&version=' + version.id);
    await page.locator('.welcome-screen.is-hidden').waitFor({state: 'attached'});
    // Selecting an intermediate step must not change the exported final result.
    await page.getByLabel('查看处理步骤', {exact:true}).selectOption('step:0');
    await page.getByRole('button', {name: '导出', exact: true}).click();
    await page.getByRole('heading', {name: '导出光谱', exact: true}).waitFor();
    assert.equal(await page.getByRole('button', {name: '原始光谱 TXT', exact: true}).count(), 1);
    assert.equal(await page.getByRole('button', {name: '处理后光谱 TXT', exact: true}).count(), 1);
    async function image(label, suffix) {
      const event = page.waitForEvent('download');
      await page.getByRole('button', {name: label, exact: true}).click();
      const download = await event; assert.ok(download.suggestedFilename().endsWith(suffix));
      const file = path.join(out, download.suggestedFilename()); await download.saveAs(file);
      const bytes = await fs.readFile(file);
      assert.equal(bytes.subarray(0, 8).toString('hex'), '89504e470d0a1a0a');
      assert.equal(bytes.readUInt32BE(16), 2400); assert.equal(bytes.readUInt32BE(20), 1440);
      const pixels = await page.evaluate(async dataUrl => {
        const img = new Image(); img.src = dataUrl; await img.decode();
        const canvas = document.createElement('canvas'); canvas.width = img.width; canvas.height = img.height;
        const ctx = canvas.getContext('2d'); ctx.drawImage(img, 0, 0);
        const data = ctx.getImageData(0, 0, canvas.width, canvas.height).data; let blue = 0;
        for (let i = 0; i < data.length; i += 4) if (data[i] < 40 && data[i + 1] > 70 && data[i + 1] < 150 && data[i + 2] > 180) blue++;
        return {corner: [...data.subarray(0, 4)], blue};
      }, 'data:image/png;base64,' + bytes.toString('base64'));
      assert.deepEqual(pixels.corner, [255, 255, 255, 255]); assert.ok(pixels.blue > 2000, 'Export must contain a spectrum curve');
      return bytes;
    }
    const original = await image('原始光谱 PNG', '_original.png');
    const processed = await image('处理后光谱 PNG', '_processed_V1.png');
    assert.notDeepEqual(original, processed);
    await page.screenshot({path: path.join(out, 'save-desktop.png'), animations: 'disabled'});
    await page.setViewportSize({width: 390, height: 844});
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await page.getByRole('button', {name: '原始光谱 PNG', exact: true}).scrollIntoViewIfNeeded();
    await page.screenshot({path: path.join(out, 'save-mobile.png'), animations: 'disabled'});
    await image('处理后光谱 PNG', '_processed_V1.png');
    // Unsaved edits must disable processed downloads for both formats.
    await page.getByRole('button', {name: '关闭',exact:true}).click();
    await page.locator('.ai-plan-details > summary').click();
    await page.locator('.ai-step input[type="checkbox"]').first().uncheck();
    await page.getByRole('button', {name: '导出', exact: true}).click();
    assert.ok(await page.getByRole('button', {name: '处理后光谱 PNG', exact: true}).isDisabled());
    assert.ok(await page.getByRole('button', {name: '处理后光谱 TXT', exact: true}).isDisabled());
    assert.ok(await page.getByRole('button', {name: '原始光谱 PNG', exact: true}).isEnabled());
    assert.deepEqual(errors, []);
    console.log('SPECTRUM_IMAGE_UI_OK', JSON.stringify({png: '2400x1440', whiteBackground: true, rawAndProcessed: true, mobile: true, pendingEditsBlocked: true, errors}));
  } catch (error) {
    if (page) {await page.screenshot({path: path.join(out, 'error.png')}).catch(() => {}); await fs.writeFile(path.join(out, 'error-text.txt'), await page.locator('body').innerText()).catch(() => {});}
    throw error;
  } finally {await context.close(); await browser.close();}
}
main().catch(error => {console.error(error); process.exitCode = 1;});
