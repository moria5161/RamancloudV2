import React, { useState, useCallback, useRef } from 'react';
import { Upload, FileUp, Database, AlertCircle } from 'lucide-react';
import SpectralChart, { CompareChart } from '../components/SpectralChart';
import ControlPanel from '../components/ControlPanel';
import axios from 'axios';
import { usePreferences } from '../i18n';

const API_BASE = import.meta.env.BASE_URL.replace(/\/$/, '');
const DEMOS = ['bacteria', 'ulf', 'tutorial'];

export default function SpectralProcessing() {
  const { t } = usePreferences();
  const [fileName, setFileName] = useState(null);
  const [demoName, setDemoName] = useState('');
  const [rawData, setRawData] = useState(null);
  const [processedData, setProcessedData] = useState(null);
  const [baselineData, setBaselineData] = useState(null);
  const [cutRange, setCutRange] = useState(null);
  const [steps, setSteps] = useState([]);
  const [isProcessing, setIsProcessing] = useState(false);
  const [error, setError] = useState(null);
  const [viewMode, setViewMode] = useState('overlay');
  const fileInputRef = useRef(null);

  const showError = (msg) => {
    setError(msg);
    setTimeout(() => setError(null), 5000);
  };

  const loadDemo = useCallback(async (name) => {
    if (!name) return;
    try {
      setError(null);
      const { data: res } = await axios.get(`${API_BASE}/api/demo/${name}`);
      if (res.code === 0) {
        setRawData({ wavenumber: res.data.wavenumber, intensity: res.data.intensity });
        setProcessedData(null);
        setBaselineData(null);
        setFileName(null);
        setDemoName(name);
        setCutRange([res.data.wavenumber[0], res.data.wavenumber[res.data.wavenumber.length - 1]]);
      } else {
        showError(res.msg);
      }
    } catch (e) {
      showError('Failed to load demo. Is the backend running?');
    }
  }, []);

  const handleFileUpload = useCallback(async (e) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;
    try {
      setError(null);
      const formData = new FormData();
      for (const f of files) formData.append('files', f);
      const { data: res } = await axios.post(`${API_BASE}/api/upload`, formData);
      if (res.code === 0 && res.data.spectra.length > 0) {
        const spec = res.data.spectra[0];
        setRawData({ wavenumber: spec.wavenumber, intensity: spec.intensity });
        setProcessedData(null);
        setBaselineData(null);
        setFileName(spec.filename);
        setDemoName('');
        setCutRange([spec.wavenumber[0], spec.wavenumber[spec.wavenumber.length - 1]]);
      } else {
        showError(res.msg || 'Upload failed');
      }
    } catch (e) {
      showError('Upload failed. Is the backend running?');
    }
  }, []);

  const handleProcess = useCallback(async () => {
    if (!rawData) return;
    setIsProcessing(true);
    setError(null);
    try {
      const pipelineSteps = [...steps.map(s => ({
        type: s.type, method: s.method, params: s.params,
      }))];

      const { data: res } = await axios.post(`${API_BASE}/api/process`, {
        wavenumber: rawData.wavenumber,
        intensity: rawData.intensity,
        steps: pipelineSteps,
      });

      if (res.code === 0) {
        setProcessedData({ wavenumber: res.data.wavenumber, intensity: res.data.intensity });
        setBaselineData(res.data.baseline || null);
      } else {
        showError(res.msg);
      }
    } catch (e) {
      showError('Processing failed. Check backend connection.');
    } finally {
      setIsProcessing(false);
    }
  }, [rawData, steps, cutRange]);

  const handleDownload = useCallback(async () => {
    if (!processedData) return;
    try {
      const { data: res } = await axios.post(
        `${API_BASE}/api/download`,
        {
          wavenumber: processedData.wavenumber,
          intensity: processedData.intensity,
          baseline: baselineData,
          include_baseline: !!baselineData,
          filename: `processed_${fileName || demoName || 'spectrum'}.txt`,
        },
        { responseType: 'blob' }
      );
      const url = URL.createObjectURL(new Blob([res]));
      const a = document.createElement('a');
      a.href = url;
      a.download = `processed_${fileName || demoName || 'spectrum'}.txt`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      showError('Download failed');
    }
  }, [processedData, baselineData, fileName, demoName]);

  const handleReset = () => {
    if (rawData) {
      setProcessedData({ wavenumber: [...rawData.wavenumber], intensity: [...rawData.intensity] });
    }
    setBaselineData(null);
    setSteps([]);
  };

  const hasData = rawData !== null;

  return (
    <div className="flex h-full">
      {/* Center: Visualization */}
      <div className="flex-1 flex flex-col min-w-0 relative">
        <div className="flex items-center justify-between px-5 py-3 border-b border-white/5 glass">
          <div className="flex items-center gap-3">
            <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            <h2 className="text-sm font-semibold text-gray-200">{t('spectralWorkspace')}</h2>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setViewMode(viewMode === 'overlay' ? 'compare' : 'overlay')}
              className="px-3 py-1.5 text-xs rounded-lg bg-white/5 hover:bg-white/10 text-gray-400 hover:text-gray-200 transition-all"
            >
              {viewMode === 'overlay' ? t('compareView') : t('overlayView')}
            </button>
            <button
              onClick={() => fileInputRef.current?.click()}
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
                <div className="w-20 h-20 mx-auto rounded-2xl bg-gradient-to-br from-indigo-500/20 to-purple-500/20 border border-indigo-500/20 flex items-center justify-center">
                  <Database className="w-10 h-10 text-indigo-400" />
                </div>
                <div>
                  <h3 className="text-lg font-semibold text-gray-300">{t('loadSpectralData')}</h3>
                  <p className="text-sm text-gray-500 mt-1">{t('loadSpectralDataDesc')}</p>
                </div>
                <div className="flex gap-3 justify-center">
                  <button onClick={() => fileInputRef.current?.click()}
                    className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-gradient-to-r from-indigo-600 to-purple-600 text-white text-sm font-medium hover:from-indigo-500 hover:to-purple-500 transition-all shadow-lg shadow-indigo-500/20">
                    <Upload className="w-4 h-4" /> {t('uploadFile')}
                  </button>
                  <button onClick={() => loadDemo('bacteria')}
                    className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-white/5 text-gray-300 text-sm font-medium hover:bg-white/10 border border-white/5 transition-all">
                    <FileUp className="w-4 h-4" /> {t('bacteriaDemo')}
                  </button>
                </div>
                {error && (
                  <div className="flex items-center gap-2 text-red-400 bg-red-500/10 rounded-lg px-4 py-2 text-sm max-w-md mx-auto">
                    <AlertCircle className="w-4 h-4 shrink-0" /> {error}
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="h-full animate-fade-in">
              {viewMode === 'overlay' ? (
                <SpectralChart rawData={rawData} processedData={processedData} baselineData={baselineData} cutRange={cutRange} height={window.innerHeight - 140} showRaw={true} />
              ) : (
                <CompareChart rawData={rawData} processedData={processedData || rawData} height={window.innerHeight - 140} />
              )}
              <div className="absolute bottom-16 left-8 flex gap-2">
                {processedData && <span className="px-2 py-1 text-[10px] rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">{t('processed')}</span>}
                {baselineData && <span className="px-2 py-1 text-[10px] rounded-full bg-purple-500/10 text-purple-400 border border-purple-500/20">{t('baselineCorrected')}</span>}
              </div>
            </div>
          )}
        </div>

        {hasData && (
          <div className="px-5 py-2 border-t border-white/5 flex items-center gap-4 text-xs text-gray-500">
            <span>{t('points')}: {rawData.wavenumber.length}</span>
            <span>{t('range')}: {rawData.wavenumber[0].toFixed(1)} – {rawData.wavenumber[rawData.wavenumber.length - 1].toFixed(1)} cm⁻¹</span>
            {demoName && <span className="text-indigo-400">{t('demo')}: {demoName}</span>}
          </div>
        )}
      </div>

      {/* Right: Control Panel */}
      <div className="w-80 shrink-0">
        <ControlPanel
          steps={steps} onStepsChange={setSteps}
          onProcess={handleProcess} onDownload={handleDownload} onReset={handleReset}
          isProcessing={isProcessing} fileName={fileName} demoName={demoName}
          onDemoChange={loadDemo} demos={DEMOS}
          cutRange={cutRange} onCutRangeChange={setCutRange}
        />
      </div>

      <input ref={fileInputRef} type="file" accept=".txt,.asc,.csv" multiple onChange={handleFileUpload} className="hidden" />
    </div>
  );
}
