/* Two disposable users exercise project-scoped collaboration without model calls. */
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const fs = require('node:fs/promises');
const path = require('node:path');
const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');

async function main() {
  const root = path.resolve(__dirname, '../..'), logs = path.join(root, 'logs');
  const browser = await chromium.launch({ headless: true, ...(process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {}) });
  const users = [], errors = [];
  let pid, projectOwner, asset;
  const name = '协作验收项目 ' + Date.now();
  async function api(u, route, data, method = data ? 'POST' : 'GET') {
    return u.context.request.fetch('http://127.0.0.1:5000/api' + route, { method, headers: { Authorization: 'Bearer ' + u.auth.token }, ...(data ? { data } : {}) });
  }
  async function go(u, route) { await u.page.goto('http://127.0.0.1:5173/preprocessing' + route); await u.page.locator('.welcome-screen').waitFor({ state: 'hidden' }); }
  try {
    for (let i = 0; i < 2; i++) {
      const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, locale: 'zh-CN' });
      const username = 'qa_ai_' + (Date.now() + i);
      const registered = await context.request.post('http://127.0.0.1:5000/api/auth/register', { data: { username, password: 'qa-test-only-password', role: 'user' } });
      assert.equal(registered.status(), 200);
      const auth = (await registered.json()).data;
      const report = i ? 'assistant-ui-test-account.json' : 'ai-ui-test-account.json';
      await fs.writeFile(path.join(logs, report), JSON.stringify({ username, user_id: auth.user.id }));
      await context.addInitScript(token => { localStorage.setItem('ramancloud_auth_token', token); localStorage.setItem('ramancloud_language', 'zh'); }, auth.token);
      const page = await context.newPage(); page.setDefaultTimeout(30000);
      page.on('pageerror', e => errors.push(e.message)); page.on('dialog', d => d.accept());
      users.push({ context, page, auth, report });
    }
    const [owner, member] = users;
    const created = await api(owner, '/projects', { name }); assert.equal(created.status(), 200);
    pid = (await created.json()).data.project.id; projectOwner = owner;
    await go(owner, '/projects');
    const team = u => u.page.getByRole('region', { name: '项目协作', exact: true });
    await team(owner).getByLabel('邀请用户名', { exact: true }).fill(member.auth.user.username);
    await team(owner).getByRole('button', { name: '邀请', exact: true }).click();
    await team(owner).getByRole('heading', { name: '待接受邀请', exact: true }).waitFor();
    assert.equal((await api(member, `/projects/${pid}`)).status(), 404);
    await go(member, '/projects');
    await member.page.getByRole('button', { name: `接受邀请 ${name}`, exact: true }).click();
    await team(member).getByText('我的角色：项目成员', { exact: true }).waitFor();
    await team(member).getByRole('cell', { name: member.auth.user.username, exact: true }).waitFor();
    assert.equal(await team(member).getByLabel('邀请用户名', { exact: true }).count(), 0);
    assert.equal((await api(member, '/users')).status(), 403);

    const wave = Array.from({ length: 40 }, (_, i) => 400 + i);
    const intensity = wave.map((_, i) => i * i);
    const file = Buffer.from('wave,intensity\n' + wave.map((x, i) => `${x},${intensity[i]}`).join('\n'));
    const uploaded = await owner.context.request.post(`http://127.0.0.1:5000/api/projects/${pid}/datasets/upload`, { headers: { Authorization: 'Bearer ' + owner.auth.token }, multipart: { files: { name: 'shared.csv', mimeType: 'text/csv', buffer: file } } });
    assert.equal(uploaded.status(), 200); asset = (await uploaded.json()).data.datasets[0].id;
    assert.equal((await api(member, `/datasets/${asset}/download`)).status(), 200);
    const processed = await api(owner, '/process', { wavenumber: wave, intensity, steps: [], save_history: true, project_id: pid, source_dataset_id: asset, title: '协作验收结果' });
    assert.equal(processed.status(), 200);
    const rid = (await processed.json()).data.analysis_run.id;
    assert.equal((await api(member, `/analysis-runs/${rid}`)).status(), 404);
    await go(owner, '/analysis-history');
    await owner.page.getByRole('button', { name: '发布到项目', exact: true }).click();
    await owner.page.getByRole('button', { name: '撤下共享结果', exact: true }).waitFor();
    await team(member).getByRole('button', { name: '刷新协作信息', exact: true }).click();
    await team(member).getByRole('tab', { name: '共享成果', exact: true }).click();
    await team(member).getByRole('link', { name: '查看共享结果 协作验收结果', exact: true }).click();
    await member.page.getByRole('heading', { name: '协作验收结果', exact: true }).waitFor();
    assert.equal(await member.page.getByRole('button', { name: '删除', exact: true }).isDisabled(), true);
    assert.equal(await member.page.getByRole('button', { name: '发布到项目', exact: true }).count(), 0);
    await member.page.getByRole('button', { name: '读取参数', exact: true }).click();
    await member.page.getByRole('heading', { name: '格式检查通过', exact: true }).waitFor();
    const privateId = new URL(member.page.url()).searchParams.get('task');
    assert.equal((await api(member, `/ai-workflows/${privateId}`)).status(), 200);
    assert.equal((await api(owner, `/ai-workflows/${privateId}`)).status(), 404);

    await go(owner, '/projects');
    await team(owner).getByLabel(`项目角色 ${member.auth.user.username}`, { exact: true }).selectOption('admin');
    await go(member, '/projects');
    await team(member).getByText('我的角色：项目管理员', { exact: true }).waitFor();
    assert.equal((await api(member, '/users')).status(), 403);
    await owner.page.screenshot({ path: path.join(logs, 'collaboration-desktop.png'), animations: 'disabled' });
    const row = team(owner).getByRole('row').filter({ hasText: member.auth.user.username });
    await row.getByRole('button', { name: '转让所有权', exact: true }).click();
    await owner.page.waitForFunction(() => ![...document.querySelectorAll('button')].some(b => b.textContent === '转让所有权'));
    projectOwner = member;
    await team(member).getByRole('button', { name: '刷新协作信息', exact: true }).click();
    await team(member).getByRole('row').filter({ hasText: member.auth.user.username }).getByText('· 所有者', { exact: false }).waitFor();
    await member.page.setViewportSize({ width: 390, height: 844 });
    await team(member).scrollIntoViewIfNeeded();
    await member.page.screenshot({ path: path.join(logs, 'collaboration-mobile.png'), animations: 'disabled' });
    assert.ok(await member.page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await member.page.evaluate(() => localStorage.setItem('ramancloud_theme', 'dark'));
    await member.page.reload(); await team(member).waitFor(); await member.page.locator('.welcome-screen').waitFor({ state: 'hidden' }); await team(member).scrollIntoViewIfNeeded();
    await member.page.screenshot({ path: path.join(logs, 'collaboration-dark-mobile.png'), animations: 'disabled' });
    assert.deepEqual(errors, []);
    console.log('COLLABORATION_E2E_OK invite/accept/data-sharing/private-work/publish/view/role-change/transfer/desktop/mobile/dark');
  } catch (e) { for (let i = 0; i < users.length; i++) await users[i].page.screenshot({ path: path.join(logs, `collaboration-failure-${i}.png`), fullPage: true }); throw e; }
  finally {
    for (const u of users) {
      const tasks = await (await api(u, '/ai-workflows')).json();
      for (const t of tasks) assert.equal((await api(u, `/ai-workflows/${t.id}`, null, 'DELETE')).status(), 200);
      const runs = (await (await api(u, '/analysis-runs')).json()).data.runs;
      for (const r of runs) { if (r.is_shared) await api(u, `/analysis-runs/${r.id}/publish`, null, 'DELETE'); assert.equal((await api(u, `/analysis-runs/${r.id}`, null, 'DELETE')).status(), 200); }
    }
    if (asset) assert.equal((await api(users[0], `/datasets/${asset}`, null, 'DELETE')).status(), 200);
    if (pid) assert.equal((await api(projectOwner, `/projects/${pid}`, null, 'DELETE')).status(), 200);
    for (const u of users) { await u.context.close(); const cleaned = spawnSync(process.env.BACKEND_PYTHON || 'python', ['backend/tests/cleanup_ui_test.py', u.report], { cwd: root, encoding: 'utf8' }); assert.equal(cleaned.status, 0, cleaned.stderr); console.log(cleaned.stdout.trim()); }
    await browser.close();
  }
}
main().catch(e => { console.error(e); process.exitCode = 1; });
