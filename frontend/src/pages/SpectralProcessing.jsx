import React, { useState, useRef, useMemo } from 'react';
import { Upload, FileUp } from 'lucide-react';
import SpectralChart, { CompareChart } from '../components/SpectralChart';
import ControlPanel from '../components/ControlPanel';
import ControlDock from '../components/ControlDock';
import axios from 'axios';
import { usePreferences } from '../i18n';
import useWorkspaceTask from '../hooks/useWorkspaceTask';
import WorkspaceFeedback from '../components/WorkspaceFeedback';
import { createProcessingRecord, exportResult, exportArchive, pipelineSignature } from '../utils/processingRecord';

const API_BASE = import.meta.env.BASE_URL.replace(/\/$/, '');
const DEMOS = ['bacteria', 'ulf', 'tutorial'];

export default function SpectralProcessing() {
  const { t } = usePreferences();
  const [fileName, setFileName] = useState(null);
  const [demoName, setDemoName] = useState('');
  const [rawData, setRawData] = useState(null);
  const [processedData, setProcessedData] = useState(null);
  const [baselineData, setBaselineData] = useState(null);
  const [steps, setSteps] = useState([]);
  const [isProcessing, setIsProcessing] = useState(false);
  const [error, setError] = useState(null);
  const [viewMode, setViewMode] = useState('overlay');
  const fileInputRef = useRef(null);
  const task = useWorkspaceTask(t);
  const [runRecord, setRunRecord] = useState(null);
  const [includeRecord, setIncludeRecord] = useState(true);
  const [uploadedSpectra, setUploadedSpectra] = useState([]);
  const [selectedSpectrum, setSelectedSpectrum] = useState(0);
  const [processAll, setProcessAll] = useState(false);
  const [batchResult, setBatchResult] = useState(null);
  const cutRange = useMemo(() => {
    const cut = steps.find(step => step.type === 'cut');
    if (cut) return [cut.params.start, cut.params.end];
    return rawData ? [Math.min(...rawData.wavenumber), Math.max(...rawData.wavenumber)] : null;
  }, [steps, rawData?.wavenumber]);
  const isStale = !!runRecord && pipelineSignature(steps) !== JSON.stringify(runRecord.steps);

  const applyData = (data, source, demo = '') => {
    setBatchResult(null);
    setProcessAll(false);
    setRawData({ wavenumber: data.wavenumber, intensity: data.intensity });
    setProcessedData(null);
    setBaselineData(null);
    setRunRecord(null);
    setFileName(source);
    setDemoName(demo);
    setSteps([]);
    setViewMode('overlay');
  };

  const loadDemo = name => {
    if (!name || task.busy) return;
    setError(null);
    task.run('readingData', async () => {
      const { data: res } = await axios.get(`${API_BASE}/api/demo/${name}`);
      if (res.code !== 0) throw new Error(res.msg);
      setUploadedSpectra([]);
      setSelectedSpectrum(0);
      applyData(res.data, null, name);
    });
  };

  const handleFileUpload = e => {
    const files = Array.from(e.target.files || []);
    e.target.value = '';
    if (!files.length || task.busy) return;
    setError(null);
    task.run('uploadingData', async ({ uploadProgress }) => {
      const formData = new FormData();
      files.forEach(file => formData.append('files', file));
      const { data: res } = await axios.post(`${API_BASE}/api/upload`, formData, { onUploadProgress: uploadProgress });
      if (res.code !== 0 || !res.data.spectra.length) throw new Error(res.msg || 'Upload failed');
      const spec = res.data.spectra[0];
      setUploadedSpectra(res.data.spectra);
      setSelectedSpectrum(0);
      applyData(spec, spec.filename);
    });
  };

  const handleProcess = () => {
    if (!rawData || !steps.length || task.busy) return;
    setError(null);
    task.run('processing', async () => {
      setIsProcessing(true);
      const started = performance.now();
      try {
        if (processAll && uploadedSpectra.length > 1) {
          const snapshot = JSON.parse(pipelineSignature(steps));
          const { data: res } = await axios.post(`${API_BASE}/api/process-batch`, { spectra: uploadedSpectra, steps: snapshot });
          if (res.code !== 0) throw new Error(res.msg);
          const records = res.data.spectra.map((result, index) => createProcessingRecord(result.filename, 'spectrum', uploadedSpectra[index], result, steps, started));
          setBatchResult({ spectra: res.data.spectra, records, signature: pipelineSignature(steps) });
          const result = res.data.spectra[selectedSpectrum];
          setProcessedData(result);
          setBaselineData(result.baseline);
          setRunRecord(records[selectedSpectrum]);
          return;
        }
        const { data: res } = await axios.post(`${API_BASE}/api/process`, {
          wavenumber: rawData.wavenumber, intensity: rawData.intensity,
          steps: JSON.parse(pipelineSignature(steps)),
        });
        if (res.code !== 0) throw new Error(res.msg);
        setProcessedData({ wavenumber: res.data.wavenumber, intensity: res.data.intensity });
        setBaselineData(res.data.baseline || null);
        setRunRecord(createProcessingRecord(fileName || demoName, 'spectrum', rawData, res.data, steps, started));
      } finally { setIsProcessing(false); }
    });
  };

  const handleDownloadBaseline = () => {
    if (!baselineData || isStale || task.busy) return;
    task.run('preparingDownload', async () => {
      const filename = `baseline_${(fileName || demoName || 'spectrum').replace(/\.[^.]+$/, '')}.txt`;
      const { data } = await axios.post(`${API_BASE}/api/download`, { wavenumber: processedData.wavenumber, intensity: baselineData, filename }, { responseType: 'blob' });
      await exportResult(data, filename, { ...runRecord, data_kind: 'baseline', columns: ['wavenumber', 'baseline'] }, includeRecord);
    });
  };

  const handleBatchDownload = () => {
    if (!batchResult || batchResult.signature !== pipelineSignature(steps) || task.busy) return;
    task.run('preparingDownload', async () => {
      const entries = [];
      for (let index = 0; index < batchResult.spectra.length; index += 1) {
        const result = batchResult.spectra[index];
        const name = `${index + 1}_${result.filename.replace(/[\\/]/g, '_').replace(/\.[^.]+$/, '')}.txt`;
        const { data } = await axios.post(`${API_BASE}/api/download`, { wavenumber: result.wavenumber, intensity: result.intensity }, { responseType: 'blob' });
        entries.push([`spectra/${name}`, data]);
        if (result.baseline) {
          const response = await axios.post(`${API_BASE}/api/download`, { wavenumber: result.wavenumber, intensity: result.baseline }, { responseType: 'blob' });
          entries.push([`baselines/${name}`, response.data]);
        }
      }
      await exportArchive(entries, includeRecord ? batchResult.records : null);
    });
  };

  const handleDownload = () => {
    if (!processedData || isStale || task.busy) return;
    task.run('preparingDownload', async () => {
      const filename = `processed_${(fileName || demoName || 'spectrum').replace(/\.[^.]+$/, '')}.txt`;
      const { data } = await axios.post(`${API_BASE}/api/download`, {
        wavenumber: processedData.wavenumber, intensity: processedData.intensity,
        baseline: baselineData, filename,
      }, { responseType: 'blob' });
      await exportResult(data, filename, { ...runRecord, columns: baselineData ? ['wavenumber', 'intensity', 'baseline'] : ['wavenumber', 'intensity'] }, includeRecord);
    });
  };

  const handleReset = () => {
    setBatchResult(null);
    setProcessedData(null);
    setBaselineData(null);
    setRunRecord(null);
    setSteps([]);
  };

  const handleClear = () => {
    handleReset();
    setProcessAll(false);
    setRawData(null);
    setFileName(null);
    setDemoName('');
    setError(null);
    task.setError(null);
    setUploadedSpectra([]);
    setSelectedSpectrum(0);
  };

  const hasData = rawData !== null;

  return (
    <div className="flex h-full relative">
      <WorkspaceFeedback task={task} error={error} onDismiss={() => setError(null)} />
      {/* Center: Visualization */}
      <div className="workspace-visual-surface flex-1 flex flex-col min-w-0 relative">
        <div className="workspace-toolbar flex items-center justify-between px-5 py-3 border-b border-white/5 glass">
          <div className="flex items-center gap-3">
            <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            <h2 className="text-sm font-semibold text-gray-200">{t('spectralWorkspace')}</h2>
          </div>
          <div className="flex items-center gap-2">
            <button
              disabled={!processedData || task.busy}
              onClick={() => setViewMode(viewMode === 'overlay' ? 'compare' : 'overlay')}
              className="px-3 py-1.5 text-xs rounded-lg bg-white/5 hover:bg-white/10 text-gray-400 hover:text-gray-200 transition-all"
            >
              {viewMode === 'overlay' ? t('compareView') : t('overlayView')}
            </button>
            <button
              disabled={task.busy} onClick={() => fileInputRef.current?.click()}
              className="px-3 py-1.5 text-xs rounded-lg bg-white/5 hover:bg-white/10 text-gray-400 hover:text-gray-200 transition-all flex items-center gap-1"
            >
              <Upload className="w-3 h-3" /> {t('upload')}
            </button>
          </div>
        </div>

        <div className="spectral-visual-stage flex-1 p-4 overflow-hidden">
          {!hasData ? (
            <div className="h-full flex items-center justify-center">
              <div className="text-center space-y-6 animate-fade-in">
                <div>
                  <h3 className="text-lg font-semibold text-gray-300">{t('loadSpectralData')}</h3>
                  <p className="text-sm text-gray-500 mt-1">{t('loadSpectralDataDesc')}</p>
                </div>
                <div className="flex flex-wrap gap-3 justify-center">
                  <button disabled={task.busy} onClick={() => fileInputRef.current?.click()}
                    className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-gradient-to-r from-indigo-600 to-purple-600 text-white text-sm font-medium hover:from-indigo-500 hover:to-purple-500 transition-all shadow-lg shadow-indigo-500/20">
                    <Upload className="w-4 h-4" /> {t('uploadFile')}
                  </button>
                  <button disabled={task.busy} onClick={() => loadDemo('bacteria')}
                    className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-white/5 text-gray-300 text-sm font-medium hover:bg-white/10 border border-white/5 transition-all">
                    <FileUp className="w-4 h-4" /> {t('bacteriaDemo')}
                  </button>
                </div>
              </div>
            </div>
          ) : (
            <div className="h-full animate-fade-in">
              {viewMode === 'overlay' || !processedData ? (
                <SpectralChart rawData={rawData} processedData={processedData} baselineData={baselineData} cutRange={cutRange} height={window.innerHeight - 140} showRaw={true} />
              ) : (
                <CompareChart rawData={rawData} processedData={processedData || rawData} height={window.innerHeight - 140} />
              )}
              <div className="absolute bottom-16 left-8 flex gap-2">
                {processedData && <span className="px-2 py-1 text-[10px] rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">{isStale ? t('resultStale') : t('processed')}</span>}
                {baselineData && <span className="px-2 py-1 text-[10px] rounded-full bg-purple-500/10 text-purple-400 border border-purple-500/20">{t('baselineCorrected')}</span>}
              </div>
            </div>
          )}
        </div>

        {hasData && (
          <div className="px-5 py-2 border-t border-white/5 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-gray-500">
            <span>{t('points')}: {rawData.wavenumber.length}</span>
            <span>{t('range')}: {rawData.wavenumber[0].toFixed(1)} – {rawData.wavenumber[rawData.wavenumber.length - 1].toFixed(1)} cm⁻¹</span>
            {demoName && <span className="text-indigo-400">{t(`${demoName}Demo`)}</span>}
          </div>
        )}
      </div>

      {/* Right: Control Panel */}
      <ControlDock>
        <ControlPanel
          steps={steps} onStepsChange={setSteps}
          onProcess={handleProcess} onDownload={handleDownload} onReset={handleReset}
          isProcessing={isProcessing} fileName={fileName} demoName={demoName}
          hasData={hasData} busy={task.busy} hasResult={!!runRecord} isStale={isStale}
          elapsed={runRecord?.elapsed_seconds} includeRecord={includeRecord}
          onIncludeRecordChange={setIncludeRecord} onClear={handleClear}
          onDemoChange={loadDemo} demos={DEMOS}
          uploadedSpectra={uploadedSpectra} selectedSpectrum={selectedSpectrum}
          processAll={processAll} onProcessAllChange={setProcessAll}
          hasBaseline={!!baselineData} onDownloadBaseline={handleDownloadBaseline}
          hasBatchResult={!!batchResult} onBatchDownload={handleBatchDownload}
          batchStale={!!batchResult && batchResult.signature !== pipelineSignature(steps)}
          onSpectrumChange={index => {
            if (task.busy || !uploadedSpectra[index]) return;
            setSelectedSpectrum(index);
            task.setError(null);
            setError(null);
            const source = uploadedSpectra[index];
            setRawData({ wavenumber: source.wavenumber, intensity: source.intensity });
            setFileName(source.filename);
            const result = batchResult?.spectra[index];
            setProcessedData(result || null);
            setBaselineData(result?.baseline || null);
            setRunRecord(batchResult?.records[index] || null);
          }}
          cutRange={cutRange}
        />
      </ControlDock>

      <input ref={fileInputRef} type="file" accept=".txt,.asc,.csv" multiple onChange={handleFileUpload} className="hidden" />
    </div>
  );
}
