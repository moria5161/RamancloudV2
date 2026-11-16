import test from 'node:test';
import assert from 'node:assert/strict';
import { prepareBatchDownload } from './spectralDownload.js';

const input = count => Array.from({ length: count }, (_, i) => ({
  filename: `scan-${i}.txt`, wavenumber: [100, 200], intensity: [i, i + 1], baseline: [1, 2],
}));
const success = payload => ({ code: 0, data: { spectra: payload.spectra.map(item => ({
  content: `100\t${item.intensity[0]}\n200\t${item.intensity[1]}\n`,
  baseline: item.baseline ? '100\t1\n200\t2\n' : null,
})) } });

test('139 spectra and baselines download in three requests with filenames and contents intact', async () => {
  const requests = [], progress = [];
  const entries = await prepareBatchDownload(input(139), async payload => {
    requests.push(payload.spectra.length);
    return success(payload);
  }, value => progress.push(value));
  assert.deepEqual(requests, [64, 64, 11]);
  assert.equal(entries.length, 278);
  for (let i = 0; i < 139; i++) {
    assert.equal(entries[i * 2][0], `spectra/scan-${i}.txt`);
    assert.equal(await entries[i * 2][1].text(), `100\t${i}\n200\t${i + 1}\n`);
    assert.equal(entries[i * 2 + 1][0], `baselines/scan-${i}.txt`);
    assert.equal(await entries[i * 2 + 1][1].text(), '100\t1\n200\t2\n');
  }
  assert.equal(progress.at(-1), 100);
});

test('512 files without baselines use eight requests and duplicate names keep separate directories', async () => {
  const spectra = input(512).map(item => ({ ...item, baseline: null }));
  spectra[1].filename = spectra[0].filename;
  let calls = 0;
  const entries = await prepareBatchDownload(spectra, async payload => { calls++; return success(payload); });
  assert.equal(calls, 8);
  assert.equal(entries.length, 512);
  assert.equal(entries[0][0], 'spectra/1/scan-0.txt');
  assert.equal(entries[1][0], 'spectra/2/scan-0.txt');
  assert.equal(entries.at(-1)[0], 'spectra/scan-511.txt');
});

test('failed or incomplete chunks never return a partial archive', async () => {
  let calls = 0;
  await assert.rejects(prepareBatchDownload(input(139), async payload => {
    if (++calls === 2) throw new Error('unavailable');
    return success(payload);
  }), /unavailable/);
  assert.equal(calls, 2);
  await assert.rejects(prepareBatchDownload(input(1), async () => ({ code: 0, data: { spectra: [] } })), /incomplete/);
  await assert.rejects(prepareBatchDownload(input(1), async () => ({ code: 0, data: { spectra: [{ content: 'data' }] } })), /incomplete/);
});
