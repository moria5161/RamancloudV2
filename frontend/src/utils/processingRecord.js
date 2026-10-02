import { strToU8, zip } from 'fflate';

export const pipelineSnapshot = steps => steps.map(({ type, method, params }) => ({ type, method, params: { ...params } }));
export const pipelineSignature = steps => JSON.stringify(pipelineSnapshot(steps));

export function createProcessingRecord(source, mode, rawData, result, steps, started) {
  return {
    schema_version: 1,
    application: 'RamanCloud',
    application_version: '2.1.0',
    processed_at: new Date().toISOString(),
    elapsed_seconds: Number(((performance.now() - started) / 1000).toFixed(3)),
    source_file: source,
    mode,
    input_shape: rawData.shape || [rawData.wavenumber.length],
    output_shape: result.shape || [result.wavenumber.length],
    input_wavenumber: rawData.wavenumber,
    output_wavenumber: result.wavenumber,
    steps: pipelineSnapshot(steps),
    data_format: 'Tab-separated text without a header; first column is wavenumber. Remaining columns are intensities, with an optional baseline column for single spectra.',
    effective_steps: result.history,
    algorithm_note: 'V1-derived PEER, AABS and legacy airPLS; pybaselines 1.2.1 baseline methods; PyWavelets WTD; NumPy TSVD. Legacy airPLS now honors difference order.',
  };
}

export async function exportArchive(entries, record) {
  const files = {};
  for (const [name, blob] of entries) files[name] = new Uint8Array(await blob.arrayBuffer());
  if (record) files['processing-record.json'] = strToU8(JSON.stringify(record, null, 2));
  const bytes = await new Promise((resolve, reject) => zip(files, (error, data) => error ? reject(error) : resolve(data)));
  saveBlob(new Blob([bytes], { type: 'application/zip' }), 'processed_spectra.zip');
}

export function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export async function exportResult(blob, filename, record, includeRecord) {
  if (!includeRecord) return saveBlob(blob, filename);
  const safeName = filename.replace(/[\\/]/g, '_');
  const data = new Uint8Array(await blob.arrayBuffer());
  const archive = await new Promise((resolve, reject) => zip({
    [safeName]: data,
    'processing-record.json': strToU8(JSON.stringify(record, null, 2)),
  }, (error, bytes) => error ? reject(error) : resolve(bytes)));
  saveBlob(new Blob([archive], { type: 'application/zip' }), `${safeName.replace(/\.[^.]+$/, '')}_with_record.zip`);
}
