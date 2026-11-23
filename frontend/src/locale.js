import { uiTranslations } from './uiTranslations.js';
import { systemTranslations } from './systemTranslations.js';

export const LANGUAGE_KEY = 'ramancloud_language';
let activeLanguage = 'en';
export const validLanguage = value => value === 'en' || value === 'zh';
export const accountLanguageKey = id => `${LANGUAGE_KEY}:${id}`;
export function readLanguage(storage, key = LANGUAGE_KEY) {
  try { const saved = storage?.getItem(key); return validLanguage(saved) ? saved : 'en'; }
  catch { return 'en'; }
}
export function saveLanguage(storage, language, key = LANGUAGE_KEY) {
  if (!validLanguage(language)) return;
  try { storage?.setItem(key, language); } catch { /* In-memory switching remains available. */ }
}
export function setActiveLanguage(language) { activeLanguage = validLanguage(language) ? language : 'en'; }
export function getLanguage() { return activeLanguage; }
export const getLocale = () => activeLanguage === 'zh' ? 'zh-CN' : 'en-US';
const catalog = { ...systemTranslations, ...uiTranslations };
const englishToChinese = new Map(Object.entries(catalog).filter(([, en]) => en).map(([zh, en]) => [en, zh]));
export function localize(value, language = activeLanguage) {
  if (typeof value !== 'string') return value;
  if (language === 'zh') return englishToChinese.get(value) ?? value;
  if (Object.prototype.hasOwnProperty.call(catalog, value)) return catalog[value];
  const trimmed = value.trim();
  if (trimmed && Object.prototype.hasOwnProperty.call(catalog, trimmed)) return value.replace(trimmed, catalog[trimmed]);
  return value;
}

// Use only on system labels, diagnostics and errors, never on names, file
// contents, feedback, user messages, or model-generated prose.
export function systemText(value, language = activeLanguage) {
  if (typeof value !== 'string') return value;
  const exact = localize(value, language);
  if (exact !== value || language === 'zh') return exact;
  return value.replace(systemPattern, match => catalog[match]);
}
const escape = value => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const systemPattern = new RegExp(Object.keys(catalog).filter(value => value.length > 5)
  .sort((a, b) => b.length - a.length).map(escape).join('|'), 'g');

export function systemValue(value, key = '') {
  if (Array.isArray(value)) return value.map(item => systemValue(item, key));
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([name, item]) => [name, systemValue(item, name)]));
  return /^(label|message|warning|warnings|error|axis_unit|note|notes|status_text)$/.test(key) ? systemText(value) : value;
}
