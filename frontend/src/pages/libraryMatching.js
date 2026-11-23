import { localize } from '../locale.js';
export function hasBaseline(steps = []) {
  return steps.some(step => step.type === 'baseline' && step.enabled !== false);
}

export function matchingSource(task, version) {
  if (version.status !== 'completed' || !task.versions.some(item => item.id === version.id)) throw new Error(localize("请选择当前任务已保存的处理版本。"));
  const spectrum = version.trace?.at(-1)?.after;
  if (!spectrum || spectrum.wavenumber?.length !== spectrum.intensity?.length || !spectrum.wavenumber?.length) throw new Error(localize("处理结果没有有效的光谱数据。"));
  return { name: task.source_name, kind: 'processed', spectrum: { wavenumber: [...spectrum.wavenumber], intensity: [...spectrum.intensity] },
    metadata: task.diagnostics?.source_check, steps: version.steps || [], reference: { workflow_id: task.id, version_id: version.id } };
}

export function scoreText(score) {
  if (!Number.isFinite(score) || score < 0 || score > 1) return '—';
  return score > 0 && score < .0001 ? `${(score * 100).toExponential(2)}%` : `${(score * 100).toFixed(2)}%`;
}

export function referenceCurve(candidate) {
  const reference = candidate?.reference;
  if (!reference || !Array.isArray(reference.wavenumber) || !Array.isArray(reference.intensity) || reference.wavenumber.length !== reference.intensity.length) return null;
  return { wavenumber: reference.wavenumber, intensity: reference.intensity };
}
