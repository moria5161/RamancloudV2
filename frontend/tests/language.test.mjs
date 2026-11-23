import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { readLanguage, saveLanguage, accountLanguageKey, localize, systemText, systemValue, setActiveLanguage, getLocale } from '../src/locale.js';
import { libraryName, librarySearchQuery } from '../src/libraryNames.js';
import { discussionGoal, planReadiness } from '../src/components/qaPlanReadiness.js';

test('unified algorithm catalog labels and controls are available in English', () => {
  setActiveLanguage('en');
  const catalog = JSON.parse(readFileSync(new URL('../../legacy_algorithm_catalog.json', import.meta.url), 'utf8'));
  for (const spec of catalog) {
    assert.doesNotMatch(systemText(spec.label), /\p{Script=Han}/u, spec.method);
    for (const field of Object.values(spec.params)) assert.doesNotMatch(systemText(field.label), /\p{Script=Han}/u, field.label);
  }
  for (const label of ['（需配置环境/权重）', '使用模型预设参数。']) assert.doesNotMatch(localize(label), /\p{Script=Han}/u);
  setActiveLanguage('zh');
  assert.equal(systemText('AirPLS 自适应重加权'), 'AirPLS 自适应重加权');
});

test('first visit and invalid preferences select English; explicit Chinese is retained', () => {
  const values = new Map(), storage = { getItem: key => values.get(key), setItem: (key, value) => values.set(key, value) };
  assert.equal(readLanguage(storage), 'en');
  saveLanguage(storage, 'zh'); assert.equal(readLanguage(storage), 'zh');
  saveLanguage(storage, 'en', accountLanguageKey('a'));
  saveLanguage(storage, 'zh', accountLanguageKey('b'));
  assert.equal(readLanguage(storage, accountLanguageKey('a')), 'en');
  assert.equal(readLanguage(storage, accountLanguageKey('b')), 'zh');
  values.set('ramancloud_language', 'invalid'); assert.equal(readLanguage(storage), 'en');
  assert.equal(readLanguage({ getItem() { throw Error('blocked'); } }), 'en');
});

test('system labels, dynamic range errors and dates follow the active locale', () => {
  setActiveLanguage('en');
  assert.equal(localize('一键运行'), 'Run plan');
  assert.equal(localize('\n  查看结果  '), '\n  View results  ');
  assert.equal(getLocale(), 'en-US');
  const text = systemText('当前模型需要完整覆盖 400–4000 cm⁻¹；此光谱仅覆盖 500–1800 cm⁻¹，请使用完整波段数据。');
  assert.doesNotMatch(text, /\p{Script=Han}/u);
  assert.match(text, /400–4000/); assert.match(text, /500–1800/);
  setActiveLanguage('zh'); assert.equal(localize('一键运行'), '一键运行'); assert.equal(getLocale(), 'zh-CN');
});

test('diagnostic presentation leaves user names, paths and model prose unchanged', () => {
  setActiveLanguage('en');
  const value = systemValue({ label: '去鬼峰', source_name: '中文样品.txt', answer: '保留中文模型回答', nested: { warnings: ['输入含负强度，已保留；请检查基线校正。'] } });
  assert.equal(value.source_name, '中文样品.txt'); assert.equal(value.answer, '保留中文模型回答');
  assert.equal(value.label, 'Despike'); assert.doesNotMatch(value.nested.warnings[0], /\p{Script=Han}/u);
});

test('library display retains class identity without inventing chemical translations', () => {
  assert.equal(libraryName({ name: '乙醇', class_id: 0 }, 'en'), 'Ethanol');
  assert.equal(libraryName({ name: '未核验的物质', class_id: 0 }, 'en'), 'Library class #0');
  assert.equal(libraryName({ name: '未核验的物质', class_id: 0 }, 'zh'), '未核验的物质');
  assert.equal(librarySearchQuery('ethanol'), '乙醇'); assert.equal(librarySearchQuery('Library class #0'), '0');
});

test('English discussion supports processing goals and excludes explanatory questions', () => {
  setActiveLanguage('en');
  const discussion = text => [{ role: 'user', content: text }, { role: 'assistant', content: 'Acknowledged.' }];
  assert.equal(discussionGoal(discussion('What is baseline correction?')), '');
  assert.equal(discussionGoal(discussion('Denoise the spectrum and correct the baseline')), 'Denoise the spectrum and correct the baseline');
  assert.doesNotMatch(planReadiness({ consent: false }), /\p{Script=Han}/u);
});
