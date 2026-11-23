import test from 'node:test';
import assert from 'node:assert/strict';
import { answerBlocks, inlineParts, plainAnswer } from '../src/components/qaAnswer.js';

test('headings, emphasis and lists copy as readable text', () => {
  const input = '## 建议\n\n**先预览**，再保存。\n1. 检查参数\n2. 对比曲线\n- 保留原版本';
  assert.equal(answerBlocks(input)[0].type, 'heading');
  assert.equal(plainAnswer(input), '建议\n\n先预览，再保存。\n\n1. 检查参数\n\n2. 对比曲线\n\n• 保留原版本');
});
test('literal math, units, C# and code symbols are preserved', () => {
  const input = 'C#；2 * 3 * 4；cm⁻¹；[comparison]';
  assert.equal(plainAnswer(input), input);
  for (const literal of ['*', '**', '`']) assert.equal(plainAnswer(literal), literal);
  assert.equal(inlineParts('* 3 *').map(part => part.text).join(''), '* 3 *');
  assert.equal(plainAnswer('```python\nx = a * b\n# comment\n```'), 'x = a * b\n# comment');
});
test('tables render as cells and raw HTML remains text', () => {
  const blocks = answerBlocks('| 方法 | 参数 |\n| --- | --- |\n| SG | 7 |');
  assert.equal(blocks[0].type, 'table');
  assert.deepEqual(blocks[0].rows, [['方法', '参数'], ['SG', '7']]);
  assert.equal(inlineParts('<img src=x onerror=alert(1)>')[0].type, 'text');
});
