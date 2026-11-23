export const QUALITY_LABELS = {
  uneven_spacing: ['波数间距不均匀', 'Uneven spectral spacing'],
  narrow_spike: ['疑似异常尖峰', 'Narrow spike candidates'],
  flat_top: ['疑似平顶截幅', 'Flat-top / clipping candidates'],
  constant_signal: ['近常量信号', 'Nearly constant signal'],
};

export function qualityMarkers(report) {
  if (!report || report.spectra_total !== 1) return [];
  return report.issues.filter(issue => ['narrow_spike', 'flat_top'].includes(issue.code)).flatMap(issue => issue.locations.filter(point => Number.isFinite(point.intensity))
    .map(point => ({ ...point, quality_code: issue.code })));
}
