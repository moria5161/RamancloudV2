/* Real private instrument fixtures, isolated QA service only. */
const { chromium } = require('playwright');
const fs = require('fs/promises'), path = require('path'), assert = require('assert/strict');
async function main() {
  assert.ok(process.env.NATIVE_INSTRUMENT_FIXTURES, 'Set the local three-instrument fixture directory');
  const fixture = path.resolve(process.env.NATIVE_INSTRUMENT_FIXTURES), names = await fs.readdir(fixture);
  const logs = path.resolve(__dirname, '../../logs/native-import-ui'); await fs.mkdir(logs, { recursive: true });
  const browser = await chromium.launch({ headless: true, executablePath: process.env.CHROME_PATH });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1050 }, locale: 'zh-CN' });
  const errors = [];
  try {
    const api = 'http://127.0.0.1:5001/api', ui = 'http://127.0.0.1:5174/preprocessing';
    const register = await context.request.post(api + '/auth/register', { data: { username: 'qa_native_' + Date.now(), password: 'isolated-native-format-qa' } });
    assert.equal(register.status(), 200); const auth = (await register.json()).data;
    const headers = { Authorization: 'Bearer ' + auth.token };
    await context.addInitScript(token => { localStorage.setItem('ramancloud_auth_token', token); localStorage.setItem('ramancloud_language', 'zh'); localStorage.setItem('ramancloud_theme', 'light'); }, auth.token);
    const page = await context.newPage(); page.setDefaultTimeout(30000); page.on('pageerror', error => errors.push(error.message));
    async function open(route) { await page.goto(ui + route); await page.locator('.welcome-screen.is-hidden').waitFor({ state: 'attached' }); }
    async function tasks() { const res = await context.request.get(api + '/ai-workflows', { headers }); assert.equal(res.status(), 200); return res.json(); }
    const imported = {};
    for (const ext of ['.l6m', '.npg', '.wxd']) {
      await open('/ai-analysis');
      const name = names.find(name => name.endsWith(ext)); assert.ok(name);
      const before = (await tasks()).length;
      const uploaded = page.waitForResponse(res => res.url().endsWith('/ai-workflows/upload') && res.request().method() === 'POST');
      await page.getByLabel('上传光谱', { exact: true }).setInputFiles(path.join(fixture, name));
      const inspectionResponse = await uploaded; assert.equal(inspectionResponse.status(), 200, await inspectionResponse.text());
      const inspection = await inspectionResponse.json(); assert.ok(inspection.requires_confirmation);
      assert.equal((await tasks()).length, before);
      if (ext === '.l6m') {
        assert.equal(inspection.source_check.spectrum_count, 140);
        const choices = page.getByLabel('选择光谱位置', { exact: true });
        await choices.selectOption('17');
        const first = await page.locator('.spectrum-import-items tbody tr').first().locator('td').allTextContents();
        assert.equal(Number(first[1]), Number(inspection.source_check.spectrum_choices[17].preview[0][1].toPrecision(8)));
        await page.screenshot({ path: path.join(logs, 'horiba-select-desktop.png'), animations: 'disabled' });
        await page.setViewportSize({ width: 390, height: 844 });
        assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
        await page.screenshot({ path: path.join(logs, 'horiba-select-mobile.png'), animations: 'disabled' });
        await page.setViewportSize({ width: 1440, height: 1050 });
      }
      if (ext === '.npg') {
        await page.getByText('仪器记录横轴未校准，请核对峰位。', { exact: true }).waitFor();
        assert.equal(inspection.source_check.axis_conversion, 'wavelength_nm_to_raman_shift');
        await page.screenshot({ path: path.join(logs, 'nanophoton-confirm.png'), animations: 'disabled' });
      }
      const confirmed = page.waitForResponse(res => res.url().endsWith('/ai-workflows/upload') && res.request().method() === 'POST');
      await page.getByRole('button', { name: '确认转换并导入', exact: true }).click();
      const result = await confirmed; assert.equal(result.status(), 200, await result.text()); const task = await result.json(); imported[ext] = task;
      if (ext === '.l6m') assert.equal(task.diagnostics.source_check.spectrum_index, 17);
      assert.equal((await tasks()).length, before + 1);
      const original = await context.request.get(api + '/ai-workflows/' + task.id + '/download?kind=original', { headers });
      assert.deepEqual(await original.body(), await fs.readFile(path.join(fixture, name)));
      const standard = await context.request.get(api + '/ai-workflows/' + task.id + '/download?kind=standardized', { headers });
      assert.equal(standard.status(), 200);
      const rows = (await standard.text()).trim().split('\n').slice(1).map(row => row.split('\t').map(Number));
      assert.equal(rows.length, task.original.wavenumber.length);
      rows.forEach(([x,y], i) => { assert.equal(x, task.original.wavenumber[i]); assert.equal(y, task.original.intensity[i]); });
    }
    for (const [slug, route] of [['ssnet', '/spectral-unmixing'], ['library-matching', '/library-matching'], ['structure-generation', '/structure-generation']]) {
      await open(route);
      const upload = page.waitForResponse(res => res.url().endsWith('/' + slug + '/sources/upload') && res.request().method() === 'POST');
      await page.locator('input[type="file"]').first().setInputFiles(path.join(fixture, names.find(name => name.endsWith('.l6m'))));
      assert.equal((await upload).status(), 200);
      await page.getByLabel('选择光谱位置', { exact: true }).selectOption('8');
      const confirm = page.waitForResponse(res => res.url().endsWith('/' + slug + '/sources/upload') && res.request().method() === 'POST');
      await page.getByRole('button', { name: '确认转换并导入', exact: true }).click();
      const res = await confirm; assert.equal(res.status(), 200, await res.text());
      assert.equal((await res.json()).diagnostics.source_check.spectrum_index, 8);
      assert.equal((await tasks()).length, 3);
    }
    await open('/extra-tools');
    assert.equal(await page.locator('.tools-chat-panel').count(), 0);
    assert.ok((await page.locator('input[type="file"]').getAttribute('accept')).includes('.l6m'));
    await page.locator('input[type="file"]').setInputFiles(path.join(fixture, names.find(name => name.endsWith('.l6m'))));
    const splitDownload = page.waitForEvent('download');
    await page.getByRole('button', { name: '运行工具', exact: true }).click();
    await (await splitDownload).saveAs(path.join(logs, 'split_horiba.zip'));
    await page.screenshot({ path: path.join(logs, 'split-horiba-desktop.png'), animations: 'disabled' });
    await page.getByRole('button', { name: /标准双列转换/ }).click();
    await page.locator('input[type="file"]').setInputFiles(path.join(fixture, names.find(name => name.endsWith('.l6m'))));
    const download = page.waitForEvent('download');
    await page.getByRole('button', { name: '转换并下载', exact: true }).click();
    await (await download).saveAs(path.join(logs, 'standard_spectra.zip'));
    await page.screenshot({ path: path.join(logs, 'tools-desktop.png'), animations: 'disabled' });
    await page.setViewportSize({ width: 390, height: 844 });
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await page.screenshot({ path: path.join(logs, 'tools-mobile.png'), animations: 'disabled' });
    assert.deepEqual(errors, []);
    console.log('NATIVE_IMPORT_UI_OK', JSON.stringify({ points: Object.fromEntries(Object.entries(imported).map(([key, task]) => [key, task.original.intensity.length])), mappingSelection: 17, otherModuleSelection: 8, originalsPreserved: true, doublePrecisionExports: true, noDuplicateChat: true, pageErrors: errors }));
  } finally { await context.close(); await browser.close(); }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
