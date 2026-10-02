import React from 'react';
import StepController from './StepController';
import { Play, Download, RotateCcw, Loader2, Zap, Trash2 } from 'lucide-react';
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
  hasData,
  busy = false,
  hasResult = false,
  isStale = false,
  elapsed,
  includeRecord,
  onIncludeRecordChange,
  onClear,
  uploadedSpectra = [],
  selectedSpectrum = 0,
  onSpectrumChange,
  processAll = false,
  onProcessAllChange,
  allowBatch = false,
  hasBaseline = false,
  onDownloadBaseline,
  hasBatchResult = false,
  onBatchDownload,
  batchStale = false,
}) {
  const { t, language } = usePreferences();
  const isZh = language === 'zh';

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
            disabled={busy}
            value={demoName || ''}
            onChange={e => onDemoChange(e.target.value)}
            className="w-full px-2.5 py-1.5 text-xs bg-black/30 border border-white/10 rounded-lg text-gray-200 focus:border-indigo-500/50 focus:outline-none"
          >
            <option value="">{t('uploadFileEllipsis')}</option>
            {demos.map(d => (
              <option key={d} value={d}>{t(d === 'imaging_horiba' ? 'imagingDemo' : d === 'timeseries_horiba' ? 'timeSeriesDemo' : `${d}Demo`)}</option>
            ))}
          </select>
          {fileName && (
            <p className="text-[10px] text-gray-500 truncate">{t('file')}: {fileName}</p>
          )}
          {uploadedSpectra.length > 1 && (
            <div>
              <label htmlFor="uploaded-spectrum" className="text-[10px] text-gray-500">{t('uploadedSpectrum')}</label>
              <select id="uploaded-spectrum" disabled={busy} value={selectedSpectrum}
                onChange={e => onSpectrumChange(Number(e.target.value))}
                className="w-full px-2.5 py-1.5 text-xs bg-black/30 border border-white/10 rounded-lg text-gray-200">
                {uploadedSpectra.map((spectrum, index) => <option key={index} value={index}>{spectrum.filename}</option>)}
              </select>
            </div>
          )}
          {uploadedSpectra.length > 1 && <label className="flex items-center gap-2 text-xs text-gray-500">
            <input type="checkbox" checked={processAll} disabled={busy} onChange={event => onProcessAllChange(event.target.checked)} />
            {isZh ? `对全部 ${uploadedSpectra.length} 条光谱应用流程` : `Apply pipeline to all ${uploadedSpectra.length} spectra`}
          </label>}
        </div>

      </div>

      {/* Pipeline steps */}
      <fieldset disabled={busy} className="flex-1 overflow-y-auto p-4 min-h-0">
        <StepController steps={steps} onChange={onStepsChange} defaultCutRange={cutRange} allowBatch={allowBatch || processAll} />
      </fieldset>

      {/* Action buttons */}
      <div className="p-4 border-t border-white/5 space-y-2">
        <div role="status" className={`text-xs ${isStale ? 'text-amber-600' : 'text-gray-500'}`}>
          {hasResult && (isStale ? t('resultStale') : `${t('processingComplete')} · ${elapsed?.toFixed(2)} s`)}
        </div>
        {hasBaseline && <button onClick={onDownloadBaseline} disabled={busy || isStale}
          className="flex items-center justify-center gap-2 w-full py-2 rounded-lg bg-white/5 text-xs text-gray-400">
          <Download className="w-3.5 h-3.5" />{isZh ? '下载独立基线' : 'Download baseline'}
        </button>}
        {hasBatchResult && <button onClick={onBatchDownload} disabled={busy || batchStale}
          className="flex items-center justify-center gap-2 w-full py-2 rounded-lg bg-white/5 text-xs text-gray-400">
          <Download className="w-3.5 h-3.5" />{isZh ? '下载批量结果' : 'Download batch results'}
        </button>}
        <button
          onClick={onProcess}
          disabled={busy || !hasData || steps.length === 0}
          className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 text-white text-sm font-medium transition-all duration-200 disabled:opacity-40 disabled:cursor-not-allowed shadow-lg shadow-indigo-500/20"
        >
          {isProcessing ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Play className="w-4 h-4" />
          )}
          {isProcessing ? t('processing') : t('runPipeline')}
        </button>

        <label className="flex items-center gap-2 text-xs text-gray-500">
          <input type="checkbox" checked={includeRecord} onChange={e => onIncludeRecordChange(e.target.checked)} disabled={busy} />
          {t('includeRecord')}
        </label>

        <div className="flex gap-2">
          <button
            onClick={onDownload}
            disabled={busy || !hasResult || isStale}
            title={isStale ? t('resultStale') : t('download')}
            className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg bg-white/5 hover:bg-white/10 text-gray-300 text-xs font-medium transition-all"
          >
            <Download className="w-3 h-3" />
            {t('download')}
          </button>
          <button
            onClick={onReset}
            disabled={busy || !hasData}
            className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg bg-white/5 hover:bg-white/10 text-gray-400 text-xs font-medium transition-all"
          >
            <RotateCcw className="w-3 h-3" />
            {t('reset')}
          </button>
        </div>
        <button onClick={onClear} disabled={busy || !hasData} className="flex items-center justify-center gap-2 w-full py-2 text-xs text-gray-500" title={t('clearWorkspace')}>
          <Trash2 className="w-3.5 h-3.5" />{t('clearWorkspace')}
        </button>
      </div>
    </div>
  );
}
