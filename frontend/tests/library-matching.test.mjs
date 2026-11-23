import test from 'node:test';
import assert from 'node:assert/strict';
import { hasBaseline, matchingSource, referenceCurve, scoreText } from '../src/pages/libraryMatching.js';

test('matching handoff uses the pinned final saved version and baseline status', () => {
  const task = { id: 'task-a', source_name: 'spectrum.txt', versions: [{ id: 'v2' }] };
  const version = { id: 'v2', status: 'completed', steps: [{ type: 'baseline', enabled: true }], trace: [{ after: { wavenumber: [220, 1800], intensity: [1, 2] } }] };
  const input = matchingSource(task, version);
  assert.deepEqual(input.reference, { workflow_id: 'task-a', version_id: 'v2' });
  assert.equal(hasBaseline(input.steps), true);
  input.spectrum.intensity[0] = 9;
  assert.equal(version.trace[0].after.intensity[0], 1);
  assert.throws(() => matchingSource(task, { ...version, id: 'other' }));
  assert.throws(() => matchingSource(task, { ...version, status: 'running' }));
  assert.equal(hasBaseline([{ type: 'baseline', enabled: false }]), false);
});

test('scores remain scores and reference plots use the actual supplied cache', () => {
  assert.equal(scoreText(.2), '20.00%');
  assert.equal(scoreText(null), '—');
  assert.equal(scoreText(1.1), '—');
  const reference = { wavenumber: [220, 1800], intensity: [.1, 1] };
  assert.deepEqual(referenceCurve({ reference }), reference);
  assert.equal(referenceCurve({}), null);
  assert.equal(referenceCurve({ reference: { wavenumber: [220], intensity: [] } }), null);
});
