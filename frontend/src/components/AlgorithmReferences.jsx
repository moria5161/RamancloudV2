import React from 'react';
import { ArrowUpRight } from 'lucide-react';
import { usePreferences } from '../i18n';
import { algorithmReferences } from '../data/algorithmReferences';

export default function AlgorithmReferences() {
  const { language } = usePreferences();
  const isZh = language === 'zh';
  return (
    <section id="references" aria-labelledby="references-heading" className="space-y-5 border-t border-white/10 pt-8">
      <h2 id="references-heading" className="text-lg font-semibold text-gray-200">{isZh ? '算法与参考文献' : 'References'}</h2>
      <p className="text-sm text-gray-400">
        {isZh ? '以下方法用于单光谱、成像和时间序列的预处理。算法沿用 V1 的实现或同名科学计算库方法；各处理步骤提供可调参数与参数说明。' : 'These methods use V1-derived implementations or the same scientific-library methods as V1. Each processing step includes adjustable parameters and a parameter guide.'}
      </p>
      {['denoise', 'baseline'].map(group => (
        <div key={group} className="space-y-3">
          <h3 className="text-base font-semibold text-gray-200">{group === 'denoise' ? (isZh ? '降噪' : 'Denoising') : (isZh ? '基线校正' : 'Baseline Correction')}</h3>
          <dl className="divide-y divide-white/10">
            {algorithmReferences.filter(item => item.group === group).map(item => (
              <div key={item.id} className="py-3 space-y-1.5">
                <dt><a href={item.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-sm font-medium text-indigo-400 hover:text-indigo-300">
                  {item.name}<ArrowUpRight className="w-3.5 h-3.5 shrink-0" />
                </a></dt>
                <dd className="text-sm text-gray-400 leading-relaxed">{isZh ? item.zh : item.en}</dd>
              </div>
            ))}
          </dl>
        </div>
      ))}
    </section>
  );
}
