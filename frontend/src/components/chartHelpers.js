export function sharedHeatmapBounds(matrices) {
  const values = [];
  for (const matrix of matrices) {
    for (const row of matrix || []) {
      for (const value of row || []) {
        if (typeof value === 'number' && Number.isFinite(value)) {
          values.push(value);
        }
      }
    }
  }
  if (!values.length) return {};
  // Sort a private numeric copy; display bounds never alter source intensities.
  const sorted = new Float64Array(values).sort();
  const percentile = fraction => {
    const index = (sorted.length - 1) * fraction;
    const lower = Math.floor(index);
    const upper = Math.ceil(index);
    if (sorted[lower] === sorted[upper]) return sorted[lower];
    const weight = index - lower;
    return sorted[lower] * (1 - weight) + sorted[upper] * weight;
  };
  let zmin = percentile(0.01);
  let zmax = percentile(0.99);
  if (zmin === zmax) {
    const padding = Math.max(1, Math.abs(zmin) * Number.EPSILON);
    if (Number.isFinite(zmax + padding)) zmax += padding;
    else zmin -= padding;
  }
  return { zmin, zmax, zauto: false };
}

export function selectionShapes({ pixel, index, compare }) {
  if (!pixel && index == null) return [];
  return (compare ? ['', '2'] : ['']).map(suffix => pixel ? {
    type: 'rect', xref: `x${suffix}`, yref: `y${suffix}`,
    x0: pixel.x - 0.5, x1: pixel.x + 0.5,
    y0: pixel.y - 0.5, y1: pixel.y + 0.5,
    line: { color: '#ffffff', width: 3 }, fillcolor: 'rgba(0,0,0,0)',
  } : {
    type: 'line', xref: `x${suffix} domain`, yref: `y${suffix}`,
    x0: 0, x1: 1, y0: index, y1: index,
    line: { color: '#ffffff', width: 2, dash: 'dot' },
  });
}
