import test from 'node:test';
import assert from 'node:assert/strict';
import { algorithmReferences } from './algorithmReferences.js';

test('references cover every non-skip algorithm exposed by the pipeline', () => {
  assert.deepEqual(algorithmReferences.map(item => item.id).sort(), ['aabs', 'airpls', 'airpls_old', 'imodpoly', 'peer', 'sg', 'snip', 'wtd']);
  assert.equal(new Set(algorithmReferences.map(item => item.id)).size, algorithmReferences.length);
  for (const item of algorithmReferences) {
    assert.equal(new URL(item.url).protocol, 'https:');
    assert.ok(item.name && item.en && item.zh);
    assert.ok(['denoise', 'baseline'].includes(item.group));
  }
});

test('retains the V1 paper links and distinguishes simplified V2 implementations', () => {
  for (const id of ['peer', 'airpls', 'aabs', 'imodpoly', 'airpls_old']) {
    const item = algorithmReferences.find(item => item.id === id);
    assert.ok(item.en.includes('V2'));
    assert.ok(item.zh.includes('V2'));
  }
  assert.equal(algorithmReferences.find(item => item.id === 'aabs').url, 'https://doi.org/10.1016/j.saa.2016.02.016');
});
