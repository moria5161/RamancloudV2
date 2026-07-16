import React from 'react';
import StepController from './StepController';
import { Play, Download, RotateCcw, Loader2, Zap } from 'lucide-react';
import { usePreferences } from '../i18n';

export default function ControlPanel({
  steps,
  onStepsChange,
  onProcess,
  onDownload,
  onReset,
  isProcessing,
  fileName,
  demoName,
  onDemoChange,
  demos,
  cutRange,
  onCutRangeChange,
}) {
  const { t } = usePreferences();

  return (
    <div className="h-full flex flex-col glass border-l border-white/5">
      {/* Header */}
      <div className="p-4 border-b border-white/5">
        <div className="flex items-center gap-2 mb-3">
          <Zap className="w-4 h-4 text-indigo-400" />
          <h2 className="text-sm font-semibold text-gray-200 uppercase tracking-wider">{t('controls')}</h2>
        </div>

        {/* Data source */}
        <div className="space-y-2">
          <label className="text-[10px] text-gray-500 uppercase tracking-wider">{t('dataSource')}</label>
          <select
            value={demoName || ''}
            onChange={e => onDemoChange(e.target.value)}
            className="w-full px-2.5 py-1.5 text-xs bg-black/30 border border-white/10 rounded-lg text-gray-200 focus:border-indigo-500/50 focus:outline-none"
          >
            <option value="">{t('uploadFileEllipsis')}</option>
            {demos.map(d => (
              <option key={d} value={d}>{d === 'bacteria' ? 'Bacteria' : d === 'ulf' ? 'ULF Raman' : 'Tutorial Raman'}</option>
            ))}
          </select>
          {fileName && (
            <p className="text-[10px] text-gray-500 truncate">{t('file')}: {fileName}</p>
          )}
        </div>

        {/* Quick cut range */}
        <div className="mt-3 space-y-1.5">
          <label className="text-[10px] text-gray-500 uppercase tracking-wider">{t('quickCutRange')}</label>
          <div className="flex gap-1.5">
            <input
              type="number"
              placeholder={t('min')}
              value={cutRange?.[0] || ''}
              onChange={e => onCutRangeChange?.([parseFloat(e.target.value) || 0, cutRange?.[1] || 4000])}
              className="w-full px-2 py-1 text-xs bg-black/30 border border-white/10 rounded text-gray-200 focus:border-indigo-500/50 focus:outline-none"
            />
            <input
              type="number"
              placeholder={t('max')}
              value={cutRange?.[1] || ''}
              onChange={e => onCutRangeChange?.([cutRange?.[0] || 0, parseFloat(e.target.value) || 4000])}
              className="w-full px-2 py-1 text-xs bg-black/30 border border-white/10 rounded text-gray-200 focus:border-indigo-500/50 focus:outline-none"
            />
          </div>
        </div>
      </div>

      {/* Pipeline steps */}
      <div className="flex-1 overflow-y-auto p-4">
        <StepController steps={steps} onChange={onStepsChange} defaultCutRange={cutRange} />
      </div>

      {/* Action buttons */}
      <div className="p-4 border-t border-white/5 space-y-2">
        <button
          onClick={onProcess}
          disabled={isProcessing || (!fileName && !demoName)}
          className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 text-white text-sm font-medium transition-all duration-200 disabled:opacity-40 disabled:cursor-not-allowed shadow-lg shadow-indigo-500/20"
        >
          {isProcessing ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Play className="w-4 h-4" />
          )}
          {isProcessing ? t('processing') : t('runPipeline')}
        </button>

        <div className="flex gap-2">
          <button
            onClick={onDownload}
            className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg bg-white/5 hover:bg-white/10 text-gray-300 text-xs font-medium transition-all"
          >
            <Download className="w-3 h-3" />
            {t('download')}
          </button>
          <button
            onClick={onReset}
            className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg bg-white/5 hover:bg-white/10 text-gray-400 text-xs font-medium transition-all"
          >
            <RotateCcw className="w-3 h-3" />
            {t('reset')}
          </button>
        </div>
      </div>
    </div>
  );
}
