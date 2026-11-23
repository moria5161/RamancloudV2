import { getLanguage } from './locale.js';

// Exact, unambiguous name translations only. The model's original labels and
// zero-based class IDs remain authoritative; never guess an unknown chemical.
export const knownLibraryNames = {
  '乙醇': 'Ethanol', '甲醇': 'Methanol', '丙酮': 'Acetone', '苯': 'Benzene',
  '甲苯': 'Toluene', '苯酚': 'Phenol', '环己烷': 'Cyclohexane', '苯甲醚': 'Anisole',
  '乙腈': 'Acetonitrile', '乙酸': 'Acetic acid', '乙酸乙酯': 'Ethyl acetate',
  '二甲基亚砜': 'Dimethyl sulfoxide', '四氢呋喃': 'Tetrahydrofuran', '水': 'Water',
};
export function libraryName(entry, language = getLanguage()) {
  const name = entry?.name || '';
  if (language === 'zh' || !/\p{Script=Han}/u.test(name)) return name;
  return entry.name_en || knownLibraryNames[name] || `Library class #${entry.class_id ?? entry.reference_id ?? '—'}`;
}
export function librarySearchQuery(query) {
  const value = query.trim();
  const id = value.match(/^(?:library\s+)?class\s*#?\s*(\d+)$/i);
  if (id) return id[1];
  return Object.entries(knownLibraryNames).find(([, en]) => en.toLowerCase() === value.toLowerCase())?.[0] || query;
}
