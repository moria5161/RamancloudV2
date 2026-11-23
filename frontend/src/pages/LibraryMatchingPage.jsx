import { API_BASE as BASE } from '../apiBase';
import { systemText, localize } from '../locale.js';
import { useQAExecutionInput } from '../components/qaExecution';
import {NewAnalysisButton,useWorkspaceList} from '../components/AnalysisWorkspaces';
import React, { useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import { Link, useSearchParams } from 'react-router-dom';
import { ArrowRight, Check, ChevronRight, Database, FileText, Info, Layers, Loader2, Search, Upload, Waves, X } from 'lucide-react';
import { apiErrorMessage, useAuth } from '../auth';
import { usePreferences } from '../i18n';
import { libraryName, librarySearchQuery } from '../libraryNames.js';
import SpectralChart from '../components/SpectralChart';
import ImportReport, { SPECTRAL_ACCEPT } from '../components/ImportReport';
import SpectrumImportConfirmation from '../components/SpectrumImportConfirmation';
import LibraryMatchResults from '../components/LibraryMatchResults';
import ModuleUploadHistory from '../components/ModuleUploadHistory';
import ModuleInputActions from '../components/ModuleInputActions';
import SavedAnalysisRecords from '../components/SavedAnalysisRecords';
import { moduleSpectrum } from '../components/moduleSpectrum';
import { hasBaseline, matchingSource } from './libraryMatching';
import './StructureGenerationPage.css';
import './LibraryMatchingPage.css';


export default function LibraryMatchingPage() {
  const { token } = useAuth();
  const { language, theme } = usePreferences();
  const txt = (zh, en) => language === 'zh' ? zh : en;
  const [search, setSearch] = useSearchParams();
  const requestedTask = search.get('workflow'), requestedVersion = search.get('version'), requestedJob = search.get('job');
  const api = useMemo(() => axios.create({ baseURL: BASE, headers: { Authorization: `Bearer ${token}` }, timeout: 30000 }), [token]);
  const fileRef = useRef(), sequence = useRef(0);
  const [config, setConfig] = useState(null), [tasks, setTasks] = useState([]);
  const [tab, setTab] = useState(requestedTask ? 'processed' : 'upload'), [task, setTask] = useState(null), [versionId, setVersionId] = useState('');
  const [source, setSource] = useState(null), [pending, setPending] = useState(null), [unitConfirmed, setUnitConfirmed] = useState(false);
  const [topK, setTopK] = useState(3), [preprocess, setPreprocess] = useState(true), [prepared, setPrepared] = useState(null), [validationError, setValidationError] = useState('');
  const [job, setJob] = useState(null), [jobs, setJobs] = useState([]), [busy, setBusy] = useState(false), [validating, setValidating] = useState(false), [error, setError] = useState('');
  const [query, setQuery] = useState(''), [materials, setMaterials] = useState(null);
  const active = ['queued', 'running'].includes(job?.status), locked = busy || active || !!pending;
  const completed = task?.versions.filter(v => v.status === 'completed') || [];

  useWorkspaceList(api,'/ai-workflows',setTasks,setError);
  useEffect(() => {
    let cancelled = false;
    api.get('/library-matching/config').then(({ data }) => { if (!cancelled) setConfig(data); }).catch(err => { if (!cancelled) setError(apiErrorMessage(err)); });
    api.get('/library-matching/jobs').then(({ data }) => { if (!cancelled) setJobs(data); }).catch(() => {});
    return () => { cancelled = true; };
  }, [api]);
  useEffect(() => {
    let cancelled = false;
    const timer = setTimeout(() => api.get('/library-matching/catalog', { params: { q: librarySearchQuery(query) } }).then(({ data }) => { if (!cancelled) setMaterials(data); }).catch(() => {}), 200);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [query, api]);
  function chooseSource(input) {
    setSource(input); setJob(null); setPrepared(null); setUnitConfirmed(input.kind === 'reference');
    setPreprocess(input.kind !== 'reference' && !hasBaseline(input.steps)); setError('');
  }
  async function loadWorkflow(id, vid, manual = false) {
    const currentSequence = ++sequence.current;
    setBusy(true); setError(''); setPending(null);
    try {
      const current = (await api.get(`/ai-workflows/${encodeURIComponent(id)}`)).data;
      const versions = current.versions.filter(v => v.status === 'completed');
      if (!versions.length) throw new Error(txt('请先完成并保存该光谱的预处理。', 'Complete and save preprocessing first.'));
      const selected = vid || versions.at(-1).id;
      const version = (await api.get(`/ai-workflows/${encodeURIComponent(id)}/versions/${encodeURIComponent(selected)}`)).data;
      if (currentSequence !== sequence.current) return;
      chooseSource(matchingSource(current, version)); setTask(current); setVersionId(selected);
      if (manual) setSearch({}, { replace: true });
    } catch (err) { if (currentSequence === sequence.current) setError(apiErrorMessage(err, err.message)); }
    finally { if (currentSequence === sequence.current) setBusy(false); }
  }
  useEffect(() => {
    if (requestedTask) { setTab('processed'); loadWorkflow(requestedTask, requestedVersion); }
    return () => { sequence.current += 1; };
  }, [requestedTask, requestedVersion, api]);
  useEffect(() => {
    if (!requestedJob) return;
    let cancelled = false;
    api.get(`/library-matching/jobs/${encodeURIComponent(requestedJob)}`).then(({ data }) => {
      if (cancelled) return;
      const snapshot = data.input.source;
      setJob(data); setSource({ name: data.source_name, ...snapshot, kind: snapshot.metadata?.kind === 'library_cache' ? 'reference' : snapshot.reference.version_id ? 'processed' : 'uploaded', reuse_job_id: data.id });
      setTask(null); setVersionId(''); setTopK(data.settings.top_k); setPreprocess(data.settings.preprocessing_mode === 'auto'); setUnitConfirmed(true);
    }).catch(err => { if (!cancelled) setError(apiErrorMessage(err)); });
    return () => { cancelled = true; };
  }, [requestedJob, api]);
  useEffect(() => {
    if (!active) return;
    let cancelled = false, timer;
    async function poll() {
      try {
        const { data } = await api.get(`/library-matching/jobs/${job.id}`);
        if (!cancelled) { setJob(data); if (['queued', 'running'].includes(data.status)) timer = setTimeout(poll, 1200); }
      } catch (err) { if (!cancelled) { setError(apiErrorMessage(err)); timer = setTimeout(poll, 5000); } }
    }
    timer = setTimeout(poll, 1000);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [job?.id, active, api]);
  function payload() { return { ...source?.reference, reuse_job_id: source?.reuse_job_id, unit_confirmed: unitConfirmed, top_k: topK, preprocessing_mode: preprocess ? 'auto' : 'prepared' }; }
  useEffect(() => {
    setPrepared(null); setValidationError('');
    if (!source || !unitConfirmed || !config?.ready) { setValidating(false); return; }
    let cancelled = false;
    setValidating(true);
    const timer = setTimeout(async () => {
      try { const { data } = await api.post('/library-matching/validate', payload()); if (!cancelled) setPrepared(data); }
      catch (err) { if (!cancelled) setValidationError(apiErrorMessage(err)); }
      finally { if (!cancelled) setValidating(false); }
    }, 250);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [source, unitConfirmed, topK, preprocess, config, api]);
  async function upload(file, confirmed = false, spectrumIndex) {
    if (!file) return;
    setBusy(true); setError('');
    try {
      const form = new FormData(); form.append('file', file); form.append('confirm_conversion', String(confirmed));
      if (spectrumIndex != null) form.append('spectrum_index', String(spectrumIndex));
      const { data } = await api.post('/library-matching/sources/upload', form);
      if (data.requires_confirmation) { setPending({ file, inspection: data }); return; }
      setPending(null); setTask(null); setVersionId('');
      chooseSource(moduleSpectrum(data, 'library-matching'));
      setSearch({}, { replace: true });
    } catch (err) { setError(apiErrorMessage(err)); }
    finally { setBusy(false); if (fileRef.current) fileRef.current.value = ''; }
  }
  async function example() {
    setBusy(true); setError('');
    try {
      const { data } = await api.get(`/library-matching/references/${config.example_class_id}`);
      chooseSource({ name: `${libraryName(data)} · ${txt('库内验证输入', 'In-library test input')}`, kind: 'reference', spectrum: { wavenumber: data.wavenumber, intensity: data.intensity }, steps: [], metadata: { kind: 'library_cache' }, reference: { reference_id: data.class_id } });
      setTask(null); setVersionId(''); setSearch({}, { replace: true });
    } catch (err) { setError(apiErrorMessage(err)); }
    finally { setBusy(false); }
  }
  async function match() {
    setBusy(true); setError('');
    try {
      const { data } = await api.post('/library-matching/jobs', payload());
      setJob(data); setJobs(old => [data, ...old.filter(v => v.id !== data.id)]); setSearch({ job: data.id }, { replace: true });
    } catch (err) { setError(apiErrorMessage(err)); }
    finally { setBusy(false); }
  }
  const sourceLabel = source?.kind === 'reference' ? txt('库内缓存 · 用于验证流程', 'Library cache · Workflow check') : source?.kind === 'processed' ? txt('已保存的预处理结果', 'Saved preprocessing result') : txt('原始上传', 'Original upload');

  useQAExecutionInput('library-matching', { source: source?.reuse_job_id ? { reuse_job_id: source.reuse_job_id, module: 'library-matching' } : source?.reference ? { ...source.reference, module: source.reference.module || 'library-matching' } : null, unit_confirmed: unitConfirmed, settings: { top_k: topK, preprocessing_mode: preprocess ? 'auto' : 'prepared' }, source_label: source?.name }, [], locked);

  return <div className="sg-workspace lm-workspace" data-qa-run={job?.analysis_run_id || undefined} data-qa-state={JSON.stringify({ module: localize("库匹配"), job_id: job?.id, status: job?.status, filename: source?.source_name || job?.source_name, source_kind: source?.kind, selected_settings: { topK, preprocess, unitConfirmed }, executed_settings: job?.settings, error: error?.slice(0, 200), candidates: job?.result?.candidates?.slice(0, 5).map(c => ({ name: c.name, score: c.model_score, class_id: c.class_id })) })}>
    <header className="sg-header"><div><div className="sg-eyebrow">RAMANCLOUD <ChevronRight size={12} /> PEAKNET</div><h1><Database size={25} />{txt('库匹配', 'Library matching')}</h1><p>{txt("匹配库内物质，对比参考谱。", "Find library candidates and compare reference spectra.")}</p></div><span className="sg-service-state"><span />{!config ? txt('检查模型…', 'Checking model…') : config.ready ? txt('模型已安装', 'Model installed') : txt('模型未安装', 'Model not installed')}</span><NewAnalysisButton disabled={busy} txt={txt} /></header>
    <nav className="sg-flow" aria-label={txt('库匹配流程', 'Library matching workflow')}>{[['选择光谱', 'Choose spectrum', Waves], ['确认预处理', 'Confirm preparation', Layers], ['匹配与比对', 'Match and compare', Search]].map(([zh, en, Icon], i) => <div key={en} className={source && i === 0 ? 'is-complete' : ''}><span>{source && i === 0 ? <Check size={13} /> : i + 1}</span><Icon size={16} />{txt(zh, en)}{i < 2 && <ChevronRight size={15} className="sg-flow-arrow" />}</div>)}</nav>
    {error && <div className="sg-alert is-error" role="alert">{systemText(error)}<button onClick={() => setError('')} aria-label={txt('关闭错误', 'Dismiss error')}><X size={15} /></button></div>}
    {config && !config.ready && <div className="sg-model-note"><Info size={18} /><p>{systemText(config.message)}</p></div>}
    <div className="sg-layout lm-layout"><div className="sg-input-column">
      <section className="sg-panel"><div className="sg-panel-heading"><h2><span>01</span>{txt('输入光谱', 'Input spectrum')}</h2>{busy && <Loader2 size={16} className="sg-spin" />}</div>

        <div className="sg-source-tabs" role="tablist" aria-label={txt('库匹配光谱来源', 'Matching spectrum source')}><button role="tab" aria-selected={tab === 'upload'} disabled={locked} onClick={() => setTab('upload')}><Upload size={15} />{txt('本地上传', 'Upload')}</button><button role="tab" aria-selected={tab === 'processed'} disabled={locked} onClick={() => setTab('processed')}><Layers size={15} />{txt('预处理结果', 'Processed result')}</button></div>
        {tab === 'upload' ? <><input hidden type="file" ref={fileRef} accept={SPECTRAL_ACCEPT} onChange={e => upload(e.target.files?.[0])} /><button className="sg-upload" disabled={locked} onClick={() => fileRef.current?.click()}><Upload size={24} /><strong>{txt('上传待匹配光谱', 'Upload a spectrum to match')}</strong><span>TXT · CSV · XLSX · JCAMP · WDF · WXD · L6M · NPG</span></button></> : <div className="sg-source-selectors"><label>{txt('分析任务', 'Analysis task')}<select aria-label={txt('库匹配分析任务', 'Matching analysis task')} value={task?.id || ''} disabled={locked} onChange={e => e.target.value && loadWorkflow(e.target.value, null, true)}><option value="">{txt('选择已完成的预处理任务', 'Select a preprocessed task')}</option>{tasks.map(t => <option key={t.id} value={t.id}>{t.source_name}</option>)}</select></label><label>{txt('保存版本', 'Saved version')}<select value={versionId} aria-label={txt('库匹配输入版本', 'Matching input version')} disabled={locked || !completed.length} onChange={e => loadWorkflow(task.id, e.target.value, true)}><option value="">{txt('先选择任务', 'Choose a task first')}</option>{completed.map(v => <option key={v.id} value={v.id}>V{task.versions.findIndex(t => t.id === v.id) + 1} · {txt('已保存', 'Saved')}</option>)}</select></label></div>}
        {tab === 'upload' && <ModuleUploadHistory api={api} module="library-matching" revision={source?.reference.source_id} txt={txt} disabled={locked} onLoading={setBusy} onError={setError} onSelect={data => { setTask(null); setVersionId(''); chooseSource(moduleSpectrum(data, 'library-matching')); setSearch({}, { replace: true }); }} />}
        {pending && <SpectrumImportConfirmation inspection={pending.inspection} busy={busy} txt={txt} onConfirm={index => upload(pending.file, true, index)} onCancel={() => setPending(null)} />}
        {source && !pending && <div className="sg-selected-source"><div className="sg-file-heading"><FileText size={18} /><div><strong>{source.name}</strong><span>{sourceLabel}</span></div></div><div className="sg-spectrum"><SpectralChart rawData={source.spectrum} rawLabel={sourceLabel} height={205} dark={theme === 'dark'} showToolbar={false} /></div>{source.kind !== 'reference' && <details className="sg-import-details"><summary>{txt('查看导入与质量检查', 'Import and quality report')}</summary><ImportReport metadata={source.metadata} /></details>}<label className="sg-checkbox"><input type="checkbox" checked={unitConfirmed} disabled={locked} onChange={e => setUnitConfirmed(e.target.checked)} />{txt('确认横轴为拉曼位移 cm⁻¹', 'Confirm Raman shift in cm⁻¹')}</label><ModuleInputActions api={api} module="library-matching" source={source} txt={txt} disabled={locked} onError={setError} /></div>}
      </section>
      <section className="sg-panel"><div className="sg-panel-heading"><h2><span>02</span>{txt('匹配设置', 'Matching settings')}</h2><span className="sg-pill">PeakNet</span></div>
        <div className="lm-library-card"><Database size={21} /><div><strong>{txt('普识纳米光谱库', 'PERS Raman library')}</strong><span>2805 {txt('类物质', 'classes')} · 220–1800 cm⁻¹ · 750 {txt('点', 'points')}</span></div></div>
        <details className="lm-catalog"><summary>{txt('查看库内物质', 'Browse library materials')}</summary><label className="lm-search"><Search size={14} /><input aria-label={txt('搜索库内物质', 'Search library materials')} placeholder={txt('输入物质名称', 'Search material names')} value={query} onChange={e => setQuery(e.target.value)} /></label>{materials && <><small>{txt(`找到 ${materials.matched} 类，显示前 ${materials.items.length} 类`, `${materials.matched} classes found; showing ${materials.items.length}`)}</small><p className="sg-help">{txt('英文名称未核验的条目以库内类别编号显示。', 'Entries without a verified English name use their library class ID.')}</p><ul>{materials.items.map(item => <li key={item.class_id}>{libraryName(item)}</li>)}</ul></>}</details>
        <label className="sg-checkbox"><input type="checkbox" checked={preprocess} disabled={locked || source?.kind === 'reference'} onChange={e => setPreprocess(e.target.checked)} />{txt('按模型流程预处理（AirNet + PEER）', 'Use model preprocessing (AirNet + PEER)')}</label>
        <label>{txt('候选数量', 'Candidate count')}<select aria-label={txt('库匹配候选数量', 'Library candidate count')} value={topK} disabled={locked} onChange={e => setTopK(Number(e.target.value))}>{[3, 5, 10].map(k => <option key={k} value={k}>Top {k}</option>)}</select></label>
        {validating && <p className="sg-help" role="status">{txt('正在检查输入…', 'Checking input…')}</p>}{validationError && <p className="sg-field-error" role="alert">{systemText(validationError)}</p>}{prepared && <p className="sg-ready">{txt(`波段检查通过 · ${prepared.cropped.intensity.length} 个波段内点 → 750 点模型输入`, `Range checked · ${prepared.cropped.intensity.length} band points → 750 model points`)}</p>}{prepared?.warnings.map((warning, i) => <p key={i} className="sg-help">{systemText(warning)}</p>)}
        <div className="sg-generate-actions"><button className="sg-primary" disabled={locked || validating || !prepared || !config?.ready} onClick={match}>{active ? <Loader2 size={17} className="sg-spin" /> : <Search size={17} />}{active ? txt('正在匹配', 'Matching') : txt('开始库匹配', 'Start library matching')}</button>{config?.example_class_id != null && <button disabled={locked} onClick={example}>{txt('载入乙醇库内示例', 'Load in-library ethanol example')}</button>}</div>
      </section>
    </div><section className="sg-panel lm-results"><div className="sg-panel-heading"><h2><span>03</span>{txt('候选与谱图比对', 'Candidates and spectrum comparison')}</h2><span className="sg-pill">{txt('固定类别库', 'Fixed class library')}</span></div>
      <SavedAnalysisRecords api={api} module="library-matching" job={job} txt={txt} disabled={locked} onError={setError} onOpen={id => setSearch({ job: id }, { replace: true })} />
      {job ? <LibraryMatchResults key={job.id} job={job} api={api} txt={txt} dark={theme === 'dark'} onError={setError} /> : <div className="sg-empty-results"><div className="sg-empty-atom"><Database size={50} strokeWidth={1.2} /></div><h3>{txt("暂无匹配结果", "No matches yet")}</h3><p>{txt("上传光谱后开始匹配。", "Upload a spectrum to start matching.")}</p><div className="lm-empty-flow"><span>220–1800 cm⁻¹</span><ChevronRight size={15} /><span>PeakNet</span><ChevronRight size={15} /><span>Top {topK}</span></div></div>}
    </section></div><footer className="sg-footer"><span>PeakNet · AirNet</span><span>{txt("2805 类物质", "2805 classes")}</span></footer>
  </div>;
}
