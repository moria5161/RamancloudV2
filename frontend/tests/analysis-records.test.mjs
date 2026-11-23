import {test} from 'node:test';
import assert from 'node:assert/strict';
import {historyView, recordDeletionGroups} from '../src/analysisRecords.js';

const stamp = '2026-11-05T09:00:00Z';
const record = (id, extra = {}) => ({id, title:id, source_name:id, created_at:stamp, analysis_type:'spectrum', ...extra});
const runs = [record('single'), record('bulk-v1', {batch_id:'batch', result:{ai_workflow_id:'bulk-task'}}), record('bulk-v2', {batch_id:'batch', result:{ai_workflow_id:'bulk-task'}}), ...['hyperspectral','mixture_analysis','library_matching','structure_generation'].map(analysis_type=>record(analysis_type,{analysis_type}))];
const pending = [record('draft', {kind:'workflow',status:'draft'}),record('failed',{kind:'workflow',status:'failed'}), record('stopped',{kind:'workflow',status:'cancelled'}), record('bulk-draft',{batch_id:'batch',workflow_id:'bulk-draft',kind:'workflow',status:'draft'}),record('invalid-file',{batch_id:'invalid',item_id:'item',kind:'batch_item',status:'invalid'})];
const batches = [{id:'batch',name:'实验批次',total:2,counts:{completed:1,ready:1},created_at:stamp}, {id:'invalid',name:'导入异常批次',total:1,counts:{invalid:1},created_at:stamp}];
const view = (extra = {}) => historyView({runs, pending, batches, type:'spectrum',processingMode:'single',status:'all',project:'',days:'',query:'', ...extra});
test('single records exclude every batch member and count each task once', () => {
  assert.deepEqual(view().visible.map(r=>r.id), ['single','draft','failed','stopped']);
  assert.equal(view().count,4);
  assert.deepEqual(view({status:'completed'}).visible.map(r=>r.id),['single']);
  assert.deepEqual(view({status:'pending'}).visible.map(r=>r.id),['draft','failed','stopped']);
});
test('batch status filters select members, keep versions together and preserve invalid imports', () => {
  const all = view({processingMode:'batch'});
  assert.equal(all.count,3);
  assert.ok(all.visible.some(r=>r.id==='invalid-file'));
  assert.ok(all.visible.every(r=>r.batch_id));
  assert.equal(view({processingMode:'batch',status:'completed'}).count,1);
  assert.deepEqual(view({processingMode:'batch',status:'pending'}).visible.map(r=>r.id),['bulk-draft','invalid-file']);
});
test('batch names are searchable without pulling unrelated files into results', () => {
  assert.equal(view({processingMode:'batch',query:'实验批次'}).count,2);
  assert.equal(view({processingMode:'batch',query:'bulk-v2'}).count,1);
  assert.equal(view({processingMode:'batch',query:'missing'}).visible.length,0);
});
test('other modules ignore single/batch mode and remain isolated', () => {
  for (const type of ['hyperspectral','mixture_analysis','library_matching','structure_generation']) {
    for (const processingMode of ['single','batch']) assert.deepEqual(view({type,processingMode}).visible.map(r=>r.id),[type]);
  }
});
test('project/time filters also apply to batch summaries and placeholders', () => {
  assert.equal(view({processingMode:'batch',project:'different'}).visible.length,0);
  assert.equal(view({processingMode:'batch',days:'7',now:Date.parse('2026-12-01')}).visible.length,0);
});
test('bulk deletion includes all versions of checked tasks, never unrelated tasks', () => {
  const all = [record('a1',{user_id:'me',result:{ai_workflow_id:'a'}}),record('a2',{user_id:'me',result:{ai_workflow_id:'a'}}),record('b',{user_id:'me'})];
  const groups = recordDeletionGroups([all[1]],all,'me');
  assert.equal(groups.length,1);
  assert.equal(groups[0].deletable,true);
  assert.deepEqual(groups[0].targets.map(item=>item.path),['/analysis-runs/a1','/analysis-runs/a2']);
});
test('shared versions, others records, busy tasks and placeholders cannot be selected', () => {
  const all = [record('shared',{user_id:'me',is_shared:true,result:{ai_workflow_id:'a'}}),record('a2',{user_id:'me',result:{ai_workflow_id:'a'}}),record('other',{user_id:'other'}),record('busy',{kind:'workflow',status:'running'}),record('batch',{kind:'batch'}),record('job',{kind:'module',status:'failed'})];
  assert.ok(recordDeletionGroups(all,all,'me').every(group=>!group.deletable));
});
test('unfinished workflow deletion uses its task endpoint', () => {
  const all = [record('draft',{kind:'workflow',workflow_id:'task',status:'draft'})];
  assert.equal(recordDeletionGroups(all,all,'me')[0].targets[0].path,'/ai-workflows/task');
});
test('batch files and imported-invalid files use atomic member deletion endpoints', () => {
  const all = [...runs.map(record=>({...record,user_id:'me'})),...pending];
  for (const id of ['bulk-v1','bulk-draft','invalid-file']) {
    const group = recordDeletionGroups(all.filter(record=>record.id===id),all,'me')[0];
    assert.equal(group.deletable,true);
    assert.equal(group.targets.length,1);
    assert.match(group.targets[0].path,/^\/ai-workflow-batches\/[^/]+\/items\//);
  }
});
