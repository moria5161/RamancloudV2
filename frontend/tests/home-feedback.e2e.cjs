/* Requires fresh, isolated QA accounts. Never run against the normal user database. */
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');

async function main() {
  const api = process.env.E2E_API_URL || 'http://127.0.0.1:5001/api';
  const ui = process.env.E2E_UI_URL || 'http://127.0.0.1:5174/preprocessing';
  assert.equal(new URL(api).hostname, '127.0.0.1');
  assert.equal(new URL(api).port, '5001', 'Use the isolated QA backend');
  assert.equal(new URL(ui).hostname, '127.0.0.1');
  assert.equal(new URL(ui).port, '5174', 'Use the isolated QA frontend');
  assert.ok(process.env.FEEDBACK_E2E_ACCOUNTS, 'Set FEEDBACK_E2E_ACCOUNTS to disposable QA account JSON');
  const accounts = JSON.parse(await fs.readFile(process.env.FEEDBACK_E2E_ACCOUNTS, 'utf8'));
  for (const account of Object.values(accounts)) assert.match(account.user.username, /^qa_fb_/);
  const logs = path.resolve(__dirname, '../../logs/home-feedback-ui');
  await fs.mkdir(logs, { recursive: true });
  const browser = await chromium.launch({ headless: true, ...(process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {}) });
  const errors = [], contexts = [];
  try {
    async function session(role) {
      const context = await browser.newContext({ viewport: { width: 1440, height: 1050 }, locale: 'zh-CN' });
      contexts.push(context);
      await context.addInitScript(token => {
        localStorage.setItem('ramancloud_auth_token', token);
        if (!localStorage.getItem('ramancloud_language')) localStorage.setItem('ramancloud_language', 'zh');
        if (!localStorage.getItem('ramancloud_theme')) localStorage.setItem('ramancloud_theme', 'light');
        // Exercise the fallback used by deployments without crypto.randomUUID.
        Object.defineProperty(globalThis.crypto, 'randomUUID', { value: undefined, configurable: true });
      }, accounts[role].token);
      const page = await context.newPage();
      page.setDefaultTimeout(30000);
      page.on('pageerror', error => errors.push(error.message));
      return { context, page, headers: { Authorization: 'Bearer ' + accounts[role].token } };
    }
    const owner = await session('owner'), admin = await session('admin'), other = await session('other');
    await owner.page.goto(ui + '/tutorial#faq');
    await owner.page.locator('.welcome-screen.is-hidden').waitFor({ state: 'attached' });
    const form = owner.page.getByRole('form', { name: '提交用户反馈' });
    const title = 'QA：仪器导入说明需要补充 ' + Date.now();
    const body = '<img src=x onerror=alert(1)>\n上传 WXD 后希望教程解释支持的保存结构。这里是测试文字。';
    await form.getByLabel('反馈类型').selectOption('data');
    await form.getByRole('textbox', { name: '标题', exact: true }).fill(title);
    await form.getByRole('textbox', { name: /问题或建议/ }).fill(body);
    let savedId;
    await owner.page.route('**/api/feedback', async route => {
      if (route.request().method() !== 'POST') return route.continue();
      const response = await route.fetch();
      assert.equal(response.status(), 201);
      savedId = (await response.json()).id;
      await route.abort('failed'); // The database committed, but the browser lost the reply.
    });
    await form.getByRole('button', { name: '提交反馈', exact: true }).click();
    await form.getByRole('alert').waitFor();
    assert.equal(await form.getByRole('textbox', { name: /问题或建议/ }).inputValue(), body);
    await owner.page.unroute('**/api/feedback');
    const retry = owner.page.waitForResponse(response => new URL(response.url()).pathname.endsWith('/api/feedback') && response.request().method() === 'POST');
    await form.getByRole('button', { name: '提交反馈', exact: true }).click();
    assert.equal((await retry).status(), 200, 'Lost-response retry reuses the existing record');
    await form.getByText('反馈已提交', { exact: true }).waitFor();
    const mine = await (await owner.context.request.get(api + '/feedback', { headers: owner.headers })).json();
    assert.equal(mine.total, 1);
    assert.equal(mine.items[0].id, savedId);
    await form.getByRole('link', { name: '查看处理状态与回复' }).click();
    await owner.page.getByRole('heading', { name: title, exact: true }).waitFor();
    assert.equal(await owner.page.getByRole('button', { name: '提交新反馈', exact: true }).count(), 1);
    assert.equal(await owner.page.locator('.feedback-body').innerText(), body);
    assert.equal(await owner.page.locator('.feedback-body img, .feedback-body script').count(), 0, 'Feedback renders as plain text');
    await owner.page.reload();
    await owner.page.getByRole('heading', { name: title, exact: true }).waitFor();
    await owner.page.locator('.welcome-screen.is-hidden').waitFor({ state: 'attached' });
    await owner.page.screenshot({ path: path.join(logs, 'my-feedback-desktop.png'), animations: 'disabled' });

    assert.equal((await other.context.request.get(api + '/feedback/' + savedId, { headers: other.headers })).status(), 404);
    assert.equal((await other.context.request.get(api + '/feedback?scope=all', { headers: other.headers })).status(), 403);
    await other.page.goto(ui + '/feedback?item=' + savedId);
    await other.page.getByRole('alert').waitFor();
    assert.doesNotMatch(await other.page.locator('.feedback-detail').innerText(), /上传 WXD/);
    assert.equal(await other.page.getByRole('link', { name: '反馈管理', exact: true }).count(), 0);

    await admin.page.goto(ui + '/feedback');
    await admin.page.getByRole('heading', { name: title, exact: true }).waitFor();
    await admin.page.getByRole('link', { name: '反馈管理', exact: true }).waitFor();
    assert.equal(await admin.page.getByRole('button', { name: '提交新反馈', exact: true }).count(), 0);
    assert.equal(await admin.page.getByRole('button', { name: '我提交的', exact: true }).count(), 0);
    assert.equal((await admin.context.request.post(api + '/feedback', { headers: admin.headers, data: { request_id: '587d49a2-4229-4ede-8116-af963af04fd4', category: 'bug', title: '管理员不提交反馈', body: '管理员应只查看和处理普通用户提交的反馈内容。', page_path: '/feedback' } })).status(), 403);
    await admin.page.goto(ui + '/tutorial#faq');
    await admin.page.getByRole('link', { name: '查看与处理用户反馈' }).waitFor();
    assert.equal(await admin.page.getByRole('form', { name: '提交用户反馈' }).count(), 0);
    await admin.page.getByRole('link', { name: '查看与处理用户反馈' }).click();
    await admin.page.getByRole('heading', { name: title, exact: true }).waitFor();
    const responseForm = admin.page.getByRole('form', { name: '管理员处理反馈' });
    await responseForm.getByLabel('处理状态').selectOption('in_progress');
    const reply = '已收到，正在核对 WXD 的保存结构，后续会补充教程说明。';
    await responseForm.getByLabel('站内回复', { exact: true }).fill(reply);
    const patch = admin.page.waitForResponse(response => response.request().method() === 'PATCH' && response.url().endsWith('/feedback/' + savedId));
    await responseForm.getByRole('button', { name: '保存处理结果' }).click();
    assert.equal((await patch).status(), 200);
    await admin.page.getByText(/处理状态与回复已保存/).waitFor();
    await admin.page.locator('.welcome-screen.is-hidden').waitFor({ state: 'attached' });
    await admin.page.screenshot({ path: path.join(logs, 'admin-inbox-desktop.png'), animations: 'disabled' });
    await owner.page.reload();
    await owner.page.locator('.feedback-reply').getByText(reply, { exact: true }).waitFor();
    assert.equal(await owner.page.locator('.feedback-detail-heading .feedback-status').innerText(), '处理中');
    assert.equal(await owner.page.getByRole('form', { name: '管理员处理反馈' }).count(), 0);

    await owner.page.goto(ui + '/');
    await owner.page.locator('.research-section').waitFor();
    const tabs = owner.page.getByRole('tablist', { name: '论文研究方向' });
    let papers = 0;
    for (const [index, count] of [[0, 4], [1, 7], [2, 4]]) {
      await tabs.getByRole('tab').nth(index).click();
      if (count > 4) await owner.page.getByRole('button', { name: `查看本类全部 ${count} 篇` }).click();
      assert.equal(await owner.page.locator('.research-card').count(), count);
      for (const image of await owner.page.locator('.research-illustration img').all()) {
        await image.scrollIntoViewIfNeeded();
        await image.evaluate(image => image.complete && image.naturalWidth ? true : new Promise((resolve, reject) => { image.onload = () => resolve(true); image.onerror = () => reject(new Error('Research image failed: ' + image.src)); }));
      }
      for (const link of await owner.page.locator('.research-card h3 a').all()) assert.match(await link.getAttribute('href'), /^https:\/\//);
      papers += count;
    }
    await tabs.getByRole('tab').nth(2).focus();
    await owner.page.keyboard.press('ArrowRight');
    assert.equal(await tabs.getByRole('tab').nth(0).getAttribute('aria-selected'), 'true');
    await owner.page.locator('.research-section').evaluate(el => el.scrollIntoView({ block: 'start' }));
    const imageHeights = await owner.page.locator('.research-illustration').evaluateAll(nodes => nodes.map(node => node.getBoundingClientRect().height));
    assert.ok(Math.max(...imageHeights) - Math.min(...imageHeights) < 2, 'Paper illustrations have equal-height frames');
    await owner.page.screenshot({ path: path.join(logs, 'research-desktop.png'), animations: 'disabled' });

    async function preferences(page, language, theme) {
      const trigger = page.getByRole('button', { name: /^(设置|Settings)$/ });
      await trigger.click();
      await page.locator('.settings-popover').getByRole('button', { name: language === 'en' ? 'English' : '中文', exact: true }).click();
      await page.locator('.settings-popover').getByRole('button', { name: theme === 'dark' ? /^(深色|Dark)$/ : /^(浅色|Light)$/ }).click();
      await trigger.click();
    }
    for (const [language, theme] of [['zh', 'light'], ['en', 'dark']]) {
      await preferences(owner.page, language, theme);
      await preferences(admin.page, language, theme);
      for (const [name, page, route] of [['research', owner.page, '/'], ['tutorial', owner.page, '/tutorial#faq'], ['admin', admin.page, '/feedback']]) {
        await page.goto(ui + route);
        await page.locator('.learning-page').waitFor();
        await page.locator('.welcome-screen.is-hidden').waitFor({ state: 'attached' });
        for (const width of [390, 320]) {
          await page.setViewportSize({ width, height: 844 });
          if (name === 'research') await page.locator('.research-section').evaluate(el => el.scrollIntoView({ block: 'start' }));
          if (name === 'admin') await page.locator('.feedback-detail h2').waitFor();
          const overflow = await page.evaluate(() => ({ page: document.documentElement.scrollWidth > innerWidth, workspace: document.querySelector('.learning-page').scrollWidth > document.querySelector('.learning-page').clientWidth + 1 }));
          assert.deepEqual(overflow, { page: false, workspace: false }, name + language + theme + width);
          if (width === 390) await page.screenshot({ path: path.join(logs, `${name}-${language}-${theme}-mobile.png`), animations: 'disabled' });
        }
      }
    }
    assert.deepEqual(errors, []);
    console.log('HOME_FEEDBACK_UI_OK', JSON.stringify({ papers, retryCreatesOne: true, privateRecords: true, administratorReply: true, persistentOnReload: true, plaintext: true, mobileWidths: [320,390], pageErrors: errors }));
  } finally {
    await Promise.all(contexts.map(context => context.close()));
    await browser.close();
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
