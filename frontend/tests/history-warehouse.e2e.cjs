/* Run only after the parent confirms the redesigned server is ready.
 * Authorized scope: two disposable QA users and their exact project/run/assets.
 * No existing user data, app source, or broad database cleanup is touched.
 * node frontend/tests/history-warehouse.e2e.cjs
 */
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const { inflateRawSync } = require('node:zlib');
const { spawnSync } = require('node:child_process');

const root = path.resolve(__dirname, '../..');
const logs = path.join(root, 'logs');
const apiBase = process.env.E2E_API_URL || 'http://127.0.0.1:5000/api';
const uiBase = process.env.E2E_UI_URL || 'http://127.0.0.1:5173/preprocessing';
const stamp = Date.now();
const title = `QA history warehouse ${stamp}`;
const wave = Array.from({ length: 80 }, (_, i) => 400 + i * 2);
const intensity = wave.map((_, i) => 20 + i + 70 * Math.exp(-(((i - 35) / 7) ** 2)));
const original = Buffer.from('wave,intensity\n' + wave.map((x, i) => `${x},${intensity[i]}`).join('\n'));

// Inspect actual ZIP entry bodies without adding an archive dependency.
function unzip(buffer) {
  const entries = new Map();
  let offset = 0;
  while (buffer.readUInt32LE(offset) === 0x04034b50) {
    assert.equal(buffer.readUInt16LE(offset + 6) & 8, 0, 'ZIP must contain explicit entry sizes');
    const method = buffer.readUInt16LE(offset + 8), size = buffer.readUInt32LE(offset + 18);
    const nameSize = buffer.readUInt16LE(offset + 26), extra = buffer.readUInt16LE(offset + 28);
    const start = offset + 30 + nameSize + extra;
    const name = buffer.subarray(offset + 30, offset + 30 + nameSize).toString();
    const body = buffer.subarray(start, start + size);
    assert.ok(method === 0 || method === 8);
    entries.set(name, method === 8 ? inflateRawSync(body) : body);
    offset = start + size;
  }
  assert.ok(entries.size >= 4, 'ZIP contains original, processed, process and README');
  return entries;
}
function checkCSV(body, expected) {
  const rows = body.toString('utf8').replace(/^\uFEFF/, '').trim().split(/\r?\n/);
  assert.equal(rows.length, wave.length + 1);
  rows.slice(1).forEach((row, i) => {
    const [x, y] = row.split(',').map(Number);
    assert.equal(x, wave[i]);
    assert.ok(Math.abs(y - expected[i]) < 1e-7, `CSV point ${i} matches saved values`);
  });
}
async function main() {
  await fs.mkdir(logs, { recursive: true });
  const users = [], reserved = [], assets = new Set(), tasks = new Set(), errors = [];
  let browser, pid, rid, failure;
  const cleanupErrors = [];
  async function api(user, route, data, method = data === undefined ? 'GET' : 'POST') {
    return user.context.request.fetch(apiBase + route, {
      method, headers: { Authorization: `Bearer ${user.auth.token}` },
      ...(data === undefined ? {} : { data }),
    });
  }
  async function json(user, route, data, method) {
    const response = await api(user, route, data, method);
    assert.equal(response.status(), 200, `${method || 'API'} ${route}: ${await response.text()}`);
    return response.json();
  }
  async function go(user, route) {
    await user.page.goto(uiBase + route);
    await user.page.locator('.welcome-screen').waitFor({ state: 'hidden' });
  }
  async function noJSON(page) {
    assert.equal(await page.locator('pre:visible').count(), 0, 'No raw JSON/pre dump');
    assert.doesNotMatch(await page.locator('body').innerText(), /"(?:wavenumber|intensity|processed_dataset_id)"\s*:/);
  }
  async function chart(page, count = 2) {
    // Plotly SVG paths are inspected only for rendering, never for interaction.
    await page.waitForFunction(n => [...document.querySelectorAll('svg .scatterlayer path.js-line')]
      .filter(p => p.getBoundingClientRect().width > 30 && p.getBoundingClientRect().height > 5 && p.getAttribute('d')?.length > 30).length === n, count);
  }
  async function screenshot(page, name) {
    await page.locator('.welcome-screen').waitFor({ state: 'hidden' });
    await page.evaluate(() => dispatchEvent(new Event('resize')));
    await page.waitForFunction(() => [...document.querySelectorAll('.js-plotly-plot .main-svg')].every(svg =>
      Math.abs(Number(svg.getAttribute('width')) - svg.closest('.js-plotly-plot').getBoundingClientRect().width) < 3));
    await page.screenshot({ path: path.join(logs, `history-warehouse-${stamp}-${name}.png`), fullPage: true, animations: 'disabled' });
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), 'No horizontal page overflow');
  }
  try {
    // The existing helper allowlists these filenames. Exclusive reservations avoid
    // overwriting another test's reports; never remove a report we did not reserve.
    for (const report of ['history-warehouse-owner-test-account.json', 'history-warehouse-member-test-account.json']) {
      const handle = await fs.open(path.join(logs, report), 'wx'); await handle.close(); reserved.push(report);
    }
    browser = await chromium.launch({ headless: true, ...(process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {}) });
    for (let i = 0; i < 2; i++) {
      const context = await browser.newContext({ acceptDownloads: true, viewport: { width: 1440, height: 1000 }, locale: 'zh-CN' });
      const username = `qa_ai_${stamp + i}`;
      const response = await context.request.post(apiBase + '/auth/register', { data: { username, password: 'qa-test-only-password', role: 'user' } });
      assert.equal(response.status(), 200);
      const auth = (await response.json()).data;
      const user = { context, auth, report: reserved[i], username };
      users.push(user);
      await fs.writeFile(path.join(logs, user.report), JSON.stringify({ username, user_id: auth.user.id }));
      await context.addInitScript(token => {
        localStorage.setItem('ramancloud_auth_token', token);
        localStorage.setItem('ramancloud_language', 'zh');
        if (!localStorage.getItem('ramancloud_theme')) localStorage.setItem('ramancloud_theme', 'light');
      }, auth.token);
      user.page = await context.newPage(); user.page.setDefaultTimeout(30000);
      user.page.on('pageerror', e => errors.push(e.message));
    }
    const [owner, member] = users, page = owner.page;
    pid = (await json(owner, '/projects', { name: title })).data.project.id;
    const invitation = await json(owner, `/projects/${pid}/invitations`, { username: member.username, role: 'member' });
    assert.equal((await api(member, `/projects/${pid}`)).status(), 404);
    await json(member, `/project-invitations/${invitation.id}/respond`, { decision: 'accept' });
    await json(member, `/projects/${pid}`);
    const uploaded = await owner.context.request.post(`${apiBase}/projects/${pid}/datasets/upload`, {
      headers: { Authorization: `Bearer ${owner.auth.token}` },
      multipart: { files: { name: `qa-history-${stamp}.csv`, mimeType: 'text/csv', buffer: original } },
    });
    assert.equal(uploaded.status(), 200);
    const source = (await uploaded.json()).data.datasets[0].id; assets.add(source);
    const processed = (await json(owner, '/process', { wavenumber: wave, intensity, steps: [], save_history: true,
      project_id: pid, source_dataset_id: source, source_name: `qa-history-${stamp}.csv`, title })).data;
    rid = processed.analysis_run.id;
    const run = (await json(owner, `/analysis-runs/${rid}`)).data.run;
    const expected = run.result.intensity;
    assert.equal(expected.length, wave.length);
    for (const suffix of ['', '/resources/original', '/resources/data', '/resources/bundle'])
      assert.equal((await api(member, `/analysis-runs/${rid}${suffix}`)).status(), 404, 'Project membership alone does not expose private history');
    assert.equal((await api(owner, `/analysis-runs/${rid}/warehouse`, { project_id: pid, confirm_sharing: false })).status(), 400);
    assert.equal((await json(owner, `/projects/${pid}/datasets`)).data.datasets.filter(a => a.data_kind === 'processed').length, 0);
    await go(owner, `/analysis-history?run=${rid}`);
    await page.getByRole('heading', { name: /分析历史/, level: 1 }).waitFor();
    await page.getByLabel('搜索分析历史', { exact: true }).fill('no-match-' + stamp);
    await page.getByText('暂无符合条件的记录', { exact: true }).waitFor();
    await page.getByLabel('搜索分析历史', { exact: true }).fill(title);
    await page.getByRole('button', { name: new RegExp(title) }).waitFor();
    await page.getByRole('heading', { name: title, exact: true }).waitFor();
    await chart(page); await noJSON(page);
    for (const mode of ['原始', '处理后']) {
      await page.getByRole('button', { name: mode, exact: true }).click(); await chart(page, 1);
    }
    await page.getByRole('button', { name: '叠加对比', exact: true }).click(); await chart(page);
    await screenshot(page, 'desktop');
    await page.getByRole('button', { name: '处理过程', exact: true }).click();
    await page.getByRole('heading', { name: '执行记录', exact: true }).waitFor(); await noJSON(page);
    await page.getByRole('button', { name: '数据与文件', exact: true }).click();
    assert.equal(await page.getByRole('table').getByRole('row').count(), wave.length + 1); await noJSON(page);
    for (const [kind, label] of [['original', '原始文件 / 数据'], ['data', '处理后数据'], ['bundle', '下载全部']]) {
      const responseReady = page.waitForResponse(r => r.url().endsWith(`/analysis-runs/${rid}/resources/${kind}`));
      const downloadReady = page.waitForEvent('download');
      await page.getByRole('button', { name: label, exact: true }).click();
      assert.equal((await responseReady).status(), 200);
      const download = await downloadReady;
      assert.equal(await download.failure(), null);
      const body = await fs.readFile(await download.path());
      if (kind === 'original') assert.deepEqual(body, original);
      if (kind === 'data') checkCSV(body, expected);
      if (kind === 'bundle') {
        const entries = unzip(body);
        assert.deepEqual(entries.get(`original/qa-history-${stamp}.csv`), original);
        checkCSV(entries.get('processed/processed.csv'), expected);
        assert.equal(JSON.parse(entries.get('process.json').toString()).title, title);
        assert.ok(entries.get('README.txt').toString().includes(title));
      }
    }
    await page.getByRole('button', { name: '结果总览', exact: true }).click(); await chart(page);
    for (let attempt = 0; attempt < 2; attempt++) {
      await page.getByRole('button', { name: '保存到处理后仓库', exact: true }).click();
      const dialog = page.getByRole('dialog', { name: '保存到处理后仓库', exact: true });
      assert.equal(await dialog.getByLabel('目标项目', { exact: true }).inputValue(), pid);
      const ready = page.waitForResponse(r => r.url().endsWith(`/analysis-runs/${rid}/warehouse`) && r.request().method() === 'POST');
      await dialog.getByRole('button', { name: '确认保存并向成员开放', exact: true }).click();
      const response = await ready; assert.equal(response.status(), 200);
      assert.deepEqual(response.request().postDataJSON(), { project_id: pid, confirm_sharing: true });
      assets.add((await response.json()).dataset_id);
      await dialog.waitFor({ state: 'hidden' });
    }
    assert.equal(assets.size, 2, 'Repeated saves reuse the same processed asset');
    const saved = (await json(owner, `/projects/${pid}/datasets`)).data.datasets.filter(a => a.data_kind === 'processed');
    assert.equal(saved.length, 1); assert.equal(saved[0].metadata.analysis_run_id, rid);
    const persisted = (await json(owner, `/analysis-runs/${rid}`)).data.run;
    assert.equal(persisted.result_dataset_id, saved[0].id); assert.ok(persisted.is_shared);
    checkCSV(await (await api(member, `/datasets/${saved[0].id}/download`)).body(), expected);
    assert.ok((await json(member, `/projects/${pid}/collaboration`)).results.some(r => r.id === rid));
    assert.equal((await api(owner, `/analysis-runs/${rid}`, undefined, 'DELETE')).status(), 409, 'Shared history cannot be deleted');
    assert.equal((await api(member, `/analysis-runs/${rid}/warehouse`, { project_id: pid, confirm_sharing: true })).status(), 403);
    assert.equal((await api(member, `/analysis-runs/${rid}`, undefined, 'DELETE')).status(), 403);
    for (const kind of ['original', 'data', 'bundle']) assert.equal((await api(member, `/analysis-runs/${rid}/resources/${kind}`)).status(), 200);
    await go(member, `/analysis-history?project=${pid}&run=${rid}`);
    await member.page.getByRole('heading', { name: title, exact: true }).waitFor(); await chart(member.page); await noJSON(member.page);
    assert.equal(await member.page.getByRole('button', { name: '保存到处理后仓库', exact: true }).count(), 0);
    assert.ok(await member.page.getByRole('button', { name: '删除记录', exact: true }).isDisabled());
    await page.setViewportSize({ width: 390, height: 844 }); await chart(page); await screenshot(page, 'mobile');
    await page.evaluate(() => localStorage.setItem('ramancloud_theme', 'dark'));
    await page.reload(); await page.locator('.welcome-screen').waitFor({ state: 'hidden' }); await chart(page); await screenshot(page, 'dark-mobile');
    await page.setViewportSize({ width: 1440, height: 1000 }); await chart(page); await screenshot(page, 'dark-desktop');
    await go(owner, '/projects');
    await page.getByRole('heading', { name: title, exact: true }).waitFor();
    // Warehouse worker owns these accessible labels and preview/link controls.
    await page.getByText('原始数据仓库', { exact: true }).waitFor();
    await page.getByText('处理后数据仓库', { exact: true }).waitFor();
    await page.getByRole('tab', { name: '处理后数据仓库', exact: true }).click();
    const row = page.getByRole('row').filter({ hasText: title });
    await row.getByRole('button', { name: /预览/ }).click();
    await chart(page, 1); await noJSON(page);
    await screenshot(page, 'project-processed');
    await page.getByRole('link', { name: /查看分析历史|查看处理记录/ }).click();
    await page.getByRole('heading', { name: title, exact: true }).waitFor();
    assert.equal(new URL(page.url()).searchParams.get('run'), rid);
    await go(owner, '/projects');
    await page.getByRole('tab', { name: '原始数据仓库', exact: true }).click();
    await page.getByRole('button', { name: '预览 qa-history-' + stamp, exact: true }).click();
    await chart(page, 1); await screenshot(page, 'project-original');
    const rawDownload = page.waitForEvent('download');
    await page.getByRole('button', { name: '下载原件', exact: true }).click();
    assert.deepEqual(await fs.readFile(await (await rawDownload).path()), original);
    await page.setViewportSize({ width: 390, height: 844 });
    await screenshot(page, 'project-mobile');
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.getByRole('button', { name: '开始处理', exact: true }).click();
    await page.waitForURL(url => url.pathname.endsWith('/ai-analysis') && url.searchParams.has('task'));
    const single = new URL(page.url()).searchParams.get('task'); tasks.add(single);
    assert.equal((await json(owner, `/ai-workflows/${single}`)).project_id, pid);
    await go(owner, '/projects');
    await page.getByRole('checkbox', { name: '选择当前列表文件', exact: true }).check();
    await page.getByRole('button', { name: '批量处理', exact: true }).click();
    await page.waitForURL(url => url.pathname.endsWith('/ai-analysis') && url.searchParams.has('batch'));
    const batch = await json(owner, '/ai-workflow-batches/' + new URL(page.url()).searchParams.get('batch'));
    for (const item of batch.items) if (item.workflow_id) tasks.add(item.workflow_id);
    assert.equal(batch.counts.ready, 1);
    assert.deepEqual(errors, []);
  } catch (error) {
    failure = error;
    for (const user of users) if (user.page) await screenshot(user.page, `failure-${user.username}`).catch(() => {});
  } finally {
    const owner = users[0];
    async function remove(route) {
      const response = await api(owner, route, undefined, 'DELETE');
      assert.ok([200, 404].includes(response.status()), `Cleanup ${route}: ${response.status()} ${await response.text()}`);
    }
    try {
      for (const id of tasks) await remove(`/ai-workflows/${id}`);
      if (rid) {
        // Recover an asset ID even if the UI failed immediately after saving.
        const current = await json(owner, `/analysis-runs/${rid}`);
        if (current.data.run.result_dataset_id) assets.add(current.data.run.result_dataset_id);
        await remove(`/analysis-runs/${rid}/publish`);
        await remove(`/analysis-runs/${rid}`);
      }
      for (const id of assets) await remove(`/datasets/${id}`);
      if (pid) await remove(`/projects/${pid}`);
    } catch (error) { cleanupErrors.push(error); }
    // Do not force-delete cyclic references or mask an API cleanup failure.
    if (!cleanupErrors.length) for (const user of users) {
      const result = spawnSync(process.env.BACKEND_PYTHON || process.env.PYTHON_PATH || 'python',
        ['backend/tests/cleanup_ui_test.py', user.report], { cwd: root, encoding: 'utf8' });
      if (result.status !== 0) cleanupErrors.push(new Error(result.stderr || result.stdout || String(result.error)));
      else { console.log(result.stdout.trim()); await fs.unlink(path.join(logs, user.report)); }
    }
    for (const report of reserved) if (!users.some(u => u.report === report)) await fs.unlink(path.join(logs, report));
    for (const user of users) await user.context.close();
    if (browser) await browser.close();
    if (cleanupErrors.length) {
      await fs.writeFile(path.join(logs, `history-warehouse-${stamp}-cleanup.json`), JSON.stringify({
        users: users.map(u => ({ username: u.username, user_id: u.auth.user.id, report: u.report })),
        project_id: pid, analysis_run_id: rid, asset_ids: [...assets], errors: cleanupErrors.map(String),
      }, null, 2));
      console.error('Exact QA cleanup needs attention; retained reports in logs. No broad database cleanup attempted.');
    }
  }
  if (failure || cleanupErrors.length) throw new AggregateError([failure, ...cleanupErrors].filter(Boolean), 'History/warehouse E2E failed');
  console.log('HISTORY_WAREHOUSE_E2E_OK private/exports/chart/warehouse/idempotency/member/desktop/mobile/dark/cleanup');
}
main().catch(error => { console.error(error); process.exitCode = 1; });
