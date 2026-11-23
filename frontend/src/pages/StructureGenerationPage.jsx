import { API_BASE as BASE } from '../apiBase';
import { systemText, localize } from '../locale.js';
import { useQAExecutionInput } from '../components/qaExecution';
import {NewAnalysisButton,useWorkspaceList} from '../components/AnalysisWorkspaces';
import React, { useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import { Link, useSearchParams } from 'react-router-dom';
import { ArrowRight, Atom, Check, ChevronRight, Copy, Download, FileText, FlaskConical, Info, Layers, Loader2, SlidersHorizontal, Sparkles, Upload, Waves, X } from 'lucide-react';
import { apiErrorMessage, useAuth } from '../auth';
import { usePreferences } from '../i18n';
import SpectralChart from '../components/SpectralChart';
import ImportReport, { SPECTRAL_ACCEPT } from '../components/ImportReport';
import SpectrumImportConfirmation from '../components/SpectrumImportConfirmation';
import ModuleUploadHistory from '../components/ModuleUploadHistory';
import ModuleInputActions from '../components/ModuleInputActions';
import SavedAnalysisRecords from '../components/SavedAnalysisRecords';
import { moduleSpectrum } from '../components/moduleSpectrum';
import MoleculePreview from '../components/MoleculePreview';
import StructureGenerationResults from '../components/StructureGenerationResults';
import { LAYOUT_CANDIDATES, makeGenerationDraft, modelCoverage, validFormula, validateSpectrum, workflowSpectrum } from './structureGeneration';
import './StructureGenerationPage.css';


function downloadJson(value, filename) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' }));
  const link = document.createElement('a'); link.href = url; link.download = filename; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export default function StructureGenerationPage() {
  const { token } = useAuth();
  const { language, theme } = usePreferences();
  const txt = (zh, en) => language === 'zh' ? zh : en;
  const [search, setSearch] = useSearchParams();
  const requestedTask = search.get('workflow'), requestedVersion = search.get('version'), requestedJob = search.get('job');
  const api = useMemo(() => axios.create({ baseURL: BASE, headers: { Authorization: `Bearer ${token}` }, timeout: 20000 }), [token]);
  const fileRef = useRef(), requestSequence = useRef(0);
  const [tab, setTab] = useState(requestedTask ? 'processed' : 'upload');
  const [tasks, setTasks] = useState([]), [task, setTask] = useState(null), [source, setSource] = useState(null);
  const [selectedVersion, setSelectedVersion] = useState(''), [pending, setPending] = useState(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [notice, setNotice] = useState('');
  const [formula, setFormula] = useState(''), [topK, setTopK] = useState(5), [rerank, setRerank] = useState(true), [unitConfirmed, setUnitConfirmed] = useState(false);
  const [layoutDemo, setLayoutDemo] = useState(false), [selectedCandidate, setSelectedCandidate] = useState(LAYOUT_CANDIDATES[0].id);
  const [config, setConfig] = useState(null), [prepared, setPrepared] = useState(null), [preparationError, setPreparationError] = useState('');
  const [inputPreviewOpen, setInputPreviewOpen] = useState(false);
  const [engine, setEngine] = useState('');
  const [job, setJob] = useState(null), [jobs, setJobs] = useState([]), [validating, setValidating] = useState(false);
  const active = ['queued', 'running'].includes(job?.status);
  const locked = busy || Boolean(pending) || active;
  const stats = source ? validateSpectrum(source.spectrum) : null;
  const coverage = modelCoverage(source?.spectrum, config?.profile);
  const missingRange = coverage?.missing.map(([start, end]) => `${Number(start.toFixed(2))}–${Number(end.toFixed(2))}`).join('、');
  const formulaValid = validFormula(formula.trim());
  const candidates = LAYOUT_CANDIDATES.slice(0, Math.min(topK, LAYOUT_CANDIDATES.length));
  const candidate = candidates.find(item => item.id === selectedCandidate) || candidates[0];
  const completedVersions = task?.versions.filter(item => item.status === 'completed') || [];
  const generationBlocker = active ? txt('当前任务正在生成，请等待完成。', 'Generation is in progress.')
    : busy ? txt('正在读取数据，请稍候。', 'Loading data…')
    : pending ? txt('请先确认仪器数据转换。', 'Confirm the instrument file conversion first.')
    : !source ? txt('请先上传光谱，或选择已保存的预处理结果。', 'Upload a spectrum or select a saved processed result first.')
    : coverage && !coverage.complete ? txt(`缺少 ${missingRange} cm⁻¹ 的实测波段。`, `Missing measured range: ${missingRange} cm⁻¹.`)
    : !unitConfirmed ? txt('请先勾选“确认横轴为拉曼位移 cm⁻¹”。', 'Confirm that the axis is Raman shift in cm⁻¹ first.')
    : !formulaValid ? txt('请修正分子式，未知时可以留空。', 'Correct the molecular formula, or leave it blank if unknown.')
    : !config ? txt('正在检查所选模型服务。', 'Checking the selected model service…')
    : !config.ready ? txt('所选模型尚未安装，请查看上方服务提示。', 'The selected model is not installed. See the service notice above.')
    : validating ? txt('正在检查模型输入。', 'Checking the model input…')
    : preparationError || (!prepared || prepared.profile.engine !== engine ? txt('等待模型输入检查通过。', 'Waiting for model input validation.') : '');

  async function loadWorkflow(id, vid, manual = false) {
    const sequence = ++requestSequence.current;
    setBusy(true); setError(''); setPending(null);
    try {
      const current = (await api.get(`/ai-workflows/${encodeURIComponent(id)}`)).data;
      const completed = current.versions.filter(item => item.status === 'completed');
      if (!completed.length) throw new Error(txt('这个任务还没有已保存的预处理结果，请先完成预处理。', 'Complete and save preprocessing before selecting this task.'));
      const chosen = vid || completed.at(-1).id;
      const version = (await api.get(`/ai-workflows/${encodeURIComponent(id)}/versions/${encodeURIComponent(chosen)}`)).data;
      const input = workflowSpectrum(current, version);
      if (sequence !== requestSequence.current) return;
      setTask(current); setSelectedVersion(chosen); setSource(input); setUnitConfirmed(false); setJob(null); setLayoutDemo(false); setNotice('');
      if (manual) setSearch({}, { replace: true });
    } catch (err) { if (sequence === requestSequence.current) setError(apiErrorMessage(err, err.message || txt('读取处理结果失败。', 'Unable to load the processed spectrum.'))); }
    finally { if (sequence === requestSequence.current) setBusy(false); }
  }

  useWorkspaceList(api,'/ai-workflows',setTasks,setError);

  useEffect(() => {
    if (requestedTask) { setTab('processed'); loadWorkflow(requestedTask, requestedVersion); }
    return () => { requestSequence.current += 1; };
  }, [requestedTask, requestedVersion, api]);
  useEffect(() => {
    let cancelled = false;
    api.get('/structure-generation/jobs').then(({ data }) => { if (!cancelled) setJobs(data); }).catch(() => {});
    return () => { cancelled = true; };
  }, [api]);
  useEffect(() => {
    let cancelled = false;
    setConfig(null);
    api.get('/structure-generation/config', { params: { engine: engine || undefined } }).then(({ data }) => {
      if (cancelled) return;
      if (!engine) setEngine(data.default_engine || 'official');
      else setConfig(data);
    }).catch(err => { if (!cancelled) setError(apiErrorMessage(err)); });
    return () => { cancelled = true; };
  }, [engine, api]);
  useEffect(() => {
    if (!requestedJob) return;
    let cancelled = false;
    api.get(`/structure-generation/jobs/${encodeURIComponent(requestedJob)}`).then(({ data }) => {
      if (cancelled) return;
      setJob(data); setLayoutDemo(false); setTask(null); setSelectedVersion('');
      setSource({ name: data.source_name, kind: data.input.source.reference.version_id ? 'processed' : 'uploaded', ...data.input.source, reuse_job_id: data.id });
      setFormula(data.settings.formula); setTopK(data.settings.top_k); setRerank(data.settings.rerank); setUnitConfirmed(true); setEngine(data.settings.engine || 'official');
    }).catch(err => { if (!cancelled) setError(apiErrorMessage(err)); });
    return () => { cancelled = true; };
  }, [requestedJob, api]);
  useEffect(() => {
    if (!active) return;
    let cancelled = false, timer;
    const poll = async () => {
      try {
        const { data } = await api.get(`/structure-generation/jobs/${job.id}`);
        if (!cancelled) { setJob(data); if (['queued', 'running'].includes(data.status)) timer = setTimeout(poll, 1500); }
      } catch (err) { if (!cancelled) { setError(apiErrorMessage(err)); timer = setTimeout(poll, 5000); } }
    };
    timer = setTimeout(poll, 1000);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [job?.id, active, api]);
  function requestPayload() {
    return { ...source?.reference, engine: engine || 'official', reuse_job_id: source?.reuse_job_id, unit_confirmed: unitConfirmed, formula: formula.trim(), top_k: topK, rerank };
  }
  useEffect(() => {
    setPrepared(null); setPreparationError('');
    if (!source || !unitConfirmed || !formulaValid) { setValidating(false); return; }
    let cancelled = false;
    setValidating(true);
    const timer = setTimeout(async () => {
      try { const { data } = await api.post('/structure-generation/validate', requestPayload()); if (!cancelled) setPrepared(data); }
      catch (err) { if (!cancelled) setPreparationError(apiErrorMessage(err)); }
      finally { if (!cancelled) setValidating(false); }
    }, 250);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [source, unitConfirmed, formula, topK, rerank, engine, api]);
  async function generate() {
    setBusy(true); setError(''); setLayoutDemo(false);
    try {
      const { data } = await api.post('/structure-generation/jobs', requestPayload());
      setJob(data); setJobs(previous => [data, ...previous.filter(item => item.id !== data.id)]);
      setSearch({ job: data.id }, { replace: true });
    } catch (err) { setError(apiErrorMessage(err)); }
    finally { setBusy(false); }
  }

  async function upload(file, confirmed = false, spectrumIndex) {
    if (!file) return;
    setBusy(true); setError(''); setNotice('');
    try {
      const form = new FormData(); form.append('file', file); form.append('confirm_conversion', String(confirmed));
      if (spectrumIndex != null) form.append('spectrum_index', String(spectrumIndex));
      const { data } = await api.post('/structure-generation/sources/upload', form);
      if (data.requires_confirmation) { setPending({ file, inspection: data }); return; }
      validateSpectrum(data.original);
      setPending(null); setTask(null); setSelectedVersion(''); setLayoutDemo(false); setJob(null); setUnitConfirmed(false);
      setSource(moduleSpectrum(data, 'structure-generation'));
      setSearch({}, { replace: true });
    } catch (err) { setError(apiErrorMessage(err, txt('上传失败，请检查光谱格式。', 'Upload failed. Check the spectrum format.'))); }
    finally { setBusy(false); if (fileRef.current) fileRef.current.value = ''; }
  }

  function exportDraft() {
    try {
      const draft = makeGenerationDraft(source, { formula, topK, rerank, unitConfirmed });
      draft.requested_engine = engine;
      downloadJson(draft, 'structure_generation_draft.json');
      setNotice(txt('已导出当前光谱及接入参数草稿，尚未调用模型。', 'Input and integration settings exported. No inference was performed.'));
    } catch (err) { setError(err.message); }
  }
  async function copySmiles() {
    try { await navigator.clipboard.writeText(candidate.smiles); setNotice(txt('已复制示例 SMILES。', 'Example SMILES copied.')); }
    catch { setError(txt('复制失败，可在下方选中 SMILES 手动复制。', 'Select the SMILES below to copy it manually.')); }
  }
  function openDemo() { setLayoutDemo(true); setSelectedCandidate(LAYOUT_CANDIDATES[0].id); setNotice(''); }

  useQAExecutionInput('structure-generation', { source: source?.reuse_job_id ? { reuse_job_id: source.reuse_job_id, module: 'structure-generation' } : source?.reference ? { ...source.reference, module: source.reference.module || 'structure-generation' } : null, unit_confirmed: unitConfirmed, settings: { engine: engine || 'official', formula, top_k: topK, rerank }, source_label: source?.name }, [], locked);

  return <div className="sg-workspace" data-qa-run={job?.analysis_run_id || undefined} data-qa-state={JSON.stringify({ module: localize("光谱到结构"), job_id: job?.id, status: job?.status, filename: job?.source_name, selected_settings: { formula, topK, rerank, engine, unitConfirmed }, executed_settings: job?.settings, layout_demo: layoutDemo, error: error?.slice(0, 200), candidate_count: job?.result?.candidates?.length })}>
    <header className="sg-header">
      <div><div className="sg-eyebrow">RAMANCLOUD <ChevronRight size={12} /> VIB2MOL</div><h1><Atom size={25} />{txt('光谱到结构', 'Spectrum to Structure')}</h1><p>{txt("由拉曼光谱生成候选结构。", "Generate candidate structures from Raman spectra.")}</p></div>
      <span className="sg-service-state"><span />{!config ? txt('检查服务…', 'Checking service…') : config.ready ? (engine === 'agent' ? txt('Agent 扩展已安装', 'Agent installed') : txt('官方模型已安装', 'Official model installed')) : txt('所选模式未安装', 'Selected mode not installed')}</span>
    <NewAnalysisButton disabled={busy} txt={txt} /></header>

    <nav className="sg-flow" aria-label={txt('光谱到结构流程', 'Spectrum to Structure workflow')}>
      {[['选择光谱', 'Choose spectrum', Waves], ['生成设置', 'Generation settings', SlidersHorizontal], ['候选结构', 'Candidate structures', FlaskConical]].map(([zh, en, Icon], index) => <div key={en} className={source && index === 0 ? 'is-complete' : ''}><span>{source && index === 0 ? <Check size={13} /> : index + 1}</span><Icon size={16} />{txt(zh, en)}{index < 2 && <ChevronRight size={15} className="sg-flow-arrow" />}</div>)}
    </nav>

    {config && !config.ready && <div className="sg-model-note"><Info size={18} /><p>{systemText(config.message)}</p></div>}
    {error && <div className="sg-alert is-error" role="alert">{systemText(error)}<button aria-label={txt('关闭错误提示', 'Dismiss error')} onClick={() => setError('')}><X size={15} /></button></div>}
    {notice && <div className="sg-alert" role="status">{systemText(notice)}</div>}

    <div className="sg-layout"><div className="sg-input-column">
      <section className="sg-panel" aria-label={txt('选择输入光谱', 'Select input spectrum')}>
        <div className="sg-panel-heading"><h2><span>01</span>{txt('输入光谱', 'Input spectrum')}</h2>{busy && <Loader2 size={17} className="sg-spin" />}</div>
        <p className="sg-help">{txt('所需波段：400–4000 cm⁻¹', 'Required range: 400–4000 cm⁻¹')}</p>
        <div className="sg-source-tabs" role="tablist" aria-label={txt('光谱来源', 'Spectrum source')}>
          <button role="tab" aria-selected={tab === 'upload'} disabled={locked} onClick={() => setTab('upload')}><Upload size={15} />{txt('本地上传', 'Upload')}</button>
          <button role="tab" aria-selected={tab === 'processed'} disabled={locked} onClick={() => setTab('processed')}><Layers size={15} />{txt('预处理结果', 'Processed result')}</button>
        </div>
        {tab === 'upload' ? <>
          <input ref={fileRef} type="file" hidden accept={SPECTRAL_ACCEPT} aria-label={txt('上传用于生成结构的光谱', 'Upload a spectrum for generation')} onChange={e => upload(e.target.files?.[0])} />
          <button className="sg-upload" disabled={locked} onClick={() => fileRef.current?.click()}><Upload size={24} /><strong>{txt('选择一条拉曼光谱', 'Choose a Raman spectrum')}</strong><span>TXT · CSV · XLSX · JCAMP · WDF · WXD · L6M · NPG</span></button>

        </> : <div className="sg-source-selectors">
          <label>{txt('分析任务', 'Analysis task')}<select aria-label={txt('光谱到结构分析任务', 'Spectrum to Structure task')} value={task?.id || ''} disabled={locked} onChange={e => e.target.value && loadWorkflow(e.target.value, undefined, true)}><option value="">{txt('选择已完成预处理的任务', 'Select a preprocessed task')}</option>{tasks.map(item => <option key={item.id} value={item.id}>{item.source_name}</option>)}</select></label>
          <label>{txt('已保存版本', 'Saved version')}<select aria-label={txt('光谱到结构输入版本', 'Spectrum to Structure input version')} value={selectedVersion} disabled={locked || !completedVersions.length} onChange={e => loadWorkflow(task.id, e.target.value, true)}><option value="">{txt('先选择任务', 'Choose a task first')}</option>{completedVersions.map(item => <option key={item.id} value={item.id}>V{task.versions.findIndex(v => v.id === item.id) + 1} · {txt('已保存', 'Saved')}</option>)}</select></label>

        </div>}
        {tab === 'upload' && <ModuleUploadHistory api={api} module="structure-generation" revision={source?.reference.source_id} txt={txt} disabled={locked} onLoading={setBusy} onError={setError} onSelect={data => { setTask(null); setSelectedVersion(''); setLayoutDemo(false); setJob(null); setUnitConfirmed(false); setSource(moduleSpectrum(data, 'structure-generation')); setSearch({}, { replace: true }); }} />}
        {pending && <SpectrumImportConfirmation inspection={pending.inspection} busy={busy} txt={txt} onConfirm={index => upload(pending.file, true, index)} onCancel={() => setPending(null)} />}
        {source && !pending && <div className="sg-selected-source">
          <div className="sg-file-heading"><FileText size={18} /><div><strong>{source.name}</strong><span>{source.reuse_job_id ? txt('已保存的输入快照', 'Saved input snapshot') : source.kind === 'processed' ? txt(`处理结果 · V${task?.versions.findIndex(v => v.id === selectedVersion) + 1}`, `Processed · V${task?.versions.findIndex(v => v.id === selectedVersion) + 1}`) : txt('原始上传 · 尚未预处理', 'Original upload · Not preprocessed')}</span></div></div>
          <div className="sg-spectrum-facts"><span>{stats.points} {txt('个点', 'points')}</span><span>{stats.min.toFixed(1)}–{stats.max.toFixed(1)} cm⁻¹</span></div>
          {coverage && <div className={`sg-coverage ${coverage.complete ? 'is-complete' : 'is-incomplete'}`} role="status"><strong>{coverage.complete ? txt("波段检查通过", "Range checked") : txt("波段不足，无法生成", "Insufficient range for generation")}</strong><p>{txt(`当前模型输入：${coverage.start}–${coverage.end} cm⁻¹`, `Selected model input: ${coverage.start}–${coverage.end} cm⁻¹`)}</p>{!coverage.complete && <><p>{txt(`缺少实测波段：${missingRange} cm⁻¹`, `Missing measured range: ${missingRange} cm⁻¹`)}</p><p>{txt("请上传完整波段光谱，或选择未截断的处理版本。", "Upload a full-range spectrum or choose an uncropped version.")}</p></>}</div>}
          <div className="sg-spectrum"><SpectralChart rawData={source.spectrum} rawLabel={txt('当前输入', 'Current input')} height={205} dark={theme === 'dark'} horizontalLegend showToolbar={false} /></div>
          <details className="sg-import-details"><summary>{txt('查看导入与质量检查', 'Import and quality report')}</summary><ImportReport metadata={source.metadata} /></details>
          <label className="sg-checkbox"><input type="checkbox" checked={unitConfirmed} onChange={e => setUnitConfirmed(e.target.checked)} disabled={locked} />{txt('确认横轴为拉曼位移 cm⁻¹', 'Confirm the axis is Raman shift in cm⁻¹')}</label>
          <ModuleInputActions api={api} module="structure-generation" source={source} txt={txt} disabled={locked} onError={setError} />
        </div>}
      </section>

      <section className="sg-panel" aria-label={txt('光谱到结构设置', 'Spectrum to Structure settings')}>
        <div className="sg-panel-heading"><h2><span>02</span>{txt('生成条件', 'Generation settings')}</h2><span className="sg-pill">Raman</span></div>
        <label>{txt('生成模式', 'Generation mode')}<select aria-label={txt('生成模式', 'Generation mode')} disabled={locked || !config} value={engine} onChange={e => setEngine(e.target.value)}>{(config?.engines || [{ id: engine, label: '…', ready: true }]).map(item => <option key={item.id} value={item.id}>{systemText(item.label)}{!item.ready ? txt('（未安装）', ' (not installed)') : ''}</option>)}</select></label>
        <label>{txt('已知分子式', 'Known molecular formula')}<span className="sg-optional">{txt('可选', 'Optional')}</span><input disabled={locked} aria-label={txt('已知分子式', 'Known molecular formula')} value={formula} maxLength={120} placeholder={txt('例如 C6H6；未知时留空', 'e.g. C6H6; leave blank if unknown')} onChange={e => setFormula(e.target.value)} aria-invalid={!formulaValid} /></label>
        {!formulaValid && <p className="sg-field-error">{txt('请填写元素及原子数，例如 C6H6，不含括号或电荷。', 'Use element counts, such as C6H6, without brackets or charges.')}</p>}
        <p className="sg-help">{txt("填写后仅保留分子式一致的候选。", "Keep only candidates matching this formula.")}</p>
        <label>{txt('展示候选数量', 'Number of candidates')}<select disabled={locked} aria-label={txt('候选数量', 'Candidate count')} value={topK} onChange={e => setTopK(Number(e.target.value))}>{[3, 5, 10].map(n => <option key={n} value={n}>Top {n}</option>)}</select></label>
        <label className="sg-checkbox"><input disabled={locked} type="checkbox" checked={rerank} onChange={e => setRerank(e.target.checked)} />{txt('按光谱匹配得分重排候选', 'Rerank by spectrum–molecule matching')}</label>

        <details className="sg-preparation" onToggle={event => setInputPreviewOpen(event.currentTarget.open)}><summary>{txt('模型输入预览', 'Model input preview')}</summary><p>{txt("400–4000 cm⁻¹ · 插值至 1024 点 · 强度归一化", "400–4000 cm⁻¹ · Resampled to 1024 points · Normalized intensity")}</p>
          {validating && <p role="status">{txt('正在检查输入…', 'Checking input…')}</p>}{preparationError && <p className="sg-field-error" role="alert">{preparationError}</p>}
          {prepared && inputPreviewOpen && <><p className="sg-ready">{txt("输入检查通过 · 1024 点", "Input checked · 1024 points")}</p><div className="sg-spectrum"><SpectralChart rawData={prepared.model_input} rawLabel={txt('实际模型输入', 'Actual model input')} height={175} dark={theme === 'dark'} showToolbar={false} /></div></>}
        </details>
        <div className="sg-generate-actions"><button className="sg-primary" aria-describedby={generationBlocker ? 'sg-generation-blocker' : undefined} disabled={Boolean(generationBlocker)} onClick={generate}>{active ? <Loader2 className="sg-spin" size={17} /> : <Sparkles size={17} />}{active ? txt('正在生成', 'Generating') : txt('生成候选结构', 'Generate candidates')}</button>{generationBlocker && <p id="sg-generation-blocker" className="sg-generation-blocker" role="status">{generationBlocker}</p>}<button disabled={locked || !source || !unitConfirmed || !formulaValid} onClick={exportDraft}><Download size={15} />{txt('导出输入草稿', 'Export input draft')}</button></div>
      </section>
    </div>

    <section className="sg-panel sg-results" aria-label={txt('候选结构区域', 'Candidate structures')}>
      <div className="sg-panel-heading"><h2><span>03</span>{txt('候选结构', 'Candidate structures')}</h2>{layoutDemo && <span className="sg-example-tag">{txt('界面示例', 'Layout examples')}</span>}</div>
      <SavedAnalysisRecords api={api} module="structure-generation" job={job} txt={txt} disabled={locked} onError={setError} onOpen={id => setSearch({ job: id }, { replace: true })} />
      {job ? <StructureGenerationResults job={job} api={api} txt={txt} onError={setError} /> : !layoutDemo ? <div className="sg-empty-results"><div className="sg-empty-atom"><Atom size={55} strokeWidth={1.2} /></div><h3>{txt("暂无生成结果", "No generated results yet")}</h3><p>{txt("上传光谱后生成候选结构。", "Upload a spectrum to generate candidates.")}</p><div className="sg-result-placeholders" aria-hidden="true">{[0, 1, 2].map(n => <div key={n}><Atom size={27} /><span /><small /></div>)}</div><button onClick={openDemo}><EyeIcon />{txt('查看结果布局示例', 'Preview the result layout')}</button></div> : <>
        <div className="sg-demo-notice"><Info size={17} /><p>{txt("固定示例，与上传光谱无关。", "Fixed examples, unrelated to the uploaded spectrum.")}</p><button aria-label={txt('关闭布局示例', 'Close layout examples')} onClick={() => setLayoutDemo(false)}><X size={16} /></button></div>
        <div className="sg-candidate-grid">{candidates.map((item, index) => <button key={item.id} className={`sg-candidate ${candidate.id === item.id ? 'is-selected' : ''}`} aria-pressed={candidate.id === item.id} aria-label={`${txt('示例候选', 'Example candidate')} ${index + 1} ${txt(item.name, item.en)}`} onClick={() => setSelectedCandidate(item.id)}><div className="sg-candidate-top"><span>#{index + 1}</span><small>{txt('示例', 'Example')}</small></div><MoleculePreview molecule={item} label={txt(item.name, item.en)} /><strong>{txt(item.name, item.en)}</strong><span className="sg-formula">{item.formula}</span><span className="sg-candidate-score">{txt('匹配得分', 'Match score')} <b>—</b></span></button>)}</div>
        <div className="sg-candidate-detail"><div className="sg-detail-illustration"><MoleculePreview molecule={candidate} label={txt(`${candidate.name}示例结构`, `${candidate.en} example structure`)} /></div><div><span className="sg-detail-eyebrow">{txt('示例结构详情', 'Example structure details')}</span><h3>{txt(candidate.name, candidate.en)}</h3><p className="sg-formula">{candidate.formula}</p><label>SMILES<code>{candidate.smiles}</code></label><div className="sg-detail-actions"><button onClick={copySmiles}><Copy size={14} />{txt('复制 SMILES', 'Copy SMILES')}</button><button onClick={() => downloadJson({ purpose: 'layout_examples_only', inference_performed: false, associated_with_input: false, candidates }, 'structure_layout_examples.json')}><Download size={14} />{txt('导出示例', 'Export examples')}</button></div></div></div>
        <p className="sg-results-footnote">{txt("候选结构需结合实验确认。", "Verify candidate structures experimentally.")}</p>
      </>}
    </section></div>
    <footer className="sg-footer"><span>Vib2Mol</span><a href="https://github.com/X1nyuLu/vib2mol" target="_blank" rel="noreferrer">{txt('算法来源', 'Algorithm source')} ↗</a><span>{systemText(config?.profile?.label || 'Raman')} · {txt('本地推理', 'Local inference')}</span></footer>
  </div>;
}

function EyeIcon() {
  usePreferences(); return <FlaskConical size={16} />; }
