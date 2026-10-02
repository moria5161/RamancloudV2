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
    en: 'The published method extracts and retains peaks during denoising. V2 uses a simplified iterative smoothing and residual-retention implementation.',
    zh: '原始方法在降噪中提取并保留峰。V2 使用迭代平滑与残差保留的简化实现。',
  },
  {
    id: 'airpls', group: 'baseline', name: 'airPLS',
    url: 'https://doi.org/10.1039/B922045C',
    en: 'The reference introduces adaptive reweighted penalized least squares. V2 currently uses Whittaker smoothing with asymmetric weights.',
    zh: '文献介绍自适应重加权惩罚最小二乘方法。V2 当前采用带非对称权重的 Whittaker 平滑。',
  },
  {
    id: 'aabs', group: 'baseline', name: 'Auto-Adaptive Background Subtraction (AABS)',
    url: 'https://doi.org/10.1016/j.saa.2016.02.016',
    en: 'The reference describes auto-adaptive Raman background subtraction. V2 currently uses the shared penalized-smoothing baseline implementation.',
    zh: '文献介绍拉曼光谱自适应背景扣除。V2 当前采用共用的惩罚平滑基线实现。',
  },
  {
    id: 'imodpoly', group: 'baseline', name: 'IModPoly',
    url: 'https://doi.org/10.1366/000370207782597003',
    en: 'The reference improves modified polynomial fluorescence subtraction. V2 fits polynomials iteratively with quantile-based point selection.',
    zh: '文献改进多项式荧光背景扣除方法。V2 采用基于分位数筛选拟合点的迭代多项式实现。',
  },
  {
    id: 'airpls_old', group: 'baseline', name: 'airPLS (Legacy) / ModPoly',
    url: 'https://doi.org/10.1366/000370203322554518',
    en: 'V2 retains the legacy menu name, but uses polynomial baseline fitting. The linked ModPoly paper describes polynomial fluorescence subtraction.',
    zh: 'V2 保留旧版菜单名称，但实际采用多项式基线拟合；链接为多项式荧光背景扣除方法 ModPoly 的原始文献。',
  },
  {
    id: 'snip', group: 'baseline', name: 'SNIP',
    url: 'https://pybaselines.readthedocs.io/en/stable/generated/api/pybaselines.Baseline.snip.html',
    en: 'The reference describes iterative peak clipping. V2 currently approximates the baseline with rolling minima followed by smoothing.',
    zh: '原始方法通过迭代削峰估计背景。V2 当前用滑动最小值及后续平滑近似基线。',
  },
];
