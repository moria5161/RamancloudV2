import React from 'react';
import {
  BookMarked,
  BookOpen,
  Atom,
  Download,
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
    <span className="relative z-10 grid h-10 w-10 place-items-center text-indigo-400">
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

const SectionHeader = ({ id, number, icon: Icon, title, description }) => (
  <header className="space-y-3">
    <span className="block text-xs font-semibold text-indigo-400">{number}</span>
    <div className="flex items-center gap-3">
      <Icon className="h-5 w-5 shrink-0 text-indigo-400" />
      <h2 id={`${id}-heading`} className="text-xl font-semibold text-gray-200">{title}</h2>
    </div>
    <p className="text-sm leading-relaxed text-gray-400">{description}</p>
  </header>
);

export default function Tutorial() {
  const { language } = usePreferences();
  const isZh = language === 'zh';

  return (
    <div className="h-full overflow-y-auto">
      <article className="mx-auto max-w-4xl space-y-8 px-4 py-10 sm:px-8 animate-fade-in">
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
          <p className="text-sm leading-relaxed text-gray-400">
            {isZh ? '旧版本网页可在此访问：' : 'The previous website is available here: '}
            <a
              href="https://ramancloud.xmu.edu.cn/old-version/"
              target="_blank"
              rel="noopener noreferrer"
              className="text-indigo-400 hover:underline"
            >
              {isZh ? '旧版 RamanCloud' : 'RamanCloud (previous website)'}
            </a>
            {isZh ? '。' : '.'}
          </p>
        </header>

        <div className="space-y-8" aria-label={isZh ? '教程章节' : 'Tutorial sections'}>
          <section aria-labelledby="getting-started-heading" className="space-y-6">
            <SectionHeader
              id="getting-started"
              number={isZh ? '第一部分' : 'Part 1'}
              icon={ListOrdered}
              title={isZh ? '快速开始' : 'Getting Started'}
              description={isZh
                ? 'RamanCloud 支持光谱预处理与分子光谱预测。单光谱、成像和时间序列的处理流程如下；结构预测光谱的流程见后文。'
                : 'RamanCloud supports spectral preprocessing and molecular spectrum prediction. The workflow for spectra, imaging, and time series is below, followed by structure-to-spectrum prediction.'}
            />
            <div id="getting-started-content" className="space-y-6">
              <ol>
                <FlowStep number={1} icon={Layers3} title={isZh ? '选择处理工作区' : 'Choose a workspace'}>
                  {isZh
                    ? '单条或批量一维光谱使用“单光谱处理”；成像和时间序列数据使用“高光谱处理”。'
                    : 'Use Spectral Processing for individual or batched 1D spectra. Use Hyperspectral Processing for imaging and time-series data.'}
                </FlowStep>
                <FlowStep number={2} icon={Upload} title={isZh ? '加载数据' : 'Load your data'}>
                  {isZh
                    ? '选择示例，或上传单谱 .txt、.asc、.csv 文件。高光谱上传使用 .txt，并确认仪器和成像/时间序列类型。加载后检查波数范围、形状和预览。'
                    : 'Choose an example, or upload .txt, .asc, or .csv single-spectrum files. Hyperspectral uploads use .txt: confirm the instrument and imaging/time-series type, then check the range, shape, and preview.'}
                </FlowStep>
                <FlowStep number={3} icon={SlidersHorizontal} title={isZh ? '构建处理流程' : 'Build the pipeline'}>
                  {isZh
                    ? '按需要添加裁剪、降噪和基线校正步骤。步骤可以自由排序和重复添加；选择算法后，再根据数据特征调整参数。'
                    : 'Add Cut, Denoise, and Baseline steps as needed. Reorder or repeat steps freely, then tune each algorithm for your data.'}
                  <p className="mt-2 text-xs leading-relaxed">
                    {isZh
                      ? 'TSVD 需要各条光谱使用完全一致的波数轴，因此仅适用于对齐的批量光谱、成像或时间序列数据。'
                      : 'TSVD requires identical wavenumber axes and is available only for aligned spectrum batches, imaging, or time-series data.'}
                  </p>
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
                  <p className="mt-2 text-xs leading-relaxed">
                    {isZh
                      ? '处理结果不归档，高光谱处理缓存会在闲置约 30 分钟后清理，请及时下载结果。'
                      : 'Processing results are not archived; hyperspectral processing caches expire after about 30 minutes of inactivity. Download results promptly.'}
                  </p>
                </FlowStep>
              </ol>

              <section className="border-t pt-6 space-y-4" style={{ borderColor: 'var(--rc-hairline)' }}>
                <h3 className="text-base font-semibold text-gray-200 flex items-center gap-2"><Atom className="h-4 w-4 text-indigo-400" />{isZh ? '谱构解析：结构预测光谱' : 'Spectrum-Structure Elucidation: structure2spectrum'}</h3>
                <ol>
                  <FlowStep number={1} icon={Atom} title={isZh ? '输入分子结构' : 'Provide a molecular structure'}>
                    {isZh
                      ? '从主页或侧栏进入“谱构解析”，选择 structure2spectrum。可使用苯或咖啡因示例、输入 SMILES、上传 XYZ 文件，或在分子编辑器中绘制结构。输入后自动加载三维构象，无需先预测光谱。SMILES 和绘制的结构会自动添加氢原子并进行 MMFF 优化。'
                      : 'Open Spectrum-Structure Elucidation from the homepage or sidebar and select structure2spectrum. Choose benzene or caffeine, enter SMILES, upload XYZ, or draw a molecule. The 3D conformer loads before spectrum prediction. SMILES and drawn structures are hydrogenated and MMFF-optimized.'}
                  </FlowStep>
                  <FlowStep number={2} icon={Play} title={isZh ? '运行预测' : 'Run the prediction'}>
                    {isZh
                      ? '点击“预测拉曼光谱”。模型使用分子的三维构象计算预测谱，输出 500–4000 cm⁻¹ 的 3501 个数据点，最大强度归一化为 1。'
                      : 'Select Predict Raman spectrum. The model uses the molecular 3D conformer to generate 3,501 points from 500 to 4,000 cm⁻¹, normalized to a maximum intensity of 1.'}
                  </FlowStep>
                  <FlowStep number={3} icon={Download} title={isZh ? '查看并下载' : 'Inspect and download'} last>
                    {isZh
                      ? '切换“三维构象”和“预测拉曼光谱”查看结果。光谱支持缩放和悬停；可下载两列制表符分隔的 TXT 光谱，以及此次预测所用的 XYZ 构象。栏目切换会保留当前工作区。'
                      : 'Switch between 3D conformer and Predicted Raman spectrum. Zoom or inspect spectral values, then download the two-column, tab-separated TXT spectrum and its XYZ conformer. Workspace state is retained when navigating between modules.'}
                  </FlowStep>
                </ol>
                <p className="text-xs leading-relaxed text-gray-500">{isZh
                  ? 'XYZ 文件须为单个分子，第一行为原子数，第二行为注释，之后每行为元素与 x/y/z 坐标（Å），须包含氢原子。文件上限 256 KiB；模型接受 4–96 个原子（含氢），元素原子序数为 1–35，并要求能形成四原子键路径。预测结果依赖输入构象，不能视为实测光谱。'
                  : 'XYZ must contain one molecule: atom count, a comment line, then element and x/y/z coordinates in angstroms, including hydrogens. Files are limited to 256 KiB. The model accepts 4–96 atoms including H, atomic numbers 1–35, and requires connected four-atom bond paths. Predictions depend on the conformer and are not measured spectra.'}</p>
                <p className="text-sm text-gray-400">{isZh ? 'spectrum2structure：即将推出，目前尚不提供从光谱反推分子结构的功能。' : 'spectrum2structure: Coming soon. Molecular identification from spectra is not yet available.'}</p>
              </section>

            </div>
          </section>

          <section aria-labelledby="reference-heading" className="border-t pt-8 space-y-6" style={{ borderColor: 'var(--rc-hairline)' }}>
            <SectionHeader
              id="reference"
              number={isZh ? '第二部分' : 'Part 2'}
              icon={BookMarked}
              title={isZh ? '算法参考' : 'Reference'}
              description={isZh
                ? '了解光谱预处理与结构预测光谱的基本原理、参数及适用范围。点击算法名称可打开原始论文或官方文档；预训练模型无需调节训练参数。'
                : 'Explore the principles, parameters, and scope of spectral preprocessing and structure-to-spectrum prediction. Select an algorithm name to open its paper or official documentation; pretrained models require no training parameters.'}
            />
            <div id="reference-content">
              <AlgorithmReferences />
            </div>
          </section>
        </div>
      </article>
    </div>
  );
}
