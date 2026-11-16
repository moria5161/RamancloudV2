import React, { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { Activity, Atom, Download, Pencil, Play, RotateCcw, Upload, Zap } from 'lucide-react';
import { usePreferences } from '../i18n';
import ControlDock from '../components/ControlDock';
import WorkspaceFeedback from '../components/WorkspaceFeedback';
import useWorkspaceTask from '../hooks/useWorkspaceTask';
import { requestErrorDetail } from '../utils/requestError';

const MoleculeViewer = lazy(() => import('../components/MoleculeViewer'));
const PredictionChart = lazy(() => import('../components/PredictionChart'));
import { API_BASE } from '../utils/apiBase';

function saveText(text, filename) {
  const url = URL.createObjectURL(new Blob([text], { type: 'text/plain;charset=utf-8' }));
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export default function SpectrumStructure() {
  const { t, language } = usePreferences();
  const isZh = language === 'zh';
  const [direction, setDirection] = useState('structure2spectrum');
  const [source, setSource] = useState('demo');
  const [demo, setDemo] = useState('benzene');
  const [smiles, setSmiles] = useState('CCCO');
  const [file, setFile] = useState(null);
  const [result, setResult] = useState(null);
  const [conformer, setConformer] = useState(null);
  const [loadingConformer, setLoadingConformer] = useState(false);
  const [conformerError, setConformerError] = useState(null);
  const [previewRevision, setPreviewRevision] = useState(0);
  const [view, setView] = useState('conformer');
  const [editorReady, setEditorReady] = useState(false);
  const [editorMounted, setEditorMounted] = useState(false);
  const frame = useRef(null);
  const pending = useRef(new Map());
  const initialSmiles = useRef(smiles);
  const currentSource = useRef(source);
  currentSource.current = source;
  const previewRequest = useRef(null);
  const inputRevision = useRef(0);
  const task = useWorkspaceTask(t);
  const predictionMode = direction === 'structure2spectrum';
  const inputReady = source !== 'drawing' || editorReady;

  const invalidateInput = () => {
    inputRevision.current += 1;
    previewRequest.current?.abort();
    setResult(null);
    setConformer(null);
    setConformerError(null);
    task.setError(null);
    setView(current => current === 'editor' ? current : 'conformer');
  };

  useEffect(() => {
    const receive = event => {
      if (event.origin !== window.location.origin || event.source !== frame.current?.contentWindow || event.data?.channel !== 'ramancloud-structure') return;
      const message = event.data;
      if (message.type === 'initialized') {
        frame.current.contentWindow.postMessage({ channel: 'ramancloud-structure', type: 'set-smiles', smiles: initialSmiles.current }, window.location.origin);
      } else if (message.type === 'ready') {
        setEditorReady(true);
      } else if (message.type === 'changed') {
        if (currentSource.current === 'drawing') {
          invalidateInput();
          setPreviewRevision(current => current + 1);
        }
      } else if (message.type === 'smiles') {
        const request = pending.current.get(message.requestId);
        if (!request) return;
        clearTimeout(request.timer);
        pending.current.delete(message.requestId);
        if (message.error) request.reject(new Error(message.error));
        else request.resolve(message.smiles);
      } else if (message.type === 'error') {
        task.setError(String(message.error));
      }
    };
    window.addEventListener('message', receive);
    return () => {
      window.removeEventListener('message', receive);
      pending.current.forEach(request => { clearTimeout(request.timer); request.reject(new Error('Editor closed')); });
      pending.current.clear();
    };
  }, []);

  const getDrawnSmiles = useCallback(() => new Promise((resolve, reject) => {
    const requestId = crypto.randomUUID();
    const timer = setTimeout(() => {
      pending.current.delete(requestId);
      reject(new Error('Molecular editor did not respond. Please retry.'));
    }, 15000);
    pending.current.set(requestId, { resolve, reject, timer });
    frame.current.contentWindow.postMessage({ channel: 'ramancloud-structure', type: 'get-smiles', requestId }, window.location.origin);
  }), []);

  const inputForm = useCallback(async () => {
    const form = new FormData();
    form.append('source', source);
    if (source === 'demo') form.append('demo', demo);
    else if (source === 'xyz') form.append('file', file);
    else form.append('smiles', source === 'drawing' ? await getDrawnSmiles() : smiles);
    return form;
  }, [source, demo, file, smiles, getDrawnSmiles]);

  useEffect(() => {
    setResult(null);
    setConformer(null);
    setConformerError(null);
    const available = (source !== 'xyz' || file) && (source !== 'smiles' || smiles.trim()) && inputReady;
    setLoadingConformer(Boolean(available));
    if (!available) return;
    const controller = new AbortController();
    previewRequest.current = controller;
    // Wait for typing/drawing to pause, and discard results for superseded inputs.
    const timer = setTimeout(async () => {
      try {
        const form = await inputForm();
        if (controller.signal.aborted) return;
        for (let attempt = 0; attempt < 3 && !controller.signal.aborted; attempt += 1) {
          try {
            const { data } = await axios.post(`${API_BASE}/structure/conformer`, form, { signal: controller.signal, timeout: 60000 });
            if (!controller.signal.aborted) setConformer(data);
            break;
          } catch (error) {
            if (error.response?.status !== 429 || attempt === 2) throw error;
            await new Promise(resolve => setTimeout(resolve, 2000));
          }
        }
      } catch (error) {
        if (!controller.signal.aborted) {
          const detail = await requestErrorDetail(error);
          if (!controller.signal.aborted) setConformerError(detail || error.message);
        }
      } finally {
        if (!controller.signal.aborted) setLoadingConformer(false);
      }
    }, source === 'smiles' || source === 'drawing' ? 700 : 0);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [inputForm, source, file, smiles, inputReady, previewRevision]);

  const resetResult = () => { setResult(null); setView('conformer'); task.setError(null); };
  const changeSource = value => {
    setSource(value);
    invalidateInput();
    setView('conformer');
    if (value === 'drawing') {
      initialSmiles.current = smiles;
      setEditorMounted(true);
    }
  };

  const predict = () => task.run('predictingSpectrum', async () => {
    const revision = inputRevision.current;
    const form = await inputForm();
    form.append('share_data', 'true');
    const { data } = await axios.post(`${API_BASE}/structure/predict`, form, { timeout: 180000 });
    if (revision !== inputRevision.current) return;
    setResult(data);
    setView('spectrum');
    if (data.data_sharing?.status === 'failed') task.setError(t('archiveFailed'));
  });

  const molecule = result?.molecule || conformer?.molecule;
  const canPredict = predictionMode && !task.busy && !loadingConformer && !!conformer;
  const tabs = [
    ...(source === 'drawing' ? [['editor', Pencil, t('structureEditor')]] : []),
    ['conformer', Atom, t('conformer')],
    ['spectrum', Activity, t('predictedSpectrum')],
  ];

  return <div className="flex h-full min-w-0 relative">
    <div className="flex-1 min-w-0 flex flex-col overflow-hidden">
      <header className="workspace-toolbar glass border-b border-white/5 px-5 py-3 flex items-center gap-3">
        <Atom className="w-4 h-4 shrink-0 text-indigo-400" />
        <h1 className="text-sm font-semibold text-gray-200">{t('structureWorkspace')}</h1>
      </header>
      <div className="structure-module-tabs border-b border-white/5 px-4 py-3" role="tablist" aria-label={t('spectrumStructure')}>
        {['spectrum2structure', 'structure2spectrum'].map(value => <button key={value} type="button" role="tab" aria-selected={direction === value}
          className={`structure-tab ${direction === value ? 'is-active' : ''}`} disabled={task.busy}
          onClick={() => setDirection(value)}>{value}</button>)}
      </div>
      {!predictionMode && <div className="flex-1 flex flex-col items-center justify-center gap-3 px-6 text-center">
        <h2 className="text-xl font-semibold text-gray-200">spectrum2structure</h2>
        <span className="text-sm text-indigo-400">{t('comingSoon')}</span>
        <p className="text-sm text-gray-500">{t('spectrumStructurePending')}</p>
      </div>}
      <div className={`flex-1 min-h-0 flex-col ${predictionMode ? 'flex' : 'hidden'}`}>
        <div className="structure-view-tabs flex flex-wrap items-center gap-2 px-4 py-3 border-b border-white/5" role="tablist" aria-label={isZh ? '结果视图' : 'Result views'}>
          {tabs.map(([id, Icon, label]) => <button key={id} role="tab" type="button" aria-selected={view === id} disabled={id === 'spectrum' && !result}
            className={`structure-tab ${view === id ? 'is-active' : ''}`} onClick={() => setView(id)}><Icon className="w-4 h-4" />{label}</button>)}
          {molecule && <span className="ml-auto text-xs text-gray-500">{molecule.formula} · {t('atomCount')}: {molecule.atoms.length}</span>}
        </div>
        <div className="structure-visual-surface flex-1 min-h-0 relative overflow-auto">
          {editorMounted && <iframe ref={frame} hidden={source !== 'drawing' || view !== 'editor'}
            title={t('structureEditor')} src={`${import.meta.env.BASE_URL}structure-editor.html`}
            className="structure-editor-frame" />}
          {view !== 'editor' && (molecule ? <Suspense fallback={<div className="h-full grid place-items-center text-gray-500 text-sm">{t('loadingWorkspace')}</div>}>
            {view === 'conformer' ? <MoleculeViewer molecule={molecule} /> : result && <PredictionChart result={result} />}
          </Suspense> : <div className="h-full min-h-64 flex flex-col items-center justify-center gap-3 px-6 text-sm text-gray-500">
            <p role={conformerError ? 'alert' : 'status'}>{loadingConformer || (source === 'drawing' && !editorReady) ? t('loadingConformer') : conformerError || t('enterMolecule')}</p>
            {conformerError && <button type="button" onClick={() => setPreviewRevision(current => current + 1)} className="liquid-button flex items-center gap-2 rounded-lg px-3 py-2"><RotateCcw className="w-4 h-4" />{t('retry')}</button>}
          </div>)}
        </div>
      </div>
    </div>

    <ControlDock>
      <div className="glass h-full flex flex-col border-l border-white/5">
        <div className="p-4 border-b border-white/5 flex items-center gap-2 pr-12">
          <Zap className="w-4 h-4 text-indigo-400" /><h2 className="text-sm font-semibold text-gray-200">{t('controls')}</h2>
        </div>
        {predictionMode ? <>
          <fieldset disabled={task.busy} className="flex-1 min-h-0 overflow-y-auto p-4 space-y-5">
            <label className="block text-xs text-gray-400 space-y-2">
              <span>{t('structureInput')}</span>
              <select aria-label={t('structureInput')} className="w-full bg-black/20 border border-white/10 rounded-lg p-2 text-sm text-gray-200" value={source} onChange={event => changeSource(event.target.value)}>
                <option value="demo">{t('showStructureDemo')}</option><option value="smiles">{t('enterSmiles')}</option>
                <option value="xyz">{t('uploadXyz')}</option><option value="drawing">{t('drawMolecule')}</option>
              </select>
            </label>
            {source === 'demo' && <label className="block text-xs text-gray-400 space-y-2"><span>{t('structureDemo')}</span>
              <select aria-label={t('structureDemo')} className="w-full bg-black/20 border border-white/10 rounded-lg p-2 text-sm text-gray-200" value={demo} onChange={event => { setDemo(event.target.value); invalidateInput(); }}>
                <option value="benzene">{t('benzeneDemo')}</option><option value="caffeine">{t('caffeineDemo')}</option>
              </select></label>}
            {source === 'smiles' && <label className="block text-xs text-gray-400 space-y-2"><span>{t('smilesInput')}</span>
              <textarea rows={4} maxLength={4096} spellCheck={false} className="w-full resize-y bg-black/20 border border-white/10 rounded-lg p-2 text-sm font-mono text-gray-200" value={smiles} onChange={event => { setSmiles(event.target.value); invalidateInput(); }} />
            </label>}
            {source === 'xyz' && <label className="block text-xs text-gray-400 space-y-2"><span className="flex items-center gap-2"><Upload className="w-3.5 h-3.5" />{t('xyzInput')}</span>
              <input type="file" accept=".xyz" className="w-full text-xs" onChange={event => {
                const selected = event.target.files?.[0] || null;
                invalidateInput();
                if (selected?.size > 256 * 1024) { task.setError(isZh ? 'XYZ 文件不能超过 256 KiB。' : 'XYZ files must not exceed 256 KiB.'); setFile(null); event.target.value = ''; }
                else setFile(selected);
              }} />
              <span className="block break-all">{file?.name}</span>
            </label>}
            {source === 'drawing' && <button type="button" onClick={() => setView('editor')} className="liquid-button flex w-full items-center justify-center gap-2 rounded-lg py-2 text-sm text-indigo-400"><Pencil className="w-4 h-4" />{t('structureEditor')}</button>}
            <dl className="border-t border-white/10 pt-4 space-y-2 text-xs text-gray-500">
              <div className="flex justify-between gap-3"><dt>{isZh ? '波数范围' : 'Wavenumber range'}</dt><dd>500–4000 cm⁻¹</dd></div>
              <div className="flex justify-between gap-3"><dt>{isZh ? '激发波长' : 'Laser wavelength'}</dt><dd>532 nm</dd></div>
              <div className="flex justify-between gap-3"><dt>{isZh ? '温度' : 'Temperature'}</dt><dd>298 K</dd></div>
            </dl>
          </fieldset>
          <div className="p-4 border-t border-white/5 space-y-3">
            <button type="button" disabled={!canPredict} onClick={predict} className="liquid-button w-full flex items-center justify-center gap-2 rounded-lg py-3 text-sm font-semibold text-indigo-400"><Play className="w-4 h-4" />{t('predictSpectrum')}</button>
            {result && <>
              <p className="text-xs text-gray-500">{t('processingComplete')} · {result.elapsed_seconds} s</p>
              <button disabled={task.busy} className="liquid-button w-full flex items-center justify-center gap-2 py-2 rounded-lg text-sm text-gray-300" onClick={() => saveText(result.wavenumber.map((x, i) => `${x}\t${result.intensity[i]}`).join('\n') + '\n', result.filename)}><Download className="w-4 h-4" />{t('downloadPrediction')}</button>
            </>}
            {molecule && <button disabled={task.busy} className="liquid-button w-full flex items-center justify-center gap-2 py-2 rounded-lg text-sm text-gray-300" onClick={() => saveText(molecule.xyz, (result || conformer).filename.replace(/\.txt$/, '.xyz'))}><Download className="w-4 h-4" />{t('downloadConformer')}</button>}
            {result && <button type="button" disabled={task.busy} onClick={resetResult} className="w-full flex items-center justify-center gap-2 py-2 text-xs text-gray-500"><RotateCcw className="w-3.5 h-3.5" />{t('reset')}</button>}
          </div>
        </> : <div className="p-4 text-sm text-gray-500">{t('comingSoon')}</div>}
      </div>
    </ControlDock>
    <WorkspaceFeedback task={task} />
  </div>;
}
