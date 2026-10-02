import test from 'node:test';
import assert from 'node:assert/strict';
import { sharedHeatmapBounds, selectionShapes } from './chartHelpers.js';

function checkBounds(actual, minimum, maximum) {
  assert.ok(Math.abs(actual.zmin - minimum) < 1e-10);
  assert.ok(Math.abs(actual.zmax - maximum) < 1e-10);
  assert.equal(actual.zauto, false);
}

test('uses exact linearly interpolated P1/P99, excluding extreme outliers', () => {
  const row = [...Array.from({ length: 1000 }, (_, index) => index), 1e9];
  checkBounds(sharedHeatmapBounds([[row]]), 10, 990);
});

test('shared scale pools all values rather than averaging individual percentiles', () => {
  const raw = [[0, 1]];
  const processed = [[100, 101, 102, 103]];
  checkBounds(sharedHeatmapBounds([raw, processed]), 0.05, 102.95);
});

test('independent calls calculate each matrix separately', () => {
  checkBounds(sharedHeatmapBounds([[[0, 1]]]), 0.01, 0.99);
  checkBounds(sharedHeatmapBounds([[[100, 101]]]), 100.01, 100.99);
});

test('ignores non-finite and non-numeric entries', () => {
  checkBounds(sharedHeatmapBounds([null, [[NaN, Infinity, -Infinity, null, undefined, '100', false, -10, 10]]]), -9.8, 9.8);
});

test('empty matrices retain the existing empty-bounds fallback', () => {
  assert.deepEqual(sharedHeatmapBounds([]), {});
  assert.deepEqual(sharedHeatmapBounds([null, [], [[]], [[NaN, Infinity]]]), {});
});

test('constant and single-value arrays retain a non-zero color range', () => {
  assert.deepEqual(sharedHeatmapBounds([[[5, 5, 5]]]), { zmin: 5, zmax: 6, zauto: false });
  assert.deepEqual(sharedHeatmapBounds([[[-7]]]), { zmin: -7, zmax: -6, zauto: false });
  assert.deepEqual(sharedHeatmapBounds([[[0, 0, 0, 0, 1000]]]), { zmin: 0, zmax: 960, zauto: false });
});

test('handles extreme finite values without overflow or collapsed bounds', () => {
  for (const matrix of [[[Number.MAX_VALUE]], [[-Number.MAX_VALUE]], [[-Number.MAX_VALUE, Number.MAX_VALUE]]]) {
    const bounds = sharedHeatmapBounds([matrix]);
    assert.ok(Number.isFinite(bounds.zmin) && Number.isFinite(bounds.zmax));
    assert.ok(bounds.zmin < bounds.zmax);
  }
});

test('never sorts, clips or changes input intensities in place', () => {
  const raw = Object.freeze([Object.freeze([10000, 3, -2]), Object.freeze([8, NaN, 1])]);
  const processed = Object.freeze([Object.freeze([7, 4, 2])]);
  const before = structuredClone([raw, processed]);
  sharedHeatmapBounds(Object.freeze([raw, processed]));
  assert.deepEqual([raw, processed], before);
});

test('selection markers are unchanged', () => {
  const shapes = selectionShapes({ pixel: { x: 3, y: 5 }, compare: true });
  assert.equal(shapes.length, 2);
  assert.deepEqual(shapes.map(shape => [shape.xref, shape.yref]), [['x', 'y'], ['x2', 'y2']]);
  assert.equal(shapes[0].x0, 2.5);
  assert.equal(shapes[0].y1, 5.5);
});
