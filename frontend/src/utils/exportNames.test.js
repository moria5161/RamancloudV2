import test from 'node:test';
import assert from 'node:assert/strict';
import { originalDownloadName, batchDownloadNames } from './exportNames.js';

test('original filenames, Unicode and extensions remain unchanged', () => {
  for (const name of ['sample.txt', 'scan.01.asc', '电解质.csv', 'processed_source.txt']) {
    assert.equal(originalDownloadName(name), name);
  }
  assert.equal(originalDownloadName(null), 'spectrum.txt');
});

test('512 distinct files keep their names without numeric prefixes', () => {
  const spectra = Array.from({ length: 512 }, (_, index) => ({ filename: `scan-${index}.txt` }));
  assert.deepEqual(batchDownloadNames(spectra), spectra.map(item => item.filename));
});

test('duplicate and case-colliding names use directories without renaming files', () => {
  assert.deepEqual(batchDownloadNames([{ filename: 'scan.txt' }, { filename: 'scan.txt' },
    { filename: 'SCAN.txt' }, { filename: 'unique.csv' }]),
  ['1/scan.txt', '2/scan.txt', '3/SCAN.txt', 'unique.csv']);
});

test('ZIP paths cannot contain source directory traversal', () => {
  for (const filename of ['../scan.txt', '..\\scan.txt', '.', '..']) {
    const safe = originalDownloadName(filename);
    assert.equal(safe.includes('/'), false);
    assert.equal(safe.includes('\\'), false);
    assert.notEqual(safe, '..');
  }
});
