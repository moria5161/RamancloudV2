export const algorithmReferences = [
  {
    id: 'sg', group: 'denoise', name: 'Savitzky-Golay (SG)',
    url: 'https://doi.org/10.1021/ac60214a047',
    en: 'Fits local polynomials in a sliding window to smooth noise while preserving spectral features.',
    zh: '在滑动窗口内进行局部多项式拟合，平滑噪声并保留光谱特征。',
  },
  {
    id: 'wtd', group: 'denoise', name: 'Wavelet Threshold Denoising (WTD)',
    url: 'https://pywavelets.readthedocs.io/en/latest/ref/thresholding-functions.html',
    en: 'Decomposes each spectrum into wavelet coefficients, soft-thresholds detail coefficients, and reconstructs the spectrum.',
    zh: '将每条光谱分解为小波系数，对细节系数进行软阈值处理后重构光谱。',
  },
  {
    id: 'peer', group: 'denoise', name: 'Peak Extraction and Retention (PEER)',
    url: 'https://pubs.acs.org/doi/10.1021/acs.analchem.0c05391',
    en: 'Extracts and retains peaks during denoising.',
    zh: '在降噪中提取并保留峰。',
  },
  {
    id: 'airpls', group: 'baseline', name: 'airPLS',
    url: 'https://doi.org/10.1039/B922045C',
    en: 'Adaptive reweighted penalized least squares, implemented with pybaselines.',
    zh: '自适应重加权惩罚最小二乘方法，使用 pybaselines 实现。',
  },
  {
    id: 'aabs', group: 'baseline', name: 'Auto-Adaptive Background Subtraction (AABS)',
    url: 'https://doi.org/10.1016/j.saa.2016.02.016',
    en: 'Auto-adaptive Raman background subtraction; Ln and Lb control noise and baseline windows.',
    zh: '拉曼光谱自适应背景扣除；Ln 和 Lb 分别控制噪声与基线窗口。',
  },
  {
    id: 'imodpoly', group: 'baseline', name: 'IModPoly',
    url: 'https://doi.org/10.1366/000370207782597003',
    en: 'Iterative polynomial fitting with a noise-aware threshold, implemented with pybaselines.',
    zh: '带噪声阈值的迭代多项式拟合，使用 pybaselines 实现。',
  },
  {
    id: 'snip', group: 'baseline', name: 'SNIP',
    url: 'https://pybaselines.readthedocs.io/en/stable/generated/api/pybaselines.Baseline.snip.html',
    en: 'Estimates the background through decreasing-window iterative peak clipping, using pybaselines.',
    zh: '使用逐步缩小窗口的迭代削峰估计背景，通过 pybaselines 实现。',
  },
  {"id":"tsvd","group":"denoise","name":"Truncated SVD (TSVD)","url":"https://numpy.org/doc/stable/reference/generated/numpy.linalg.svd.html","en":"Filters singular values using a log-spectrum curvature threshold. For aligned batches, imaging, or time series, not individual spectra.","zh":"按照奇异值对数曲率阈值过滤分量，用于波数一致的批量光谱、成像或时间序列，不适用于单条光谱。"},
];
