import { API_BASE } from '../apiBase';
import { systemText, localize } from '../locale.js';
import { useQAExecutionInput } from '../components/qaExecution';
import {Link} from 'react-router-dom';
import {NewAnalysisButton} from '../components/AnalysisWorkspaces';
import React, { useState, useCallback, useEffect, useRef, useMemo } from 'react';
import { Upload, AlertCircle, Layers, Image, Activity, Crosshair, Map, X } from 'lucide-react';
import SpectralChart from '../components/SpectralChart';
import { ImagingHeatmap, PixelSpectrum, CompareImaging, TimeSeriesHeatmap, CompareTimeSeriesHeatmap } from '../components/HyperspectralChart';
import ControlPanel from '../components/ControlPanel';
import TSHIResults from '../components/TSHIResults';
import ImportReport, { SPECTRAL_ACCEPT } from '../components/ImportReport';
import './hyperspectral.css';
import usePlotHeight from '../components/usePlotHeight';
import axiosClient from 'axios';
import { apiErrorMessage, useAuth } from '../auth';
import { usePreferences } from '../i18n';


const DEMOS = ['imaging_horiba', 'timeseries_horiba'];

const TABS = [
  { id: 'imaging', labelKey: 'imaging', icon: Map },
  { id: 'spectrum', labelKey: 'avgSpectrum', icon: Activity },
  { id: 'pixel', labelKey: 'singlePixel', icon: Crosshair },
];

export default function HyperspectralProcessing() {
  const { t } = usePreferences();
  const { token } = useAuth();
  const axios = useMemo(() => axiosClient.create({
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  }), [token]);
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
  const [selectedSeriesIndex, setSelectedSeriesIndex] = useState(null);
  const [rawPixelSpectrum, setRawPixelSpectrum] = useState(null);
  const [processedPixelSpectrum, setProcessedPixelSpectrum] = useState(null);
  const [rawSeriesSpectrum, setRawSeriesSpectrum] = useState(null);
  const [processedSeriesSpectrum, setProcessedSeriesSpectrum] = useState(null);
  const [uploadInstrument, setUploadInstrument] = useState('auto');
  const [uploadMode, setUploadMode] = useState('imaging');
  const [uploadFormat, setUploadFormat] = useState('auto');
  const [matLayout, setMatLayout] = useState('auto');
  const [matHeight, setMatHeight] = useState('');
  const [matWidth, setMatWidth] = useState('');
  const [pixelOrder, setPixelOrder] = useState('F');
  const [downloadFormat, setDownloadFormat] = useState('mat');
  const [bm3dAvailable, setBm3dAvailable] = useState(false);
  const fileInputRef = useRef(null);
  const sliceTimerRef = useRef(null);
  const sliceRequestRef = useRef(0);
  const replayStepsRef = useRef(null);
  const [plotRef, plotHeight] = usePlotHeight();

  useEffect(() => {
    const abort = new AbortController();
    axios.get(`${API_BASE}/health`, { signal: abort.signal }).then(({ data }) => setBm3dAvailable(!!data.data?.tshi?.bm3d_available)).catch(() => {});
    return () => { abort.abort(); clearTimeout(sliceTimerRef.current); sliceRequestRef.current += 1; };
  }, [axios]);

  useEffect(() => {
    const replay = localStorage.getItem('ramancloud_replay_hyperspectral');
    if (!replay) return;
    try {
      const payload = JSON.parse(replay);
      replayStepsRef.current = (payload.steps || []).map(step => ({ ...step, id: crypto.randomUUID() }));
      setSteps(replayStepsRef.current);
      showError(t('historyParamsLoaded'));
    } catch (event) {
      showError('Failed to load history parameters.');
    } finally {
      localStorage.removeItem('ramancloud_replay_hyperspectral');
    }
  }, [t]);

  const hasData = rawData !== null;
  const isImaging = mode === 'imaging';
  const isTimeSeries = mode === 'time_series';

  const showError = (msg) => setError(msg);
  const fetchSlice = useCallback(async (datasetId, value) => {
    if (!datasetId || value == null) return null;
    const { data: res } = await axios.get(`${API_BASE}/hyperspectral-slice/${datasetId}`, {
      params: { wavenumber_value: value },
    });
    return res.code === 0 ? res.data : null;
  }, [axios]);

  // Load demo hyperspectral data
  const loadDemo = useCallback(async (name) => {
    if (!name) return;
    sliceRequestRef.current += 1;
    clearTimeout(sliceTimerRef.current);
    setIsProcessing(true);
    try {
      setError(null);
      const { data: res } = await axios.get(`${API_BASE}/demo-hyperspectral/${name}`);
      if (res.code === 0) {
        setRawData(res.data);
        setMode(res.data.mode);
        setFileName(res.data.filename);
        const wn = res.data.wavenumber;
        setMeanSpectrum({ wavenumber: wn, intensity: res.data.mean_spectrum });
        setProcessedMean(null);
        setProcessedData(null);
        setSelectedPixel(null);
        setSelectedSeriesIndex(res.data.mode === 'time_series' ? 0 : null);
        setRawPixelSpectrum(null);
        setProcessedPixelSpectrum(null);
        setRawSeriesSpectrum(null);
        setProcessedSeriesSpectrum(null);
        setCutRange([Math.min(...wn), Math.max(...wn)]);
        setSelectedWN(res.data.preview_wavenumber ?? Math.round((Math.min(...wn) + Math.max(...wn)) / 2));
        setSteps(replayStepsRef.current || []);
        replayStepsRef.current = null;
        setActiveTab('imaging');
      } else {
        showError(res.msg);
      }
    } catch (e) {
      showError(apiErrorMessage(e, '无法载入高光谱示例。'));
    } finally {
      setIsProcessing(false);
    }
  }, [axios]);

  const handleFileUpload = useCallback(async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    sliceRequestRef.current += 1;
    clearTimeout(sliceTimerRef.current);
    setIsProcessing(true);
    try {
      setError(null);
      const formData = new FormData();
      formData.append('file', file);
      formData.append('instrument', uploadInstrument);
      formData.append('mode', uploadMode);
      if (matHeight) formData.append('height', matHeight);
      if (matWidth) formData.append('width', matWidth);
      formData.append('layout', matLayout);
      formData.append('pixel_order', pixelOrder);

      const { data: res } = await axios.post(`${API_BASE}/upload-hyperspectral`, formData);
      if (res.code === 0) {
        setRawData(res.data);
        setMode(res.data.mode);
        setFileName(res.data.filename);
        const wn = res.data.wavenumber;
        setMeanSpectrum({ wavenumber: wn, intensity: res.data.mean_spectrum });
        setProcessedMean(null);
        setProcessedData(null);
        setSelectedPixel(null);
        setSelectedSeriesIndex(res.data.mode === 'time_series' ? 0 : null);
        setRawPixelSpectrum(null);
        setProcessedPixelSpectrum(null);
        setRawSeriesSpectrum(null);
        setProcessedSeriesSpectrum(null);
        setCutRange([Math.min(...wn), Math.max(...wn)]);
        setSelectedWN(res.data.preview_wavenumber ?? Math.round((Math.min(...wn) + Math.max(...wn)) / 2));
        setSteps(replayStepsRef.current || []);
        replayStepsRef.current = null;
        setActiveTab('imaging');
      } else {
        showError(res.msg);
      }
    } catch (e) {
      showError(apiErrorMessage(e, '无法上传高光谱数据。'));
    } finally {
      setIsProcessing(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  }, [axios, uploadInstrument, uploadMode, matHeight, matWidth, matLayout, pixelOrder]);

  const processWithSteps = useCallback(async (pipeline) => {
    if (!rawData?.dataset_id && !rawData?.spectra) throw new Error('Load a dataset first.');
    sliceRequestRef.current += 1;
    clearTimeout(sliceTimerRef.current);
    setIsProcessing(true);
    setError(null);
    try {
      const pipelineSteps = pipeline.map(s => ({ type: s.type, method: s.method, params: s.params }));

      const { data: res } = await axios.post(`${API_BASE}/process-hyperspectral`, {
        wavenumber: rawData.wavenumber,
        dataset_id: rawData.dataset_id,
        spectra: rawData.spectra,
        shape: rawData.shape,
        mode: rawData.mode,
        steps: pipelineSteps,
        save_history: true,
        preview_wavenumber: selectedWN,
        source_name: fileName || rawData.filename || 'hyperspectral',
        title: `${fileName || rawData.filename || 'Hyperspectral'} analysis`,
      });

      if (res.code === 0) {
        setProcessedMean({ wavenumber: res.data.wavenumber, intensity: res.data.mean_spectrum });
        setProcessedData(res.data);
        const center = res.data.preview_wavenumber;
        setSelectedWN(center);
        setActiveTab(res.data.history?.some(item => item.method === 'tshi') ? 'tshi' : 'imaging');
        setProcessedPixelSpectrum(null);
        setProcessedSeriesSpectrum(null);
        if (rawData.mode === 'imaging' && rawData.dataset_id && center !== rawData.preview_wavenumber) {
          try {
            const rawSlice = await fetchSlice(rawData.dataset_id, center);
            if (rawSlice) setRawData(prev => ({ ...prev, preview: rawSlice.preview, preview_wavenumber: rawSlice.wavenumber }));
          } catch {
            showError('处理已完成。请重新选择波数以刷新原始成像。');
          }
        }
        return res.data.analysis_run;
      } else {
        throw new Error(res.msg || '高光谱处理失败。');
      }
    } catch (e) {
      showError(apiErrorMessage(e, e.response ? '高光谱处理失败。' : e.message || '高光谱处理失败。'));
      throw e;
    } finally {
      setIsProcessing(false);
    }
  }, [axios, rawData, fileName, selectedWN, fetchSlice]);

  const handleProcess = useCallback(async () => {
    try { await processWithSteps(steps); } catch { /* The workspace already shows the error. */ }
  }, [processWithSteps, steps]);

  const handleDownload = useCallback(async () => {
    if (!processedMean) return;
    try {
      const format = isImaging ? downloadFormat : 'txt';
      const name = `processed_${(fileName || 'hyperspectral').replace(/\.[^.]+$/, '')}.${format}`;
      const { data: res } = await axios.post(
        `${API_BASE}/download`,
        processedData?.processed_dataset_id || processedData?.spectra
          ? {
              wavenumber: processedMean.wavenumber,
              dataset_id: processedData.processed_dataset_id,
              spectra: processedData.spectra,
              shape: processedData.shape,
              mode: mode,
              filename: name,
              format,
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
      a.href = url; a.download = name; a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) { showError(apiErrorMessage(e, '无法下载高光谱结果。')); }
  }, [axios, processedMean, processedData, fileName, mode, isImaging, downloadFormat]);

  const handleReset = () => {
    sliceRequestRef.current += 1;
    clearTimeout(sliceTimerRef.current);
    setSelectedWN(rawData?.preview_wavenumber ?? null);
    setProcessedMean(null);
    setProcessedData(null);
    setProcessedPixelSpectrum(null);
    setProcessedSeriesSpectrum(null);
    setSteps([]);
    setActiveTab('imaging');
  };

  const handleHeatmapClick = useCallback((event) => {
    if (!event.points?.length) return;
    const pt = event.points[0];
    if (isTimeSeries) {
      setSelectedSeriesIndex(Math.round(pt.y));
      setActiveTab('pixel');
      return;
    }
    const scale = rawData?.preview_scale || 1;
    setSelectedPixel({ x: Math.round(pt.x * scale), y: Math.round(pt.y * scale) });
    setActiveTab('pixel');
  }, [rawData?.preview_scale, isTimeSeries]);

  const handleWavenumberChange = useCallback((value) => {
    if (isProcessing) return;
    const axis = processedData?.wavenumber || rawData?.wavenumber || [];
    const actual = axis.length ? axis.reduce((best, wave) => Math.abs(wave - value) < Math.abs(best - value) ? wave : best) : value;
    setSelectedWN(actual);
    const request = ++sliceRequestRef.current;
    if (sliceTimerRef.current) clearTimeout(sliceTimerRef.current);
    sliceTimerRef.current = setTimeout(async () => {
      try {
        const [rawSlice, processedSlice] = await Promise.all([
          fetchSlice(rawData?.dataset_id, actual),
          fetchSlice(processedData?.processed_dataset_id, actual),
        ]);
        if (request !== sliceRequestRef.current) return;
        if (rawSlice) {
          setRawData(prev => prev ? { ...prev, preview: rawSlice.preview, preview_wavenumber: rawSlice.wavenumber } : prev);
        }
        if (processedSlice) {
          setProcessedData(prev => prev ? { ...prev, preview: processedSlice.preview, preview_wavenumber: processedSlice.wavenumber } : prev);
        }
      } catch (e) {
        if (request !== sliceRequestRef.current) return;
        setSelectedWN(processedData?.preview_wavenumber ?? rawData?.preview_wavenumber ?? actual);
        showError(apiErrorMessage(e, '无法读取成像切片。'));
      }
    }, 120);
  }, [rawData?.dataset_id, rawData?.wavenumber, rawData?.preview_wavenumber, processedData?.processed_dataset_id,
    processedData?.wavenumber, processedData?.preview_wavenumber, fetchSlice, isProcessing]);

  useEffect(() => {
    let cancelled = false;
    async function loadPixelSpectra() {
      if (!selectedPixel || !rawData?.dataset_id || !isImaging) return;
      try {
        const rawReq = axios.get(`${API_BASE}/hyperspectral-pixel/${rawData.dataset_id}`, {
          params: { x: selectedPixel.x, y: selectedPixel.y },
        });
        const processedReq = processedData?.processed_dataset_id
          ? axios.get(`${API_BASE}/hyperspectral-pixel/${processedData.processed_dataset_id}`, {
              params: { x: selectedPixel.x, y: selectedPixel.y },
            })
          : null;
        const [rawRes, processedRes] = await Promise.all([rawReq, processedReq]);
        if (cancelled) return;
        setRawPixelSpectrum(rawRes.data.code === 0 ? rawRes.data.data : null);
        setProcessedPixelSpectrum(processedRes?.data?.code === 0 ? processedRes.data.data : null);
      } catch (e) {
        if (!cancelled) showError(apiErrorMessage(e, '无法读取像素光谱。'));
      }
    }
    loadPixelSpectra();
    return () => { cancelled = true; };
  }, [axios, selectedPixel, rawData?.dataset_id, processedData?.processed_dataset_id, isImaging]);

  useEffect(() => {
    let cancelled = false;
    async function loadSeriesSpectra() {
      if (selectedSeriesIndex == null || !rawData?.dataset_id || !isTimeSeries) return;
      try {
        const rawReq = axios.get(`${API_BASE}/hyperspectral-spectrum/${rawData.dataset_id}`, {
          params: { index: selectedSeriesIndex },
        });
        const processedReq = processedData?.processed_dataset_id
          ? axios.get(`${API_BASE}/hyperspectral-spectrum/${processedData.processed_dataset_id}`, {
              params: { index: selectedSeriesIndex },
            })
          : null;
        const [rawRes, processedRes] = await Promise.all([rawReq, processedReq]);
        if (cancelled) return;
        setRawSeriesSpectrum(rawRes.data.code === 0 ? rawRes.data.data : null);
        setProcessedSeriesSpectrum(processedRes?.data?.code === 0 ? processedRes.data.data : null);
      } catch (e) {
        if (!cancelled) showError(apiErrorMessage(e, '无法读取时间序列光谱。'));
      }
    }
    loadSeriesSpectra();
    return () => { cancelled = true; };
  }, [axios, selectedSeriesIndex, rawData?.dataset_id, processedData?.processed_dataset_id, isTimeSeries]);

  const chartHeight = Math.max(160, plotHeight - 120);
  const sampledSeries = isTimeSeries && (
    rawData.preview_y?.length < rawData.shape?.[0] || rawData.preview_x?.length < rawData.shape?.[1]
  );
  const tshiRecords = processedData?.history?.filter(item => item.method === 'tshi' && item.details) || [];

  useQAExecutionInput('hyperspectral', { dataset_id: rawData?.dataset_id, settings: { steps, preview_wavenumber: selectedWN }, source_label: fileName }, [], isProcessing);

  const [dockOpen, setDockOpen] = useState(true);

  return (
    <div className="processing-workspace hyperspectral-workspace" data-qa-run={processedData?.analysis_run?.id || undefined} data-qa-state={JSON.stringify({ module: localize("高光谱处理"), filename: fileName, mode, status: isProcessing ? 'running' : processedData ? 'completed' : rawData ? 'loaded' : 'empty', displayed_steps: steps, selected_wavenumber: selectedWN, selected_pixel: selectedPixel ? (Array.isArray(selectedPixel) ? selectedPixel.slice(0,2) : {x:selectedPixel.x,y:selectedPixel.y}) : null, selected_band: cutRange, tab: activeTab, error: error ? String(error).slice(0, 200) : '' })}>
      <div className="hyper-page-content flex-1 flex flex-col min-w-0 relative">
        {/* Top bar */}
        <div className="hyperspectral-toolbar flex items-center justify-between px-5 py-3 border-b border-white/5 glass">
          <div className="flex items-center gap-3">
            <div className="w-2 h-2 rounded-full bg-purple-400 animate-pulse" />
            <h2 className="text-sm font-semibold text-gray-200">{t('hyperspectralWorkspace')}</h2>
            {mode && <span className="text-[10px] text-gray-500 bg-white/5 px-2 py-0.5 rounded uppercase">{mode}</span>}
          </div>
          <div className="flex items-center gap-2">
            <NewAnalysisButton className="hyperspectral-action" disabled={isProcessing} />
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
                {!!tshiRecords.length && <button onClick={() => setActiveTab('tshi')} aria-pressed={activeTab === 'tshi'}
                  className={`px-3 py-1.5 text-xs rounded-md ${activeTab === 'tshi' ? 'bg-indigo-500/20 text-indigo-400' : 'text-gray-500'}`}>{localize("TSHI 结果")}</button>}
              </div>
            )}
            <button disabled={isProcessing} onClick={() => fileInputRef.current?.click()}
              className="hyperspectral-action">
              <Upload className="w-3 h-3" /> {t('upload')}
            </button>
          </div>
        </div>

        <details className="hyper-import-settings"><summary>{localize('导入设置')} <span>{localize('自动识别 · 文件格式 / 数据模式 / 空间布局')}</span></summary>
        <fieldset disabled={isProcessing} className="hyperspectral-upload-options">
          <label><span>{localize("文件格式")}</span><select aria-label={localize("文件格式")} value={uploadFormat} onChange={e => setUploadFormat(e.target.value)}>
            <option value="auto">{localize("自动识别")}</option><option value="txt">{localize("文本 TXT/CSV/TSV")}</option>
            <option value="mat">MAT</option><option value="xlsx">Excel XLSX</option>
            <option value="wdf">Renishaw WDF</option><option value="jdx">JCAMP-DX</option>
          </select></label>
          <label><span>{localize("数据模式")}</span><select aria-label={localize("数据模式")} value={uploadMode} onChange={e => setUploadMode(e.target.value)}>
            <option value="imaging">{t('imaging')}</option><option value="time_series">{t('timeSeries')}</option>
          </select></label>
          <label><span>{localize("解析结构")}</span><select aria-label={localize("解析结构")} value={uploadInstrument} onChange={e => setUploadInstrument(e.target.value)}>
            <option value="auto">{localize("自动识别")}</option><option value="Horiba">{localize("Horiba 行矩阵")}</option>
            <option value="Nanophoton">Nanophoton</option><option value="Renishaw">{localize("Renishaw 无表头长表")}</option>
            <option value="columns">{localize("波数在第一列")}</option><option value="rows">{localize("波数在第一行")}</option>
          </select></label>
          <details><summary>{localize("空间布局 / MAT 参数")}</summary><div className="hyperspectral-layout-options">
            <label><span>{localize("MAT 布局")}</span><select aria-label={localize("MAT 布局")} value={matLayout} onChange={e => setMatLayout(e.target.value)}>
              <option value="auto">{localize("自动识别")}</option><option value="bands_pixels">{localize("波段 × 像素")}</option>
              <option value="pixels_bands">{localize("像素 × 波段")}</option><option value="rows_cols_bands">{localize("行 × 列 × 波段")}</option>
              <option value="bands_rows_cols">{localize("波段 × 行 × 列")}</option>
            </select></label>
            <label><span>{localize("二维矩阵图像行数")}</span><input type="number" min="1" max="4096" placeholder={localize("行数")} value={matHeight}
              onChange={e => setMatHeight(e.target.value)} /></label>
            <label><span>{localize("二维矩阵图像列数")}</span><input type="number" min="1" max="4096" placeholder={localize("列数")} value={matWidth}
              onChange={e => setMatWidth(e.target.value)} /></label>
            <label><span>{localize("二维像素排列")}</span><select aria-label={localize("二维像素排列")} value={pixelOrder} onChange={e => setPixelOrder(e.target.value)}>
              <option value="F">{localize("列优先（沿用源码）")}</option><option value="C">{localize("行优先")}</option>
            </select></label>
          </div></details>
        </fieldset></details>
        {error && <div role="alert" className="hyperspectral-error">
          <AlertCircle size={16} /><span>{systemText(error)}</span>
          <button type="button" title={localize("关闭提示")} aria-label={localize("关闭提示")} onClick={() => setError(null)}><X size={16} /></button>
        </div>}

        {/* Main content */}
        <div ref={plotRef} className="hyperspectral-main flex-1 min-h-0 p-4 overflow-auto">
          {!hasData ? (
            <div className="h-full flex items-center justify-center">
              <div className="text-center space-y-6 animate-fade-in">
                <div className="w-20 h-20 mx-auto rounded-2xl bg-gradient-to-br from-purple-500/20 to-pink-500/20 border border-purple-500/20 flex items-center justify-center">
                  <Layers className="w-10 h-10 text-purple-400" />
                </div>
                <div>
                  <h3 className="text-lg font-semibold text-gray-300">{t('loadHyperspectralData')}</h3>
                  <p className="text-sm text-gray-500 mt-1">{t('loadHyperspectralDataDesc')}</p>
                </div>
                <div className="flex gap-3 justify-center">
                  <button disabled={isProcessing} onClick={() => fileInputRef.current?.click()}
                    className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-gradient-to-r from-purple-600 to-pink-600 text-white text-sm font-medium hover:from-purple-500 hover:to-pink-500 transition-all shadow-lg shadow-purple-500/20">
                    <Upload className="w-4 h-4" /> {t('uploadFile')}
                  </button>
                  <button disabled={isProcessing} onClick={() => loadDemo('imaging_horiba')}
                    className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-white/5 text-gray-300 text-sm font-medium hover:bg-white/10 border border-white/5 transition-all">
                    <Image className="w-4 h-4" /> {t('imagingDemo')}
                  </button>
                  <button disabled={isProcessing} onClick={() => loadDemo('timeseries_horiba')}
                    className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-white/5 text-gray-300 text-sm font-medium hover:bg-white/10 border border-white/5 transition-all">
                    <Activity className="w-4 h-4" /> {t('timeSeriesDemo')}
                  </button>
                </div>
              </div>
            </div>
          ) : (
            <div className="h-full animate-fade-in space-y-4">
              <details className="hyper-quality-report"><summary>{localize('数据格式与质量检查')}</summary><ImportReport metadata={rawData.import_metadata} /></details>
              {/* Dataset info bar */}
              <div className="hyperspectral-data-info py-3 border-b border-white/5 flex flex-wrap items-center gap-4 text-xs text-gray-500">
                <Image className="w-4 h-4 text-purple-400" />
                <span>{t('shape')}: {rawData.shape?.join(' × ')}</span>
                <span>{t('spectralPoints')}: {rawData.wavenumber?.length}</span>
                <span>{t('file')}: {fileName}</span>
                {processedMean && (
                  <span className="px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 text-[10px]">{t('processed')}</span>
                )}
              </div>

              {/* Tab content */}
              <div className="flex-1" style={{ minHeight: 300 }}>
                {activeTab === 'tshi' && <TSHIResults records={tshiRecords} />}
                {/* Imaging Tab */}
                {activeTab === 'imaging' && isImaging && rawData.preview && (
                  processedData?.preview && rawData.preview_wavenumber === processedData.preview_wavenumber ? (
                    <CompareImaging
                      rawPreview={rawData.preview}
                      processedPreview={processedData.preview}
                      wavenumber={rawData.wavenumber}
                      processedWavenumber={processedData.wavenumber}
                      selectedWN={selectedWN}
                      onSelectWN={handleWavenumberChange}
                      onHeatmapClick={handleHeatmapClick}
                      height={chartHeight}
                    />
                  ) : (
                    <ImagingHeatmap
                      previewData={processedData?.preview || rawData.preview}
                      wavenumber={processedData?.wavenumber || rawData.wavenumber}
                      selectedWN={selectedWN}
                      onSelectWN={handleWavenumberChange}
                      onHeatmapClick={handleHeatmapClick}
                      title={processedData?.preview ? localize('处理后') : t('imaging')}
                      height={chartHeight}
                      colorscale="Jet"
                    />
                  )
                )}

                {/* Time Series Tab */}
                {activeTab === 'imaging' && sampledSeries && <p className="hyperspectral-data-info">{localize('热图为抽样预览，点击采集行可查看该位置的完整光谱。')}</p>}
                {activeTab === 'imaging' && isTimeSeries && (
                  processedData?.preview ? (
                    <CompareTimeSeriesHeatmap
                      rawData2D={rawData.preview}
                      processedData2D={processedData.preview}
                      rawWavenumber={rawData.preview_x || rawData.wavenumber}
                      processedWavenumber={processedData.preview_x || processedData.wavenumber}
                      rawIndices={rawData.preview_y}
                      processedIndices={processedData.preview_y}
                      title="Raw (top) vs Processed (bottom)"
                      height={chartHeight}
                      colorscale="Jet"
                      onHeatmapClick={handleHeatmapClick}
                    />
                  ) : (
                    <TimeSeriesHeatmap
                      data2D={rawData.preview}
                      wavenumber={rawData.preview_x || rawData.wavenumber}
                      indices={rawData.preview_y}
                      title="Time Series Heatmap"
                      height={chartHeight}
                      colorscale="Jet"
                      onHeatmapClick={handleHeatmapClick}
                    />
                  )
                )}

                {/* Average Spectrum Tab */}
                {activeTab === 'spectrum' && (
                  <SpectralChart
                    rawData={meanSpectrum}
                    processedData={processedMean}
                    cutRange={cutRange}
                    height={chartHeight}
                    showRaw={true}
                  />
                )}

                {/* Single Pixel Tab */}
                {activeTab === 'pixel' && isImaging && (
                  <div className="space-y-4">
                    <div className="flex gap-4">
                      <div>
                        <label className="text-xs text-gray-500">{t('pixelX')}</label>
                        <input type="number" value={selectedPixel?.x ?? 0}
                          onChange={e => setSelectedPixel(p => ({ ...p, x: parseInt(e.target.value) || 0 }))}
                          className="w-20 px-2 py-1 text-xs bg-black/30 border border-white/10 rounded text-gray-200 ml-2" />
                      </div>
                      <div>
                        <label className="text-xs text-gray-500">{t('pixelY')}</label>
                        <input type="number" value={selectedPixel?.y ?? 0}
                          onChange={e => setSelectedPixel(p => ({ ...p, y: parseInt(e.target.value) || 0 }))}
                          className="w-20 px-2 py-1 text-xs bg-black/30 border border-white/10 rounded text-gray-200 ml-2" />
                      </div>
                      {!selectedPixel && (
                        <span className="text-xs text-gray-600 self-end">{t('selectPixelHint')}</span>
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
                      height={chartHeight}
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
                          onChange={e => setSelectedSeriesIndex(parseInt(e.target.value) || 0)}
                          className="w-24 px-2 py-1 text-xs bg-black/30 border border-white/10 rounded text-gray-200 ml-2" />
                      </div>
                      {selectedSeriesIndex == null && (
                        <span className="text-xs text-gray-600 self-end">{t('selectTimeHint')}</span>
                      )}
                    </div>
                    <PixelSpectrum
                      wavenumber={rawSeriesSpectrum?.wavenumber || rawData.wavenumber}
                      pixelX={selectedSeriesIndex ?? 0}
                      pixelY={0}
                      rawSpectrum={rawSeriesSpectrum?.intensity}
                      processedSpectrum={processedSeriesSpectrum?.intensity}
                      processedWavenumber={processedSeriesSpectrum?.wavenumber}
                      title={`${t('spectrumAtTime')} ${selectedSeriesIndex ?? 0}`}
                      height={chartHeight}
                    />
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        <section className="hyper-bottom-dock" aria-label={localize('处理设置')}>
          <div className="hyper-dock-heading">
            <strong>{localize('处理设置')} <small>{steps.length} {t(steps.length === 1 ? 'stepSingular' : 'stepPlural')}</small></strong>
            <button type="button" aria-expanded={dockOpen} aria-controls="hyper-dock-body"
              onClick={() => setDockOpen(value => !value)}>{localize(dockOpen ? '收起参数 ⌄' : '展开参数 ⌃')}</button>
          </div>
          <div id="hyper-dock-body" className="hyper-dock-body" hidden={!dockOpen}>
        <ControlPanel horizontal hideActions
          steps={steps} onStepsChange={setSteps}
          onProcess={handleProcess} onDownload={handleDownload} onReset={handleReset}
          isProcessing={isProcessing} fileName={fileName} demoName={fileName ? '' : (rawData?.filename || '')}
          onDemoChange={loadDemo} demos={DEMOS}
          cutRange={cutRange} onCutRangeChange={setCutRange}
          tshiContext={{ isImaging, wavenumber: rawData?.wavenumber, shape: rawData?.shape, selectedWN, bm3dAvailable }}
          downloadFormat={downloadFormat} onDownloadFormatChange={setDownloadFormat} canDownload={!!processedData}
        />

          </div>
        <ControlPanel horizontal actionsOnly
          steps={steps} onStepsChange={setSteps}
          onProcess={handleProcess} onDownload={handleDownload} onReset={handleReset}
          isProcessing={isProcessing} fileName={fileName} demoName={fileName ? '' : (rawData?.filename || '')}
          onDemoChange={loadDemo} demos={DEMOS}
          cutRange={cutRange} onCutRangeChange={setCutRange}
          tshiContext={{ isImaging, wavenumber: rawData?.wavenumber, shape: rawData?.shape, selectedWN, bm3dAvailable }}
          downloadFormat={downloadFormat} onDownloadFormatChange={setDownloadFormat} canDownload={!!processedData}
        />

        </section>

        {/* Bottom info bar */}
        {hasData && (
          <div className="px-5 py-2 border-t border-white/5 flex flex-wrap items-center gap-4 text-xs text-gray-500">
            <span>{t('spectralPoints')}: {isImaging ? (rawData.shape?.[0] || 1) * (rawData.shape?.[1] || 1) : rawData.time_points || 'N/A'}</span>
            <span>{t('range')}: {rawData.wavenumber?.[0]?.toFixed(1)} – {rawData.wavenumber?.[rawData.wavenumber?.length - 1]?.toFixed(1)} cm⁻¹</span>
            {processedData?.analysis_run && <Link className="text-indigo-400" to={`/analysis-history?run=${encodeURIComponent(processedData.analysis_run.id)}${isImaging && selectedWN!=null ? `&wavenumber=${encodeURIComponent(selectedWN)}` : ''}`}>{localize("已保存分析记录")}</Link>}
          </div>
        )}
      </div>

      <input ref={fileInputRef} disabled={isProcessing} type="file" accept={uploadFormat === 'auto' ? SPECTRAL_ACCEPT : uploadFormat === 'txt' ? '.txt,.csv,.tsv,.dat,.asc,.xy,.prn' : uploadFormat === 'jdx' ? '.jdx,.dx' : `.${uploadFormat}`} onChange={handleFileUpload} className="hidden" />
    </div>
  );
}
