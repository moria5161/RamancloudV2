import catalog from '../../../legacy_algorithm_catalog.json' with { type: 'json' };
export const legacyAlgorithms = catalog;
export function legacyDefaults(method) {
  const spec = catalog.find(s => s.method === method);
  return spec ? Object.fromEntries(Object.entries(spec.params).map(([k,r]) => [k,r.default])) : null;
}
