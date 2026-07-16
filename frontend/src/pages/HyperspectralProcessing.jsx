import React, { useState, useCallback, useEffect, useRef } from 'react';
import { Upload, AlertCircle, Layers, Image, Activity, Crosshair, Map } from 'lucide-react';
import SpectralChart from '../components/SpectralChart';
import { ImagingHeatmap, PixelSpectrum, CompareImaging, TimeSeriesHeatmap } from '../components/HyperspectralChart';
import ControlPanel from '../components/ControlPanel';
import axios from 'axios';

const API_BASE = import.meta.env.BASE_URL.replace(/\/$/, '');

const DEMOS = ['imaging_horiba', 'timeseries_horiba'];

const TABS = [
  { id: 'imaging', label: 'Imaging', icon: Map },
  { id: 'spectrum', label: 'Avg Spectrum', icon: Activity },
  { id: 'pixel', label: 'Single Pixel', icon: Crosshair },
];

export default function HyperspectralProcessing() {
  const [fileName, setFileName] = useState(null);
  const [rawData, setRawData] = useState(null);
  const [processedData, setProcessedData] = useState(null);
  const [mode, setMode] = useState(null);
  const [meanSpectrum, setMeanSpectrum] = useState(null);
  const [processedMean, setProcessedMean] = useState(null);
  const [steps, setSteps] = useState([]);
  const [isProcessing, setIsProcessing] = useState(false);
  const [error, setError] = useState(null);
  const [cutRange, setCutRange] = useState(null);
  const [activeTab, setActiveTab] = useState('imaging');
  const [selectedWN, setSelectedWN] = useState(null);
  const [selectedPixel, setSelectedPixel] = useState(null); // {x, y}
  const [rawPixelSpectrum, setRawPixelSpectrum] = useState(null);
  const [processedPixelSpectrum, setProcessedPixelSpectrum] = useState(null);
  const [uploadInstrument, setUploadInstrument] = useState('Horiba');
  const [uploadMode, setUploadMode] = useState('imaging');
  const fileInputRef = useRef(null);
  const sliceTimerRef = useRef(null);

  const showError = (msg) => { setError(msg); setTimeout(() => setError(null), 5000); };

  // Load demo hyperspectral data
  const loadDemo = useCallback(async (name) => {
    if (!name) return;
    try {
      setError(null);
      const { data: res } = await axios.get(`${API_BASE}/api/demo-hyperspectral/${name}`);
      if (res.code === 0) {
        setRawData(res.data);
        setMode(res.data.mode);
        setFileName(res.data.filename);
        const wn = res.data.wavenumber;
        setMeanSpectrum({ wavenumber: wn, intensity: res.data.mean_spectrum });
        setProcessedMean(null);
        setProcessedData(null);
        setSelectedPixel(null);
        setRawPixelSpectrum(null);
        setProcessedPixelSpectrum(null);
        setCutRange([Math.min(...wn), Math.max(...wn)]);
        setSelectedWN(res.data.preview_wavenumber ?? Math.round((Math.min(...wn) + Math.max(...wn)) / 2));
        setSteps([]);
        setActiveTab('imaging');
      } else {
        showError(res.msg);
      }
    } catch (e) {
      showError('Failed to load demo. Is the backend running?');
    }
  }, []);

  const handleFileUpload = useCallback(async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      setError(null);
      const formData = new FormData();
      formData.append('file', file);
      formData.append('instrument', uploadInstrument);
      formData.append('mode', uploadMode);

      const { data: res } = await axios.post(`${API_BASE}/api/upload-hyperspectral`, formData);
      if (res.code === 0) {
        setRawData(res.data);
        setMode(res.data.mode);
        setFileName(res.data.filename);
        const wn = res.data.wavenumber;
        setMeanSpectrum({ wavenumber: wn, intensity: res.data.mean_spectrum });
        setProcessedMean(null);
        setProcessedData(null);
        setSelectedPixel(null);
        setRawPixelSpectrum(null);
        setProcessedPixelSpectrum(null);
        setCutRange([Math.min(...wn), Math.max(...wn)]);
        setSelectedWN(res.data.preview_wavenumber ?? Math.round((Math.min(...wn) + Math.max(...wn)) / 2));
        setSteps([]);
      } else {
        showError(res.msg);
      }
    } catch (e) {
      showError('Upload failed. Is the backend running?');
    }
  }, [uploadInstrument, uploadMode]);

  const handleProcess = useCallback(async () => {
    if (!rawData?.dataset_id && !rawData?.spectra) return;
    setIsProcessing(true);
    setError(null);
    try {
      const pipelineSteps = steps.map(s => ({ type: s.type, method: s.method, params: s.params }));

      const { data: res } = await axios.post(`${API_BASE}/api/process-hyperspectral`, {
        wavenumber: rawData.wavenumber,
        dataset_id: rawData.dataset_id,
        spectra: rawData.spectra,
        shape: rawData.shape,
        mode: rawData.mode,
        steps: pipelineSteps,
      });

      if (res.code === 0) {
        setProcessedMean({ wavenumber: res.data.wavenumber, intensity: res.data.mean_spectrum });
        setProcessedData(res.data);
        setProcessedPixelSpectrum(null);
      } else {
        showError(res.msg);
      }
    } catch (e) {
      showError('Processing failed.');
    } finally {
      setIsProcessing(false);
    }
  }, [rawData, steps]);

  const handleDownload = useCallback(async () => {
    if (!processedMean) return;
    try {
      const { data: res } = await axios.post(
        `${API_BASE}/api/download`,
        processedData?.processed_dataset_id || processedData?.spectra
          ? {
              wavenumber: processedMean.wavenumber,
              dataset_id: processedData.processed_dataset_id,
              spectra: processedData.spectra,
              shape: processedData.shape,
              mode: mode,
              filename: `processed_${fileName || 'mapping.txt'}`,
            }
          : {
              wavenumber: processedMean.wavenumber,
              intensity: processedMean.intensity,
              filename: 'processed_hyperspectral_mean.txt',
            },
        { responseType: 'blob' }
      );
      const url = URL.createObjectURL(new Blob([res]));
      const a = document.createElement('a');
      a.href = url; a.download = `processed_${fileName || 'hyperspectral.txt'}`; a.click();
      URL.revokeObjectURL(url);
    } catch (e) { showError('Download failed'); }
  }, [processedMean, processedData, fileName, mode]);

  const handleReset = () => {
    setProcessedMean(null);
    setProcessedData(null);
    setProcessedPixelSpectrum(null);
    setSteps([]);
  };

  const handleHeatmapClick = useCallback((event) => {
    if (!event.points?.length) return;
    const pt = event.points[0];
    const scale = rawData?.preview_scale || 1;
    setSelectedPixel({ x: Math.round(pt.x * scale), y: Math.round(pt.y * scale) });
    setActiveTab('pixel');
  }, [rawData?.preview_scale]);

  const fetchSlice = useCallback(async (datasetId, value) => {
    if (!datasetId || value == null) return null;
    const { data: res } = await axios.get(`${API_BASE}/api/hyperspectral-slice/${datasetId}`, {
      params: { wavenumber_value: value },
    });
    return res.code === 0 ? res.data : null;
  }, []);

  const handleWavenumberChange = useCallback((value) => {
    setSelectedWN(value);
    if (sliceTimerRef.current) clearTimeout(sliceTimerRef.current);
    sliceTimerRef.current = setTimeout(async () => {
      try {
        const rawSlice = await fetchSlice(rawData?.dataset_id, value);
        if (rawSlice) {
          setRawData(prev => prev ? { ...prev, preview: rawSlice.preview, preview_wavenumber: rawSlice.wavenumber } : prev);
        }
        const processedSlice = await fetchSlice(processedData?.processed_dataset_id, value);
        if (processedSlice) {
          setProcessedData(prev => prev ? { ...prev, preview: processedSlice.preview, preview_wavenumber: processedSlice.wavenumber } : prev);
        }
      } catch (e) {
        showError('Failed to load imaging slice.');
      }
    }, 120);
  }, [rawData?.dataset_id, processedData?.processed_dataset_id, fetchSlice]);

  const hasData = rawData !== null;
  const isImaging = mode === 'imaging';
  const isTimeSeries = mode === 'time_series';

  useEffect(() => {
    let cancelled = false;
    async function loadPixelSpectra() {
      if (!selectedPixel || !rawData?.dataset_id || !isImaging) return;
      try {
        const rawReq = axios.get(`${API_BASE}/api/hyperspectral-pixel/${rawData.dataset_id}`, {
          params: { x: selectedPixel.x, y: selectedPixel.y },
        });
        const processedReq = processedData?.processed_dataset_id
          ? axios.get(`${API_BASE}/api/hyperspectral-pixel/${processedData.processed_dataset_id}`, {
              params: { x: selectedPixel.x, y: selectedPixel.y },
            })
          : null;
        const [rawRes, processedRes] = await Promise.all([rawReq, processedReq]);
        if (cancelled) return;
        setRawPixelSpectrum(rawRes.data.code === 0 ? rawRes.data.data : null);
        setProcessedPixelSpectrum(processedRes?.data?.code === 0 ? processedRes.data.data : null);
      } catch (e) {
        if (!cancelled) showError('Failed to load pixel spectrum.');
      }
    }
    loadPixelSpectra();
    return () => { cancelled = true; };
  }, [selectedPixel, rawData?.dataset_id, processedData?.processed_dataset_id, isImaging]);

  return (
    <div className="flex h-full">
      <div className="flex-1 flex flex-col min-w-0 relative">
        {/* Top bar */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-white/5 glass">
          <div className="flex items-center gap-3">
            <div className="w-2 h-2 rounded-full bg-purple-400 animate-pulse" />
            <h2 className="text-sm font-semibold text-gray-200">Hyperspectral Processing Workspace</h2>
            {mode && <span className="text-[10px] text-gray-500 bg-white/5 px-2 py-0.5 rounded uppercase">{mode}</span>}
          </div>
          <div className="flex items-center gap-2">
            {/* Tab switcher */}
            {hasData && (
              <div className="flex bg-white/5 rounded-lg p-0.5">
                {TABS.filter(t => t.id !== 'imaging' || isImaging).map(({ id, label, icon: Icon }) => (
                  <button key={id} onClick={() => setActiveTab(id)}
                    className={`flex items-center gap-1 px-3 py-1.5 text-xs rounded-md transition-all ${
                      activeTab === id ? 'bg-indigo-500/20 text-indigo-400' : 'text-gray-500 hover:text-gray-300'
                    }`}>
                    <Icon className="w-3 h-3" /> {label}
                  </button>
                ))}
              </div>
            )}
            <button onClick={() => fileInputRef.current?.click()}
              className="px-3 py-1.5 text-xs rounded-lg bg-white/5 hover:bg-white/10 text-gray-400 hover:text-gray-200 transition-all flex items-center gap-1">
              <Upload className="w-3 h-3" /> Upload
            </button>
          </div>
        </div>

        {/* Main content */}
        <div className="flex-1 p-4 overflow-auto">
          {!hasData ? (
            <div className="h-full flex items-center justify-center">
              <div className="text-center space-y-6 animate-fade-in">
                <div className="w-20 h-20 mx-auto rounded-2xl bg-gradient-to-br from-purple-500/20 to-pink-500/20 border border-purple-500/20 flex items-center justify-center">
                  <Layers className="w-10 h-10 text-purple-400" />
                </div>
                <div>
                  <h3 className="text-lg font-semibold text-gray-300">Load Hyperspectral Data</h3>
                  <p className="text-sm text-gray-500 mt-1">Upload Horiba format imaging or time-series data (.txt)</p>
                </div>
                <div className="flex gap-2 justify-center">
                  <select value={uploadInstrument} onChange={e => setUploadInstrument(e.target.value)}
                    className="px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-sm text-gray-300">
                    <option value="Horiba">Horiba</option>
                    <option value="Nanophoton">Nanophoton</option>
                    <option value="Renishaw">Renishaw</option>
                  </select>
                  <select value={uploadMode} onChange={e => setUploadMode(e.target.value)}
                    className="px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-sm text-gray-300">
                    <option value="imaging">Imaging</option>
                    <option value="time_series">Time series</option>
                  </select>
                </div>
                <div className="flex gap-3 justify-center">
                  <button onClick={() => fileInputRef.current?.click()}
                    className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-gradient-to-r from-purple-600 to-pink-600 text-white text-sm font-medium hover:from-purple-500 hover:to-pink-500 transition-all shadow-lg shadow-purple-500/20">
                    <Upload className="w-4 h-4" /> Upload File
                  </button>
                  <button onClick={() => loadDemo('imaging_horiba')}
                    className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-white/5 text-gray-300 text-sm font-medium hover:bg-white/10 border border-white/5 transition-all">
                    <Image className="w-4 h-4" /> Imaging Demo
                  </button>
                  <button onClick={() => loadDemo('timeseries_horiba')}
                    className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-white/5 text-gray-300 text-sm font-medium hover:bg-white/10 border border-white/5 transition-all">
                    <Activity className="w-4 h-4" /> Time Series Demo
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
            <div className="h-full animate-fade-in space-y-4">
              {/* Dataset info bar */}
              <div className="glass rounded-xl p-3 border border-white/5 flex items-center gap-4 text-xs text-gray-500">
                <Image className="w-4 h-4 text-purple-400" />
                <span>Shape: {rawData.shape?.join(' × ')}</span>
                <span>Spectral points: {rawData.wavenumber?.length}</span>
                <span>File: {fileName}</span>
                {processedMean && (
                  <span className="px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 text-[10px]">Processed</span>
                )}
              </div>

              {/* Tab content */}
              <div className="flex-1" style={{ height: window.innerHeight - 260 }}>
                {/* Imaging Tab */}
                {activeTab === 'imaging' && isImaging && rawData.preview && (
                  processedData?.preview ? (
                    <CompareImaging
                      rawPreview={rawData.preview}
                      processedPreview={processedData.preview}
                      wavenumber={rawData.wavenumber}
                      selectedWN={selectedWN}
                      onSelectWN={handleWavenumberChange}
                      onHeatmapClick={handleHeatmapClick}
                      height={window.innerHeight - 280}
                    />
                  ) : (
                    <ImagingHeatmap
                      previewData={rawData.preview}
                      wavenumber={rawData.wavenumber}
                      selectedWN={selectedWN}
                      onSelectWN={handleWavenumberChange}
                      onHeatmapClick={handleHeatmapClick}
                      title="Hyperspectral Imaging — Select Wavenumber"
                      height={window.innerHeight - 280}
                      colorscale="Jet"
                    />
                  )
                )}

                {/* Time Series Tab */}
                {activeTab === 'imaging' && isTimeSeries && (
                  <TimeSeriesHeatmap
                    data2D={rawData.preview || rawData.mean_spectrum}
                    wavenumber={rawData.wavenumber}
                    title="Time Series Heatmap"
                    height={window.innerHeight - 280}
                    colorscale="Jet"
                  />
                )}

                {/* Average Spectrum Tab */}
                {activeTab === 'spectrum' && (
                  <SpectralChart
                    rawData={meanSpectrum}
                    processedData={processedMean}
                    cutRange={cutRange}
                    height={window.innerHeight - 260}
                    showRaw={true}
                  />
                )}

                {/* Single Pixel Tab */}
                {activeTab === 'pixel' && isImaging && (
                  <div className="space-y-4">
                    <div className="flex gap-4">
                      <div>
                        <label className="text-xs text-gray-500">Pixel X</label>
                        <input type="number" value={selectedPixel?.x ?? 0}
                          onChange={e => setSelectedPixel(p => ({ ...p, x: parseInt(e.target.value) || 0 }))}
                          className="w-20 px-2 py-1 text-xs bg-black/30 border border-white/10 rounded text-gray-200 ml-2" />
                      </div>
                      <div>
                        <label className="text-xs text-gray-500">Pixel Y</label>
                        <input type="number" value={selectedPixel?.y ?? 0}
                          onChange={e => setSelectedPixel(p => ({ ...p, y: parseInt(e.target.value) || 0 }))}
                          className="w-20 px-2 py-1 text-xs bg-black/30 border border-white/10 rounded text-gray-200 ml-2" />
                      </div>
                      {!selectedPixel && (
                        <span className="text-xs text-gray-600 self-end">Select a pixel from the Imaging tab heatmap</span>
                      )}
                    </div>
                    <PixelSpectrum
                      previewData={rawData.preview}
                      wavenumber={rawPixelSpectrum?.wavenumber || rawData.wavenumber}
                      pixelX={selectedPixel?.x}
                      pixelY={selectedPixel?.y}
                      rawSpectrum={rawPixelSpectrum?.intensity}
                      processedSpectrum={processedPixelSpectrum?.intensity}
                      processedWavenumber={processedPixelSpectrum?.wavenumber}
                      height={window.innerHeight - 360}
                    />
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Bottom info bar */}
        {hasData && (
          <div className="px-5 py-2 border-t border-white/5 flex items-center gap-4 text-xs text-gray-500">
            <span>Total spectra: {isImaging ? (rawData.shape?.[0] || 1) * (rawData.shape?.[1] || 1) : rawData.time_points || 'N/A'}</span>
            <span>Range: {rawData.wavenumber?.[0]?.toFixed(1)} – {rawData.wavenumber?.[rawData.wavenumber?.length - 1]?.toFixed(1)} cm⁻¹</span>
          </div>
        )}
      </div>

      {/* Right: Control Panel */}
      <div className="w-80 shrink-0">
        <ControlPanel
          steps={steps} onStepsChange={setSteps}
          onProcess={handleProcess} onDownload={handleDownload} onReset={handleReset}
          isProcessing={isProcessing} fileName={fileName} demoName={fileName ? '' : (rawData?.filename || '')}
          onDemoChange={loadDemo} demos={DEMOS}
          cutRange={cutRange} onCutRangeChange={setCutRange}
        />
      </div>

      <input ref={fileInputRef} type="file" accept=".txt" onChange={handleFileUpload} className="hidden" />
    </div>
  );
}
