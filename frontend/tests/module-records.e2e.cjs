/* Storage/UI fixtures run only in the isolated service on ports 5001 and 5174. */
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');

async function main() {
  const api = 'http://127.0.0.1:5001/api', ui = 'http://127.0.0.1:5174/preprocessing';
  assert.equal(process.env.MODULE_RECORDS_FIXTURE_SERVICE, '1', 'Use only the isolated fixture service');
  const logs = path.resolve(__dirname, '../../logs/module-records-ui');
  await fs.mkdir(logs, { recursive: true });
  const browser = await chromium.launch({ headless: true, ...(process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {}) });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1050 }, locale: 'zh-CN' });
  try {
    const response = await context.request.post(api + '/auth/register', { data: { username: 'qa_module_' + Date.now(), password: 'qa-module-records-only-password' } });
    assert.equal(response.status(), 200);
    const auth = (await response.json()).data, headers = { Authorization: 'Bearer ' + auth.token };
    await context.addInitScript(token => {
      localStorage.setItem('ramancloud_auth_token', token);
      localStorage.setItem('ramancloud_language', 'zh');
      localStorage.setItem('ramancloud_theme', 'light');
    }, auth.token);
    const page = await context.newPage(), errors = [], sources = {}, saved = {};
    page.setDefaultTimeout(30000);
    page.on('pageerror', error => errors.push(error.message));
    const buffer = Buffer.from('RamanShift(cm^-1)\tIntensity\n' + Array.from({ length: 41 }, (_, i) => `${200 + i * 100}\t${i*i+1}`).join('\n'));
    const get = async route => { const res = await context.request.get(api + route, { headers }); assert.equal(res.status(), 200, await res.text()); return res.json(); };
    async function open(route) {
      await page.goto(ui + route);
      await page.locator('.welcome-screen.is-hidden').waitFor({ state: 'attached' });
    }
    async function upload(module, name) {
      const completed = page.waitForResponse(res => res.url().endsWith(`/api/${module}/sources/upload`) && res.request().method() === 'POST');
      await page.locator('input[type="file"]').first().setInputFiles({ name, mimeType: 'text/plain', buffer });
      const response = await completed;
      assert.equal(response.status(), 200, await response.text());
      const source = await response.json();
      assert.ok(source.id && !source.requires_confirmation);
      assert.equal((await get('/ai-workflows')).length, 0, 'Uploading here must not create a preprocessing task');
      return source;
    }
    async function waitJob(module, kind, click) {
      const created = page.waitForResponse(res => res.url().endsWith(`/api/${module}/${kind}`) && res.request().method() === 'POST');
      await click();
      const response = await created;
      assert.equal(response.status(), 200, await response.text());
      const first = await response.json();
      for (let i = 0; i < 100; i++) {
        const job = await get(`/${module}/jobs/${first.id}`);
        if (job.status === 'failed') throw new Error(job.error);
        if (job.status === 'completed') return job;
        await page.waitForTimeout(50);
      }
      throw new Error('Fixture job timed out');
    }
    async function save(module, title) {
      const form = page.getByRole('form', { name: '保存分析结果', exact: true });
      await form.getByLabel('结果名称', { exact: true }).fill(title);
      const response = page.waitForResponse(res => res.url().endsWith(`/api/${module}/saved-results`) && res.request().method() === 'POST');
      await form.getByRole('button', { name: '保存分析结果', exact: true }).click();
      assert.equal((await response).status(), 200);
      await page.getByText('分析结果已保存', { exact: false }).waitFor();
      const results = await get(`/${module}/saved-results`);
      assert.equal(results.total, 1);
      assert.equal(results.items[0].title, title);
      saved[module] = results.items[0];
      await page.reload();
      await page.locator('.welcome-screen.is-hidden').waitFor({ state: 'attached' });
      await page.getByRole('combobox', { name: '已保存分析', exact: true }).selectOption(results.items[0].id);
      await page.getByText('分析结果已保存', { exact: false }).waitFor();
    }

    await open('/spectral-unmixing');
    await page.getByRole('tab', { name: '建立标准品模型', exact: true }).click();
    sources.ssnet = await upload('ssnet', 'QA_standard_R1.txt');
    await upload('ssnet', 'QA_standard_R2.txt');
    assert.equal(await page.locator('.mx-standards li').count(), 2, 'Both replicate standards remain selected');
    await page.getByLabel('标准品物质名称', { exact: true }).fill('QA synthetic standard');
    await page.getByLabel('SSnet 模型点数', { exact: true }).selectOption('512');
    await page.getByRole('checkbox', { name: '确认标准品横轴为拉曼位移 cm⁻¹', exact: true }).check();
    const model = await waitJob('ssnet', 'train', () => page.getByRole('button', { name: '开始训练并保存模型', exact: true }).click());
    await page.getByText('标准品模型已保存', { exact: true }).waitFor();
    assert.equal(await page.getByRole('button', { name: '保存分析结果', exact: true }).count(), 0, 'A training model is not a mixture result');
    await page.getByRole('tab', { name: '解析混合谱', exact: true }).click();
    await page.getByLabel('SSnet 标准品模型', { exact: true }).selectOption(model.id);
    await upload('ssnet', 'QA_mixture.txt');
    await page.getByRole('checkbox', { name: '确认混合谱横轴为拉曼位移 cm⁻¹', exact: true }).check();
    await waitJob('ssnet', 'predict', () => page.getByRole('button', { name: '开始解析混合谱', exact: true }).click());
    await save('ssnet', 'QA mixture saved result');
    await page.screenshot({ path: path.join(logs, 'mixture-saved.png'), animations: 'disabled' });

    await open('/library-matching');
    sources['library-matching'] = await upload('library-matching', 'QA_library.txt');
    await page.getByRole('checkbox', { name: '确认横轴为拉曼位移 cm⁻¹', exact: true }).check();
    await waitJob('library-matching', 'jobs', () => page.getByRole('button', { name: '开始库匹配', exact: true }).click());
    await save('library-matching', 'QA library saved result');
    await page.screenshot({ path: path.join(logs, 'library-saved.png'), animations: 'disabled' });

    await open('/structure-generation');
    sources['structure-generation'] = await upload('structure-generation', 'QA_generation.txt');
    await page.getByRole('checkbox', { name: '确认横轴为拉曼位移 cm⁻¹', exact: true }).check();
    await waitJob('structure-generation', 'jobs', () => page.getByRole('button', { name: '生成候选结构', exact: true }).click());
    await save('structure-generation', 'QA generation saved result');
    await page.screenshot({ path: path.join(logs, 'generation-saved.png'), animations: 'disabled' });

    assert.equal((await get('/ai-workflows')).length, 0);
    await open('/ai-analysis');
    assert.equal(await page.locator('.ai-task-row').count(), 0, 'Recent preprocessing tasks contain no analysis uploads');
    const newTask = page.waitForResponse(res => res.url().endsWith('/api/ai-workflows/upload') && res.request().method() === 'POST');
    await page.getByLabel('上传光谱', { exact: true }).setInputFiles({ name: 'QA_preprocessing.txt', mimeType: 'text/plain', buffer });
    assert.equal((await newTask).status(), 200);
    await page.locator('.ai-task-row').getByText('QA_preprocessing.txt', { exact: true }).waitFor();
    assert.equal(await page.locator('.ai-task-row').count(), 1);
    await page.screenshot({ path: path.join(logs, 'preprocessing-isolated.png'), animations: 'disabled' });

    await open('/library-matching?job=' + saved['library-matching'].job_id);
    const copied = page.waitForResponse(res => res.url().endsWith('/preprocess') && res.request().method() === 'POST');
    await page.getByRole('button', { name: '复制到智能光谱处理', exact: true }).click();
    assert.equal((await copied).status(), 200);
    await page.waitForURL('**/ai-analysis?task=*');
    assert.equal((await get('/ai-workflows')).length, 2, 'An explicit copy creates a new preprocessing task');

    for (const [module, route] of [['ssnet', '/spectral-unmixing'], ['library-matching', '/library-matching'], ['structure-generation', '/structure-generation']]) {
      await open(route + '?job=' + saved[module].job_id);
      await page.getByText('分析结果已保存', { exact: false }).waitFor();
      const labels = await page.getByRole('combobox', { name: '已保存分析', exact: true }).locator('option').allTextContents();
      assert.equal(labels.filter(label => label.includes('QA ')).length, 1);
      await page.setViewportSize({ width: 390, height: 844 });
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      if (module === 'ssnet') await page.waitForFunction(() => {
        const plot = document.querySelector('.mx-results .js-plotly-plot');
        return plot?._fullLayout?.width <= plot?.getBoundingClientRect().width + 2 && plot.getBoundingClientRect().height >= 340;
      });
      await page.locator('.module-saved-results').evaluate(el => el.scrollIntoView({ block: 'start' }));
      await page.screenshot({ path: path.join(logs, module + '-saved-mobile.png'), animations: 'disabled' });
      await page.setViewportSize({ width: 1440, height: 1050 });
    }
    assert.deepEqual(errors, []);
    await fs.writeFile(path.join(logs, 'persistence.json'), JSON.stringify({ token: auth.token, sources, saved }));
    console.log('MODULE_RECORDS_UI_OK', JSON.stringify({ independentUploads: true, recentPreprocessingOnly: true, replicates: 2, savedModules: Object.keys(saved), reopenAfterReload: true, explicitCopy: true, pageErrors: errors }));
  } finally { await context.close(); await browser.close(); }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
