import test from 'node:test';
import assert from 'node:assert/strict';
import { activeTask, appendStandard, commonBand, readyModels } from '../src/pages/mixtureAnalysis.js';

test('SSnet models are reusable only after completed training', () => {
  const jobs = [{id:'a',kind:'train',status:'running'},{id:'b',kind:'predict',status:'completed'},{id:'c',kind:'train',status:'cancelled'},{id:'d',kind:'train',status:'completed'}];
  assert.deepEqual(readyModels(jobs).map(j=>j.id), ['d']);
  assert.equal(activeTask(jobs[0]), true);
  assert.equal(activeTask(jobs[2]), false);
});
test('standard common bands use physical axes and distinguish saved versions', () => {
  const source = (id, version, x) => ({reference:{workflow_id:id,version_id:version},spectrum:{wavenumber:x}});
  const a=source('a',null,[100,1000,2600]), b=source('b','v1',[2500,1000,200]);
  assert.deepEqual(commonBand([a,b]), {start:200,end:2500});
  assert.equal(commonBand([a,source('c',null,[2700,3000])]), null);
  assert.equal(commonBand([]), null);
  assert.equal(appendStandard([a],a).length,1);
  assert.equal(appendStandard([a],source('a','v2',[100,200])).length,2);
});

test('replicate standards uploaded within SSnet remain distinct from preprocessing inputs', () => {
  const first = {reference:{module:'ssnet',source_id:'replicate-1'},spectrum:{wavenumber:[100,200]}};
  const second = {reference:{module:'ssnet',source_id:'replicate-2'},spectrum:{wavenumber:[100,200]}};
  const pair = appendStandard([first],second);
  assert.equal(pair.length,2);
  assert.equal(appendStandard(pair,first).length,2);
  assert.equal(appendStandard(pair,{reference:{workflow_id:'replicate-1',version_id:'saved-v1'}}).length,3);
});
