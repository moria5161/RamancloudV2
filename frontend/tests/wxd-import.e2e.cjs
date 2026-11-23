/* Uses an isolated QA backend only. WXD_E2E_FILE points to a private sample. */
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const fs = require('node:fs/promises');
const path = require('node:path');
const assert = require('node:assert/strict');

async function main() {
  const apiBase = process.env.E2E_API_URL || 'http://127.0.0.1:5001/api';
  const uiBase = process.env.E2E_UI_URL || 'http://127.0.0.1:5174/preprocessing';
  assert.equal(new URL(apiBase).hostname, '127.0.0.1');
  assert.equal(new URL(apiBase).port, '5001', 'Use the isolated QA service, never the normal user database');
  assert.ok(process.env.WXD_E2E_FILE, 'Set WXD_E2E_FILE to a verified WXD single-spectrum file');
  const source = await fs.readFile(process.env.WXD_E2E_FILE);
  const root = path.resolve(__dirname, '../..'), logs = path.join(root, 'logs', 'wxd-ui');
  await fs.mkdir(logs, { recursive: true });
  const browser = await chromium.launch({ headless: true, ...(process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {}) });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, locale: 'zh-CN', acceptDownloads: true });
  try {
    const response = await context.request.post(apiBase + '/auth/register', {
      data: { username: 'qa_wxd_' + Date.now(), password: 'qa-wxd-only-password', role: 'user' },
    });
    assert.equal(response.status(), 200);
    const auth = (await response.json()).data;
    await context.addInitScript(token => {
      localStorage.setItem('ramancloud_auth_token', token);
      localStorage.setItem('ramancloud_language', 'zh');
    }, auth.token);
    const headers = { Authorization: 'Bearer ' + auth.token };
    const taskCount = async () => (await (await context.request.get(apiBase + '/ai-workflows', { headers })).json()).length;
    const page = await context.newPage(), errors = [];
    page.setDefaultTimeout(30000);
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(uiBase + '/ai-analysis');
    await page.locator('.welcome-screen.is-hidden').waitFor({ state: 'attached' });
    await page.waitForFunction(() => !document.querySelector('.ai-upload')?.disabled);
    const input = page.getByLabel('上传光谱', { exact: true });
    assert.match(await input.getAttribute('accept'), /\.wxd/);
    const before = await taskCount();
    async function upload() {
      const request = page.waitForResponse(r => r.url().endsWith('/api/ai-workflows/upload') && r.request().method() === 'POST');
      await input.setInputFiles({ name: 'measurement.wxd', mimeType: 'application/octet-stream', buffer: source });
      const response = await request;
      assert.equal(response.status(), 200, await response.text());
      const preview = await response.json();
      assert.equal(preview.requires_confirmation, true);
      assert.equal(preview.source_check.detected_format, 'renishaw_wxd_single');
      return preview;
    }
    const preview = await upload();
    const dialog = page.getByRole('region', { name: '格式转换确认', exact: true });
    await dialog.getByText(/从 WXD 读取拉曼位移和强度/).waitFor();
    assert.equal(await taskCount(), before);
    await page.setViewportSize({ width: 390, height: 844 });
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await dialog.scrollIntoViewIfNeeded();
    await dialog.screenshot({ path: path.join(logs, 'confirmation-mobile.png'), animations: 'disabled' });
    await dialog.getByRole('button', { name: '取消导入', exact: true }).click();
    assert.equal(await taskCount(), before);
    await page.setViewportSize({ width: 1440, height: 1000 });
    await upload();
    const confirmed = page.waitForResponse(r => r.url().endsWith('/api/ai-workflows/upload') && r.request().method() === 'POST');
    await dialog.getByRole('button', { name: '确认转换并导入', exact: true }).click();
    const confirmedResponse = await confirmed;
    assert.equal(confirmedResponse.status(), 200, await confirmedResponse.text());
    const task = await confirmedResponse.json();
    await page.getByRole('heading', { name: '格式检查通过', exact: true }).waitFor();
    await page.getByLabel('导入检查结果', { exact: true }).getByText('Renishaw WXD 单谱', { exact: true }).waitFor();
    assert.equal(task.diagnostics.source_check.original_preserved, true);
    assert.equal(task.diagnostics.source_check.conversion_confirmed, true);
    for (const [name, kind] of [['下载原始文件', 'original'], ['下载标准双列', 'standardized']]) {
      const event = page.waitForEvent('download');
      await page.getByRole('button', { name, exact: true }).click();
      const download = await event;
      const target = path.join(logs, kind === 'original' ? 'downloaded.wxd' : 'standardized.txt');
      await download.saveAs(target);
      const bytes = await fs.readFile(target);
      if (kind === 'original') assert.deepEqual(bytes, source);
      else {
        const rows = bytes.toString('utf8').trim().split(/\r?\n/).slice(1).map(row => row.split('\t').map(Number));
        assert.equal(rows.length, preview.points);
        rows.forEach(([x, y], i) => {
          assert.equal(x, task.original.wavenumber[i]);
          assert.equal(y, task.original.intensity[i]);
        });
      }
    }
    await page.screenshot({ path: path.join(logs, 'converted-desktop.png'), fullPage: true, animations: 'disabled' });
    assert.deepEqual(errors, []);
    console.log('WXD_UI_OK', JSON.stringify({ points: preview.points, cancellation: true, originalBytesPreserved: true, standardValuesPreserved: true }));
  } finally {
    await context.close();
    await browser.close();
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
