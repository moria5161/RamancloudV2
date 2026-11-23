export const WORKFLOW_STAGES = [
  ['上传数据', 'Upload data'], ['光谱处理', 'Process spectrum'], ['查看结果', 'View result'],
];

export function validDespikeOrder(steps) {
  let denoising = false, count = 0;
  for (const step of steps) {
    if (step.type === 'despike' && ++count > 1) return false;
    if (step.enabled === false || step.method === 'skip') continue;
    if (step.type === 'despike' && denoising) return false;
    if (step.type === 'denoise') denoising = true;
  }
  return true;
}

export function insertDespike(steps, step) {
  if (steps.some(item => item.type === 'despike')) return steps;
  const result = [...steps], first = result.findIndex(item => item.type !== 'cut');
  result.splice(first < 0 ? result.length : first, 0, step);
  return result;
}

export function canMoveStep(steps, index, delta) {
  const target = index + delta;
  if (target < 0 || target >= steps.length) return false;
  const result = [...steps];
  [result[index], result[target]] = [result[target], result[index]];
  return validDespikeOrder(result);
}

export function selectedBand(steps, original) {
  const cut = steps.find(step => step.type === 'cut' && step.enabled);
  return cut ? { start: cut.params.start, end: cut.params.end } : {
    start: original?.wavenumber_min ?? '', end: original?.wavenumber_max ?? '',
  };
}

export function spectrumResidual(before, after) {
  if (!before || !after) return null;
  const samples = new Map(before.wavenumber.map((wave, index) => [wave, before.intensity[index]]));
  if (!after.wavenumber.every(wave => samples.has(wave))) return null;
  return { wavenumber: after.wavenumber, intensity: after.wavenumber.map((wave, index) => samples.get(wave) - after.intensity[index]) };
}

export function initialStage(task, version) {
  if (!task) return 0;
  if (!version) return 0;
  if (version.status === 'completed') return 2;
  return version.metadata?.phase === 'preprocess' ? 1 : 2;
}

export function uploadNextStage(task, version, dirty) {
  if (!version || dirty || version.status === 'failed') return null;
  return initialStage(task, version);
}

export function refinementRequest(goal, feedback, version) {
  const explicitGoal = goal.trim(), revision = feedback.trim();
  const previousGoal = version?.goal?.trim() || '', previousFeedback = version?.feedback?.trim() || '';
  const target = explicitGoal || (revision ? previousGoal : '');
  return {
    goal: target, feedback: revision, canSubmit: target.length >= 2,
    pending: Boolean(explicitGoal && explicitGoal !== previousGoal || revision && revision !== previousFeedback),
  };
}
