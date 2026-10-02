const number = (key, value, min, max, label, zh, help, helpZh, step = 1) => ({ key, value, min, max, label, zh, help, helpZh, step });
const lam = value => number('lam', value, 1e-12, 1e12, 'Lambda', '平滑强度', 'Larger values produce smoother baselines.', '数值越大，基线通常越平滑。', 'any');
const diff = number('diff_order', 3, 1, 3, 'Difference order', '差分阶数', 'Order of the smoothness penalty; this is not a polynomial degree.', '平滑惩罚的差分阶数，不是多项式阶数。');
const poly = number('poly_order', 3, 0, 10, 'Polynomial order', '多项式阶数', 'Higher orders fit more complex backgrounds, with a greater risk of fitting peaks.', '高阶适用于复杂背景，但更容易拟合到光谱峰。');

export const algorithms = [
  { id: 'sg', type: 'denoise', name: 'Savitzky-Golay', fields: [
    number('window_size', 7, 3, 10001, 'Window size', '窗口大小', 'Must be odd, no longer than the spectrum, and greater than the polynomial order.', '必须为奇数，不超过光谱点数，且大于多项式阶数。', 2),
    number('order', 3, 0, 20, 'Polynomial order', '多项式阶数', 'Degree of the local polynomial fit.', '窗口内局部拟合的多项式阶数。'),
  ] },
  { id: 'wtd', type: 'denoise', name: 'Wavelet (WTD)', fields: [
    { key: 'wavelet', value: 'db3', label: 'Wavelet', zh: '小波类型', options: Array.from({ length: 9 }, (_, i) => `db${i + 1}`), help: 'Daubechies wavelet family. The choice affects peak shape and the supported decomposition depth.', helpZh: 'Daubechies 小波族；影响峰形和允许的分解层数。' },
    number('level', 3, 1, 20, 'Decomposition level', '分解层数', 'Maximum supported level depends on spectral length and wavelet. Excessive values are rejected.', '最大层数取决于光谱长度和小波类型，超出时会提示错误。'),
  ] },
  { id: 'peer', type: 'denoise', name: 'PEER', fields: [
    number('loops', 3, 1, 20, 'Iterations', '迭代次数', 'Number of peak-retaining smoothing passes.', '保留峰形的平滑迭代次数。'),
    number('half_k_threshold', 2, 0, 7, 'Peak seeking', '寻峰参数', 'Controls derivative-based peak rejection; compare peak retention when adjusting it.', '控制基于导数的峰筛选；调节时应比较峰的保留情况。'),
  ] },
  { id: 'tsvd', type: 'denoise', name: 'TSVD', batchOnly: true, fields: [number('threshold', 0.001, 0, 100, 'Curvature threshold', '曲率阈值', 'V1 criterion: threshold the second derivative of log1p singular values. Requires multiple aligned spectra.', 'V1 判据：对 log1p 奇异值的二阶差分设阈值；需要多条波数对齐的光谱。', 'any')] },
  { id: 'airpls', type: 'baseline', name: 'airPLS', fields: [lam(1e7), diff] },
  { id: 'aabs', type: 'baseline', name: 'Auto-Adaptive (AABS)', fields: [
    number('Ln', 6, 2, 100, 'Ln', 'Ln', 'Local noise/derivative smoothing window in the V1 auto-adaptive algorithm.', 'V1 自适应算法中的局部噪声和导数平滑窗口。'),
    number('Lb', 140, 5, 1000, 'Lb', 'Lb', 'Background smoothing window. Requires at least max(100, Ln, Lb) spectral points.', '背景平滑窗口；光谱至少需 max(100, Ln, Lb) 个点。'),
  ] },
  { id: 'imodpoly', type: 'baseline', name: 'IModPoly', fields: [poly] },
  { id: 'snip', type: 'baseline', name: 'SNIP', fields: [
    number('max_half_window', 20, 1, 1000, 'Maximum half window', '最大半窗口', 'Approximately half the widest peak width; cannot exceed half the spectral length.', '参考最宽峰宽的一半设置，不得超过光谱长度的一半。'),
    number('smooth_half_window', 7, 0, 1000, 'Smoothing half window', '平滑半窗口', 'Pre-smoothing during peak clipping. Zero disables smoothing.', '削峰过程中的预平滑窗口；0 表示不平滑。'),
  ] },
];

export const algorithmDefaults = id => Object.fromEntries((algorithms.find(item => item.id === id)?.fields || []).map(field => [field.key, field.value]));
