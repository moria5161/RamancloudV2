import test, { beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import { planReadiness, discussionGoal } from '../src/components/qaPlanReadiness.js';
import { setActiveLanguage } from '../src/locale.js';
beforeEach(() => setActiveLanguage('zh'));

const source = { source_id: 's1' };
const ready = (module, inputs, extra = {}) => planReadiness({ context: { module, inputs, files: [] }, consent: true, messages: [{role:'user',content:'处理当前数据'},{role:'assistant',content:'建议按目标处理，保留原始数据。'}], ...extra });

test('submission preserves the actionable user goal after discussion and acknowledgements', () => {
  const goal='先去鬼峰，再适度降噪，最后扣除基线';
  const messages=[{role:'user',content:goal},{role:'assistant',content:'建议进行这三步。'},
    {role:'user',content:'是的'},{role:'assistant',content:'请核对。'},
    {role:'user',content:'好的'},{role:'assistant',content:'是否每步检查质量？'},
    {role:'user',content:'是的'},{role:'assistant',content:'等待生成方案。'}];
  assert.equal(discussionGoal(messages),goal);
  const changed=[...messages,{role:'user',content:'只降噪，不扣基线'},{role:'assistant',content:'按新目标调整。'}];
  assert.equal(discussionGoal(changed),'只降噪，不扣基线');
  assert.equal(ready('ai-analysis',{source},{input:'',messages}),'');
  assert.equal(discussionGoal([{role:'assistant',content:goal},{role:'user',content:'是的'}]),'');
});

test('all eight modules require meaningful input and accept their real source types', () => {
  for (const [module, inputs] of [
    ['ai-analysis', { source: { workflow_id: 'w1' } }],
    ['hyperspectral', { dataset_id: 'cube' }],
    ['library-matching', { source }],
    ['structure-generation', { source: { reuse_job_id: 'j1' } }],
    ['spectral-unmixing', { source, model_id: 'm1' }],
    ['analysis-history', { export_refs: [{ workflow_id: 'w1' }] }],
    ['projects', { asset_ids: ['a1'] }],
  ]) {
    assert.notEqual(ready(module, {}), '', module);
    assert.equal(ready(module, inputs), '', module);
  }
  assert.notEqual(ready('extra-tools', {}), '');
  assert.equal(ready('extra-tools', {}, { context: { module: 'extra-tools', inputs: {}, files: [{ name: 'x.txt' }] } }), '');
});

test('empty chat, greetings and help requests do not enable generation; discussed objectives do', () => {
  for (const input of ['', '你好', '运行', '下一步该怎么操作？', '帮我解读当前结果']) assert.notEqual(ready('ai-analysis', { source }, { input, messages: [] }), '');
  assert.equal(ready('ai-analysis', { source }, { input: '', messages: [{ role: 'user', content: '温和降噪并去除基线' },{role:'assistant',content:'建议SG降噪并校正基线。'}] }), '');
  assert.notEqual(ready('ai-analysis', { source }, { input: '', messages: [{ role: 'assistant', content: '推荐降噪' }] }), '');
});

test('missing model, empty batch, permissions and active operations block generation', () => {
  assert.match(ready('spectral-unmixing', { source }), /模型/);
  assert.match(ready('spectral-unmixing', { settings: { name: '标准品' }, standards: [] }), /标准品/);
  assert.equal(ready('spectral-unmixing', { settings: { name: '标准品' }, standards: [source] }), '');
  assert.match(ready('ai-analysis', { source, batch_id: 'b1', workflow_ids: [] }), /勾选/);
  assert.equal(ready('ai-analysis', { batch_id: 'b1', workflow_ids: ['w1'] }), '');
  assert.match(ready('ai-analysis', { source }, { consent: false }), /允许/);
  assert.match(ready('ai-analysis', { source }, { status: 'running' }), /等待/);
  assert.match(ready('ai-analysis', { source }, { contextError: '输入冲突' }), /冲突/);
  assert.match(ready('ai-analysis', {}, { context: { locked: true } }), /等待/);
});

test('unsent objectives and unfinished replies never unlock generation',()=>{for(const messages of [[],[{role:'user',content:'降噪并扣除基线'}],[{role:'user',content:'降噪并扣除基线'},{role:'assistant',content:'正在建议',incomplete:true}]])assert.notEqual(ready('ai-analysis',{source},{input:'降噪并扣除基线',messages}), '');});

test('class zero is a valid library source and training mode asks for a target name', () => {
  assert.equal(ready('library-matching', { source: { reference_id: 0 } }), '');
  assert.match(ready('spectral-unmixing', { settings: { mode: 'train', name: '' }, standards: [source] }), /目标名称/);
  assert.match(ready('spectral-unmixing', { settings: { mode: 'train', name: '   ' }, standards: [source] }), /目标名称/);
  assert.equal(ready('spectral-unmixing', { settings: { mode: 'train', name: '标准品' }, standards: [source], model_id: 'old-model' }), '');
});
