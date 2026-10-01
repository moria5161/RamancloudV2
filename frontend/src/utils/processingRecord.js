import { strToU8, zip } from 'fflate';

export const pipelineSnapshot = steps => steps.map(({ type, method, params }) => ({ type, method, params: { ...params } }));
export const pipelineSignature = steps => JSON.stringify(pipelineSnapshot(steps));

export function createProcessingRecord(source, mode, rawData, result, steps, started) {
  return {
    schema_version: 1,
    application: 'RamanCloud',
    application_version: '2.0.0',
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
    algorithm_note: 'Algorithm identifiers refer to RamanCloud implementations; some are local approximations.',
  };
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
