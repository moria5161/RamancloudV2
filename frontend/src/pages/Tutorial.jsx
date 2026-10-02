import React, { useState } from 'react';
import {
  BookMarked,
  BookOpen,
  ChevronDown,
  Download,
  FileText,
  Layers3,
  ListOrdered,
  Play,
  SlidersHorizontal,
  Upload,
} from 'lucide-react';
import { usePreferences } from '../i18n';
import AlgorithmReferences from '../components/AlgorithmReferences';

const FlowStep = ({ number, icon: Icon, title, children, last = false }) => (
  <li className="relative grid grid-cols-[40px_minmax(0,1fr)] gap-4 pb-7 last:pb-0">
    {!last && <span aria-hidden="true" className="absolute left-5 top-10 bottom-0 w-px" style={{ background: 'var(--rc-hairline)' }} />}
    <span className="relative z-10 grid h-10 w-10 place-items-center rounded-xl bg-indigo-500/10 text-indigo-400">
      <Icon className="h-4 w-4" />
      <span className="sr-only">{number}</span>
    </span>
    <div className="min-w-0 pt-0.5">
      <div className="mb-1 flex items-baseline gap-2">
        <span className="text-xs font-semibold text-indigo-400">{String(number).padStart(2, '0')}</span>
        <h3 className="text-base font-semibold text-gray-200">{title}</h3>
      </div>
      <div className="text-sm leading-relaxed text-gray-400">{children}</div>
    </div>
  </li>
);

const SectionToggle = ({ id, number, icon: Icon, title, description, expanded, onClick }) => (
  <button
    type="button"
    aria-expanded={expanded}
    aria-controls={`${id}-content`}
    onClick={onClick}
    className={`glass flex min-h-[82px] w-full items-center gap-3 rounded-xl px-4 text-left transition-all ${expanded ? 'border-indigo-500/30 ring-1 ring-blue-500/30' : 'border-white/5 hover:-translate-y-0.5'}`}
  >
    <span className={`grid h-10 w-10 shrink-0 place-items-center rounded-xl ${expanded ? 'bg-indigo-500/10 text-indigo-400' : 'bg-black/20 text-gray-500'}`}>
      <Icon className="h-4 w-4" />
    </span>
    <span className="min-w-0 flex-1">
      <span className="block text-xs font-semibold text-indigo-400">{number}</span>
      <span className="block text-base font-semibold text-gray-200">{title}</span>
      <span className="block text-xs text-gray-500">{description}</span>
    </span>
    <ChevronDown className={`h-4 w-4 shrink-0 text-gray-500 transition-transform duration-300 ${expanded ? 'rotate-180' : ''}`} />
  </button>
);

export default function Tutorial() {
  const { language } = usePreferences();
  const isZh = language === 'zh';
  const [section, setSection] = useState(null);
  const toggleSection = id => setSection(current => current === id ? null : id);

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-4xl space-y-8 px-4 py-10 sm:px-8 animate-fade-in">
        <header className="space-y-3">
          <div className="flex items-center gap-3">
            <BookOpen className="h-6 w-6 text-indigo-400" />
            <h1 className="text-2xl font-bold text-white">{isZh ? '教程' : 'Tutorial'}</h1>
          </div>
          <p className="max-w-2xl text-sm leading-relaxed text-gray-400">
            {isZh
              ? '先了解 RamanCloud 的完整处理流程，再按需查阅算法原理、参数作用与参考文献。'
              : 'Start with the complete RamanCloud workflow, then explore algorithm principles, parameters, and literature as needed.'}
          </p>
        </header>

        <div className="space-y-4" aria-label={isZh ? '教程章节' : 'Tutorial sections'}>
          <section>
            <SectionToggle
              id="getting-started"
              number={isZh ? '第一部分' : 'Part 1'}
              icon={ListOrdered}
              title="Getting Started"
              description={isZh ? '从数据加载到结果导出' : 'From data loading to export'}
              expanded={section === 'getting-started'}
              onClick={() => toggleSection('getting-started')}
            />
            {section === 'getting-started' && (
              <div id="getting-started-content" className="space-y-6 px-1 pb-3 pt-6 animate-fade-in">
                <p className="text-sm text-gray-400">
                  {isZh
                    ? 'RamanCloud 支持单光谱、成像和时间序列数据。你可以使用内置示例熟悉流程，也可以直接上传自己的数据。'
                    : 'RamanCloud supports single spectra, imaging, and time-series data. Explore the workflow with a built-in demo or upload your own data.'}
                </p>

                <div className="glass rounded-xl border border-white/5 p-5 sm:p-6">
                  <ol>
                    <FlowStep number={1} icon={Layers3} title={isZh ? '选择处理工作区' : 'Choose a workspace'}>
                      {isZh
                        ? '单条或批量一维光谱使用“单光谱处理”；成像和时间序列数据使用“高光谱处理”。'
                        : 'Use Spectral Processing for individual or batched 1D spectra. Use Hyperspectral Processing for imaging and time-series data.'}
                    </FlowStep>
                    <FlowStep number={2} icon={Upload} title={isZh ? '加载数据' : 'Load your data'}>
                      {isZh
                        ? '选择一个示例数据集，或上传 .txt、.asc、.csv 文件。加载后先确认波数范围、数据形状和光谱预览是否正确。'
                        : 'Choose a demo dataset or upload a .txt, .asc, or .csv file. Confirm the wavenumber range, data shape, and spectrum preview before processing.'}
                    </FlowStep>
                    <FlowStep number={3} icon={SlidersHorizontal} title={isZh ? '构建处理流程' : 'Build the pipeline'}>
                      {isZh
                        ? '按需要添加裁剪、降噪和基线校正步骤。步骤可以自由排序和重复添加；选择算法后，再根据数据特征调整参数。'
                        : 'Add Cut, Denoise, and Baseline steps as needed. Reorder or repeat steps freely, then tune each algorithm for your data.'}
                    </FlowStep>
                    <FlowStep number={4} icon={Play} title={isZh ? '运行并检查结果' : 'Run and review'}>
                      {isZh
                        ? '运行流程后，对比处理前后的光谱或热图。高光谱工作区还可以查看平均光谱与单像素光谱，避免仅凭成像颜色判断处理效果。'
                        : 'Run the pipeline and compare raw and processed spectra or heatmaps. In the hyperspectral workspace, inspect average and single-pixel spectra rather than judging by image color alone.'}
                    </FlowStep>
                    <FlowStep number={5} icon={Download} title={isZh ? '导出结果' : 'Export the results'} last>
                      {isZh
                        ? '确认结果后下载处理数据；基线校正结果可同时导出基线。批量光谱可将全部结果打包为 ZIP。'
                        : 'Download processed data after review. Baseline correction can export the estimated baseline, and batch spectra can be packaged as a ZIP.'}
                    </FlowStep>
                  </ol>
                </div>

                <div className="grid gap-4 sm:grid-cols-2">
                  <section className="border-t border-white/10 pt-4">
                    <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-gray-200">
                      <FileText className="h-4 w-4 text-indigo-400" />
                      {isZh ? '批量数据提示' : 'Batch data note'}
                    </div>
                    <p className="text-xs leading-relaxed text-gray-400">
                      {isZh
                        ? 'TSVD 需要各条光谱使用完全一致的波数轴，因此仅适用于对齐的批量光谱、成像或时间序列数据。'
                        : 'TSVD requires identical wavenumber axes and is available only for aligned spectrum batches, imaging, or time-series data.'}
                    </p>
                  </section>
                  <section className="border-t border-white/10 pt-4">
                    <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-gray-200">
                      <Download className="h-4 w-4 text-indigo-400" />
                      {isZh ? '数据保存说明' : 'Data retention'}
                    </div>
                    <p className="text-xs leading-relaxed text-gray-400">
                      {isZh
                        ? '上传内容不会保存为永久数据集。高光谱数据在服务器内存中临时缓存，并会在闲置约 30 分钟后清理，请及时下载结果。'
                        : 'Uploads are not retained as permanent datasets. Hyperspectral data is cached temporarily in server memory and removed after about 30 minutes of inactivity, so download results promptly.'}
                    </p>
                  </section>
                </div>
              </div>
            )}
          </section>

          <section>
            <SectionToggle
              id="reference"
              number={isZh ? '第二部分' : 'Part 2'}
              icon={BookMarked}
              title="Reference"
              description={isZh ? '算法原理与参考文献' : 'Algorithms and literature'}
              expanded={section === 'reference'}
              onClick={() => toggleSection('reference')}
            />
            {section === 'reference' && (
              <div id="reference-content" className="px-1 pb-3 pt-6 animate-fade-in">
                <AlgorithmReferences />
              </div>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
