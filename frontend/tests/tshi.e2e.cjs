/* Synthetic MAT workflow; disposable account, no model/cloud API requests. */
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const fs = require('node:fs/promises');
const path = require('node:path');
const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');

async function main() {
  const root = path.resolve(__dirname, '../..');
  const logs = path.join(root, 'logs');
  const python = process.env.BACKEND_PYTHON || 'python';
  const fixture = spawnSync(python, ['backend/tests/tshi_browser_fixture.py'], { cwd: root, encoding: 'utf8' });
  assert.equal(fixture.status, 0, fixture.stderr);
  const info = JSON.parse(fixture.stdout);
  const browser = await chromium.launch({ headless: true, ...(process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {}) });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, locale: 'zh-CN' });
  const page = await context.newPage();
  page.setDefaultTimeout(30000);
  const errors = [];
  const results = [];
  const assistantRequests = [];
  page.on('request', request => {
    if (/\/api\/assistant\//.test(request.url())) assistantRequests.push(request.url());
  });
  page.on('pageerror', error => errors.push(error.message));
  page.on('response', async response => {
    if (response.url().endsWith('/api/process-hyperspectral') && response.status() === 200) results.push((await response.json()).data);
  });
  const username = 'qa_ai_' + Date.now();
  const response = await context.request.post('http://127.0.0.1:5000/api/auth/register', { data: { username, password: 'qa-test-only-password', role: 'user' } });
  assert.equal(response.status(), 200);
  const auth = (await response.json()).data;
  await fs.writeFile(path.join(logs, 'assistant-ui-test-account.json'), JSON.stringify({ username, user_id: auth.user.id }));
  await context.addInitScript(token => {
    localStorage.setItem('ramancloud_auth_token', token);
    localStorage.setItem('ramancloud_language', 'zh');
  }, auth.token);
  try {
    await page.goto('http://127.0.0.1:5173/preprocessing/hyperspectral');
    await page.locator('.welcome-screen.is-hidden').waitFor({ state: 'attached' });
    await page.locator('.hyper-import-settings > summary').click();
    await page.getByText('空间布局 / MAT 参数', { exact: true }).click();
    await page.getByLabel('二维矩阵图像行数', { exact: true }).fill(String(info.height));
    await page.getByLabel('二维矩阵图像列数', { exact: true }).fill(String(info.width));
    await page.getByLabel('MAT 布局', { exact: true }).selectOption('bands_pixels');
    const uploaded = page.waitForResponse(r => r.url().endsWith('/api/upload-hyperspectral') && r.status() === 200);
    await page.locator('input[type=file]').setInputFiles(path.join(logs, 'tshi-browser-input.mat'));
    await uploaded;
    assert.equal(await page.getByRole('tab', { name: 'AI 对话', exact: true }).count(), 0);
    assert.equal(await page.locator('.assistant-chat').count(), 0);
    const controls = page.locator('.hyper-bottom-dock');
    await controls.getByRole('button', { name: '去噪', exact: true }).click();
    await controls.getByLabel('降噪算法', { exact: true }).selectOption('tshi');
    await controls.getByLabel('中心波数 (cm⁻¹)', { exact: true }).fill(String(info.center_wavenumber));
    await controls.getByLabel('波段半宽', { exact: true }).fill('6');
    const run = () => controls.getByRole('button', { name: '运行流程', exact: true }).click();
    const processed = page.waitForResponse(r => r.url().endsWith('/api/process-hyperspectral') && r.status() === 200);
    await run();
    await processed;
    await page.getByTestId('tshi-results').waitFor();
    await page.getByRole('button', { name: '运行流程', exact: true }).waitFor();
    await page.waitForFunction(() => document.querySelectorAll('.tshi-images .heatmaplayer image').length === 2);
    assert.deepEqual(results[0].shape, [24, 20, 12]);
    assert.equal(results[0].history[0].details.center_wavenumber, info.center_wavenumber);

    await controls.getByLabel('空间窗口边长', { exact: true }).fill('4');
    const failed = page.waitForResponse(r => r.url().endsWith('/api/process-hyperspectral') && r.status() === 400);
    await run();
    await failed;
    await page.getByText('TSHI 空间窗口必须为不超过图像行列数的奇数。', { exact: true }).waitFor();
    assert.equal(results.length, 1);
    await controls.getByLabel('空间窗口边长', { exact: true }).fill('5');
    await controls.getByRole('checkbox', { name: /BM3D 中心图像/ }).check();
    await controls.getByLabel('BM3D 噪声标准差（原始强度单位）', { exact: true }).fill('0.5');
    const second = page.waitForResponse(r => r.url().endsWith('/api/process-hyperspectral') && r.status() === 200);
    await run();
    await second;
    await page.waitForFunction(() => document.querySelectorAll('.tshi-images .heatmaplayer image').length === 3);
    const pixels = await page.locator('.tshi-images .heatmaplayer image').evaluateAll(async images => {
      const counts = [];
      for (const element of images) {
        const bitmap = new Image();
        bitmap.src = element.getAttribute('href') || element.getAttribute('xlink:href');
        await bitmap.decode();
        const canvas = document.createElement('canvas');
        canvas.width = bitmap.naturalWidth; canvas.height = bitmap.naturalHeight;
        const ctx = canvas.getContext('2d'); ctx.drawImage(bitmap, 0, 0);
        const data = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
        const colors = new Set();
        for (let i = 0; i < data.length; i += 4) colors.add(`${data[i]},${data[i + 1]},${data[i + 2]}`);
        counts.push(colors.size);
      }
      return counts;
    });
    assert.ok(pixels.every(value => value > 15), JSON.stringify(pixels));
    await page.screenshot({ path: path.join(logs, 'tshi-desktop.png'), fullPage: true });

    const downloadEvent = page.waitForEvent('download');
    await controls.getByRole('button', { name: '下载', exact: true }).click();
    const download = await downloadEvent;
    assert.match(download.suggestedFilename(), /\.mat$/);
    await download.saveAs(path.join(logs, 'tshi-browser-result.mat'));
    const verify = spawnSync(python, ['backend/tests/tshi_browser_fixture.py', 'verify'], { cwd: root, encoding: 'utf8' });
    assert.equal(verify.status, 0, verify.stderr);

    await page.getByRole('button', { name: '成像', exact: true }).click();
    const slider = page.locator('input[type=range]');
    assert.equal(Number(await slider.getAttribute('min')), Math.min(...results[1].wavenumber));
    assert.equal(Number(await slider.getAttribute('max')), Math.max(...results[1].wavenumber));
    await page.getByRole('button', { name: '单像素', exact: true }).click();
    await page.getByRole('button', { name: 'TSHI 结果', exact: true }).click();
    await page.setViewportSize({ width: 390, height: 844 });
    assert.ok(await page.locator('.hyperspectral-main').evaluate(el => el.getBoundingClientRect().height >= 400));
    await page.locator('.tshi-images figure').first().scrollIntoViewIfNeeded();
    await page.waitForFunction(() => [...document.querySelectorAll('.tshi-images .main-svg')].every(svg => svg.getBoundingClientRect().right <= svg.closest('.js-plotly-plot').getBoundingClientRect().right + 1));
    await page.screenshot({ path: path.join(logs, 'tshi-mobile.png'), fullPage: true });
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await page.getByRole('button', { name: '设置', exact: true }).click();
    await page.getByRole('button', { name: '深色', exact: true }).click();
    await page.getByRole('button', { name: '设置', exact: true }).click();
    await page.waitForFunction(() => [...document.querySelectorAll('.tshi-images .heatmaplayer image')].every(el => el.getBoundingClientRect().height > 150));
    await page.screenshot({ path: path.join(logs, 'tshi-mobile-dark.png'), fullPage: true });

    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.getByRole('link', { name: '已保存分析记录', exact: true }).click();
    await page.getByRole('button', { name: '读取参数', exact: true }).click();
    await page.getByRole('alert').waitFor();
    await page.getByText('空间布局 / MAT 参数', { exact: true }).click();
    await page.getByLabel('二维矩阵图像行数', { exact: true }).fill(String(info.height));
    await page.getByLabel('二维矩阵图像列数', { exact: true }).fill(String(info.width));
    await page.getByLabel('MAT 布局', { exact: true }).selectOption('bands_pixels');
    const reloaded = page.waitForResponse(r => r.url().endsWith('/api/upload-hyperspectral') && r.status() === 200);
    await page.locator('input[type=file]').setInputFiles(path.join(logs, 'tshi-browser-input.mat'));
    await reloaded;
    const step = controls.locator('[aria-label="降噪算法"]');
    if (!await step.isVisible()) await controls.locator('.cursor-pointer').first().click();
    assert.equal(await step.inputValue(), 'tshi');
    assert.equal(await controls.getByLabel('波段半宽', { exact: true }).inputValue(), '6');
    assert.deepEqual(assistantRequests, []);
    assert.deepEqual(errors, []);
    console.log('TSHI_E2E_OK', JSON.stringify({ runs: results.length, nonblank_heatmaps: pixels, errors: errors.length }));
  } catch (error) {
    await page.screenshot({ path: path.join(logs, 'tshi-failure.png'), fullPage: true });
    throw error;
  } finally {
    await context.close(); await browser.close();
    const cleanup = spawnSync(python, ['backend/tests/cleanup_ui_test.py', 'assistant-ui-test-account.json'], { cwd: root, encoding: 'utf8' });
    assert.equal(cleanup.status, 0, cleanup.stderr);
    console.log(cleanup.stdout.trim());
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
