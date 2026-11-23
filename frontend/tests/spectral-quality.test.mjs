import test from 'node:test';
import assert from 'node:assert/strict';
import { qualityMarkers } from '../src/components/spectralQuality.js';

test('quality markers keep original values and never mix cube pixels into a single spectrum', () => {
  const point = { index: 20, wavenumber: 420, intensity: 30 };
  const report = { spectra_total: 1, issues: [{ code: 'narrow_spike', locations: [point] }, { code: 'uneven_spacing', locations: [{ wavenumber: 430 }] }] };
  assert.deepEqual(qualityMarkers(report), [{ ...point, quality_code: 'narrow_spike' }]);
  assert.deepEqual(point, { index: 20, wavenumber: 420, intensity: 30 });
  assert.deepEqual(qualityMarkers({ ...report, spectra_total: 16 }), []);
  assert.deepEqual(qualityMarkers(null), []);
});
