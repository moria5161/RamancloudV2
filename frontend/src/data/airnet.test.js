import test from 'node:test';
import assert from 'node:assert/strict';
import { algorithms, algorithmDefaults } from './algorithms.js';
import { algorithmReferences } from './algorithmReferences.js';
import { researchCategories } from './research.js';

test('AirNet is the first baseline choice and exposes no parameters', () => {
  const first = algorithms.filter(item => item.type === 'baseline')[0];
  assert.equal(first.id, 'airnet');
  assert.deepEqual(first.fields, []);
  assert.deepEqual(algorithmDefaults('airnet'), {});
});

test('AirNet has a concise bilingual reference and a publication entry', () => {
  const reference = algorithmReferences.find(item => item.id === 'airnet');
  assert.match(reference.en, /Deep learning/);
  assert.match(reference.zh, /深度学习/);
  const paper = researchCategories.find(item => item.id === 'denoising').papers.find(item => item.title.startsWith('AirNet:'));
  assert.equal(reference.url, paper.url);
  assert.equal(paper.image, 'airnet-toc.png');
  assert.match(paper.citation, /98, 24, 18042-18051/);
});
