import React from 'react';
import { ArrowUpRight } from 'lucide-react';
import { usePreferences } from '../i18n';
import { algorithmReferences } from '../data/algorithmReferences';

export default function AlgorithmReferences() {
  const { language } = usePreferences();
  const isZh = language === 'zh';
  return (
    <div id="references" className="space-y-6">
      {['denoise', 'baseline'].map(group => (
        <div key={group} className="border-t pt-6 first:border-0 first:pt-0" style={{ borderColor: 'var(--rc-hairline)' }}>
          <h3 className="mb-2 text-base font-semibold text-gray-200">{group === 'denoise' ? (isZh ? '降噪算法' : 'Denoising') : (isZh ? '基线校正算法' : 'Baseline Correction')}</h3>
          <dl className="divide-y divide-white/10">
            {algorithmReferences.filter(item => item.group === group).map(item => (
              <div key={item.id} className="py-3 space-y-1.5">
                <dt>{item.url ? (
                  <a href={item.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-sm font-medium text-indigo-400 hover:text-indigo-300">
                    {item.name}<ArrowUpRight className="w-3.5 h-3.5 shrink-0" />
                  </a>
                ) : <span className="text-sm font-medium text-indigo-400">{item.name}</span>}</dt>
                <dd className="text-sm text-gray-400 leading-relaxed">{isZh ? item.zh : item.en}</dd>
              </div>
            ))}
          </dl>
        </div>
      ))}
      <div className="border-t pt-6 space-y-3" style={{ borderColor: 'var(--rc-hairline)' }}>
        <h3 className="text-base font-semibold text-gray-200">{isZh ? '结构预测光谱' : 'Structure-to-Spectrum Prediction'}</h3>
        <p className="text-sm text-gray-400 leading-relaxed">{isZh
          ? '预训练的等变图神经网络从分子的原子种类和三维坐标预测 Hessian 矩阵与极化率导数，再通过振动分析获得拉曼活性并生成光谱。固定条件：频率缩放系数 0.965，洛伦兹展宽半高全宽 12 cm⁻¹，激发波长 532 nm，温度 298 K。'
          : 'Pretrained equivariant graph neural networks predict the molecular Hessian and polarizability derivatives from atom types and 3D coordinates. Vibrational analysis yields Raman activities, which are broadened into a spectrum. Fixed settings: frequency scale 0.965, Lorentzian FWHM 12 cm⁻¹, excitation wavelength 532 nm, and temperature 298 K.'}</p>
        <p className="text-sm text-gray-400 leading-relaxed">{isZh
          ? 'SMILES 构象生成与 MMFF 优化使用 RDKit；XYZ 键连接识别使用 Open Babel；交互式分子绘制使用 Ketcher。'
          : 'RDKit generates conformers and performs MMFF optimization; Open Babel identifies bonds in XYZ files; Ketcher provides interactive molecular drawing.'}</p>
        <div className="flex flex-wrap gap-4 text-sm text-indigo-400">
          {[['RDKit', 'https://www.rdkit.org/docs/GettingStartedInPython.html'], ['Open Babel', 'https://openbabel.org/docs/'], ['Ketcher', 'https://github.com/epam/ketcher']].map(([label, url]) =>
            <a key={label} href={url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1">{label}<ArrowUpRight className="w-3.5 h-3.5" /></a>)}
        </div>
      </div>
    </div>
  );
}
