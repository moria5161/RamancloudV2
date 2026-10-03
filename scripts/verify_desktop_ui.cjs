const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const { PNG } = require('pngjs');

function changedPixels(a, b) {
  const first = PNG.sync.read(a), second = PNG.sync.read(b);
  assert.equal(first.width, second.width);
  assert.equal(first.height, second.height);
  let changed = 0;
  for (let i = 0; i < first.data.length; i += 4) {
    if (Math.abs(first.data[i] - second.data[i]) + Math.abs(first.data[i + 1] - second.data[i + 1]) + Math.abs(first.data[i + 2] - second.data[i + 2]) > 15) changed++;
  }
  return changed;
}

async function main() {
  const base = process.env.RAMANCLOUD_TEST_URL;
  assert.ok(base, 'Set RAMANCLOUD_TEST_URL to the desktop loopback URL');
  const origin = new URL(base).origin;
  const output = process.env.RAMANCLOUD_TEST_OUTPUT || 'desktop/build/ui-checks';
  await fs.mkdir(output, { recursive: true });
  const browser = await chromium.launch({ args: ['--no-sandbox', '--disable-dev-shm-usage', '--enable-unsafe-swiftshader'] });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, acceptDownloads: true });
  const errors = [];
  const remoteRequests = [];
  const exports = new Map();
  let exportCompleted;
  await page.exposeFunction('__testBeginDownload', (filename, size) => {
    const id = String(exports.size);
    exports.set(id, { filename, size, chunks: [], sequence: 0 });
    return { id };
  });
  await page.exposeFunction('__testWriteDownload', (id, sequence, chunk) => {
    const session = exports.get(id);
    assert.equal(sequence, session.sequence++);
    session.chunks.push(Buffer.from(chunk, 'base64'));
    return { ok: true };
  });
  await page.exposeFunction('__testFinishDownload', id => {
    const session = exports.get(id);
    const bytes = Buffer.concat(session.chunks);
    assert.equal(bytes.length, session.size);
    exportCompleted({ bytes, filename: session.filename });
    return { ok: true };
  });
  await page.exposeFunction('__testAbortDownload', id => { exports.delete(id); return { ok: true }; });
  await page.addInitScript(() => {
    window.pywebview = { api: {
      begin_download: window.__testBeginDownload,
      write_download: window.__testWriteDownload,
      finish_download: window.__testFinishDownload,
      abort_download: window.__testAbortDownload,
    } };
  });
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/*', route => {
    const url = route.request().url();
    if (url.startsWith(origin) || /^(data|blob):/.test(url)) return route.continue();
    remoteRequests.push(url);
    return route.abort();
  });
  const workspace = () => page.locator('.workspace-route:not([hidden])');
  const controls = () => workspace().locator('.control-dock');
  const idle = () => workspace().locator('.workspace-busy').waitFor({ state: 'hidden', timeout: 90000 });
  const ready = () => page.waitForFunction(() => document.querySelector('.workspace-route:not([hidden]) .js-plotly-plot')?.data?.length);
  const run = async () => {
    const response = page.waitForResponse(r => /\/api\/process(?:-hyperspectral)?$/.test(r.url()) && r.request().method() === 'POST');
    await controls().getByRole('button', { name: 'Run Pipeline', exact: true }).click();
    assert.equal((await response).status(), 200);
    await idle();
  };
  const download = async (button, filename) => {
    let timer;
    const nativeExport = new Promise((resolve, reject) => {
      exportCompleted = resolve;
      timer = setTimeout(() => reject(new Error('Native download bridge did not finish')), 60000);
    });
    const pending = Promise.race([nativeExport, page.waitForEvent('download', { timeout: 60000 })]);
    await button.click();
    const file = await pending.finally(() => clearTimeout(timer));
    const destination = path.join(output, filename || (file.bytes ? file.filename : file.suggestedFilename()));
    if (file.bytes) await fs.writeFile(destination, file.bytes);
    else {
      assert.equal(await file.failure(), null);
      await file.saveAs(destination);
    }
    assert.ok((await fs.stat(destination)).size > 0);
  };
  try {
    await page.goto(base);
    await page.locator('.welcome-screen').waitFor({ state: 'hidden' });
    assert.equal(await page.locator('.home-page').getByRole('link', { name: /Extra Tools/ }).count(), 1);
    await page.locator('.home-page img').first().scrollIntoViewIfNeeded();
    await page.waitForFunction(() => [...document.querySelectorAll('.home-page img')].filter(img => img.loading !== 'lazy' || img.getBoundingClientRect().top < innerHeight).every(img => img.complete && img.naturalWidth > 0));
    await page.getByRole('link', { name: 'Spectral Processing', exact: true }).click();
    await workspace().getByRole('button', { name: 'Demo - Bacterial Spectrum', exact: true }).click();
    await idle();
    await ready();
    await controls().getByRole('button', { name: 'Denoise', exact: true }).click();
    await run();
    const spectrum = await workspace().locator('.js-plotly-plot').first().evaluate(plot => ({ traces: plot.data.length, background: plot._fullLayout.modebar.bgcolor }));
    assert.equal(spectrum.traces, 2);
    assert.equal(spectrum.background.replace(/\s/g, ''), 'rgba(0,0,0,0)');
    await controls().getByRole('checkbox', { name: 'Include processing record (ZIP)', exact: true }).uncheck();
    await download(controls().getByRole('button', { name: 'Download', exact: true }), 'spectrum.txt');
    await controls().getByRole('checkbox', { name: 'Include processing record (ZIP)', exact: true }).check();
    await download(controls().getByRole('button', { name: 'Download', exact: true }), 'spectrum-record.zip');
    assert.equal((await fs.readFile(path.join(output, 'spectrum-record.zip'))).subarray(0, 2).toString(), 'PK');
    await page.screenshot({ path: path.join(output, 'spectral.png') });
    await page.getByRole('link', { name: 'Hyperspectral Processing', exact: true }).click();
    await workspace().getByRole('button', { name: 'Demo - Electrolyte Time Series Data', exact: true }).click();
    await idle();
    await ready();
    await controls().getByRole('button', { name: 'Denoise', exact: true }).click();
    await run();
    await page.waitForFunction(() => document.querySelector('.workspace-route:not([hidden]) .js-plotly-plot')?.data?.length >= 2);
    await controls().getByRole('checkbox', { name: 'Include processing record (ZIP)', exact: true }).uncheck();
    await download(controls().getByRole('button', { name: 'Download', exact: true }), 'timeseries.txt');
    await page.screenshot({ path: path.join(output, 'timeseries.png') });
    const imagingLoaded = page.waitForResponse(r => r.url().includes('/api/demo-hyperspectral/imaging_horiba'));
    await controls().locator('select').first().selectOption('imaging_horiba');
    assert.equal((await imagingLoaded).status(), 200);
    await idle();
    await ready();
    await controls().getByRole('button', { name: 'Denoise', exact: true }).click();
    await run();
    await page.waitForFunction(() => document.querySelector('.workspace-route:not([hidden]) .js-plotly-plot')?.data?.length >= 2);
    await download(controls().getByRole('button', { name: 'Download', exact: true }), 'imaging.txt');
    await page.screenshot({ path: path.join(output, 'imaging.png') });
    await page.getByRole('link', { name: 'Extra Tools', exact: true }).click();
    const tools = page.locator('.route-surface:not([hidden])');
    await tools.locator('input[type=file]').setInputFiles(path.join(output, 'imaging.txt'));
    await download(tools.getByRole('button', { name: 'Run Tool', exact: true }), 'split.zip');
    await tools.getByRole('button', { name: /^Merge Spectra/ }).click();
    await tools.locator('input[type=file]').setInputFiles([path.join(output, 'spectrum.txt'), path.join(output, 'spectrum.txt')]);
    await download(tools.getByRole('button', { name: 'Run Tool', exact: true }), 'merged.txt');
    await tools.getByRole('button', { name: /^Format Conversion/ }).click();
    await tools.locator('input[type=file]').setInputFiles(path.join(output, 'imaging.txt'));
    await download(tools.getByRole('button', { name: 'Run Tool', exact: true }), 'nanophoton.txt');
    await page.getByRole('link', { name: 'Tutorial', exact: true }).click();
    await page.getByRole('button', { name: /Reference/ }).click();
    await page.getByRole('link', { name: 'airPLS', exact: true }).waitFor();
    await page.getByRole('link', { name: 'Contributors', exact: true }).click();
    await page.getByText('Nannan Zhang', { exact: true }).waitFor();
    await page.getByRole('link', { name: 'Homepage', exact: true }).click();
    await page.getByRole('button', { name: 'View global visits', exact: true }).click();
    const globe = page.locator('.visitor-globe-section');
    await globe.scrollIntoViewIfNeeded();
    const canvas = globe.locator('canvas');
    await canvas.waitFor({ timeout: 60000 });
    await page.waitForTimeout(700);
    const first = await canvas.screenshot();
    const pixels = PNG.sync.read(first);
    const colors = new Set();
    for (let i = 0; i < pixels.data.length; i += 4) colors.add(`${pixels.data[i] >> 4},${pixels.data[i + 1] >> 4},${pixels.data[i + 2] >> 4}`);
    assert.ok(colors.size > 40, `Globe must render mapped pixels, got ${colors.size} colors`);
    await page.waitForTimeout(1000);
    assert.ok(changedPixels(first, await canvas.screenshot()) > 300, 'Globe rotates');
    await globe.getByRole('button', { name: 'Pause rotation', exact: true }).click();
    const paused = await canvas.screenshot();
    await globe.getByRole('button', { name: 'Zoom in globe', exact: true }).click();
    await page.waitForTimeout(300);
    assert.ok(changedPixels(paused, await canvas.screenshot()) > 1000, 'Globe zoom works');
    await canvas.screenshot({ path: path.join(output, 'globe.png') });
    await page.getByRole('button', { name: 'Settings', exact: true }).click();
    await page.getByRole('button', { name: 'Dark', exact: true }).click();
    await page.getByRole('button', { name: '中文', exact: true }).click();
    await page.waitForFunction(() => document.documentElement.dataset.theme === 'dark');
    await page.screenshot({ path: path.join(output, 'homepage-dark-zh.png') });
    assert.deepEqual(errors, [], 'No frontend runtime errors');
    assert.deepEqual(remoteRequests, [], 'All content loads offline');
    console.log('PASS desktop UI: routes, offline assets, spectra, time series, imaging, downloads, split/merge/convert, tutorial, contributors, globe, preferences');
  } catch (error) {
    await page.screenshot({ path: path.join(output, 'failure.png') }).catch(() => {});
    await fs.writeFile(path.join(output, 'failure.json'), JSON.stringify({ error: String(error), errors, remoteRequests }, null, 2));
    throw error;
  } finally {
    await browser.close();
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
