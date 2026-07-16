import React from 'react';
import { BookOpen, Scissors, Waves, Baseline, ArrowRight, FileText, Download } from 'lucide-react';
import { usePreferences } from '../i18n';

const Section = ({ id, title, children }) => (
  <section id={id} className="space-y-2">
    <h3 className="text-base font-semibold text-gray-200">{title}</h3>
    <div className="text-sm text-gray-400 leading-relaxed space-y-1.5">{children}</div>
  </section>
);

export default function Tutorial() {
  const { language } = usePreferences();
  const isZh = language === 'zh';

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-3xl mx-auto px-8 py-10 space-y-8 animate-fade-in">
        {/* Header */}
        <div className="space-y-3">
          <div className="flex items-center gap-3">
            <BookOpen className="w-6 h-6 text-indigo-400" />
            <h1 className="text-2xl font-bold text-white">{isZh ? '教程' : 'Tutorial'}</h1>
          </div>
          <p className="text-gray-400">
            {isZh
              ? '了解如何使用 RamanCloud 完成光谱预处理。本教程覆盖数据加载、处理流程、算法参数和结果下载。'
              : 'Learn how to use RamanCloud for spectral preprocessing. This guide covers data loading, the processing pipeline, algorithm parameters, and downloading results.'}
          </p>
        </div>

        <div className="glass rounded-xl p-5 border border-white/5 space-y-6">
          <h2 className="text-lg font-semibold text-gray-200">{isZh ? '快速开始' : 'Getting Started'}</h2>
          <p className="text-sm text-gray-400">
            {isZh
              ? 'RamanCloud 是面向拉曼光谱数据预处理的网页平台。你可以上传自己的 .txt 文件，也可以使用内置示例数据体验平台功能。'
              : 'RamanCloud is a web-based platform for Raman spectral data preprocessing. You can upload your own .txt files or use built-in demo datasets (Bacteria, Ultra-Low Frequency Raman) to explore the platform.'}
          </p>
          <div className="flex gap-4 text-xs">
            <div className="flex items-center gap-1.5 text-indigo-400">
              <FileText className="w-3 h-3" /> {isZh ? '支持格式：.txt、.asc、.csv' : 'Supported: .txt, .asc, .csv'}
            </div>
            <div className="flex items-center gap-1.5 text-indigo-400">
              <Download className="w-3 h-3" /> {isZh ? '下载：处理后的 .txt' : 'Download: Processed .txt'}
            </div>
          </div>
        </div>

        {/* Cut */}
        <div className="glass rounded-xl p-5 border border-white/5 space-y-3">
          <div className="flex items-center gap-2">
            <Scissors className="w-4 h-4 text-emerald-400" />
            <h2 className="text-lg font-semibold text-gray-200">{isZh ? '步骤 1：光谱裁剪' : 'Step 1: Spectral Cut'}</h2>
          </div>
          <p className="text-sm text-gray-400">
            {isZh
              ? '选择波数范围来裁剪光谱。你可以使用控制面板中的快速裁剪范围，也可以在流程中添加 Cut 步骤并设置起止值。裁剪区域会在图中高亮显示。'
              : 'Select a wavenumber range to crop your spectrum. Use the Quick Cut Range inputs in the control panel or add a Cut step to your pipeline with custom start/end values. The cut region is highlighted on the chart.'}
          </p>
          <div className="bg-black/20 rounded-lg p-3 text-xs text-gray-500 font-mono">
            {isZh ? '提示：拖拽图表可缩放，双击可重置视图；也可以使用图表工具栏进行平移和缩放。' : 'Tip: Drag on the chart to zoom, double-click to reset view. Use the mode bar for pan/zoom tools.'}
          </div>
        </div>

        {/* Denoising */}
        <div className="glass rounded-xl p-5 border border-white/5 space-y-4">
          <div className="flex items-center gap-2">
            <Waves className="w-4 h-4 text-blue-400" />
            <h2 className="text-lg font-semibold text-gray-200">{isZh ? '步骤 2：去噪' : 'Step 2: Denoising'}</h2>
          </div>
          <p className="text-sm text-gray-400">
            {isZh ? '可以选择多种去噪算法。每种方法都有对应参数，用于进一步微调处理效果。' : 'Choose from multiple denoising algorithms. Each method has its own parameters for fine-tuning.'}
          </p>
          <div className="space-y-3">
            <div className="bg-black/20 rounded-lg p-3">
              <h4 className="text-sm font-medium text-gray-300">Savitzky-Golay (SG)</h4>
              <p className="text-xs text-gray-500 mt-1">
                {isZh ? 'Window Size：控制平滑窗口，越大越平滑，必须为奇数且大于 order+1。' : 'Window Size: Controls the smoothing window. Larger = smoother. Must be odd and greater than order+1.'}<br />
                {isZh ? 'Order：拟合多项式阶数，越高拟合越灵活。' : 'Order: Polynomial order for fitting. Higher = more flexible fit.'}
              </p>
            </div>
            <div className="bg-black/20 rounded-lg p-3">
              <h4 className="text-sm font-medium text-gray-300">Wavelet (WTD)</h4>
              <p className="text-xs text-gray-500 mt-1">
                {isZh ? 'Wavelet：Daubechies 小波类型（db1-db8）。Level：分解层数，层数越高通常去除噪声越多。' : 'Wavelet: Daubechies wavelet type (db1-db8). Level: Decomposition depth. Higher level removes more noise.'}
              </p>
            </div>
            <div className="bg-black/20 rounded-lg p-3">
              <h4 className="text-sm font-medium text-gray-300">PEER</h4>
              <p className="text-xs text-gray-500 mt-1">
                {isZh
                  ? 'Peak Extraction and Retention 算法。Loops：迭代次数（1-10）。Peak Seek：寻峰阈值，数值越高通常保留更多峰。'
                  : 'Peak Extraction and Retention algorithm. Loops: iteration count (1-10). Peak Seek: threshold for peak identification. Higher values retain more peaks.'}{' '}
                <a href="https://pubs.acs.org/doi/10.1021/acs.analchem.0c05391" target="_blank" rel="noopener noreferrer" className="text-indigo-400">{isZh ? '参考文献' : 'Reference'}</a>
              </p>
            </div>
          </div>
        </div>

        {/* Baseline */}
        <div className="glass rounded-xl p-5 border border-white/5 space-y-4">
          <div className="flex items-center gap-2">
            <Baseline className="w-4 h-4 text-purple-400" />
            <h2 className="text-lg font-semibold text-gray-200">{isZh ? '步骤 3：基线校正' : 'Step 3: Baseline Correction'}</h2>
          </div>
          <p className="text-sm text-gray-400">
            {isZh ? '去除荧光背景以及其它基线伪影，使峰形和强度更利于后续分析。' : 'Remove fluorescence background and other baseline artifacts from your spectra.'}
          </p>
          <div className="space-y-3">
            <div className="bg-black/20 rounded-lg p-3">
              <h4 className="text-sm font-medium text-gray-300">airPLS</h4>
              <p className="text-xs text-gray-500 mt-1">
                {isZh
                  ? '自适应迭代重加权惩罚最小二乘方法。Lambda：平滑强度，数值越大基线越平滑。Diff Order：惩罚阶数，通常为 2-3。'
                  : 'Adaptive Iteratively Reweighted Penalized Least Squares. Lambda: smoothness (larger = smoother baseline). Diff Order: penalty order (2-3 typical).'}{' '}
                <a href="https://doi.org/10.1039/B922045C" target="_blank" rel="noopener noreferrer" className="text-indigo-400">{isZh ? '参考文献' : 'Reference'}</a>
              </p>
            </div>
            <div className="bg-black/20 rounded-lg p-3">
              <h4 className="text-sm font-medium text-gray-300">Auto-Adaptive (AABS)</h4>
              <p className="text-xs text-gray-500 mt-1">
                {isZh ? '自动背景扣除方法。Ln：噪声平滑窗口。Lb：基线确定窗口，可根据光谱特征自动调整。' : 'Automatic background subtraction. Ln: noise smoothing window. Lb: baseline determination window. Adjusts automatically to spectral features.'}
              </p>
            </div>
            <div className="bg-black/20 rounded-lg p-3">
              <h4 className="text-sm font-medium text-gray-300">IModPoly</h4>
              <p className="text-xs text-gray-500 mt-1">
                {isZh ? '迭代改进多项式拟合。Poly Order：多项式阶数，阶数越高越适合复杂基线，但也可能过拟合。' : 'Iterative Modified Polynomial fitting. Poly Order: polynomial degree. Higher = better fit for complex baselines but may overfit.'}
              </p>
            </div>
          </div>
        </div>

        {/* Pipeline */}
        <div className="glass rounded-xl p-5 border border-indigo-500/20 space-y-3 bg-indigo-500/5">
          <h2 className="text-lg font-semibold text-gray-200">{isZh ? '流程控制' : 'Pipeline Control'}</h2>
          <p className="text-sm text-gray-400">
            {isZh
              ? '你可以自由控制处理顺序。向流程中添加步骤，并使用上下箭头调整顺序。系统会按照显示顺序执行，也可以多次添加同类步骤。'
              : 'You control the order of operations. Add steps to the pipeline and reorder them using the up/down arrows. Operations execute in the order shown. You can add multiple steps of the same type (e.g., multiple denoising passes).'}
          </p>
          <div className="flex items-center gap-2 text-xs text-indigo-400">
            <ArrowRight className="w-3 h-3" />
            {isZh ? '示例：Cut -> Denoise -> Baseline，或 Denoise -> Cut -> Baseline，由你决定。' : 'Example: Cut -> Denoise -> Baseline, or Denoise -> Cut -> Baseline - you decide!'}
          </div>
        </div>
      </div>
    </div>
  );
}
