/* Quality screening is advisory and never modifies synthetic originals. */
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const fs = require('node:fs/promises');
const path = require('node:path');
const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');

async function main() {
  const root = path.resolve(__dirname, '../..'), logs = path.join(root, 'logs');
  const browser = await chromium.launch({ headless: true, ...(process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {}) });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, locale: 'zh-CN' });
  const page = await context.newPage(), errors = [];
  page.setDefaultTimeout(30000);
  page.on('pageerror', error => errors.push(error.message));
  const username = 'qa_ai_' + Date.now();
  const registered = await context.request.post('http://127.0.0.1:5000/api/auth/register', { data: { username, password: 'qa-test-only-password', role: 'user' } });
  assert.equal(registered.status(), 200);
  const auth = (await registered.json()).data, headers = { Authorization: 'Bearer ' + auth.token };
  await fs.writeFile(path.join(logs, 'assistant-ui-test-account.json'), JSON.stringify({ username, user_id: auth.user.id }));
  await context.addInitScript(token => { localStorage.setItem('ramancloud_auth_token', token); localStorage.setItem('ramancloud_language', 'zh'); }, auth.token);
  const y = Array.from({ length: 256 }, (_, i) => i >= 120 && i <= 127 ? 30 : i === 70 ? 20 : i === 180 ? -15 : 10 * Math.exp(-1 * ((i - 128) / 25) ** 2));
  const content = Buffer.from('wave,intensity\n' + y.map((value, i) => `${400 + i + (i >= 150 ? 5 : 0)},${value}`).join('\n'));
  try {
    await page.goto('http://127.0.0.1:5173/preprocessing/ai-analysis');
    await page.locator('.welcome-screen').waitFor({ state: 'hidden' });
    await page.waitForFunction(() => !document.querySelector('.ai-upload').disabled);
    const uploaded = page.waitForResponse(r => r.url().endsWith('/api/ai-workflows/upload'));
    await page.getByLabel('上传光谱', { exact: true }).setInputFiles({ name: 'quality.csv', mimeType: 'text/csv', buffer: content });
    const response = await uploaded;
    assert.equal(response.status(), 200);
    const task = await response.json(), report = task.diagnostics.source_check.quality_check;
    assert.equal(report.blocking, false);
    assert.deepEqual(report.issues.map(i => i.code).sort(), ['flat_top', 'narrow_spike', 'uneven_spacing']);
    assert.deepEqual(task.original.intensity, y);
    const region = page.getByRole('region', { name: '数据质量检查', exact: true });
    await region.getByText('3 类需复核', { exact: true }).waitFor();
    for (const title of ['波数间距不均匀', '疑似异常尖峰', '疑似平顶截幅']) await region.locator('summary').filter({ hasText: title }).click();
    assert.ok(await region.locator('tbody tr').count() > 0);
    await region.scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(logs, 'quality-desktop.png'), animations: 'disabled' });
    const markers = page.locator('.ai-chart .points path.point');
    await page.getByLabel('显示质量检查候选位置', { exact: true }).scrollIntoViewIfNeeded();
    await page.waitForFunction(() => document.querySelectorAll('.ai-chart .points path.point').length > 0);
    const markerCount = await markers.count();
    await page.getByLabel('显示质量检查候选位置', { exact: true }).uncheck();
    await page.waitForFunction(() => document.querySelectorAll('.ai-chart .points path.point').length === 0);
    await page.getByLabel('显示质量检查候选位置', { exact: true }).check();
    await page.waitForFunction(() => document.querySelectorAll('.ai-chart .points path.point').length > 0);
    assert.equal(await page.getByRole('button', { name: '生成预处理方案', exact: true }).isEnabled(), true);
    await page.screenshot({ path: path.join(logs, 'quality-markers.png'), animations: 'disabled' });
    const original = await context.request.get(`http://127.0.0.1:5000/api/ai-workflows/${task.id}/download?kind=original`, { headers });
    assert.deepEqual(await original.body(), content);
    await page.reload(); await region.waitFor(); await page.locator('.welcome-screen').waitFor({ state: 'hidden' });
    const restored = await context.request.get(`http://127.0.0.1:5000/api/ai-workflows/${task.id}`, { headers });
    assert.deepEqual((await restored.json()).diagnostics.source_check.quality_check, report);
    await page.setViewportSize({ width: 390, height: 844 });
    await region.scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(logs, 'quality-mobile.png'), animations: 'disabled' });
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await page.evaluate(() => localStorage.setItem('ramancloud_theme', 'dark'));
    await page.reload(); await region.waitFor(); await page.locator('.welcome-screen').waitFor({ state: 'hidden' }); await region.scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(logs, 'quality-dark-mobile.png'), animations: 'disabled' });

    await page.goto('http://127.0.0.1:5173/preprocessing/hyperspectral');
    await page.locator('.welcome-screen').waitFor({ state: 'hidden' });
    const names = Array.from({ length: 20 }, (_, i) => `x${i % 5}_y${Math.floor(i / 5)}`);
    const cube = Buffer.from('Wavenumber\t' + names.join('\t') + '\n' + Array.from({ length: 64 }, (_, i) => `${400 + i}\t` + names.map((_, p) => i === 20 && p === 0 ? 30 : Math.exp(-1 * ((i - 32) / 10) ** 2)).join('\t')).join('\n'));
    const mapped = page.waitForResponse(r => r.url().endsWith('/api/upload-hyperspectral'));
    await page.locator('input[type=file]').setInputFiles({ name: 'map.txt', mimeType: 'text/plain', buffer: cube });
    const result = await (await mapped).json(), quality = result.data.import_metadata.quality_check;
    assert.equal(quality.sampled, true); assert.equal(quality.spectra_checked, 16); assert.equal(quality.spectra_total, 20);
    await region.getByText(/均匀抽样，未检查全部像素/).waitFor();
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    assert.deepEqual(errors, []);
    console.log('QUALITY_E2E_OK', JSON.stringify({ issue_types: report.issues.length, markers: markerCount, original_preserved: true, sampled_cube: [quality.spectra_checked, quality.spectra_total] }));
  } catch (error) {
    await page.screenshot({ path: path.join(logs, 'quality-failure.png'), fullPage: true }); throw error;
  } finally {
    await context.close(); await browser.close();
    const cleanup = spawnSync(process.env.BACKEND_PYTHON || 'python', ['backend/tests/cleanup_ui_test.py', 'assistant-ui-test-account.json'], { cwd: root, encoding: 'utf8' });
    assert.equal(cleanup.status, 0, cleanup.stderr); console.log(cleanup.stdout.trim());
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
