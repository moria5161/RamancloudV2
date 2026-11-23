export const spectrumText = spectrum => 'RamanShift(cm^-1)\tIntensity\n' + spectrum.wavenumber.map((x, i) => `${x}\t${spectrum.intensity[i]}`).join('\n') + '\n';

export function safeSpectrumStem(name) {
  const base = String(name || 'spectrum').split(/[\\/]/).at(-1).replace(/\.[^.]+$/, '');
  return Array.from(base.replace(/[<>:"|?*\x00-\x1f]/g, '_').replace(/^[. ]+|[. ]+$/g, '') || 'spectrum').slice(0, 100).join('');
}

// Match one list row per spectrum; its selected saved version takes precedence.
export function spectrumExportTargets(records, selectedId) {
  const groups = new Map();
  for (const record of records) {
    if (record.analysis_type !== 'spectrum' || record.kind === 'batch_item' || record.kind === 'batch') continue;
    const key = record.result?.ai_workflow_id || record.workflow_id || record.id;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(record);
  }
  return [...groups.values()].map(group => {
    const completed = group.filter(record => !record.kind || record.result_available).sort((a,b) => b.created_at.localeCompare(a.created_at));
    const record = completed.find(record => record.id === selectedId) || completed[0] || group[0];
    return !record.kind ? {run_id:record.id} : {workflow_id:record.workflow_id, ...(record.result_available ? {version_id:record.version_id} : {})};
  });
}
