/* Uses a disposable account and local rules; no real model requests. */
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const fs = require('node:fs/promises');
const path = require('node:path');
const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');

async function main() {
  const root = path.resolve(__dirname, '../..');
  const logs = path.join(root, 'logs');
  await fs.mkdir(logs, { recursive: true });
  const browser = await chromium.launch({ headless: true, ...(process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {}) });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, locale: 'zh-CN' });
  const page = await context.newPage();
  page.setDefaultTimeout(30000);
  const errors = [];
  const operations = [];
  const hyperspectralAssistantRequests = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => {
    if (new URL(page.url()).pathname === '/preprocessing/hyperspectral' && /\/api\/assistant\//.test(request.url())) hyperspectralAssistantRequests.push(request.url());
    if (/\/api\/process(?:-hyperspectral)?$/.test(request.url())) operations.push(request.url());
    if (/\/api\/assistant\/chat$/.test(request.url())) assert.equal(request.postDataJSON().allow_ai, false);
  });
  const username = 'qa_ai_' + Date.now();
  const registered = await context.request.post('http://127.0.0.1:5000/api/auth/register', { data: { username, password: 'qa-test-only-password', role: 'user' } });
  assert.equal(registered.status(), 200);
  const auth = (await registered.json()).data;
  await fs.writeFile(path.join(logs, 'assistant-ui-test-account.json'), JSON.stringify({ username, user_id: auth.user.id }));
  await context.addInitScript(token => { localStorage.setItem('ramancloud_auth_token', token); localStorage.setItem('ramancloud_language', 'zh'); }, auth.token);
  const input = () => page.getByLabel('对话消息', { exact: true });
  async function ask(text) {
    await input().fill(text);
    await page.getByRole('button', { name: '发送消息', exact: true }).click();
    await page.locator('.assistant-message.user').filter({ hasText: text }).waitFor();
    await page.locator('.assistant-status').waitFor({ state: 'hidden' });
  }
  async function selectDemo(value) {
    const loaded = page.waitForResponse(response => /\/api\/demo(?:-hyperspectral)?\//.test(response.url()) && response.status() === 200);
    await page.locator('.workspace-tab-content:not([hidden]) select').first().selectOption(value);
    await loaded;
    await page.locator('.workspace-tab-content:not([hidden]) fieldset').getByRole('button', { name: '运行流程', exact: true }).waitFor();
    await page.waitForFunction(() => !document.querySelector('.workspace-side-panel fieldset').disabled);
  }
  try {
    await page.goto('http://127.0.0.1:5173/preprocessing/spectral');
    await page.locator('.welcome-screen.is-hidden').waitFor({ state: 'attached' });
    await page.getByRole('heading', { name: '智能光谱处理', exact: true }).waitFor();
    assert.equal(new URL(page.url()).pathname, '/preprocessing/ai-analysis');
    assert.equal(await page.getByRole('link', { name: '单光谱处理', exact: true }).count(), 0);
    for (const [name, route] of [['库匹配', 'library-matching'], ['光谱到结构', 'structure-generation']]) {
      await page.getByRole('link', { name, exact: true }).click();
      await page.getByRole('heading', { name, exact: true }).waitFor();
      assert.equal(new URL(page.url()).pathname, '/preprocessing/' + route);
      assert.equal(await page.getByRole('status').innerText(), '功能正在开发中......');
      await page.screenshot({ path: path.join(logs, route + '-desktop.png'), animations: 'disabled' });
      await page.setViewportSize({ width: 390, height: 844 });
      await page.screenshot({ path: path.join(logs, route + '-mobile.png'), animations: 'disabled' });
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
      await page.setViewportSize({ width: 1440, height: 1000 });
    }
    await page.goto('http://127.0.0.1:5173/preprocessing/hyperspectral');
    await selectDemo('timeseries_horiba');
    assert.equal(await page.getByRole('tab', { name: 'AI 对话', exact: true }).count(), 0);
    assert.equal(await page.locator('.assistant-chat').count(), 0);
    const controls = page.locator('.workspace-side-panel fieldset');
    await controls.getByRole('button', { name: '去噪', exact: true }).click();
    await controls.getByLabel('降噪算法', { exact: true }).selectOption('sg');
    assert.equal(operations.length, 0);
    const processed = page.waitForResponse(response => response.url().endsWith('/api/process-hyperspectral') && response.status() === 200);
    await controls.getByRole('button', { name: '运行流程', exact: true }).click();
    await processed;
    await page.getByRole('link', { name: '已保存分析记录', exact: true }).waitFor();
    assert.equal(operations.length, 1);
    assert.deepEqual(hyperspectralAssistantRequests, []);
    await page.screenshot({ path: path.join(logs, 'assistant-hyperspectral.png') });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.waitForFunction(() => [...document.querySelectorAll('.processing-workspace .main-svg')].every(svg => svg.getBoundingClientRect().right <= svg.closest('.js-plotly-plot').getBoundingClientRect().right + 1));
    await page.screenshot({ path: path.join(logs, 'assistant-hyperspectral-mobile.png') });
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto('http://127.0.0.1:5173/preprocessing/extra-tools');
    await input().waitFor();
    await ask('Horiba 和 Nanophoton 怎么转换');
    assert.match(await page.locator('.assistant-messages').innerText(), /没有执行文件操作/);
    await page.screenshot({ path: path.join(logs, 'assistant-tools.png') });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.locator('.tools-chat-panel').scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(logs, 'assistant-tools-mobile.png') });
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
    page.once('dialog', dialog => dialog.accept());
    await page.getByRole('button', { name: '清空对话', exact: true }).click();
    await page.waitForFunction(() => document.querySelectorAll('.assistant-message').length === 0);
    assert.deepEqual(errors, []);
    console.log('ASSISTANT_E2E_OK', JSON.stringify({ operations: operations.length, page_errors: errors.length, screenshots: 8 }));
  } finally {
    await context.close();
    await browser.close();
    const cleanup = spawnSync(process.env.BACKEND_PYTHON || 'python', ['backend/tests/cleanup_ui_test.py', 'assistant-ui-test-account.json'], { cwd: root, encoding: 'utf8' });
    if (cleanup.status !== 0) throw new Error('QA cleanup failed: ' + cleanup.stderr);
    console.log(cleanup.stdout.trim());
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
