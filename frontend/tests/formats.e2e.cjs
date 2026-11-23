/* Synthetic vendor-format upload checks; no model requests or permanent QA data. */
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const fs = require('node:fs/promises');
const path = require('node:path');
const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');

async function main() {
  const root = path.resolve(__dirname, '../..'), logs = path.join(root, 'logs');
  const python = process.env.BACKEND_PYTHON || 'python';
  const fixture = spawnSync(python, ['-c',
    "import sys,json,base64; sys.path.insert(0,'backend/tests'); from test_spectral_formats import xlsx,wdf_fixture; print(json.dumps({'xlsx':base64.b64encode(xlsx([['Raman shift (cm-1)','Intensity']]+[[400+i,i*i+10] for i in range(32)])).decode(),'wdf':base64.b64encode(wdf_fixture(4,mapping=True)).decode()}))"
  ], { cwd: root, encoding: 'utf8' });
  assert.equal(fixture.status, 0, fixture.stderr);
  const files = JSON.parse(fixture.stdout);
  const nano = Buffer.from('Wavenumber\tx0_y0\tx1_y0\tx0_y1\tx1_y1\n' +
    Array.from({ length: 32 }, (_, i) => `${400 + i}\t${i + 1}\t${i + 3}\t${i + 7}\t${i + 12}`).join('\n'));
  const browser = await chromium.launch({ headless: true, ...(process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {}) });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, locale: 'zh-CN' });
  const page = await context.newPage(), errors = [], assistantRequests = [];
  page.setDefaultTimeout(30000);
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => { if (/\/api\/assistant\//.test(request.url())) assistantRequests.push(request.url()); });
  const username = 'qa_ai_' + Date.now();
  const registered = await context.request.post('http://127.0.0.1:5000/api/auth/register', { data: { username, password: 'qa-test-only-password', role: 'user' } });
  assert.equal(registered.status(), 200);
  const auth = (await registered.json()).data;
  await fs.writeFile(path.join(logs, 'assistant-ui-test-account.json'), JSON.stringify({ username, user_id: auth.user.id }));
  await context.addInitScript(token => { localStorage.setItem('ramancloud_auth_token', token); localStorage.setItem('ramancloud_language', 'zh'); }, auth.token);
  async function uploadHyperspectral(name, buffer, status = 200) {
    const uploaded = page.waitForResponse(response => response.url().endsWith('/api/upload-hyperspectral'));
    await page.locator('input[type=file]').setInputFiles({ name, mimeType: 'application/octet-stream', buffer });
    const response = await uploaded;
    assert.equal(response.status(), status, await response.text());
    return response.json();
  }
  try {
    await page.goto('http://127.0.0.1:5173/preprocessing/hyperspectral');
    await page.locator('.welcome-screen.is-hidden').waitFor({ state: 'attached' });
    assert.equal(await page.getByLabel('文件格式', { exact: true }).inputValue(), 'auto');
    const uploaded = await uploadHyperspectral('nanophoton.txt', nano);
    assert.deepEqual(uploaded.data.shape, [2, 2, 32]);
    const report = page.getByLabel('导入检查结果', { exact: true });
    await report.getByText('Nanophoton 像素列', { exact: true }).waitFor();
    assert.match(await report.innerText(), /2 × 2 × 32/);
    await page.waitForFunction(() => document.querySelector('.heatmaplayer image')?.getBoundingClientRect().height > 100);
    await page.screenshot({ path: path.join(logs, 'formats-desktop.png'), fullPage: true, animations: 'disabled' });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.waitForFunction(() => [...document.querySelectorAll('.main-svg')].every(svg => svg.getBoundingClientRect().right <= svg.closest('.js-plotly-plot').getBoundingClientRect().right + 1));
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await page.screenshot({ path: path.join(logs, 'formats-mobile.png'), fullPage: true, animations: 'disabled' });
    await page.setViewportSize({ width: 1440, height: 1000 });
    await uploadHyperspectral('invalid.txt', Buffer.from(nano.toString().replace('400\t1', '400\tNaN')), 400);
    await page.getByRole('alert').filter({ hasText: 'NaN' }).waitFor();
    const wdf = await uploadHyperspectral('renishaw.wdf', Buffer.from(files.wdf, 'base64'));
    assert.deepEqual(wdf.data.shape, [2, 2, 8]);
    await report.getByText('Renishaw WDF', { exact: true }).waitFor();
    assert.equal(await page.locator('.assistant-chat').count(), 0);
    assert.deepEqual(assistantRequests, []);

    await page.goto('http://127.0.0.1:5173/preprocessing/ai-analysis');
    await page.getByRole('button', { name: /^上传光谱/ }).waitFor();
    await page.waitForFunction(() => !document.querySelector('.ai-upload').disabled);
    const created = page.waitForResponse(response => response.url().endsWith('/api/ai-workflows/upload') && response.request().method() === 'POST');
    const original = Buffer.from(files.xlsx, 'base64');
    await page.getByLabel('上传光谱', { exact: true }).setInputFiles({ name: 'raman.xlsx', mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', buffer: original });
    const createdResponse = await created;
    assert.equal(createdResponse.status(), 200, await createdResponse.text());
    assert.equal((await createdResponse.json()).requires_confirmation, true);
    await page.getByRole('region', { name: '格式转换确认', exact: true }).waitFor();
    const confirmed = page.waitForResponse(response => response.url().endsWith('/api/ai-workflows/upload') && response.request().method() === 'POST');
    await page.getByRole('button', { name: '确认转换并导入', exact: true }).click();
    assert.equal((await confirmed).status(), 200);
    await page.getByRole('heading', { name: '格式检查通过', exact: true }).waitFor();
    await page.getByLabel('导入检查结果', { exact: true }).getByText('XLSX', { exact: true }).waitFor();
    const task = new URL(page.url()).searchParams.get('task');
    const saved = await context.request.get(`http://127.0.0.1:5000/api/ai-workflows/${task}/download?kind=original`, { headers: { Authorization: 'Bearer ' + auth.token } });
    assert.equal(saved.status(), 200);
    assert.deepEqual(await saved.body(), original);
    assert.deepEqual(errors, []);
    console.log('FORMATS_E2E_OK', JSON.stringify({ nanophoton: uploaded.data.shape, wdf: wdf.data.shape, xlsx_original_preserved: true, errors: errors.length }));
  } catch (error) {
    await page.screenshot({ path: path.join(logs, 'formats-failure.png'), fullPage: true });
    throw error;
  } finally {
    await context.close(); await browser.close();
    const cleanup = spawnSync(python, ['backend/tests/cleanup_ui_test.py', 'assistant-ui-test-account.json'], { cwd: root, encoding: 'utf8' });
    assert.equal(cleanup.status, 0, cleanup.stderr);
    console.log(cleanup.stdout.trim());
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
