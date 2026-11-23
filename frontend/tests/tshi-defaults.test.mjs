import test from 'node:test';
import assert from 'node:assert/strict';
import { denoiseDefaults } from '../src/components/tshiDefaults.mjs';

test('TSHI uses the selected physical wavenumber, not a fixed array index', () => {
  const params = denoiseDefaults('tshi', { selectedWN: 0, wavenumber: [-2, 0, 2], shape: [8, 9, 3] });
  assert.equal(params.center_wavenumber, 0);
  assert.equal(params.windowsize, 5);
  assert.equal(params.bm3d_enabled, false);
  assert.equal(params.smoothness, 'legacy');
  assert.equal('window_size' in params, false);
});
test('switching algorithms clears TSHI-only parameters', () => {
  assert.deepEqual(denoiseDefaults('sg'), { window_size: 7, order: 3 });
  assert.deepEqual(denoiseDefaults('skip'), {});
  assert.equal(denoiseDefaults('tshi', { shape: [3, 4, 10] }).windowsize, 3);
});
