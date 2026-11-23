import React from 'react';
import { Scissors, Eraser, Waves, Baseline } from 'lucide-react';

const kinds = {
  cut: { icon: Scissors, zh: '裁剪', en: 'Crop' },
  despike: { icon: Eraser, zh: '去鬼峰', en: 'Despike' },
  denoise: { icon: Waves, zh: '降噪', en: 'Denoise' },
  baseline: { icon: Baseline, zh: '基线校正', en: 'Baseline' },
};

export default function PreprocessingFlow({ steps, txt }) {
  const items = steps.length ? steps.filter(step => step.type !== 'cut') : ['despike', 'denoise', 'baseline'].map(type => ({ type, enabled: true }));
  return <ol className="ai-preprocess-flow" aria-label={txt('预处理顺序', 'Preprocessing order')}>
    {items.map((step, index) => {
      const info = kinds[step.type];
      if (!info) return null;
      const Icon = info.icon;
      return <li key={step.id || `${step.type}-${index}`} className={`${step.type === 'despike' ? 'is-despike' : ''} ${step.enabled === false ? 'is-skipped' : ''}`}>
        <span>{index + 1}</span><Icon size={14} /><span>{txt(info.zh, info.en)}</span>{step.enabled === false && <small>{txt('跳过', 'Skipped')}</small>}
      </li>;
    })}
  </ol>;
}
