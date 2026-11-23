import { spectrumReferenceKey } from '../components/moduleSpectrum.js';

export const activeTask = job => ['queued', 'running'].includes(job?.status);
export const readyModels = jobs => jobs.filter(job => job.kind === 'train' && job.status === 'completed');
export function commonBand(sources) {
  if (!sources.length) return null;
  const spans = sources.map(s => s.spectrum.wavenumber);
  const start = Math.max(...spans.map(x => Math.min(x[0], x.at(-1))));
  const end = Math.min(...spans.map(x => Math.max(x[0], x.at(-1))));
  return start < end ? { start, end } : null;
}
export function appendStandard(sources, source) {
  if (sources.some(s => spectrumReferenceKey(s) === spectrumReferenceKey(source))) return sources;
  return [...sources, source];
}
