export const MAX_SPECTRA = 512;
export const PROCESSING_CHUNK_SIZE = 64;

export async function processSpectralBatch(spectra, steps, send, onProgress = () => {}) {
  if (!spectra.length || spectra.length > MAX_SPECTRA) throw new Error(`Batch processing accepts 1 to ${MAX_SPECTRA} spectra`);
  // TSVD is a joint decomposition: splitting its inputs changes the algorithm.
  const joint = steps.some(step => step.type === 'denoise' && step.method === 'tsvd');
  const chunkSize = joint ? spectra.length : PROCESSING_CHUNK_SIZE;
  const results = [];
  onProgress(0);
  for (let offset = 0; offset < spectra.length; offset += chunkSize) {
    const chunk = spectra.slice(offset, offset + chunkSize);
    const response = await send({ spectra: chunk, steps });
    if (response.code !== 0) throw new Error(response.msg || 'Batch processing failed');
    if (!Array.isArray(response.data?.spectra) || response.data.spectra.length !== chunk.length) {
      throw new Error('Batch processing returned an incomplete result');
    }
    results.push(...response.data.spectra);
    onProgress(Math.round(results.length / spectra.length * 100));
  }
  return results;
}
