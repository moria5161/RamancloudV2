export function sharedHeatmapBounds(matrices) {
  let min = Infinity;
  let max = -Infinity;
  for (const matrix of matrices) {
    for (const row of matrix || []) {
      for (const value of row || []) {
        if (typeof value === 'number' && Number.isFinite(value)) {
          min = Math.min(min, value);
          max = Math.max(max, value);
        }
      }
    }
  }
  return min === Infinity ? {} : { zmin: min, zmax: max === min ? min + 1 : max, zauto: false };
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
