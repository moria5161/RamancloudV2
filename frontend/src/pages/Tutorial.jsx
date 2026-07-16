import React from 'react';
import { BookOpen, Scissors, Waves, Baseline, ArrowRight, FileText, Download } from 'lucide-react';

const Section = ({ id, title, children }) => (
  <section id={id} className="space-y-2">
    <h3 className="text-base font-semibold text-gray-200">{title}</h3>
    <div className="text-sm text-gray-400 leading-relaxed space-y-1.5">{children}</div>
  </section>
);

export default function Tutorial() {
  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-3xl mx-auto px-8 py-10 space-y-8 animate-fade-in">
        {/* Header */}
        <div className="space-y-3">
          <div className="flex items-center gap-3">
            <BookOpen className="w-6 h-6 text-indigo-400" />
            <h1 className="text-2xl font-bold text-white">Tutorial</h1>
          </div>
          <p className="text-gray-400">
            Learn how to use RamanCloud for spectral preprocessing. This guide covers data loading,
            the processing pipeline, algorithm parameters, and downloading results.
          </p>
        </div>

        <div className="glass rounded-xl p-5 border border-white/5 space-y-6">
          <h2 className="text-lg font-semibold text-gray-200">Getting Started</h2>
          <p className="text-sm text-gray-400">
            RamanCloud is a web-based platform for Raman spectral data preprocessing. You can upload your own .txt files
            or use built-in demo datasets (Bacteria, Ultra-Low Frequency Raman) to explore the platform.
          </p>
          <div className="flex gap-4 text-xs">
            <div className="flex items-center gap-1.5 text-indigo-400">
              <FileText className="w-3 h-3" /> Supported: .txt, .asc, .csv
            </div>
            <div className="flex items-center gap-1.5 text-indigo-400">
              <Download className="w-3 h-3" /> Download: Processed .txt
            </div>
          </div>
        </div>

        {/* Cut */}
        <div className="glass rounded-xl p-5 border border-white/5 space-y-3">
          <div className="flex items-center gap-2">
            <Scissors className="w-4 h-4 text-emerald-400" />
            <h2 className="text-lg font-semibold text-gray-200">Step 1: Spectral Cut</h2>
          </div>
          <p className="text-sm text-gray-400">
            Select a wavenumber range to crop your spectrum. Use the Quick Cut Range inputs in the control panel
            or add a Cut step to your pipeline with custom start/end values. The cut region is highlighted on the chart.
          </p>
          <div className="bg-black/20 rounded-lg p-3 text-xs text-gray-500 font-mono">
            Tip: Drag on the chart to zoom, double-click to reset view. Use the mode bar for pan/zoom tools.
          </div>
        </div>

        {/* Denoising */}
        <div className="glass rounded-xl p-5 border border-white/5 space-y-4">
          <div className="flex items-center gap-2">
            <Waves className="w-4 h-4 text-blue-400" />
            <h2 className="text-lg font-semibold text-gray-200">Step 2: Denoising</h2>
          </div>
          <p className="text-sm text-gray-400">
            Choose from multiple denoising algorithms. Each method has its own parameters for fine-tuning.
          </p>
          <div className="space-y-3">
            <div className="bg-black/20 rounded-lg p-3">
              <h4 className="text-sm font-medium text-gray-300">Savitzky-Golay (SG)</h4>
              <p className="text-xs text-gray-500 mt-1">
                Window Size: Controls the smoothing window. Larger = smoother. Must be odd and greater than order+1.<br />
                Order: Polynomial order for fitting. Higher = more flexible fit.
              </p>
            </div>
            <div className="bg-black/20 rounded-lg p-3">
              <h4 className="text-sm font-medium text-gray-300">Wavelet (WTD)</h4>
              <p className="text-xs text-gray-500 mt-1">
                Wavelet: Daubechies wavelet type (db1-db8). Level: Decomposition depth. Higher level removes more noise.
              </p>
            </div>
            <div className="bg-black/20 rounded-lg p-3">
              <h4 className="text-sm font-medium text-gray-300">PEER</h4>
              <p className="text-xs text-gray-500 mt-1">
                Peak Extraction and Retention algorithm. Loops: iteration count (1-10). Peak Seek: threshold for peak identification.
                Higher values retain more peaks. <a href="https://pubs.acs.org/doi/10.1021/acs.analchem.0c05391" target="_blank" rel="noopener noreferrer" className="text-indigo-400">Reference</a>
              </p>
            </div>
          </div>
        </div>

        {/* Baseline */}
        <div className="glass rounded-xl p-5 border border-white/5 space-y-4">
          <div className="flex items-center gap-2">
            <Baseline className="w-4 h-4 text-purple-400" />
            <h2 className="text-lg font-semibold text-gray-200">Step 3: Baseline Correction</h2>
          </div>
          <p className="text-sm text-gray-400">
            Remove fluorescence background and other baseline artifacts from your spectra.
          </p>
          <div className="space-y-3">
            <div className="bg-black/20 rounded-lg p-3">
              <h4 className="text-sm font-medium text-gray-300">airPLS</h4>
              <p className="text-xs text-gray-500 mt-1">
                Adaptive Iteratively Reweighted Penalized Least Squares. Lambda: smoothness (larger = smoother baseline).
                Diff Order: penalty order (2-3 typical). <a href="https://doi.org/10.1039/B922045C" target="_blank" rel="noopener noreferrer" className="text-indigo-400">Reference</a>
              </p>
            </div>
            <div className="bg-black/20 rounded-lg p-3">
              <h4 className="text-sm font-medium text-gray-300">Auto-Adaptive (AABS)</h4>
              <p className="text-xs text-gray-500 mt-1">
                Automatic background subtraction. Ln: noise smoothing window. Lb: baseline determination window.
                Adjusts automatically to spectral features.
              </p>
            </div>
            <div className="bg-black/20 rounded-lg p-3">
              <h4 className="text-sm font-medium text-gray-300">IModPoly</h4>
              <p className="text-xs text-gray-500 mt-1">
                Iterative Modified Polynomial fitting. Poly Order: polynomial degree. Higher = better fit for complex baselines
                but may overfit.
              </p>
            </div>
          </div>
        </div>

        {/* Pipeline */}
        <div className="glass rounded-xl p-5 border border-indigo-500/20 space-y-3 bg-indigo-500/5">
          <h2 className="text-lg font-semibold text-gray-200">Pipeline Control</h2>
          <p className="text-sm text-gray-400">
            You control the order of operations. Add steps to the pipeline and reorder them using the up/down arrows.
            Operations execute in the order shown. You can add multiple steps of the same type (e.g., multiple denoising passes).
          </p>
          <div className="flex items-center gap-2 text-xs text-indigo-400">
            <ArrowRight className="w-3 h-3" />
            Example: Cut → Denoise → Baseline, or Denoise → Cut → Baseline — you decide!
          </div>
        </div>
      </div>
    </div>
  );
}
