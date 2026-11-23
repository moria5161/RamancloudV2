/* Optional integration test: requires a running backend, Ollama and Qwen3 4B Instruct. */
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

async function main() {
  const root = path.resolve(__dirname, '../..');
  const logs = path.join(root, 'logs');
  await fs.mkdir(logs, { recursive: true });
  const browser = await chromium.launch({ headless: true, ...(process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {}) });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, locale: 'zh-CN' });
  const page = await context.newPage();
  page.setDefaultTimeout(360000);
  const username = 'qa_ai_' + Date.now();
  const registered = await context.request.post('http://127.0.0.1:5000/api/auth/register', { data: { username, password: 'qa-test-only-password', role: 'user' } });
  assert.equal(registered.status(), 200);
  const auth = (await registered.json()).data;
  await fs.writeFile(path.join(logs, 'assistant-ui-test-account.json'), JSON.stringify({ username, user_id: auth.user.id }));
  await context.addInitScript(token => { localStorage.setItem('ramancloud_auth_token', token); localStorage.setItem('ramancloud_language', 'zh'); }, auth.token);
  try {
    await page.goto('http://127.0.0.1:5173/preprocessing/ai-analysis');
    await page.getByText('本地模型已就绪', { exact: false }).waitFor();
    await page.locator('.welcome-screen.is-hidden').waitFor({ state: 'attached' });
    await page.getByLabel('示例光谱', { exact: true }).selectOption('tutorial');
    await page.getByRole('heading', { name: 'tutorial_raman.txt', exact: true }).waitFor();
    await page.getByRole('heading', { name: '格式检查通过', exact: true }).waitFor();
    await page.locator('.ai-consent input').first().check();
    const recommendation = page.waitForResponse(response => /\/recommend$/.test(response.url()), { timeout: 360000 });
    const started = Date.now();
    await page.getByRole('button', { name: '生成预处理方案', exact: true }).click();
    const result = await (await recommendation).json();
    assert.equal(result.version?.provider, 'ollama:qwen3:4b-instruct-2507-q4_K_M', JSON.stringify(result));
    assert.equal(result.version.fallback_reason, '');
    assert.ok(result.version.steps.length > 0);
    assert.equal(result.version.metadata.phase, 'preprocess');
    await page.locator('.ai-provider').filter({ hasText: 'Ollama' }).waitFor();
    await page.screenshot({ path: path.join(logs, 'ollama-real-plan.png') });
    console.log('OLLAMA_REAL_PLAN_OK', JSON.stringify({ seconds: (Date.now() - started) / 1000, steps: result.version.steps.map(s => s.method) }));
    await page.goto('http://127.0.0.1:5173/preprocessing/extra-tools');
    await page.getByLabel('对话消息', { exact: true }).waitFor();
    await page.waitForFunction(() => !document.querySelector('.assistant-input textarea').disabled);
    await page.locator('.assistant-consent input').check();
    await page.getByLabel('对话消息', { exact: true }).fill('用一句话解释什么是 SG 降噪，不执行任何操作。');
    const answered = page.waitForResponse(response => /\/assistant\/chat$/.test(response.url()), { timeout: 360000 });
    await page.getByRole('button', { name: '发送消息', exact: true }).click();
    const chat = await (await answered).json();
    assert.equal(chat.reply?.provider, 'ollama', JSON.stringify(chat));
    assert.equal(chat.reply.fallback_reason, '');
    assert.ok(chat.reply.content.length > 5);
    assert.ok(chat.reply.content.length < 400, 'The short question should receive a concise final answer.');
    assert.doesNotMatch(chat.reply.content, /<\/?think>/);
    await page.locator('.assistant-message.assistant').waitFor();
    await page.screenshot({ path: path.join(logs, 'ollama-real-chat.png') });
    console.log('OLLAMA_REAL_CHAT_OK', JSON.stringify({ model: chat.reply.model, answer: chat.reply.content }));
  } finally {
    await context.close();
    await browser.close();
    const cleanup = spawnSync(process.env.BACKEND_PYTHON || 'python', ['backend/tests/cleanup_ui_test.py', 'assistant-ui-test-account.json'], { cwd: root, encoding: 'utf8' });
    if (cleanup.status !== 0) throw new Error('QA cleanup failed: ' + cleanup.stderr);
    console.log(cleanup.stdout.trim());
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
