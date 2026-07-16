import React, { createContext, useContext, useEffect, useMemo, useState } from 'react';

const translations = {
  en: {
    homepage: 'Homepage',
    spectralProcessing: 'Spectral Processing',
    hyperspectralProcessing: 'Hyperspectral Processing',
    extraTools: 'Extra Tools',
    tutorial: 'Tutorial',
    contributors: 'Contributors',
    nextGen: 'NextGen Spectroscopy',
    nextGenPlatform: 'NextGen Spectroscopy Platform',
    heroSubtitle: 'Advanced Raman spectral preprocessing platform: Cut, Denoise, and Baseline Correction with state-of-the-art algorithms and real-time visualization.',
    getStarted: 'Get Started',
    smartPipeline: 'Smart Pipeline',
    smartPipelineDesc: 'Freely reorder Cut, Denoise & Baseline steps. Full control over processing workflow.',
    realTimeViz: 'Real-time Viz',
    realTimeVizDesc: 'Interactive Plotly charts with zoom, pan, and hover. See every change instantly.',
    algorithms: '10+ Algorithms',
    algorithmsDesc: 'SG, WTD, PEER for denoising; airPLS, AABS, IModPoly and more for baseline correction.',
    processingModules: 'Processing Modules',
    singleSpectrum: 'Single spectrum analysis',
    spectralDesc: 'Compact and intuitive online Raman spectral processing with real-time data visualization. Supports Cut, Denoising, and Baseline Correction.',
    imagingTimeSeries: 'Imaging & time series',
    hyperspectralDesc: 'Extended processing for spectral imaging and time series data. Batch denoising and baseline correction for large-scale hyperspectral datasets.',
    developedBy: 'Developed by',
    settings: 'Settings',
    language: 'Language',
    english: 'English',
    chinese: '中文',
    appearance: 'Appearance',
    light: 'Light',
    dark: 'Dark',
  },
  zh: {
    homepage: '主页',
    spectralProcessing: '单光谱处理',
    hyperspectralProcessing: '高光谱处理',
    extraTools: '附加工具',
    tutorial: '教程',
    contributors: '贡献人员',
    nextGen: '新一代光谱平台',
    nextGenPlatform: '新一代光谱预处理平台',
    heroSubtitle: '面向拉曼光谱预处理的平台：支持裁剪、去噪、基线校正，并提供实时可视化。',
    getStarted: '开始使用',
    smartPipeline: '自由流程',
    smartPipelineDesc: '自由排序裁剪、去噪和基线校正步骤，完整控制处理流程。',
    realTimeViz: '实时可视化',
    realTimeVizDesc: '支持缩放、平移和悬停查看的交互式图表，处理变化即时可见。',
    algorithms: '十余种算法',
    algorithmsDesc: '支持 SG、WTD、PEER 去噪，以及 airPLS、AABS、IModPoly 等基线校正。',
    processingModules: '处理模块',
    singleSpectrum: '单谱分析',
    spectralDesc: '紧凑直观的在线拉曼光谱处理工具，支持裁剪、去噪和基线校正。',
    imagingTimeSeries: '成像与时间序列',
    hyperspectralDesc: '面向光谱成像和时间序列数据的批量处理，支持大规模高光谱数据去噪和基线校正。',
    developedBy: '开发团队',
    settings: '设置',
    language: '语言',
    english: 'English',
    chinese: '中文',
    appearance: '外观',
    light: '浅色',
    dark: '深色',
  },
};

const PreferencesContext = createContext(null);

export function PreferencesProvider({ children }) {
  const [language, setLanguage] = useState(() => localStorage.getItem('ramancloud_language') || 'en');
  const [theme, setTheme] = useState(() => localStorage.getItem('ramancloud_theme') || 'light');

  useEffect(() => {
    localStorage.setItem('ramancloud_language', language);
    document.documentElement.lang = language === 'zh' ? 'zh-CN' : 'en';
  }, [language]);

  useEffect(() => {
    localStorage.setItem('ramancloud_theme', theme);
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  const value = useMemo(() => ({
    language,
    setLanguage,
    theme,
    setTheme,
    t: (key) => translations[language]?.[key] || translations.en[key] || key,
  }), [language, theme]);

  return <PreferencesContext.Provider value={value}>{children}</PreferencesContext.Provider>;
}

export function usePreferences() {
  return useContext(PreferencesContext);
}
