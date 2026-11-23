import { localize } from '../locale.js';
const ELEMENTS = new Set('H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni Cu Zn Ga Ge As Se Br Kr Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re Os Ir Pt Au Hg Tl Pb Bi Po At Rn Fr Ra Ac Th Pa U Np Pu Am Cm Bk Cf Es Fm Md No Lr Rf Db Sg Bh Hs Mt Ds Rg Cn Nh Fl Mc Lv Ts Og'.split(' '));

export function validFormula(value) {
  if (!value) return true;
  if (value.length > 120) return false;
  const parts = [...value.matchAll(/([A-Z][a-z]?)(\d*)/g)];
  return parts.length > 0 && parts.map(p => p[0]).join('') === value && parts.every(p => ELEMENTS.has(p[1]) && (!p[2] || /^[1-9]\d*$/.test(p[2]) && Number(p[2]) <= 1000));
}

export function validateSpectrum(spectrum) {
  const x = spectrum?.wavenumber, y = spectrum?.intensity;
  if (!Array.isArray(x) || !Array.isArray(y) || x.length !== y.length || x.length < 8 || !x.every(Number.isFinite) || !y.every(Number.isFinite)) throw new Error(localize("需要至少 8 个有效的波数—强度数据点。"));
  const direction = Math.sign(x[1] - x[0]);
  if (!direction || !x.slice(1).every((v, i) => Math.sign(v - x[i]) === direction)) throw new Error(localize("波数轴必须严格单调，不能包含重复点。"));
  return { points: x.length, min: Math.min(x[0], x.at(-1)), max: Math.max(x[0], x.at(-1)) };
}

export function modelCoverage(spectrum, profile) {
  if (!spectrum || !profile) return null;
  const { min, max } = validateSpectrum(spectrum);
  const { start, end } = profile;
  if (!Number.isFinite(start) || !Number.isFinite(end) || start >= end) return null;
  const overlap = max >= start && min <= end;
  const missing = [];
  if (!overlap) missing.push([start, end]);
  else {
    if (min > start) missing.push([start, Math.min(min, end)]);
    if (max < end) missing.push([Math.max(max, start), end]);
  }
  return { start, end, min, max, complete: !missing.length, missing };
}

export function workflowSpectrum(task, version) {
  if (version.status !== 'completed' || !task.versions.some(item => item.id === version.id)) throw new Error(localize("请选择该任务已保存的处理版本。"));
  const spectrum = version.trace?.at(-1)?.after;
  validateSpectrum(spectrum);
  return { name: task.source_name, kind: 'processed', spectrum: { wavenumber: [...spectrum.wavenumber], intensity: [...spectrum.intensity] }, metadata: task.diagnostics?.source_check, reference: { workflow_id: task.id, version_id: version.id }, steps: version.steps || [] };
}

export function makeGenerationDraft(source, { formula, topK, rerank, unitConfirmed }) {
  validateSpectrum(source?.spectrum);
  if (!unitConfirmed) throw new Error(localize("请先确认横轴为拉曼位移 cm⁻¹。"));
  const normalizedFormula = formula.trim();
  if (!validFormula(normalizedFormula)) throw new Error(localize("请使用元素及原子数形式的分子式，例如 C6H6。"));
  if (![3, 5, 10].includes(topK)) throw new Error(localize("候选数量应为 3、5 或 10。"));
  return {
    schema_version: 'ramancloud.structure-generation.draft.v1',
    purpose: 'integration_draft', inference_performed: false,
    model_profile_id: null,
    input: { source_name: source.name, source_kind: source.kind, reference: source.reference, modality: 'raman', axis_unit: 'cm^-1', spectrum: source.spectrum },
    generation: { formula: normalizedFormula || null, top_k: topK, beam_size: 10, rerank_requested: rerank },
    preparation: { applied: false, grid: null, normalization: null, note: 'Model-specific preparation must be resolved against the deployed checkpoint profile.' },
  };
}

// Fixed layout fixtures: never predictions, scores, or a function of an uploaded spectrum.
export const LAYOUT_CANDIDATES = [
  { id: 'benzene', name: '苯', en: 'Benzene', formula: 'C6H6', smiles: 'c1ccccc1', aromatic: true },
  { id: 'phenol', name: '苯酚', en: 'Phenol', formula: 'C6H6O', smiles: 'Oc1ccccc1', aromatic: true, group: 'OH' },
  { id: 'toluene', name: '甲苯', en: 'Toluene', formula: 'C7H8', smiles: 'Cc1ccccc1', aromatic: true, group: 'CH₃' },
  { id: 'cyclohexane', name: '环己烷', en: 'Cyclohexane', formula: 'C6H12', smiles: 'C1CCCCC1', aromatic: false },
  { id: 'anisole', name: '苯甲醚', en: 'Anisole', formula: 'C7H8O', smiles: 'COc1ccccc1', aromatic: true, group: 'OCH₃' },
];
