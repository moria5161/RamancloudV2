import { MAX_SPECTRA, PROCESSING_CHUNK_SIZE } from './spectralBatch.js';
import { batchDownloadNames } from './exportNames.js';

export async function prepareBatchDownload(spectra, send, onProgress = () => {}) {
  if (!spectra.length || spectra.length > MAX_SPECTRA) throw new Error(`Batch download accepts 1 to ${MAX_SPECTRA} spectra`);
  const names = batchDownloadNames(spectra);
  const entries = [];
  onProgress(0);
  for (let offset = 0; offset < spectra.length; offset += PROCESSING_CHUNK_SIZE) {
    const chunk = spectra.slice(offset, offset + PROCESSING_CHUNK_SIZE);
    const response = await send({ spectra: chunk.map(({ wavenumber, intensity, baseline }) => ({ wavenumber, intensity, baseline })) });
    if (response.code !== 0) throw new Error(response.msg || 'Batch download failed');
    const results = response.data?.spectra;
    if (!Array.isArray(results) || results.length !== chunk.length) throw new Error('Batch download returned an incomplete result');
    results.forEach((result, index) => {
      if (typeof result.content !== 'string' || (chunk[index].baseline != null && typeof result.baseline !== 'string')) {
        throw new Error('Batch download returned an incomplete result');
      }
      const name = names[offset + index];
      entries.push([`spectra/${name}`, new Blob([result.content], { type: 'text/plain;charset=utf-8' })]);
      if (chunk[index].baseline != null) entries.push([`baselines/${name}`, new Blob([result.baseline], { type: 'text/plain;charset=utf-8' })]);
    });
    onProgress(Math.round((offset + chunk.length) / spectra.length * 100));
  }
  return entries;
}
