/* Run against an isolated server with controlled intent/text responses and real preprocessing. */
const { chromium } = require('playwright');
const assert = require('node:assert/strict');

const UI = process.env.RAMANCLOUD_TEST_UI || 'http://127.0.0.1:5188/preprocessing';
const API = process.env.RAMANCLOUD_TEST_API || 'http://127.0.0.1:5018/api';

async function main() {
  const browser = await chromium.launch({ headless: true, channel: process.env.CHROME_PATH ? undefined : 'msedge', executablePath: process.env.CHROME_PATH });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1050 } });
  try {
    const registered = await context.request.post(`${API}/auth/register`, {
      data: { username: `qa_turn_${Date.now()}`, password: 'isolated-discussion' },
    });
    assert.equal(registered.status(), 200);
    const { token } = (await registered.json()).data;
    const headers = { Authorization: `Bearer ${token}` };
    await context.addInitScript(value => localStorage.setItem('ramancloud_auth_token', value), token);
    await context.route('**/preprocessing/api/**', async route => {
      const url = new URL(route.request().url());
      try {
        const response = await route.fetch({ url: API + url.pathname.replace('/preprocessing/api', '') + url.search });
        await route.fulfill({ response });
      } catch (error) {
        // Reloads may cancel the original request while the fixture is responding.
        if (!error.message.includes('Route is already handled!')) throw error;
      }
    });
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(`${UI}/`);
    await page.locator('.welcome-screen.is-hidden').waitFor({ state: 'attached' });
    assert.equal(await page.locator('.qa-panel').count(), 0);
    const homeLink = page.locator('nav a[href="/preprocessing"], nav a[href="/preprocessing/"]');
    const branch = page.locator('.home-branch-links');
    const analysisPaths = ['spectral-unmixing', 'library-matching', 'structure-generation', 'hyperspectral', 'peak-fitting'];
    assert.deepEqual(await branch.getByRole('link').evaluateAll(links => links.map(link => link.getAttribute('href'))),
      analysisPaths.map(slug => '/preprocessing/' + slug));
    for (const [slug, title] of [['hyperspectral', 'Hyperspectral processing'], ['peak-fitting', 'Peak fitting']]) {
      await branch.getByRole('link', { name: title, exact: true }).click();
      await page.locator(`[data-analysis-workspace="/${slug}"]:not([hidden])`).waitFor();
      await homeLink.click();
    }
    await page.getByRole('link', { name: 'Check input requirements', exact: true }).click();
    const requirements = page.locator('#reading-requirements');
    await requirements.getByRole('heading', { name: 'Input requirements by workflow' }).waitFor();
    assert.deepEqual(await requirements.getByRole('link').evaluateAll(links => links.map(link => link.hash)),
      ['#preprocessing', '#mixture', '#library', '#structure', '#hyperspectral', '#peak-fitting']);
    await requirements.getByRole('link', { name: 'Peak fitting' }).click();
    assert.equal(new URL(page.url()).hash, '#peak-fitting');
    await homeLink.click();

    async function setLanguage(language) {
      const trigger = page.locator('.settings-trigger');
      await trigger.click();
      const saved = page.waitForResponse(r => r.url().endsWith('/account/preferences') && r.request().method() === 'PUT');
      await page.locator('.settings-popover').getByRole('button', { name: language === 'zh' ? /^(Chinese|中文)$/ : 'English', exact: true }).click();
      await page.waitForFunction(value => document.documentElement.lang === value, language === 'zh' ? 'zh-CN' : 'en');
      assert.ok((await saved).ok());
      await trigger.click();
    }
    await setLanguage('zh');
    await branch.getByRole('link', { name: '高光谱处理', exact: true }).waitFor();
    await branch.getByRole('link', { name: '分峰拟合', exact: true }).waitFor();
    await page.getByRole('link', { name: '先了解输入要求', exact: true }).click();
    await requirements.getByRole('heading', { name: '各分析模块的输入要求' }).waitFor();
    assert.equal(await requirements.getByRole('rowheader').count(), 6);
    await homeLink.click();
    await setLanguage('en');

    await page.getByRole('link', { name: /AI Q&A and preprocessing/ }).click();
    await page.getByRole('heading', { name: 'AI Q&A and preprocessing', exact: true }).waitFor();
    assert.equal(await page.locator('#assistant').getByText(/import data in the workspace/).count(), 1);
    assert.equal(await page.locator('.qa-panel').count(), 0);
    await homeLink.click();
    await page.setViewportSize({ width: 390, height: 844 });
    assert.equal(await page.locator('.qa-launch').count(), 0);
    assert.ok(await branch.evaluate(node => node.scrollWidth <= node.clientWidth + 1), 'analysis links fit on mobile');
    await page.setViewportSize({ width: 1440, height: 1050 });
    await page.getByRole('link', { name: 'Process a spectrum', exact: true }).click();
    const panel = page.locator('.qa-panel');
    const textbox = panel.locator('textarea');
    const card = panel.locator('.qa-plan-card');
    const custom = panel.locator('.qa-bottom-actions').getByRole('button', { name: 'Draft preprocessing plan' });
    const quick = panel.locator('.qa-tools').getByRole('button', { name: 'Quick preprocessing' });
    assert.match(await textbox.getAttribute('placeholder'), /describe the preprocessing/);
    await panel.getByText('Upload or select a spectrum to process first.').waitFor();
    assert.equal(await quick.isDisabled(), true);

    async function send(text, mode = 'chat') {
      await textbox.fill(text);
      const route = mode === 'chat' ? '/reply' : '/preprocessing-turn';
      const response = page.waitForResponse(r => r.url().endsWith('/qa-assistant' + route) && r.request().method() === 'POST');
      await (mode === 'chat' ? panel.getByRole('button', { name: 'Send', exact: true }) : custom).click();
      const received = await response;
      if (!received.ok()) assert.fail(`${received.status()} ${await received.text()}`);
      await page.waitForFunction(() => !document.querySelector('.qa-composer textarea').disabled);
      return received;
    }
    const question = await send('去鬼峰和降噪有什么区别？');
    assert.match(question.headers()['content-type'], /ndjson/);
    assert.equal(await card.count(), 0);

    await panel.locator('input[type=file]').setInputFiles({
      name: 'A_03.txt', mimeType: 'text/plain',
      buffer: Buffer.from(Array.from({ length: 141 }, (_, i) => `${400+i*10}\t${60+0.08*i+17*Math.exp(-((i-70)**2)/190)+0.5*Math.sin(i/5)}`).join('\n')),
    });
    const request = '可以帮我把这条谱的尖刺去掉、平滑一下，再扣掉慢变背景吗？';
    const ordinaryReply = await send(request);
    assert.match(ordinaryReply.headers()['content-type'], /ndjson/);
    assert.equal(await card.count(), 0);
    const twoStepPlan = (await (await send('对光谱进行降噪和基线矫正', 'custom')).json()).plan;
    assert.equal(twoStepPlan.source_name, 'A_03.txt');
    assert.deepEqual(twoStepPlan.steps[0].params.steps.map(s => s.method), ['f2p', 'airnet']);
    assert.equal(await panel.getByRole('button', { name: 'Generate plan', exact: true }).count(), 0);

    const result = await (await send(request, 'custom')).json();
    assert.equal(result.kind, 'plan');
    assert.equal(result.plan.status, 'draft');
    assert.deepEqual(result.plan.steps[0].params.steps.map(s => s.method), ['despike','f2p','airnet']);
    const latest = panel.locator('[data-plan-id="' + result.plan.id + '"]');
    await latest.getByText('Despike → Denoise → Baseline correction', { exact: true }).waitFor();
    assert.deepEqual(await (await context.request.get(`${API}/ai-workflows`, { headers })).json(), []);

    const fields = latest.getByRole('region', { name: 'View / edit algorithms and parameters' });
    await fields.waitFor();
    assert.equal(await latest.locator('summary').count(), 0);
    assert.equal(await latest.getByRole('button', { name: 'Discuss changes to this plan' }).count(), 0);
    const denoise = fields.locator('.qa-plan-algorithm').nth(1);
    assert.equal(await denoise.locator('select').inputValue(), 'f2p');
    assert.equal(await fields.locator('select').nth(2).inputValue(), 'airnet');
    await denoise.locator('select').selectOption('sg');
    await denoise.locator('input[type=number]').first().fill('9');
    await latest.locator('.qa-plan-run').click();
    await latest.locator('.qa-plan-heading span').getByText('Completed', { exact: true }).waitFor();
    assert.equal(await latest.locator('.qa-plan-stages li').filter({ hasText: 'Completed' }).count(), 3);
    const saved = await (await context.request.get(`${API}/qa-assistant/plans/${result.plan.id}`, { headers })).json();
    assert.equal(saved.steps[0].params.steps[1].method, 'sg');
    assert.equal(saved.steps[0].params.steps[1].params.window_size, 9);
    const answer = await send('帮我解读当前结果');
    assert.match(await answer.text(), /execution/);
    assert.equal(await card.count(), 2);

    await panel.locator('.qa-consent input').uncheck();
    await textbox.fill('输入框里留着的草稿');
    assert.equal(await custom.isDisabled(), true);
    const queued = page.waitForResponse(r => r.url().endsWith('/execute') && r.request().method() === 'POST');
    await quick.click();
    const quickResponse = await queued;
    assert.ok(quickResponse.ok(), await quickResponse.text());
    const quickPlan = await quickResponse.json();
    assert.deepEqual(quickPlan.steps[0].params.steps.map(step => step.method), ['despike','f2p','airnet']);
    const quickCard = panel.locator('[data-plan-id="' + quickPlan.id + '"]');
    await quickCard.locator('.qa-plan-heading span').getByText('Completed', { exact: true }).waitFor({ timeout: 90000 });
    const executedFields = quickCard.getByRole('region', { name: 'View algorithms and parameters', exact: true });
    await executedFields.waitFor();
    assert.deepEqual(await executedFields.locator('select').evaluateAll(nodes => nodes.map(n => [n.value, n.disabled])),
      [['despike', true], ['f2p', true], ['airnet', true]]);
    assert.equal(await quickCard.locator('summary').count(), 0);
    assert.equal(await quickCard.getByRole('button', { name: 'Discuss further changes' }).count(), 0);
    assert.equal(await textbox.inputValue(), '输入框里留着的草稿');

    const source = await context.request.post(`${API}/ai-workflows/source`, { headers, data: { demo: 'tutorial' } });
    assert.equal(source.status(), 200);
    const task = await source.json();
    await page.goto(`${UI}/ai-analysis?task=${task.id}`);
    await page.locator(`[data-qa-task="${task.id}"]`).waitFor();
    const pagePlan = await (await send('只降噪，别动基线', 'custom')).json();
    assert.equal(pagePlan.plan.source_name, task.source_name);
    assert.deepEqual(pagePlan.plan.steps[0].params.steps.map(step => step.type), ['denoise']);
    const drafts = () => page.waitForResponse(r => r.url().endsWith('/qa-assistant/plans') && r.request().method() === 'GET');
    let restored = drafts();
    await page.reload();
    await restored;
    await panel.locator(`[data-plan-id="${pagePlan.plan.id}"]`).waitFor();
    const attachmentName = 'smart-page-attachment.txt';
    await panel.locator('input[type=file]').setInputFiles({
      name: attachmentName, mimeType: 'text/plain', buffer: Buffer.from('400 1\n500 2\n600 3\n'),
    });
    await panel.locator('.qa-attachment').getByText(attachmentName, { exact: true }).waitFor();
    for (const module of ['hyperspectral', 'peak-fitting', 'spectral-unmixing', 'library-matching', 'structure-generation']) {
      await page.locator(`nav a[href="/preprocessing/${module}"]`).click();
      await page.locator(`[data-analysis-workspace="/${module}"]:not([hidden])`).waitFor();
      await panel.getByRole('button', { name: 'Send', exact: true }).waitFor();
      assert.equal(await panel.locator('.qa-create-plan, .qa-quick-preprocess, .qa-plan-readiness, .qa-plan-card, input[type=file], .qa-attachment').count(), 0);
    }
    const reply = await send('解释当前页面的设置');
    assert.match(reply.request().postData(), /"path":"\/preprocessing\/structure-generation"/);
    assert.doesNotMatch(reply.request().postData(), /name="action_plan_id"/);
    assert.doesNotMatch(reply.request().postData(), /name="spectrum"|smart-page-attachment\.txt/);
    await panel.getByRole('button', { name: 'Clear conversation', exact: true }).click();
    const retained = await (await context.request.get(`${API}/qa-assistant/plans/${pagePlan.plan.id}`, { headers })).json();
    assert.equal(retained.status, 'draft');
    for (const module of ['projects', 'analysis-history', 'extra-tools', 'tutorial']) {
      await page.locator(`nav a[href="/preprocessing/${module}"]`).click();
      assert.equal(await panel.count(), 0);
    }
    await page.locator('nav a[href="/preprocessing/ai-analysis"]').click();
    await panel.locator(`[data-plan-id="${pagePlan.plan.id}"]`).waitFor();
    await panel.locator('.qa-attachment').getByText(attachmentName, { exact: true }).waitFor();
    const clear = page.waitForResponse(r => r.url().endsWith('/qa-assistant/plans/drafts') && r.request().method() === 'DELETE');
    await panel.getByRole('button', { name: 'Clear conversation', exact: true }).click();
    assert.ok((await clear).ok());
    await card.first().waitFor({ state: 'detached' });
    restored = drafts();
    await page.reload();
    const planList = await (await restored).json();
    assert.ok(!planList.some(plan => plan.id === pagePlan.plan.id));
    assert.ok(planList.some(plan => plan.id === result.plan.id && plan.status === 'completed'));
    await panel.locator('.qa-welcome').waitFor();
    assert.equal(await card.count(), 0);
    await page.waitForLoadState('networkidle');
    assert.deepEqual(errors, []);
    console.log('PASS updated home and guide, preprocessing controls, chat context, and attachment isolation');
  } finally {
    await context.unrouteAll({ behavior: 'wait' });
    await browser.close();
  }
}

main().catch(error => { console.error(error); process.exitCode = 1; });
