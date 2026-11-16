import test from 'node:test';
import assert from 'node:assert/strict';
import { algorithms, algorithmDefaults, stepLogarithmicParameter } from './algorithms.js';

const lambda = algorithms.find(item => item.id === 'airpls').fields.find(field => field.key === 'lam');

test('F2P is available for single and batch spectra without training parameters', () => {
  const f2p = algorithms.find(item => item.id === 'f2p');
  assert.equal(f2p.name, 'F2P');
  assert.equal(algorithms.findIndex(item => item.id === 'f2p'), algorithms.findIndex(item => item.id === 'peer') + 1);
  assert.equal(f2p.type, 'denoise');
  assert.ok(!f2p.batchOnly);
  assert.deepEqual(f2p.fields, []);
  assert.deepEqual(algorithmDefaults('f2p'), {});
});

test('airPLS Lambda steps by orders of magnitude without changing defaults', () => {
  assert.equal(lambda.scale, 'log');
  assert.equal(algorithmDefaults('airpls').lam, 1e7);
  assert.equal(stepLogarithmicParameter(lambda, 1e7, 1), 1e8);
  assert.equal(stepLogarithmicParameter(lambda, 1e7, -1), 1e6);
});

test('Lambda preserves manually entered mantissas and avoids rounding drift', () => {
  assert.equal(stepLogarithmicParameter(lambda, 2.5e7, 1), 2.5e8);
  assert.equal(stepLogarithmicParameter(lambda, 2.5e7, -1), 2.5e6);
  assert.equal(stepLogarithmicParameter(lambda, 3e-12, 1), 3e-11);
});

test('Lambda stepping clamps to backend bounds and recovers empty inputs', () => {
  assert.equal(stepLogarithmicParameter(lambda, 1e12, 1), 1e12);
  assert.equal(stepLogarithmicParameter(lambda, 1e-12, -1), 1e-12);
  for (const value of ['', 0, NaN, Infinity]) {
    assert.equal(stepLogarithmicParameter(lambda, value, 1), 1e8);
  }
});
