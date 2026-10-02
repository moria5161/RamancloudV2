import test from 'node:test';
import assert from 'node:assert/strict';
import { algorithmReferences } from './algorithmReferences.js';
import { algorithms } from './algorithms.js';

test('references cover every non-skip algorithm exposed by the pipeline', () => {
  assert.deepEqual(algorithmReferences.map(item => item.id).sort(), algorithms.map(item => item.id).sort());
  assert.equal(new Set(algorithmReferences.map(item => item.id)).size, algorithmReferences.length);
  for (const item of algorithmReferences) {
    assert.equal(new URL(item.url).protocol, 'https:');
    assert.ok(item.name && item.en && item.zh);
    assert.ok(['denoise', 'baseline'].includes(item.group));
  }
});

test('retains the V1 paper links without obsolete approximation claims', () => {
  for (const id of ['peer', 'airpls', 'aabs', 'imodpoly']) {
    const item = algorithmReferences.find(item => item.id === id);
    assert.ok(!/simplified|currently uses|polynomial baseline fitting/.test(item.en));
  }
  assert.equal(algorithmReferences.find(item => item.id === 'aabs').url, 'https://doi.org/10.1016/j.saa.2016.02.016');
});
