import test from 'node:test';
import assert from 'node:assert/strict';
import { processSpectralBatch } from './spectralBatch.js';

const spectra = count => Array.from({ length: count }, (_, index) => ({ filename: `${index}.txt` }));
const success = input => ({ code: 0, data: { spectra: input } });

test('512 spectra run as eight sequential groups of 64 in original order', async () => {
  const input = spectra(512);
  const requests = [], progress = [];
  let active = 0;
  const out = await processSpectralBatch(input, [], async payload => {
    assert.equal(active++, 0);
    await new Promise(resolve => setTimeout(resolve, 1));
    requests.push(payload.spectra.length);
    active--;
    return success(payload.spectra);
  }, value => progress.push(value));
  assert.deepEqual(requests, Array(8).fill(64));
  assert.deepEqual(out, input);
  assert.equal(progress[0], 0);
  assert.equal(progress.at(-1), 100);
});

test('65 spectra preserve the final one-spectrum group', async () => {
  const counts = [];
  const out = await processSpectralBatch(spectra(65), [], async payload => {
    counts.push(payload.spectra.length);
    return success(payload.spectra);
  });
  assert.deepEqual(counts, [64, 1]);
  assert.equal(out.at(-1).filename, '64.txt');
});

test('TSVD sends all spectra together to preserve the joint decomposition', async () => {
  let calls = 0;
  const out = await processSpectralBatch(spectra(512), [{ type: 'denoise', method: 'tsvd' }], async payload => {
    calls++;
    assert.equal(payload.spectra.length, 512);
    return success(payload.spectra);
  });
  assert.equal(calls, 1);
  assert.equal(out.length, 512);
});

test('a failed group stops further processing and never returns partial results', async () => {
  let calls = 0;
  await assert.rejects(processSpectralBatch(spectra(512), [], async payload => {
    if (++calls === 2) throw new Error('request failed');
    return success(payload.spectra);
  }), /request failed/);
  assert.equal(calls, 2);
});

test('incomplete results are rejected rather than dropping files', async () => {
  await assert.rejects(processSpectralBatch(spectra(65), [], async () => success([])), /incomplete/);
});

test('empty batches and more than 512 spectra are rejected before any request', async () => {
  for (const count of [0, 513]) {
    await assert.rejects(processSpectralBatch(spectra(count), [], () => assert.fail('unexpected request')), /512/);
  }
});
