import test from 'node:test';
import assert from 'node:assert/strict';
import { WORKFLOW_STAGES, initialStage, uploadNextStage, selectedBand, spectrumResidual, refinementRequest, insertDespike, validDespikeOrder, canMoveStep } from '../src/pages/analysisWorkflow.js';

test('despiking is inserted before denoising, appears once, and cannot be moved after it', () => {
  const crop = { type: 'cut', method: 'cut' }, spike = { type: 'despike', method: 'despike' }, noise = { type: 'denoise', method: 'sg' };
  const plan = insertDespike([crop, noise], spike);
  assert.deepEqual(plan.map(step => step.type), ['cut', 'despike', 'denoise']);
  assert.deepEqual(insertDespike(plan, spike), plan);
  assert.equal(validDespikeOrder([noise, spike]), false);
  assert.equal(canMoveStep(plan, 1, 1), false);
  assert.equal(canMoveStep(plan, 2, -1), false);
  assert.equal(validDespikeOrder([noise, { ...spike, enabled: false }]), true);
  assert.equal(validDespikeOrder([noise, { ...spike, method: 'skip' }]), true);
});

test('workflow follows upload, process and result with optional refinement', () => {
  assert.deepEqual(WORKFLOW_STAGES.map(item => item[0]), ['上传数据', '光谱处理', '查看结果']);
  assert.equal(initialStage(null, null), 0);
  assert.equal(initialStage({}, null), 0);
  assert.equal(initialStage({}, { status: 'draft', metadata: { phase: 'preprocess' } }), 1);
  assert.equal(initialStage({}, { status: 'completed', metadata: { phase: 'preprocess' } }), 2);
  assert.equal(initialStage({}, { status: 'preview', metadata: { phase: 'refine' } }), 2);
});

test('returning to upload resumes the current plan without generating duplicate versions', () => {
  const draft = { status: 'draft', metadata: { phase: 'preprocess' } };
  assert.equal(uploadNextStage({}, null, false), null);
  assert.equal(uploadNextStage({}, draft, false), 1);
  assert.equal(uploadNextStage({}, draft, true), null);
  assert.equal(uploadNextStage({}, { ...draft, status: 'completed' }, false), 2);
  assert.equal(uploadNextStage({}, { ...draft, status: 'failed' }, false), null);
});

test('band is restored from the actual enabled crop, not stale metadata', () => {
  const original = { wavenumber_min: 100, wavenumber_max: 2000 };
  assert.deepEqual(selectedBand([], original), { start: 100, end: 2000 });
  assert.deepEqual(selectedBand([{ type: 'cut', enabled: true, params: { start: 400, end: 1800 } }], original), { start: 400, end: 1800 });
  assert.deepEqual(selectedBand([{ type: 'cut', enabled: false, params: { start: 400, end: 1800 } }], original), { start: 100, end: 2000 });
});

test('residual aligns exact spectral positions, including cropped descending axes', () => {
  const before = { wavenumber: [5, 4, 3, 2], intensity: [10, 8, 6, 4] };
  assert.deepEqual(spectrumResidual(before, { wavenumber: [4, 3], intensity: [7, 3] }), { wavenumber: [4, 3], intensity: [1, 3] });
  assert.equal(spectrumResidual(before, { wavenumber: [4.5], intensity: [8] }), null);
  assert.equal(spectrumResidual(null, before), null);
});

test('feedback alone inherits the active plan goal but an empty form cannot submit', () => {
  const version = { goal: '去背景并保留主要峰', feedback: '' };
  assert.deepEqual(refinementRequest('', ' 减小平滑窗口 ', version), { goal: version.goal, feedback: '减小平滑窗口', canSubmit: true, pending: true });
  assert.equal(refinementRequest('', '', version).canSubmit, false);
  assert.equal(refinementRequest('', '减小平滑窗口', null).canSubmit, false);
  assert.equal(refinementRequest('只降低噪声', '', version).goal, '只降低噪声');
});

test('batch execution must distinguish pending edits from already applied feedback', () => {
  const version = { goal: '适度降噪', feedback: '减小平滑窗口' };
  assert.equal(refinementRequest(version.goal, version.feedback, version).pending, false);
  assert.equal(refinementRequest('', version.feedback, version).pending, false);
  assert.equal(refinementRequest(version.goal, '峰变弱了，再减小窗口', version).pending, true);
  assert.equal(refinementRequest('只去背景', version.feedback, version).pending, true);
});
