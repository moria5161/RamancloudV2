import test from 'node:test';
import assert from 'node:assert/strict';
import { pipelineIssues } from './pipelineValidation.js';
import { algorithmDefaults } from '../data/algorithms.js';

const wave = Array.from({ length: 200 }, (_, index) => index);
const step = (method, params = {}) => ({ id: method, type: method === 'cut' ? 'cut' : ['sg', 'wtd', 'peer', 'tsvd', 'f2p'].includes(method) ? 'denoise' : 'baseline', method, params: { ...algorithmDefaults(method), ...params } });

test('all supported defaults are valid on a sufficiently long spectrum', () => {
  for (const method of ['sg', 'wtd', 'peer', 'tsvd', 'f2p', 'airpls', 'aabs', 'imodpoly', 'snip']) assert.deepEqual(pipelineIssues([step(method)], wave), {});
});
test('F2P validates its minimum spectral length after a cut', () => {
  assert.ok(pipelineIssues([step('cut', { start: 0, end: 2 }), step('f2p')], wave).f2p);
  assert.deepEqual(pipelineIssues([step('cut', { start: 0, end: 3 }), step('f2p')], wave), {});
});
test('SG validates odd windows and the order before processing', () => {
  assert.ok(pipelineIssues([step('sg', { window_size: 8 })], wave).sg);
  assert.ok(pipelineIssues([step('sg', { window_size: 7, order: 7 })], wave).sg);
  assert.deepEqual(pipelineIssues([step('sg', { window_size: 9 })], wave), {});
});
test('validation follows cuts and uses the remaining spectral length', () => {
  assert.ok(pipelineIssues([step('cut', { start: 0, end: 4 }), step('sg')], wave).sg);
  assert.ok(pipelineIssues([step('cut', { start: 20, end: 10 })], wave).cut);
  assert.ok(pipelineIssues([step('cut', { start: 300, end: 400 })], wave).cut);
});
test('empty and fractional integer values are invalid, logarithmic decimals are allowed', () => {
  assert.ok(pipelineIssues([step('sg', { window_size: '' })], wave).sg);
  assert.ok(pipelineIssues([step('sg', { order: 2.5 })], wave).sg);
  assert.deepEqual(pipelineIssues([step('airpls', { lam: 2.5e7 })], wave), {});
});
test('WTD, AABS and SNIP respect current spectral length', () => {
  assert.ok(pipelineIssues([step('wtd', { level: 20 })], wave).wtd);
  assert.ok(pipelineIssues([step('aabs')], wave.slice(0, 100)).aabs);
  assert.ok(pipelineIssues([step('snip', { max_half_window: 100 })], wave).snip);
});
test('Chinese validation uses Chinese explanations', () => {
  assert.match(pipelineIssues([step('sg', { window_size: 8 })], wave, 'zh').sg, /奇数/);
});
