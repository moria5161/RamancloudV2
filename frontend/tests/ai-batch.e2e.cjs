/* Real directory selection and batch execution; only disposable spectra/accounts. */
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const fs = require('node:fs/promises');
const path = require('node:path');
const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');

async function main() {
  const root = path.resolve(__dirname, '../..'), logs = path.join(root, 'logs');
  const fixtures = path.join(logs, 'qa-batch-fixtures-' + Date.now()), folder = path.join(fixtures, 'spectra');
  assert.ok(fixtures.startsWith(logs + path.sep));
  await fs.mkdir(path.join(folder, 'subfolder'), { recursive: true });
  function spectrum(count = 40, scale = 1) { return Buffer.from('wave,intensity\n' + Array.from({ length: count }, (_, i) => `${i},${scale * (i * i + i % 3)}`).join('\n')); }
  await fs.writeFile(path.join(folder, 'a.csv'), spectrum());
  await fs.writeFile(path.join(folder, 'subfolder', 'a.csv'), spectrum(40, 1.1));
  await fs.writeFile(path.join(folder, 'short.csv'), spectrum(8));
  await fs.writeFile(path.join(folder, 'bad.csv'), 'no numeric data');
  await fs.writeFile(path.join(folder, 'readme.md'), 'not a spectrum');
  const browser = await chromium.launch({ headless: true, ...(process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {}) });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, locale: 'zh-CN', acceptDownloads: true });
  const page = await context.newPage(), errors = [], dialogs = [];
  page.setDefaultTimeout(30000);
  page.on('pageerror', error => errors.push(error.message));
  page.on('dialog', dialog => { dialogs.push(dialog.message()); dialog.accept(); });
  page.on('request', request => { if (/\/recommend$/.test(request.url())) assert.equal(request.postDataJSON().allow_ai, false); });
  const username = 'qa_ai_' + Date.now();
  const registered = await context.request.post('http://127.0.0.1:5000/api/auth/register', { data: { username, password: 'qa-test-only-password', role: 'user' } });
  assert.equal(registered.status(), 200);
  const auth = (await registered.json()).data, headers = { Authorization: 'Bearer ' + auth.token };
  await fs.writeFile(path.join(logs, 'ai-ui-test-account.json'), JSON.stringify({ username, user_id: auth.user.id }));
  await context.addInitScript(token => { localStorage.setItem('ramancloud_auth_token', token); localStorage.setItem('ramancloud_language', 'zh'); }, auth.token);
  let bid;
  const panel = () => page.getByRole('region', { name: '批量处理', exact: true });
  async function snapshot(name) {
    await page.locator('.welcome-screen').waitFor({ state: 'hidden' });
    await page.screenshot({ path: path.join(logs, name + '.png'), animations: 'disabled' });
  }
  try {
    await page.goto('http://127.0.0.1:5173/preprocessing/ai-analysis');
    await page.getByRole('heading', { name: '智能光谱处理', exact: true }).waitFor();
    await page.locator('.welcome-screen').waitFor({ state: 'hidden' });
    await page.waitForFunction(() => !document.querySelector('.ai-upload').disabled);
    assert.equal(await page.getByRole('radio', { name: '单个数据', exact: true }).isChecked(), true);
    for (const name of ['single-a.csv', 'single-b.csv']) {
      await page.getByLabel('上传光谱', { exact: true }).setInputFiles({ name, mimeType: 'text/csv', buffer: spectrum() });
      await page.getByRole('heading', { name, exact: true }).waitFor();
    }
    const currentUrl = page.url();
    await page.getByRole('button', { name: '删除任务 single-a.csv', exact: true }).click();
    await page.getByRole('button', { name: '删除任务 single-a.csv', exact: true }).waitFor({ state: 'hidden' });
    assert.equal(page.url(), currentUrl);
    await page.getByRole('button', { name: '删除任务 single-b.csv', exact: true }).click();
    await page.waitForFunction(() => !new URL(location.href).searchParams.has('task'));
    assert.deepEqual(dialogs, []);
    await page.getByRole('radio', { name: '批量数据', exact: true }).check();
    const uploaded = page.waitForResponse(response => /\/ai-workflow-batches\/upload$/.test(response.url()));
    await page.getByLabel('上传光谱文件夹', { exact: true }).setInputFiles(folder);
    const batch = await (await uploaded).json();
    bid = batch.id;
    assert.equal(batch.counts.ready, 3);
    assert.equal(batch.counts.invalid, 2);
    assert.equal(batch.items.length, 5);
    assert.ok(batch.items.some(item => item.relative_path === 'spectra/subfolder/a.csv'));
    await page.getByRole('heading', { name: '格式检查通过', exact: true }).waitFor();
    await panel().waitFor();
    assert.equal(await panel().locator('tbody tr').count(), 5);
    await snapshot('batch-upload-desktop');
    await page.getByRole('button', { name: '生成预处理方案', exact: true }).click();
    await page.getByLabel('步骤 2 算法', { exact: true }).waitFor();
    await page.locator('.ai-step').nth(1).locator('summary').click();
    await page.locator('.ai-step').nth(1).locator('input[type="number"]').first().fill('11');
    const previewed = page.waitForResponse(response => /\/preview$/.test(response.url()));
    await page.getByRole('button', { name: '预览', exact: true }).click();
    assert.equal((await previewed).status(), 200);
    await panel().getByRole('button', { name: /按当前方案批量处理/ }).click();
    await page.waitForFunction(() => [...document.querySelectorAll('.ai-batch-actions button')].some(button => button.textContent.includes('下载批量结果') && !button.disabled));
    const completed = await (await context.request.get(`http://127.0.0.1:5000/api/ai-workflow-batches/${bid}`, { headers })).json();
    assert.equal(completed.counts.completed, 2, JSON.stringify(completed));
    assert.equal(completed.counts.failed, 1);
    assert.equal(completed.counts.invalid, 2);
    assert.match(completed.items.find(item => item.relative_path.endsWith('short.csv')).error, /SG/);
    const originalVersions = [];
    for (const item of completed.items.filter(item => item.status === 'completed')) {
      originalVersions.push(await (await context.request.get(`http://127.0.0.1:5000/api/ai-workflows/${item.workflow_id}/versions/${item.version_id}`, { headers })).json());
    }
    await panel().getByRole('button', { name: '调整批量方案', exact: true }).click();
    await page.getByLabel('调整反馈', { exact: true }).waitFor();
    assert.equal(await page.getByLabel('分析目标', { exact: true }).inputValue(), originalVersions[0].goal);
    await page.getByLabel('分析目标', { exact: true }).fill('');
    const revisionText = '峰变弱了，减小平滑窗口，其他步骤保持不变';
    await page.getByLabel('调整反馈', { exact: true }).fill(revisionText);
    assert.equal(await page.getByRole('button', { name: '更新批量方案并预览', exact: true }).isEnabled(), true, 'Feedback alone must be usable after batch preprocessing');
    assert.equal(await panel().getByRole('button', { name: /按当前方案批量处理/ }).isDisabled(), true, 'Pending feedback must not be silently ignored');
    const revisionResponse = page.waitForResponse(response => /\/recommend$/.test(response.url()));
    const revisionPreview = page.waitForResponse(response => /\/preview$/.test(response.url()));
    await page.getByRole('button', { name: '更新批量方案并预览', exact: true }).click();
    const revised = (await (await revisionResponse).json()).version;
    const reviewed = await (await revisionPreview).json();
    assert.equal(revised.goal, originalVersions[0].goal);
    assert.equal(revised.feedback, revisionText);
    assert.equal(revised.steps.find(step => step.method === 'sg').params.window_size, 9);
    assert.equal(reviewed.status, 'preview');
    assert.equal(reviewed.reused_steps, 1);
    await page.reload(); await panel().waitFor();
    await panel().getByRole('button', { name: '调整批量方案', exact: true }).click();
    assert.equal(await page.getByLabel('调整反馈', { exact: true }).inputValue(), revisionText);
    assert.equal(await panel().getByRole('button', { name: /按当前方案批量处理/ }).isEnabled(), true);
    await snapshot('batch-feedback-desktop');
    const executeRevised = page.waitForResponse(response => /\/ai-workflow-batches\/[^/]+\/execute$/.test(response.url()));
    await panel().getByRole('button', { name: /按当前方案批量处理/ }).click();
    assert.equal((await executeRevised).request().postDataJSON().template_version_id, revised.id);
    await page.waitForFunction(() => [...document.querySelectorAll('.ai-batch-actions button')].some(button => button.textContent.includes('下载批量结果') && !button.disabled));
    const revisedBatch = await (await context.request.get(`http://127.0.0.1:5000/api/ai-workflow-batches/${bid}`, { headers })).json();
    assert.equal(revisedBatch.counts.completed, 2);
    for (const item of revisedBatch.items.filter(item => item.status === 'completed')) {
      const current = await (await context.request.get(`http://127.0.0.1:5000/api/ai-workflows/${item.workflow_id}/versions/${item.version_id}`, { headers })).json();
      assert.equal(current.feedback, revisionText);
      assert.equal(current.steps.find(step => step.method === 'sg').params.window_size, 9);
      assert.equal(current.metadata.template_version_id, revised.id);
      const previous = originalVersions.find(version => version.workflow_id === item.workflow_id);
      assert.deepEqual(await (await context.request.get(`http://127.0.0.1:5000/api/ai-workflows/${item.workflow_id}/versions/${previous.id}`, { headers })).json(), previous);
    }
    await panel().scrollIntoViewIfNeeded();
    await snapshot('batch-results-desktop');
    const download = page.waitForEvent('download');
    await panel().getByRole('button', { name: '下载批量结果', exact: true }).click();
    const archive = path.join(logs, 'batch-results.zip');
    await (await download).saveAs(archive);
    assert.equal((await fs.readFile(archive)).subarray(0, 2).toString(), 'PK');
    const saved = completed.items.find(item => item.status === 'completed' && item.workflow_id !== new URL(page.url()).searchParams.get('task'));
    const priorTask = new URL(page.url()).searchParams.get('task');
    await page.getByRole('button', { name: `删除任务 ${saved.relative_path}`, exact: true }).click();
    await page.getByRole('button', { name: `删除任务 ${saved.relative_path}`, exact: true }).waitFor({ state: 'hidden' });
    assert.equal(new URL(page.url()).searchParams.get('task'), priorTask);
    await panel().getByText('已删除', { exact: true }).waitFor();
    await page.reload();
    await panel().waitFor();
    assert.equal(new URL(page.url()).searchParams.get('batch'), bid);
    assert.equal(await panel().locator('tbody tr').count(), 5);
    await page.setViewportSize({ width: 390, height: 844 });
    await panel().scrollIntoViewIfNeeded();
    await snapshot('batch-results-mobile');
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
    const clipped = await page.locator('.ai-workspace button').evaluateAll(elements => elements.filter(el => el.clientWidth > 0 && el.scrollWidth > el.clientWidth + 3).map(el => el.textContent));
    assert.deepEqual(clipped, []);
    await page.evaluate(() => localStorage.setItem('ramancloud_theme', 'dark'));
    await page.reload(); await panel().waitFor(); await panel().scrollIntoViewIfNeeded();
    await snapshot('batch-results-dark-mobile');
    assert.deepEqual(errors, []);
    assert.deepEqual(dialogs, []);
    console.log('BATCH_E2E_OK single-file/folder-upload/delete/feedback-only/preview-before-execution/revised-batch/old-versions/download/reload/desktop/mobile/dark');
  } finally {
    if (bid) {
      await context.request.post(`http://127.0.0.1:5000/api/ai-workflow-batches/${bid}/cancel`, { headers });
      for (let i = 0; i < 100; i++) {
        const result = await (await context.request.get(`http://127.0.0.1:5000/api/ai-workflow-batches/${bid}`, { headers })).json();
        if (!result.active) break;
        await new Promise(resolve => setTimeout(resolve, 100));
      }
    }
    await context.close(); await browser.close();
    const cleanup = spawnSync(process.env.BACKEND_PYTHON || 'python', ['backend/tests/cleanup_ui_test.py', 'ai-ui-test-account.json'], { cwd: root, encoding: 'utf8' });
    if (cleanup.status !== 0) throw new Error('QA cleanup failed: ' + cleanup.stderr);
    console.log(cleanup.stdout.trim());
    await fs.rm(fixtures, { recursive: true, force: true });
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
