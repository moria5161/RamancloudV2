export function moduleSpectrum(data, module) {
  return {
    name: data.source_name, kind: 'uploaded', spectrum: data.original,
    metadata: data.diagnostics.source_check, steps: [],
    reference: { source_id: data.id, module },
  };
}

export function spectrumReferenceKey(source) {
  const ref = source.reference;
  return ref.source_id ? `${ref.module}:${ref.source_id}` : `preprocessing:${ref.workflow_id}:${ref.version_id || ''}`;
}
