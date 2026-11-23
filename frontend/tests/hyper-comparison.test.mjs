import {test} from 'node:test';
import assert from 'node:assert/strict';
import {heatmapLimits,HYPERSPECTRAL_COLORSCALE} from '../src/components/hyperComparison.js';
test('workspace and history share one palette and numeric scale for both roles',()=>{
  assert.equal(HYPERSPECTRAL_COLORSCALE,'Jet');
  assert.deepEqual(heatmapLimits([[1,5],[null,-2]],[[3,0],[NaN,Infinity]]),{zmin:-2,zmax:5});
  assert.deepEqual(heatmapLimits([[0,0]],[[0,0]]),{zmin:0,zmax:1});
  assert.deepEqual(heatmapLimits(undefined,[]),{zmin:0,zmax:1});
});
