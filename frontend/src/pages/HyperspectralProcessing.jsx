import React, { useState, useCallback, useEffect, useRef, useMemo } from 'react';
import { Upload, Image, Activity, Crosshair, Map } from 'lucide-react';
import SpectralChart from '../components/SpectralChart';
import { ImagingHeatmap, PixelSpectrum, CompareImaging, TimeSeriesHeatmap, CompareTimeSeriesHeatmap, TimeSeriesDifference } from '../components/HyperspectralChart';
import ControlPanel from '../components/ControlPanel';
import ControlDock from '../components/ControlDock';
import axios from 'axios';
import { usePreferences } from '../i18n';
import useWorkspaceTask from '../hooks/useWorkspaceTask';
import WorkspaceFeedback from '../components/WorkspaceFeedback';
import { createProcessingRecord, exportResult, pipelineSignature } from '../utils/processingRecord';

const API_BASE = import.meta.env.BASE_URL.replace(/\/$/, '');

const DEMOS = ['imaging_horiba', 'timeseries_horiba'];

const TABS = [
  { id: 'imaging', labelKey: 'imaging', icon: Map },
  { id: 'spectrum', labelKey: 'avgSpectrum', icon: Activity },
  { id: 'pixel', labelKey: 'singlePixel', icon: Crosshair },
];

export default function HyperspectralProcessing() {
  const { t } = usePreferences();
  const [fileName, setFileName] = useState(null);
  const [rawData, setRawData] = useState(null);
  const [processedData, setProcessedData] = useState(null);
  const [mode, setMode] = useState(null);
  const [meanSpectrum, setMeanSpectrum] = useState(null);
  const [processedMean, setProcessedMean] = useState(null);
  const [steps, setSteps] = useState([]);
  const [isProcessing, setIsProcessing] = useState(false);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState('imaging');
  const [selectedWN, setSelectedWN] = useState(null);
  const [selectedPixel, setSelectedPixel] = useState(null); // {x, y}
  const [selectedSeriesIndex, setSelectedSeriesIndex] = useState(null);
  const [rawPixelSpectrum, setRawPixelSpectrum] = useState(null);
  const [processedPixelSpectrum, setProcessedPixelSpectrum] = useState(null);
  const [rawSeriesSpectrum, setRawSeriesSpectrum] = useState(null);
  const [processedSeriesSpectrum, setProcessedSeriesSpectrum] = useState(null);
  const [uploadInstrument, setUploadInstrument] = useState('Horiba');
  const [uploadMode, setUploadMode] = useState('imaging');
  const fileInputRef = useRef(null);
  const sliceTimerRef = useRef(null);
  const sliceVersion = useRef(0);
  const task = useWorkspaceTask(t);
  const [demoName, setDemoName] = useState('');
  const [runRecord, setRunRecord] = useState(null);
  const [includeRecord, setIncludeRecord] = useState(true);
  const [sharedColorScale, setSharedColorScale] = useState(true);
  const isStale = !!runRecord && pipelineSignature(steps) !== JSON.stringify(runRecord.steps);

  const cutRange = useMemo(() => {
    const cut = steps.find(step => step.type === 'cut');
    if (cut) return [cut.params.start, cut.params.end];
    return rawData ? [Math.min(...rawData.wavenumber), Math.max(...rawData.wavenumber)] : null;
  }, [steps, rawData?.wavenumber]);

  const hasData = rawData !== null;
  const isImaging = mode === 'imaging';
  const isTimeSeries = mode === 'time_series';

  const showError = msg => setError(msg);

  const clearSelections = () => {
    setSelectedPixel(null);
    setRawPixelSpectrum(null);
    setProcessedPixelSpectrum(null);
    setRawSeriesSpectrum(null);
    setProcessedSeriesSpectrum(null);
    sliceVersion.current += 1;
    clearTimeout(sliceTimerRef.current);
  };

  const applyData = (data, demo = '') => {
    clearSelections();
    setRawData(data);
    setMode(data.mode);
    setFileName(data.filename);
    setDemoName(demo);
    setMeanSpectrum({ wavenumber: data.wavenumber, intensity: data.mean_spectrum });
    setProcessedMean(null);
    setProcessedData(null);
    setRunRecord(null);
    setSelectedSeriesIndex(data.mode === 'time_series' ? 0 : null);
    setSelectedWN(data.preview_wavenumber ?? data.wavenumber[Math.floor(data.wavenumber.length / 2)]);
    setSteps([]);
    setActiveTab('imaging');
  };

  const loadDemo = name => {
    if (!name || task.busy) return;
    setError(null);
    task.run('readingData', async () => {
      const { data: res } = await axios.get(`${API_BASE}/api/demo-hyperspectral/${name}`);
      if (res.code !== 0) throw new Error(res.msg);
      applyData(res.data, name);
    });
  };

  const handleFileUpload = e => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file || task.busy) return;
    setError(null);
    task.run('uploadingData', async ({ uploadProgress }) => {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('instrument', uploadInstrument);
      formData.append('mode', uploadMode);
      const { data: res } = await axios.post(`${API_BASE}/api/upload-hyperspectral`, formData, { onUploadProgress: uploadProgress });
      if (res.code !== 0) throw new Error(res.msg);
      applyData(res.data);
    });
  };

  const handleProcess = () => {
    if (!rawData?.dataset_id || !steps.length || task.busy) return;
    setError(null);
    task.run('processing', async () => {
      setIsProcessing(true);
      sliceVersion.current += 1;
      clearTimeout(sliceTimerRef.current);
      const started = performance.now();
      try {
        const { data: res } = await axios.post(`${API_BASE}/api/process-hyperspectral`, {
          wavenumber: rawData.wavenumber, dataset_id: rawData.dataset_id,
          shape: rawData.shape, mode: rawData.mode,
          steps: JSON.parse(pipelineSignature(steps)),
        });
        if (res.code !== 0) throw new Error(res.msg);
        if (mode === 'imaging') {
          task.setPhase('generatingPreview');
          const value = Math.max(Math.min(...res.data.wavenumber), Math.min(Math.max(...res.data.wavenumber), selectedWN));
          const [rawSlice, processedSlice] = await Promise.all([
            fetchSlice(rawData.dataset_id, value),
            fetchSlice(res.data.processed_dataset_id, value),
          ]);
          if (rawSlice) setRawData(previous => ({ ...previous, preview: rawSlice.preview, preview_wavenumber: rawSlice.wavenumber }));
          if (processedSlice) res.data.preview = processedSlice.preview;
          setSelectedWN(value);
        }
        setProcessedMean({ wavenumber: res.data.wavenumber, intensity: res.data.mean_spectrum });
        setProcessedData(res.data);
        setRunRecord(createProcessingRecord(fileName, mode, rawData, res.data, steps, started));
        setProcessedPixelSpectrum(null);
        setProcessedSeriesSpectrum(null);
      } finally { setIsProcessing(false); }
    });
  };

  const handleDownload = () => {
    if (!processedData || isStale || task.busy) return;
    task.run('preparingDownload', async () => {
      const filename = `processed_${fileName || 'hyperspectral.txt'}`;
      const { data } = await axios.post(`${API_BASE}/api/download`, {
        wavenumber: processedData.wavenumber,
        dataset_id: processedData.processed_dataset_id,
        shape: processedData.shape, mode, filename,
        format: 'mapping',
      }, { responseType: 'blob' });
      await exportResult(data, filename, {
        ...runRecord, instrument: demoName ? 'Horiba' : uploadInstrument,
        coordinates: rawData.coordinates,
        export_instrument: 'Horiba',
        data_format: mode === 'imaging' ? 'Horiba tab-separated mapping: first row has two empty cells followed by wavenumbers; subsequent rows contain X, Y, intensities.' : 'Horiba tab-separated time series: first row has one empty cell followed by wavenumbers; subsequent rows contain original time/index and intensities.',
        spatial_order: mode === 'imaging' ? 'row-major (Y, X); X varies fastest' : 'source time order',
      }, includeRecord);
    });
  };

  const handleReset = () => {
    sliceVersion.current += 1;
    clearTimeout(sliceTimerRef.current);
    setProcessedMean(null);
    setProcessedData(null);
    setRunRecord(null);
    setProcessedPixelSpectrum(null);
    setProcessedSeriesSpectrum(null);
    setSteps([]);
    if (activeTab === 'difference') setActiveTab('imaging');
  };

  const handleClear = () => {
    handleReset();
    clearSelections();
    setRawData(null);
    setMeanSpectrum(null);
    setFileName(null);
    setDemoName('');
    setMode(null);
    setSelectedWN(null);
    setSelectedSeriesIndex(null);
    setError(null);
    task.setError(null);
  };

  const handleHeatmapClick = useCallback((event) => {
    if (!event.points?.length) return;
    const pt = event.points[0];
    if (isTimeSeries) {
      const times = rawData?.coordinates?.time;
      const index = times?.length ? times.reduce((best, value, current) => Math.abs(value - pt.y) < Math.abs(times[best] - pt.y) ? current : best, 0) : Math.round(pt.y);
      setSelectedSeriesIndex(index);
      setActiveTab('pixel');
      return;
    }
    const scale = rawData?.preview_scale || 1;
    setSelectedPixel({ x: Math.round(pt.x * scale), y: Math.round(pt.y * scale) });
    setActiveTab('pixel');
  }, [rawData?.preview_scale, rawData?.coordinates, isTimeSeries]);

  const fetchSlice = useCallback(async (datasetId, value) => {
    if (!datasetId || value == null) return null;
    const { data: res } = await axios.get(`${API_BASE}/api/hyperspectral-slice/${datasetId}`, {
      params: { wavenumber_value: value },
    });
    return res.code === 0 ? res.data : null;
  }, []);

  const handleWavenumberChange = useCallback((value) => {
    setSelectedWN(value);
    const version = ++sliceVersion.current;
    if (sliceTimerRef.current) clearTimeout(sliceTimerRef.current);
    sliceTimerRef.current = setTimeout(async () => {
      try {
        const [rawSlice, processedSlice] = await Promise.all([
          fetchSlice(rawData?.dataset_id, value),
          fetchSlice(processedData?.processed_dataset_id, value),
        ]);
        if (version !== sliceVersion.current) return;
        if (rawSlice) {
          setRawData(prev => prev ? { ...prev, preview: rawSlice.preview, preview_wavenumber: rawSlice.wavenumber } : prev);
        }
        if (processedSlice) {
          setProcessedData(prev => prev ? { ...prev, preview: processedSlice.preview, preview_wavenumber: processedSlice.wavenumber } : prev);
        }
      } catch (e) {
        if (version === sliceVersion.current) showError(t('requestFailed'));
      }
    }, 120);
  }, [rawData?.dataset_id, processedData?.processed_dataset_id, fetchSlice]);

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
        if (!cancelled) showError(t('requestFailed'));
      }
    }
    loadPixelSpectra();
    return () => { cancelled = true; };
  }, [selectedPixel, rawData?.dataset_id, processedData?.processed_dataset_id, isImaging]);

  useEffect(() => {
    let cancelled = false;
    async function loadSeriesSpectra() {
      if (selectedSeriesIndex == null || !rawData?.dataset_id || !isTimeSeries) return;
      try {
        const rawReq = axios.get(`${API_BASE}/api/hyperspectral-spectrum/${rawData.dataset_id}`, {
          params: { index: selectedSeriesIndex },
        });
        const processedReq = processedData?.processed_dataset_id
          ? axios.get(`${API_BASE}/api/hyperspectral-spectrum/${processedData.processed_dataset_id}`, {
              params: { index: selectedSeriesIndex },
            })
          : null;
        const [rawRes, processedRes] = await Promise.all([rawReq, processedReq]);
        if (cancelled) return;
        setRawSeriesSpectrum(rawRes.data.code === 0 ? rawRes.data.data : null);
        setProcessedSeriesSpectrum(processedRes?.data?.code === 0 ? processedRes.data.data : null);
      } catch (e) {
        if (!cancelled) showError(t('requestFailed'));
      }
    }
    loadSeriesSpectra();
    return () => { cancelled = true; };
  }, [selectedSeriesIndex, rawData?.dataset_id, processedData?.processed_dataset_id, isTimeSeries]);

  return (
    <div className="flex h-full relative">
      <WorkspaceFeedback task={task} error={error} onDismiss={() => setError(null)} />
      <div className="flex-1 flex flex-col min-w-0 relative">
        {/* Top bar */}
        <div className="workspace-toolbar flex items-center justify-between px-5 py-3 border-b border-white/5 glass">
          <div className="flex items-center gap-3">
            <div className="w-2 h-2 rounded-full bg-purple-400 animate-pulse" />
            <h2 className="text-sm font-semibold text-gray-200">{t('hyperspectralWorkspace')}</h2>
            {mode && <span className="text-[10px] text-gray-500 bg-white/5 px-2 py-0.5 rounded uppercase">{mode}</span>}
          </div>
          <div className="flex items-center gap-2">
            {/* Tab switcher */}
            {hasData && (
              <div className="flex bg-white/5 rounded-lg p-0.5">
                {TABS.map(({ id, labelKey, icon: Icon }) => (
                  <button key={id} onClick={() => setActiveTab(id)}
                    className={`flex items-center gap-1 px-3 py-1.5 text-xs rounded-md transition-all ${
                      activeTab === id ? 'bg-indigo-500/20 text-indigo-400' : 'text-gray-500 hover:text-gray-300'
                    }`}>
                    <Icon className="w-3 h-3" /> {t(id === 'imaging' && isTimeSeries ? 'timeSeries' : labelKey)}
                  </button>
                ))}
                {isTimeSeries && processedData && <button onClick={() => setActiveTab('difference')}
                  className={`flex items-center gap-1 px-3 py-1.5 text-xs rounded-md transition-all ${activeTab === 'difference' ? 'bg-indigo-500/20 text-indigo-400' : 'text-gray-500 hover:text-gray-300'}`}>
                  <Activity className="w-3 h-3" /> {t('differenceView')}
                </button>}
              </div>
            )}
            <button disabled={task.busy} onClick={() => fileInputRef.current?.click()}
              className="px-3 py-1.5 text-xs rounded-lg bg-white/5 hover:bg-white/10 text-gray-400 hover:text-gray-200 transition-all flex items-center gap-1">
              <Upload className="w-3 h-3" /> {t('upload')}
            </button>
          </div>
        </div>

        {/* Main content */}
        <div className="flex-1 p-4 overflow-auto">
          {!hasData ? (
            <div className="h-full flex items-center justify-center">
              <div className="text-center space-y-6 animate-fade-in">
                <div>
                  <h3 className="text-lg font-semibold text-gray-300">{t('loadHyperspectralData')}</h3>
                  <p className="text-sm text-gray-500 mt-1">{t('loadHyperspectralDataDesc')}</p>
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
                    <option value="imaging">{t('imaging')}</option>
                    <option value="time_series">{t('timeSeries')}</option>
                  </select>
                </div>
                <div className="flex gap-3 justify-center">
                  <button disabled={task.busy} onClick={() => fileInputRef.current?.click()}
                    className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-gradient-to-r from-purple-600 to-pink-600 text-white text-sm font-medium hover:from-purple-500 hover:to-pink-500 transition-all shadow-lg shadow-purple-500/20">
                    <Upload className="w-4 h-4" /> {t('uploadFile')}
                  </button>
                  <button disabled={task.busy} onClick={() => loadDemo('imaging_horiba')}
                    className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-white/5 text-gray-300 text-sm font-medium hover:bg-white/10 border border-white/5 transition-all">
                    <Image className="w-4 h-4" /> {t('imagingDemo')}
                  </button>
                  <button disabled={task.busy} onClick={() => loadDemo('timeseries_horiba')}
                    className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-white/5 text-gray-300 text-sm font-medium hover:bg-white/10 border border-white/5 transition-all">
                    <Activity className="w-4 h-4" /> {t('timeSeriesDemo')}
                  </button>
                </div>
              </div>
            </div>
          ) : (
            <div className="h-full animate-fade-in space-y-4">
              {/* Dataset info bar */}
              <div className="glass rounded-lg p-3 border border-white/5 flex flex-wrap items-center gap-4 text-xs text-gray-500">
                <Image className="w-4 h-4 text-purple-400" />
                <span>{t('shape')}: {rawData.shape?.join(' × ')}</span>
                <span>{t('spectralPoints')}: {rawData.wavenumber?.length}</span>
                <span className="break-all">{t('file')}: {fileName}</span>
                {processedMean && (
                  <span className="px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 text-[10px]">{isStale ? t('resultStale') : t('processed')}</span>
                )}
              </div>

              {activeTab === 'imaging' && processedData && (
                <div className="flex justify-end">
                  <div className="segmented-control" role="group" aria-label={t('colorScale')}>
                    <button className={sharedColorScale ? 'is-active' : ''} aria-pressed={sharedColorScale} onClick={() => setSharedColorScale(true)}>{t('sharedColorScale')}</button>
                    <button className={!sharedColorScale ? 'is-active' : ''} aria-pressed={!sharedColorScale} onClick={() => setSharedColorScale(false)}>{t('independentColorScale')}</button>
                  </div>
                </div>
              )}
              {/* Tab content */}
              <div className="flex-1" style={{ height: window.innerHeight - 260 }}>
                {activeTab === 'difference' && isTimeSeries && processedData && <TimeSeriesDifference
                  rawData2D={rawData.preview} processedData2D={processedData.preview}
                  rawWavenumber={rawData.wavenumber} processedWavenumber={processedData.wavenumber}
                  timeCoordinates={rawData.coordinates?.time} timeKind={rawData.coordinates?.time_kind}
                  timeUnit={rawData.coordinates?.time_unit}
                  selectedIndex={selectedSeriesIndex} onHeatmapClick={handleHeatmapClick}
                  height={window.innerHeight - 280}
                />}
                {/* Imaging Tab */}
                {activeTab === 'imaging' && isImaging && rawData.preview && (
                  processedData?.preview ? (
                    <CompareImaging
                      rawPreview={rawData.preview}
                      processedPreview={processedData.preview}
                      coordinates={rawData.coordinates}
                      previewScale={rawData.preview_scale || 1}
                      wavenumber={rawData.wavenumber}
                      selectedWN={selectedWN}
                      onSelectWN={handleWavenumberChange}
                      onHeatmapClick={handleHeatmapClick}
                      selectedPixel={selectedPixel ? { x: selectedPixel.x / (rawData.preview_scale || 1), y: selectedPixel.y / (rawData.preview_scale || 1) } : null}
                      selectedIndex={selectedSeriesIndex}
                      sharedColorScale={sharedColorScale}
                      height={window.innerHeight - 280}
                    />
                  ) : (
                    <ImagingHeatmap
                      previewData={rawData.preview}
                      coordinates={rawData.coordinates}
                      previewScale={rawData.preview_scale || 1}
                      wavenumber={rawData.wavenumber}
                      selectedWN={selectedWN}
                      onSelectWN={handleWavenumberChange}
                      onHeatmapClick={handleHeatmapClick}
                      selectedPixel={selectedPixel ? { x: selectedPixel.x / (rawData.preview_scale || 1), y: selectedPixel.y / (rawData.preview_scale || 1) } : null}
                      selectedIndex={selectedSeriesIndex}
                      sharedColorScale={sharedColorScale}
                      title={t('imaging')}
                      height={window.innerHeight - 280}
                      colorscale="Jet"
                    />
                  )
                )}

                {/* Time Series Tab */}
                {activeTab === 'imaging' && isTimeSeries && (
                  processedData?.preview ? (
                    <CompareTimeSeriesHeatmap
                      rawData2D={rawData.preview || rawData.mean_spectrum}
                      processedData2D={processedData.preview}
                      timeCoordinates={rawData.coordinates?.time}
                      timeKind={rawData.coordinates?.time_kind}
                      timeUnit={rawData.coordinates?.time_unit}
                      rawWavenumber={rawData.wavenumber}
                      processedWavenumber={processedData.wavenumber}
                      title={t('rawProcessedComparison')}
                      height={window.innerHeight - 280}
                      colorscale="Jet"
                      onHeatmapClick={handleHeatmapClick}
                      selectedPixel={selectedPixel ? { x: selectedPixel.x / (rawData.preview_scale || 1), y: selectedPixel.y / (rawData.preview_scale || 1) } : null}
                      selectedIndex={selectedSeriesIndex}
                      sharedColorScale={sharedColorScale}
                    />
                  ) : (
                    <TimeSeriesHeatmap
                      data2D={rawData.preview || rawData.mean_spectrum}
                      wavenumber={rawData.wavenumber}
                      title={t('timeSeries')}
                      height={window.innerHeight - 280}
                      colorscale="Jet"
                      onHeatmapClick={handleHeatmapClick}
                      selectedPixel={selectedPixel ? { x: selectedPixel.x / (rawData.preview_scale || 1), y: selectedPixel.y / (rawData.preview_scale || 1) } : null}
                      selectedIndex={selectedSeriesIndex}
                      sharedColorScale={sharedColorScale}
                      timeCoordinates={rawData.coordinates?.time}
                      timeKind={rawData.coordinates?.time_kind}
                      timeUnit={rawData.coordinates?.time_unit}
                    />
                  )
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
                        <label className="text-xs text-gray-500">{t('pixelX')}</label>
                        <input type="number" min="0" max={(rawData.shape?.[1] || 1) - 1} value={selectedPixel?.x ?? 0}
                          onChange={e => setSelectedPixel(p => ({ y: p?.y ?? 0, x: Math.max(0, Math.min((rawData.shape?.[1] || 1) - 1, parseInt(e.target.value) || 0)) }))}
                          className="w-20 px-2 py-1 text-xs bg-black/30 border border-white/10 rounded text-gray-200 ml-2" />
                      </div>
                      <div>
                        <label className="text-xs text-gray-500">{t('pixelY')}</label>
                        <input type="number" min="0" max={(rawData.shape?.[0] || 1) - 1} value={selectedPixel?.y ?? 0}
                          onChange={e => setSelectedPixel(p => ({ x: p?.x ?? 0, y: Math.max(0, Math.min((rawData.shape?.[0] || 1) - 1, parseInt(e.target.value) || 0)) }))}
                          className="w-20 px-2 py-1 text-xs bg-black/30 border border-white/10 rounded text-gray-200 ml-2" />
                      </div>
                      {!selectedPixel && (
                        <span className="text-xs text-gray-600 self-end">{t('selectPixelHint')}</span>
                      )}
                      {selectedPixel && <span className="text-xs text-gray-500 self-end">{t('sourceCoordinates')}: ({rawData.coordinates?.x?.[selectedPixel.x] ?? selectedPixel.x}, {rawData.coordinates?.y?.[selectedPixel.y] ?? selectedPixel.y})</span>}
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

                {/* Time Series Single Spectrum Tab */}
                {activeTab === 'pixel' && isTimeSeries && (
                  <div className="space-y-4">
                    <div className="flex gap-4">
                      <div>
                        <label className="text-xs text-gray-500">{t('timeIndex')}</label>
                        <input type="number" min="0" max={(rawData.shape?.[0] || 1) - 1} value={selectedSeriesIndex ?? 0}
                          onChange={e => setSelectedSeriesIndex(Math.max(0, Math.min((rawData.shape?.[0] || 1) - 1, parseInt(e.target.value) || 0)))}
                          className="w-24 px-2 py-1 text-xs bg-black/30 border border-white/10 rounded text-gray-200 ml-2" />
                      </div>
                      {selectedSeriesIndex == null && (
                        <span className="text-xs text-gray-600 self-end">{t('selectTimeHint')}</span>
                      )}
                      {selectedSeriesIndex != null && <span className="text-xs text-gray-500 self-end">{t(rawData.coordinates?.time_kind === 'time' ? rawData.coordinates?.time_unit === 's' ? 'timeSeconds' : 'timeCoordinate' : 'timeIndex')}: {rawData.coordinates?.time?.[selectedSeriesIndex] ?? selectedSeriesIndex}{rawData.coordinates?.time_labels?.[selectedSeriesIndex] && ` · ${rawData.coordinates.time_labels[selectedSeriesIndex]}`}</span>}
                    </div>
                    <PixelSpectrum
                      wavenumber={rawSeriesSpectrum?.wavenumber || rawData.wavenumber}
                      pixelX={selectedSeriesIndex ?? 0}
                      pixelY={0}
                      rawSpectrum={rawSeriesSpectrum?.intensity}
                      processedSpectrum={processedSeriesSpectrum?.intensity}
                      processedWavenumber={processedSeriesSpectrum?.wavenumber}
                      title={`${t('spectrumAtTime')} ${rawData.coordinates?.time?.[selectedSeriesIndex] ?? selectedSeriesIndex ?? 0}`}
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
            <span>{t(isImaging ? 'spatialPoints' : 'timePoints')}: {isImaging ? (rawData.shape?.[0] || 1) * (rawData.shape?.[1] || 1) : rawData.shape?.[0]}</span>
            <span>{t('range')}: {Math.min(...rawData.wavenumber).toFixed(1)} – {Math.max(...rawData.wavenumber).toFixed(1)} cm⁻¹</span>
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
          cutRange={cutRange}
        />
      </ControlDock>

      <input ref={fileInputRef} type="file" accept=".txt" onChange={handleFileUpload} className="hidden" />
    </div>
  );
}
