import test from 'node:test';
import assert from 'node:assert/strict';
import { makeGenerationDraft, modelCoverage, validFormula, validateSpectrum, workflowSpectrum } from '../src/pages/structureGeneration.js';

const spectrum = { wavenumber: [100, 200, 300, 400, 500, 600, 700, 800], intensity: [1, 2, -1, 6, 3, 1, 0, 2] };
const task = { id: 'task-a', source_name: 'sample.txt', original: spectrum, versions: [{ id: 'version-a', status: 'completed' }] };
const processed = { wavenumber: spectrum.wavenumber.slice(0), intensity: spectrum.intensity.map(v => v * 2) };
const version = { id: 'version-a', status: 'completed', trace: [{ after: processed }], steps: [{ type: 'despike' }] };

test('preprocessing handoff selects the final saved curve and pins its version', () => {
  const source = workflowSpectrum(task, version);
  assert.deepEqual(source.spectrum, processed);
  assert.notDeepEqual(source.spectrum, task.original);
  assert.deepEqual(source.reference, { workflow_id: task.id, version_id: version.id });
  assert.notEqual(source.spectrum.intensity, processed.intensity);
  assert.throws(() => workflowSpectrum(task, { ...version, status: 'preview' }));
  assert.throws(() => workflowSpectrum(task, { ...version, id: 'another-task-version' }));
  assert.throws(() => workflowSpectrum(task, { ...version, trace: [] }));
});

test('spectrum checks preserve descending axes and negative intensities without resampling', () => {
  assert.deepEqual(validateSpectrum({ wavenumber: [...spectrum.wavenumber].reverse(), intensity: spectrum.intensity }), { points: 8, min: 100, max: 800 });
  assert.throws(() => validateSpectrum({ ...spectrum, intensity: [1] }));
  assert.throws(() => validateSpectrum({ ...spectrum, wavenumber: [100, 100, 300, 400, 500, 600, 700, 800] }));
  assert.throws(() => validateSpectrum({ ...spectrum, intensity: [1, 2, NaN, 4, 5, 6, 7, 8] }));
});

test('formula syntax is checked without inferring unknown formulas', () => {
  for (const value of ['', 'C6H6', 'NaCl', 'C10H12N2O']) assert.equal(validFormula(value), true);
  for (const value of ['C0H6', 'Xx2', 'c6h6', 'C6 H6', '(CH3)2', 'C1001', 'Na+']) assert.equal(validFormula(value), false);
});

test('model coverage reports missing physical ranges before unit confirmation', () => {
  const profile = { start: 400, end: 4000 };
  const input = (start, end) => ({ wavenumber: Array.from({ length: 8 }, (_, i) => start + (end - start) * i / 7), intensity: spectrum.intensity });
  const teaching = input(117.1, 2598.42);
  const snapshot = JSON.stringify(teaching);
  assert.deepEqual(modelCoverage(teaching, profile).missing, [[2598.42, 4000]]);
  assert.equal(modelCoverage(teaching, profile).complete, false);
  assert.equal(JSON.stringify(teaching), snapshot);
  assert.deepEqual(modelCoverage(input(500, 3200), profile).missing, [[400, 500], [3200, 4000]]);
  assert.deepEqual(modelCoverage(input(-177, 172), profile).missing, [[400, 4000]]);
  assert.equal(modelCoverage(input(4000, 400), profile).complete, true);
  assert.equal(modelCoverage(input(-10591, 9032), profile).complete, true);
  assert.equal(modelCoverage(teaching, { start: 220, end: 1800 }).complete, true);
  assert.equal(modelCoverage(null, profile), null);
  assert.equal(modelCoverage(teaching, null), null);
});

test('integration export never claims inference or invents a model grid', () => {
  const source = workflowSpectrum(task, version);
  const settings = { formula: '', topK: 5, rerank: true, unitConfirmed: true };
  const snapshot = JSON.stringify(source);
  const draft = makeGenerationDraft(source, settings);
  assert.equal(draft.inference_performed, false);
  assert.equal(draft.purpose, 'integration_draft');
  assert.equal(draft.generation.formula, null);
  assert.equal(draft.model_profile_id, null);
  assert.equal(draft.preparation.grid, null);
  assert.equal(draft.preparation.applied, false);
  assert.deepEqual(draft.input.spectrum, processed);
  assert.equal(JSON.stringify(source), snapshot);
  assert.throws(() => makeGenerationDraft(source, { ...settings, unitConfirmed: false }));
  assert.throws(() => makeGenerationDraft(source, { ...settings, topK: 20 }));
  assert.throws(() => makeGenerationDraft(source, { ...settings, formula: 'fake-formula' }));
});
