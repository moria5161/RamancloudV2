import test from 'node:test';
import assert from 'node:assert/strict';
import { algorithmReferences } from './algorithmReferences.js';
import { algorithms } from './algorithms.js';

test('references cover every non-skip algorithm exposed by the pipeline', () => {
  assert.deepEqual(algorithmReferences.map(item => item.id).sort(), algorithms.map(item => item.id).sort());
  assert.equal(new Set(algorithmReferences.map(item => item.id)).size, algorithmReferences.length);
  for (const item of algorithmReferences) {
    if (item.url) assert.equal(new URL(item.url).protocol, 'https:');
    else assert.equal(item.id, 'f2p');
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

test('F2P reference describes the unpublished masked self-supervised algorithm', () => {
  const f2p = algorithmReferences.find(item => item.id === 'f2p');
  assert.equal(f2p.name, 'F2P');
  assert.equal(f2p.zh, 'Fast2Peak(F2P)算法是一种掩码自监督算法，目前暂未发表。');
  assert.match(f2p.en, /masked self-supervised/);
  assert.match(f2p.en, /not yet been published/);
  assert.equal(f2p.url, 'https://arxiv.org/abs/2610.29753');
});
