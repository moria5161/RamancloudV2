/* Real account preferences on an isolated backend; no external model calls. */
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const UI = process.env.RAMANCLOUD_TEST_UI || 'http://127.0.0.1:5174/preprocessing';
const API = process.env.RAMANCLOUD_TEST_API || 'http://127.0.0.1:5001/api';
const han = /\p{Script=Han}/u;

async function main() {
  const out = path.resolve(__dirname, '../../logs/language-check');
  await fs.mkdir(out, { recursive: true });
  const browser = await chromium.launch({ headless: true, channel: process.env.CHROME_PATH ? undefined : 'msedge', executablePath: process.env.CHROME_PATH });
  const errors = [], findings = [];
  async function session(token) {
    const context = await browser.newContext({ locale: 'zh-CN', viewport: { width: 1440, height: 1000 } });
    await context.route('**/preprocessing/api/**', async route => {
      const pathname = new URL(route.request().url()).pathname.replace('/preprocessing/api', '');
      const response = await route.fetch({ url: API + pathname + new URL(route.request().url()).search });
      await route.fulfill({ response });
    });
    const page = await context.newPage();
    page.on('pageerror', e => errors.push(e.message));
    page.setDefaultTimeout(20000);
    await page.goto(UI + '/login');
    if (token) {
      await page.evaluate(t => localStorage.setItem('ramancloud_auth_token', t), token);
      await page.goto(UI + '/');
      await page.locator('.welcome-screen').waitFor({ state: 'attached' });
    }
    return { context, page };
  }
  async function account() {
    const response = await fetch(API + '/auth/register', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username: 'language_' + Date.now() + '_' + Math.random().toString(36).slice(2, 7), password: 'isolated-language-test' }) });
    assert.equal(response.status, 200);
    return (await response.json()).data;
  }
  async function switchLanguage(page, next) {
    const authenticated = await page.evaluate(() => !!localStorage.getItem('ramancloud_auth_token'));
    const saved = authenticated ? page.waitForResponse(r => r.url().endsWith('/account/preferences') && r.request().method() === 'PUT') : null;
    await page.locator('.settings-trigger').click();
    await page.locator('.settings-popover').getByRole('button', { name: /^(Chinese|中文|English)$/ }).filter({ hasText: next === 'zh' ? /Chinese|中文/ : /^English$/ }).click();
    await page.waitForFunction(expected => document.documentElement.lang === expected, next === 'zh' ? 'zh-CN' : 'en');
    if (saved) assert.equal((await saved).status(), 200);
    await page.locator('.settings-trigger').click();
  }
  async function assertEnglish(page, label) {
    await page.locator('.welcome-screen.is-hidden').waitFor({ state: 'attached' });
    const chinese = await page.locator('body').evaluate(body => {
      const rows = []; const walker = document.createTreeWalker(body, NodeFilter.SHOW_TEXT);
      while (walker.nextNode()) {
        const n = walker.currentNode, parent = n.parentElement;
        if (!parent || !parent.getClientRects().length || parent.closest('[hidden],[aria-hidden="true"],script,style')) continue;
        if (/\p{Script=Han}/u.test(n.textContent)) rows.push(n.textContent.trim());
      }
      const attributes = [...body.querySelectorAll('[title],[placeholder],[aria-label]')].filter(n => n.getClientRects().length && !n.closest('[hidden],[aria-hidden="true"]')).flatMap(n => ['title','placeholder','aria-label'].map(a => n.getAttribute(a)).filter(v => v && /\p{Script=Han}/u.test(v)));
      return [...new Set([...rows, ...attributes])];
    });
    if (chinese.length) findings.push({ page: label, chinese });
  }
  try {
    const guest = await session();
    assert.equal(await guest.page.locator('html').getAttribute('lang'), 'en', 'First visit is English even in a Chinese browser');
    await switchLanguage(guest.page, 'zh');
    await guest.page.reload();
    assert.equal(await guest.page.locator('html').getAttribute('lang'), 'zh-CN');
    await guest.context.close();
    const a = await account(), b = await account();
    async function apiCall(url, body, method = 'POST') {
      const response = await fetch(API + url, { method, headers: { Authorization: 'Bearer ' + a.token, 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) });
      assert.ok(response.ok, await response.clone().text()); return response.json();
    }
    const task = await apiCall('/ai-workflows/source', { demo: 'tutorial' });
    const version = await apiCall(`/ai-workflows/${task.id}/versions`, { goal: 'Denoise and correct the baseline', steps: [
      { type: 'despike', method: 'despike', params: { threshold: null, fwhm_threshold: 4 }, enabled: true },
      { type: 'denoise', method: 'sg', params: { window_size: 7, order: 3 }, enabled: true },
      { type: 'baseline', method: 'airpls', params: { lam: 1000000, diff_order: 2 }, enabled: true },
    ] });
    await apiCall(`/ai-workflows/${task.id}/versions/${version.id}/execute`, {});
    let completed;
    for (let i = 0; i < 100; i++) {
      completed = await apiCall(`/ai-workflows/${task.id}/versions/${version.id}`, undefined, 'GET');
      if (completed.status === 'completed') break;
      await new Promise(resolve => setTimeout(resolve, 50));
    }
    assert.equal(completed.status, 'completed');
    const first = await session(a.token);
    assert.equal(await first.page.locator('html').getAttribute('lang'), 'en', 'New accounts start in English');
    for (const slug of ['', 'ai-analysis', 'hyperspectral', 'spectral-unmixing', 'library-matching', 'structure-generation', 'projects', 'analysis-history', 'extra-tools', 'tutorial', 'feedback', 'contributors', 'account']) {
      await first.page.goto(UI + '/' + slug);
      await first.page.locator('.welcome-screen').waitFor({ state: 'attached' });
      await first.page.waitForTimeout(450);
      await first.page.locator('details').evaluateAll(nodes => nodes.filter(n => !n.closest('[hidden],[aria-hidden="true"]')).forEach(n => n.open = true));
      await assertEnglish(first.page, slug || 'home');
    }
    await first.page.screenshot({ path: path.join(out, 'english-account.png'), fullPage: true });
    for (const slug of [`ai-analysis?task=${task.id}&version=${version.id}`, `analysis-history?run=${completed.analysis_run_id}`]) {
      await first.page.goto(UI + '/' + slug); await first.page.locator('.welcome-screen').waitFor({ state: 'attached' });
      await first.page.waitForTimeout(800);
      await first.page.locator('details').evaluateAll(nodes => nodes.filter(n => !n.closest('[hidden],[aria-hidden="true"]')).forEach(n => n.open = true));
      await assertEnglish(first.page, slug.split('?')[0] + '-completed');
    }
    await first.page.getByRole('button', { name: 'Export', exact: true }).first().click();
    await first.page.locator('dialog[open]').waitFor();
    await assertEnglish(first.page, 'result-export-dialog');
    await first.page.locator('dialog[open]').getByRole('button', { name: 'Close dialog' }).click();
    await first.page.route('**/api/qa-assistant/plans', route => route.fulfill({ json: [{
      id: 'language-fixture', revision: 1, module: 'ai-analysis', direct_preprocess: true,
      status: 'draft', title: 'Processing plan', summary: 'A controlled UI fixture.',
      source_name: 'spectrum.txt', file_count: 1, context_key: 'fixture', needs_units: true,
      input_summary: { points: 100, wavenumber_min: 400, wavenumber_max: 1800 },
      steps: [{ action: 'preprocess', label: '智能光谱处理', params: { steps: [
        { type: 'despike', method: 'despike', enabled: true, params: { threshold: null, fwhm_threshold: 4 } },
        { type: 'denoise', method: 'sg', enabled: true, params: { window_size: 7, order: 3 } },
      ] } }],
    }] }));
    await first.page.goto(UI + `/ai-analysis?task=${task.id}&version=${version.id}`);
    await first.page.locator('.qa-plan-card').waitFor();
    await first.page.getByText('Detection threshold (blank for automatic)', { exact: true }).waitFor();
    await assertEnglish(first.page, 'plan-card-and-parameters');
    await first.page.screenshot({ path: path.join(out, 'english-results-and-plan.png'), fullPage: true });
    await first.page.route('**/api/qa-assistant/reply', route => route.fulfill({ contentType: 'application/x-ndjson', body: [{ type: 'delta', text: '这条中文模型回答保持原样。' }, { type: 'done' }].map(v => JSON.stringify(v)).join('\n') + '\n' }));
    await first.page.getByRole('textbox', { name: 'Message', exact: true }).fill('保留这条中文用户问题');
    await first.page.getByRole('button', { name: 'Send', exact: true }).click();
    await first.page.getByText('这条中文模型回答保持原样。', { exact: true }).waitFor();
    await switchLanguage(first.page, 'zh');
    assert.equal(await first.page.getByText('保留这条中文用户问题', { exact: true }).count(), 1);
    assert.equal(await first.page.getByText('这条中文模型回答保持原样。', { exact: true }).count(), 1);
    await first.context.close();
    const again = await session(a.token);
    assert.equal(await again.page.locator('html').getAttribute('lang'), 'zh-CN', 'Account preference follows a fresh browser');
    await again.page.locator('.welcome-screen.is-hidden').waitFor({ state: 'attached' });
    await again.page.screenshot({ path: path.join(out, 'chinese-home.png'), fullPage: true });
    const other = await session(b.token);
    assert.equal(await other.page.locator('html').getAttribute('lang'), 'en', 'Other accounts keep their own language');
    await switchLanguage(again.page, 'en');
    await again.page.reload(); await again.page.locator('.welcome-screen').waitFor({ state: 'attached' });
    assert.equal(await again.page.locator('html').getAttribute('lang'), 'en');
    await again.page.setViewportSize({ width: 390, height: 844 });
    await again.page.goto(UI + '/analysis-history');
    await again.page.locator('.qa-launch').waitFor();
    await assertEnglish(again.page, 'mobile-records');
    await again.page.screenshot({ path: path.join(out, 'english-mobile-records.png'), fullPage: true });
    await fs.writeFile(path.join(out, 'findings.json'), JSON.stringify({ findings, errors }, null, 2));
    assert.deepEqual(errors, [], 'No browser runtime errors');
    assert.deepEqual(findings, [], 'English UI contains no Chinese platform text');
    console.log('Language checks passed: 13 pages, Chinese-browser default, guest persistence, account persistence, account isolation and mobile view.');
  } finally { await browser.close(); }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
