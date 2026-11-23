import { API_BASE as BASE } from '../apiBase';
import { systemText, localize } from '../locale.js';
import { useQAExecutionInput } from '../components/qaExecution';
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import { Link, useSearchParams } from 'react-router-dom';
import { ArrowRight, CheckCircle2, Database, Download, Eye, FileText, FolderOpen, GitBranch, History, Loader2, Play, Plus, RotateCcw, SlidersHorizontal, Sparkles, Upload } from 'lucide-react';
import { useAuth } from '../auth';
import { usePreferences } from '../i18n';
import SpectralChart from '../components/SpectralChart';
import { SpectrumExport, ShareResult } from '../components/ResultActions';
import BatchAnalysisPanel from '../components/BatchAnalysisPanel';
import ImportReport, { SPECTRAL_ACCEPT } from '../components/ImportReport';
import { qualityMarkers, QUALITY_LABELS } from '../components/spectralQuality';
import SpectrumImportConfirmation from '../components/SpectrumImportConfirmation';
import DespikeParameters from '../components/DespikeParameters';
import PreprocessingFlow from '../components/PreprocessingFlow';
import { WORKFLOW_STAGES, initialStage, uploadNextStage, selectedBand, spectrumResidual, refinementRequest, validDespikeOrder } from './analysisWorkflow';
import './AIAnalysisPage.css';
import {NewAnalysisButton,useWorkspaceList} from '../components/AnalysisWorkspaces';

const clone = value => JSON.parse(JSON.stringify(value));
const stageIcons = [Upload, Sparkles, Eye];
function errorText(error) { return typeof error?.response?.data?.detail === 'string' ? error.response.data.detail : error?.message || localize("请求失败"); }
function IconButton({ label, icon: Icon, ...props }) {
  usePreferences(); return <button type="button" className="ai-icon" title={systemText(label)} aria-label={systemText(label)} {...props}><Icon size={16} /></button>; }

export default function AIAnalysisPage() {
  const { token } = useAuth();
  const { language, theme } = usePreferences();
  const txt = (zh, en) => language === 'zh' ? zh : en;
  const [search, setSearch] = useSearchParams();
  const taskId = search.get('task'), versionParam = search.get('version'), batchId = search.get('batch');
  const api = useMemo(() => axios.create({ baseURL: BASE, headers: { Authorization: `Bearer ${token}` } }), [token]);
  const [config, setConfig] = useState(null), [projects, setProjects] = useState([]);
  const [projectId, setProjectId] = useState(''), [datasets, setDatasets] = useState([]), [datasetId, setDatasetId] = useState('');
  const [task, setTask] = useState(null), [version, setVersion] = useState(null), [steps, setSteps] = useState([]);
  const [goal, setGoal] = useState(''), [refinementGoal, setRefinementGoal] = useState(''), [feedback, setFeedback] = useState('');
  const [allowAI, setAllowAI] = useState(false);
  const [preprocessMode, setPreprocessMode] = useState('local_rules');
  const [stage, setStage] = useState(0), [region, setRegion] = useState({ start: '', end: '' });
  const [editingBand, setEditingBand] = useState(false), [refining, setRefining] = useState(false);
  const [showQualityMarkers, setShowQualityMarkers] = useState(true);
  const [dirty, setDirty] = useState(false), [busy, setBusy] = useState(''), [loading, setLoading] = useState(false);
  const [error, setError] = useState(''), [clarification, setClarification] = useState(''), [view, setView] = useState('original');

  const [uploadMode, setUploadMode] = useState(batchId ? 'batch' : 'single'), [batch, setBatch] = useState(null);
  const [pendingImport, setPendingImport] = useState(null);
  const [selectedTasks, setSelectedTasks] = useState([]), [batchRevision, setBatchRevision] = useState(0);
  const fileRef = useRef(), folderRef = useRef(), resultRef = useRef(), feedbackRef = useRef(), workspaceRef = useRef(), loadedLocation = useRef(''), activeLocation = useRef(''), afterRunStage = useRef(null);
  const running = ['queued', 'running', 'previewing'].includes(version?.status), working = Boolean(busy || running || loading), locked = working || Boolean(pendingImport);
  const registry = config?.registry || [], phase = version?.metadata?.phase;
  const hasCompleted = task?.versions.some(item => item.status === 'completed');
  const refinement = refinementRequest(refinementGoal, feedback, version);
  const providerName = value => value === 'ollama' ? 'Ollama' : value === 'deepseek' ? 'DeepSeek' : value === 'siliconflow' ? txt('硅基流动', 'SiliconFlow') : value || 'AI';
  const activeProvider = providerName(config?.provider);
  const qualityPoints = qualityMarkers(task?.diagnostics.source_check?.quality_check).map(point => ({ ...point, label: txt(...QUALITY_LABELS[point.quality_code]) }));
  const status = value => ({ draft: txt('待确认', 'Draft'), preview: txt('已预览', 'Previewed'), completed: txt('已记录', 'Recorded'), queued: txt('排队中', 'Queued'), running: txt('执行中', 'Running'), previewing: txt('预览中', 'Previewing'), failed: txt('失败', 'Failed') }[value] || value);

  useWorkspaceList(api,'/projects',setProjects,setError,'projects');
  const adoptVersion = useCallback(value => {
    setVersion(value); setSteps(clone(value.steps)); setGoal(value.goal); setDirty(false); setFeedback(value.feedback || ''); setClarification('');
    setRefinementGoal(value.goal);
    setView(value.trace?.length || value.preview?.length ? 'result' : 'original');
  }, []);
  useEffect(() => { setAllowAI(false); }, [config?.provider]);
  useEffect(() => { setShowQualityMarkers(true); }, [task?.id]);
  useEffect(() => { setEditingBand(false); workspaceRef.current?.scrollTo({ top: 0, left: 0 }); }, [stage, task?.id]);
  useEffect(() => {
    let cancelled = false;
    async function init() {
      try {
        const settings = (await api.get('/ai-workflows/config')).data;
        if (!cancelled) setConfig(settings);
      } catch (err) { if (!cancelled) setError(errorText(err)); }
    }
    init(); return () => { cancelled = true; };
  }, [api]);
  useEffect(() => {
    let cancelled = false;
    if (!batchId) { setBatch(null); return undefined; }
    setUploadMode('batch');
    api.get(`/ai-workflow-batches/${batchId}`).then(({ data }) => { if (!cancelled) { setBatch(data); const first = data.items.find(item => item.workflow_id); if (!taskId && first) setSearch({batch: batchId, task: first.workflow_id, ...(first.version_id ? {version: first.version_id} : {})}, {replace: true}); } }).catch(err => { if (!cancelled) { setBatch(null); setError(errorText(err)); } });
    return () => { cancelled = true; };
  }, [batchId, batchRevision, api]);
  useEffect(() => { setSelectedTasks(batch?.items.filter(item => item.workflow_id).map(item => item.workflow_id) || []); }, [batch?.id]);
  useEffect(() => {
    if (!batch?.active) return undefined;
    let cancelled = false, timer;
    async function poll() {
      try {
        const current = (await api.get(`/ai-workflow-batches/${batch.id}`)).data;
        if (cancelled) return;
        setBatch(current);
        if (current.active) timer = setTimeout(poll, 1000);
      } catch (err) { if (!cancelled) { setError(errorText(err)); timer = setTimeout(poll, 3000); } }
    }
    timer = setTimeout(poll, 600);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [batch?.id, batch?.active, api]);
  useEffect(() => {
    let cancelled = false;
    setDatasets([]); setDatasetId('');
    if (projectId) api.get(`/projects/${projectId}/datasets`).then(({ data }) => {
      if (!cancelled) setDatasets(data.data.datasets.filter(item => item.data_type === 'spectrum'));
    }).catch(err => { if (!cancelled) setError(errorText(err)); });
    return () => { cancelled = true; };
  }, [projectId, api]);
  useEffect(() => {
    const key = `${taskId || ''}:${versionParam || ''}`;
    activeLocation.current = key;
    if (loadedLocation.current === key) { loadedLocation.current = ''; return undefined; }
    let cancelled = false;
    setRefining(false); setError(''); setClarification(''); setTask(null); setVersion(null); setSteps([]); setDirty(false); setGoal(''); setRefinementGoal(''); setFeedback(''); setView('original');
    if (!taskId) { setLoading(false); setStage(0); return undefined; }
    setLoading(true);
    async function load() {
      try {
        const current = (await api.get(`/ai-workflows/${taskId}`)).data;
        if (cancelled) return;
        setTask(current);
        const vid = versionParam && current.versions.some(item => item.id === versionParam) ? versionParam : current.versions.at(-1)?.id;
        let result = null;
        if (vid) result = (await api.get(`/ai-workflows/${taskId}/versions/${vid}`)).data;
        if (!cancelled) { if (result) adoptVersion(result); setStage(initialStage(current, result)); }
      } catch (err) { if (!cancelled) setError(errorText(err)); }
      finally { if (!cancelled) setLoading(false); }
    }
    load(); return () => { cancelled = true; };
  }, [taskId, versionParam, api, adoptVersion]);
  useEffect(() => { if (task) setRegion(selectedBand(version?.steps || [], task.diagnostics)); }, [task?.id, version?.id]);
  useEffect(() => {
    if (!running || !taskId || !version?.id) return undefined;
    let cancelled = false, timer;
    async function poll() {
      try {
        const data = (await api.get(`/ai-workflows/${taskId}/versions/${version.id}`)).data;
        if (cancelled) return;
        setVersion(data);
        if (['queued', 'running', 'previewing'].includes(data.status)) timer = setTimeout(poll, 800);
        else {
          setTask((await api.get(`/ai-workflows/${taskId}`)).data);  setView('result');
          setStage(2);
          afterRunStage.current = null;
          if (data.error) setError(data.error);
        }
      } catch (err) { if (!cancelled) { setError(errorText(err)); timer = setTimeout(poll, 3000); } }
    }
    timer = setTimeout(poll, 400); return () => { cancelled = true; clearTimeout(timer); };
  }, [running, taskId, version?.id, api]);

  const regionPoints = task && Number.isFinite(region.start) && Number.isFinite(region.end) ? task.original.wavenumber.filter(x => x >= region.start && x <= region.end).length : 0;
  const regionValid = Boolean(task && region.start !== '' && region.end !== '' && region.start < region.end && region.start >= task.diagnostics.wavenumber_min && region.end <= task.diagnostics.wavenumber_max && regionPoints >= 8);
  const trace = ['running', 'completed', 'failed'].includes(version?.status) ? version?.trace || [] : version?.preview || [];
  const isResidual = view.startsWith('residual:');
  const traceIndex = view.startsWith('step:') || isResidual ? Number(view.split(':')[1]) : null;
  const selectedTrace = traceIndex === null ? null : trace[traceIndex];
  const processed = selectedTrace?.after || trace.at(-1)?.after;
  const raw = selectedTrace?.before || task?.original;
  const residual = spectrumResidual((selectedTrace || trace.at(-1))?.before, processed);
  const metrics = selectedTrace?.metrics || trace.at(-1)?.metrics || task?.diagnostics;
  const warnings = [...new Set((selectedTrace ? selectedTrace.warnings : trace.flatMap(record => record.warnings || [])) || [])];
  const candidates = dirty ? [] : version?.metadata?.candidates || [];
  const chosenCandidate = candidates.find(item => item.id === version?.metadata?.selected_candidate && item.status === 'valid');
  const versionNumber = task?.versions.findIndex(item => item.id === version?.id) + 1;
  const providerLabel = version?.provider.includes(':') ? `${providerName(version.provider.split(':')[0])} · ${version.provider.split(':').slice(1).join(':')}` : version?.provider === 'manual' ? txt('手动方案', 'Manual plan') : txt('本地规则推荐', 'Local rules');
  const nextUploadStage = uploadNextStage(task, version, dirty);
  const needsExecution = Boolean(steps.length && (dirty || version && version.status !== 'completed'));

  const despikeIndex = trace.findIndex(record => record.step.type === 'despike');
  const despikeRecord = trace[despikeIndex];

  async function act(name, fn, duringRun = false) {
    if (busy || loading || running && !duringRun) return;
    setBusy(name); setError(''); setClarification('');
    try { await fn(); } catch (err) { setError(errorText(err)); } finally { setBusy(''); }
  }
  function selectTask(id, vid) {
    if (locked || (dirty || refinement.pending) && !window.confirm(txt('放弃尚未应用的修改？', 'Discard unapplied changes?'))) return;
    setSearch(id ? { ...(batchId ? { batch: batchId } : {}), task: id, ...(vid ? { version: vid } : {}) } : {});
  }
  async function newSource(payload, file) {
    if ((dirty || refinement.pending) && !window.confirm(txt('放弃尚未应用的修改？', 'Discard unapplied changes?'))) return;
    await act('source', async () => {
      const result = await sendSource(payload, file, false, projectId);
      if (result.requires_confirmation) { setPendingImport({ inspection: result, payload, file, projectId }); setStage(0); }
      else await adoptSource(result);
    });
    if (fileRef.current) fileRef.current.value = '';
  }
  async function sendSource(payload, file, confirmed, targetProject, spectrumIndex) {
    if (!file) return (await api.post('/ai-workflows/source', { ...payload, confirm_conversion: confirmed, spectrum_index: spectrumIndex })).data;
    const form = new FormData(); form.append('file', file); form.append('confirm_conversion', String(confirmed));
    if (spectrumIndex != null) form.append('spectrum_index', String(spectrumIndex));
    if (targetProject) form.append('project_id', targetProject);
    return (await api.post('/ai-workflows/upload', form)).data;
  }
  async function adoptSource(result) {
    setPendingImport(null); setUploadMode('single'); setSearch({ task: result.id });
  }
  async function sendFolder(files, confirmed, targetProject) {
    const form = new FormData();
    files.forEach(file => { form.append('files', file, file.name); form.append('paths', file.webkitRelativePath || file.name); });
    form.append('confirm_conversion', String(confirmed));
    if (targetProject) form.append('project_id', targetProject);
    return (await api.post('/ai-workflow-batches/upload', form)).data;
  }
  async function adoptBatch(current) {
    setPendingImport(null); setBatch(current); setUploadMode('batch'); setSearch({ batch: current.id, ...(current.items.find(item => item.workflow_id) ? { task: current.items.find(item => item.workflow_id).workflow_id } : {}) });

  }
  async function confirmImport(spectrumIndex) {
    if (!pendingImport) return;
    await act('confirm-import', async () => {
      if (pendingImport.files) await adoptBatch(await sendFolder(pendingImport.files, true, pendingImport.projectId));
      else await adoptSource(await sendSource(pendingImport.payload, pendingImport.file, true, pendingImport.projectId, spectrumIndex));
    });
  }
  async function accept(value) {
    adoptVersion(value);
    setTask((await api.get(`/ai-workflows/${task.id}`)).data);
    const key = `${task.id}:${value.id}`;
    if (activeLocation.current !== key) { activeLocation.current = key; loadedLocation.current = key; setSearch({ ...(batchId ? { batch: batchId } : {}), task: task.id, version: value.id }, { replace: true }); }
  }
  async function uploadFolder(files) {
    if ((dirty || refinement.pending) && !window.confirm(txt('放弃尚未应用的修改？', 'Discard unapplied changes?'))) return;
    await act('folder-upload', async () => {
      if (files.length > config.max_batch_files || files.reduce((sum, file) => sum + file.size, 0) > config.max_batch_mb * 1024 * 1024) throw new Error(txt('每批最多 100 个文件，总大小不超过 40 MB。', 'Limit: 100 files and 40 MB per batch.'));
      const current = await sendFolder(files, false, projectId);
      if (current.requires_confirmation) { setPendingImport({ inspection: current, files, projectId }); setStage(0); }
      else await adoptBatch(current);
    });
    if (folderRef.current) folderRef.current.value = '';
  }
  async function executeBatch() {
    if (refinement.pending) { setError(txt('调整尚未预览，请先更新方案并预览。', 'Preview the revised plan before batch execution.')); setStage(2); setRefining(true); return; }
    await act('batch-execute', async () => {
      const draft = await saveDraft();
      const ids = selectedTasks.filter(id => batch.items.some(item => item.workflow_id === id));
      const current = (await api.post(`/ai-workflow-batches/${batch.id}/execute`, { template_workflow_id: task.id, template_version_id: draft.id, workflow_ids: ids })).data;
      setBatch(current);
      const first = current.items.find(item => ids.includes(item.workflow_id) && item.version_id);
      if (first) setSearch({ batch: current.id, task: first.workflow_id, version: first.version_id });
    });
  }
  function refineBatch() {
    setStage(2); setRefining(true);
    requestAnimationFrame(() => { feedbackRef.current?.scrollIntoView({ block: 'center', behavior: 'smooth' }); feedbackRef.current?.focus({ preventScroll: true }); });
  }
  async function cancelBatch() { await act('batch-cancel', async () => setBatch((await api.post(`/ai-workflow-batches/${batch.id}/cancel`)).data), true); }

  async function saveDraft(force = false) {
    if (version && !dirty && !force && version.status !== 'failed') return version;
    const result = (await api.post(`/ai-workflows/${task.id}/versions`, { goal, steps, parent_id: version?.id })).data;
    await accept(result); return result;
  }
  async function recommend(mode) {
    await act('recommend', async () => {
      let parent = version?.id;
      if (dirty && steps.length) parent = (await api.post(`/ai-workflows/${task.id}/versions`, { goal, steps, parent_id: parent })).data.id;
      const target = mode === 'preprocess' ? config.default_preprocess_goal : refinement.goal;
      const result = (await api.post(`/ai-workflows/${task.id}/recommend`, {
        goal: target, feedback: mode === 'refine' ? refinement.feedback : '', parent_id: parent, allow_ai: mode === 'preprocess' ? preprocessMode === 'model' : allowAI,
        phase: mode, region, compare_candidates: false,
      })).data;
      if (result.clarification) { setStage(mode === 'preprocess' ? 1 : 2); setClarification([result.clarification, result.fallback_reason].filter(Boolean).join(' ')); return; }
      await accept(result.version);
      if (mode === 'refine') await accept((await api.post(`/ai-workflows/${task.id}/versions/${result.version.id}/preview`)).data);
      setStage(mode === 'preprocess' ? 1 : 2); if (mode === 'refine') setRefining(false);
    });
  }
  async function continueFromUpload() {
    if (nextUploadStage !== null) setStage(nextUploadStage);
    else await recommend('preprocess');
  }
  async function preview() {
    await act('preview', async () => {
      const draft = await saveDraft();
      await accept((await api.post(`/ai-workflows/${task.id}/versions/${draft.id}/preview`)).data);
    });
  }
  async function execute() {
    await act('execute', async () => {
      const draft = await saveDraft();
      await api.post(`/ai-workflows/${task.id}/versions/${draft.id}/execute`, {});
      afterRunStage.current = 2;
      setVersion({ ...draft, status: 'running', trace: [] }); setView('result');
    });
  }
  async function chooseCandidate(id) {
    await act('candidate', async () => {
      const result = (await api.post(`/ai-workflows/${task.id}/versions/${version.id}/candidates/${id}`)).data;
      await accept(result);
      if (result.metadata?.phase === 'refine') await accept((await api.post(`/ai-workflows/${task.id}/versions/${result.id}/preview`)).data);
    });
  }
  function changeSteps(next) {
    if (!validDespikeOrder(next)) { setError(txt('去鬼峰应位于降噪之前，且只能添加一次。', 'Place a single despike step before denoising.')); return; }
    setError(''); setSteps(next); setDirty(true);
  }
  function editStep(index, patch) { changeSteps(steps.map((step, i) => i === index ? { ...step, ...patch } : step)); }
  function defaults(spec) { const params = Object.fromEntries(Object.entries(spec.params).map(([key, field]) => [key, field.default])); if (spec.type === 'cut' && task) { params.start = region.start; params.end = region.end; } return params; }
  function changeBand(next) {
    setRegion(next);
    if (!version || !Number.isFinite(next.start) || !Number.isFinite(next.end) || next.start >= next.end) return;
    const updated = steps.filter(step => step.type !== 'cut');
    if (next.start > task.diagnostics.wavenumber_min || next.end < task.diagnostics.wavenumber_max) {
      updated.unshift({ id: steps.find(step => step.type === 'cut')?.id || crypto.randomUUID(), type: 'cut', method: 'cut', params: next, enabled: true, reason: txt('用户手动选择的处理波段', 'Spectral range selected by user') });
    }
    changeSteps(updated);
  }
  async function download(kind) {
    await act('download', async () => {
      const result = await api.get(`/ai-workflows/${task.id}/download`, { params: { kind, version_id: version?.id }, responseType: 'blob' });
      const url = URL.createObjectURL(result.data), link = document.createElement('a'); link.href = url;
      link.download = kind === 'bundle' ? 'raman_workflow.zip' : kind === 'original' ? task.source_name : `${task.source_name.replace(/\.[^.]+$/, '')}_${kind === 'standardized' ? 'original' : 'processed_V' + versionNumber}.txt`;
      link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    });
  }

  const consent = <label className="ai-consent"><input type="checkbox" checked={allowAI} disabled={locked} onChange={e => setAllowAI(e.target.checked)} />{config?.provider === 'ollama' ? txt('允许本地 Ollama 模型读取目标、数据摘要和当前方案', 'Allow local Ollama access to the goal, data summary and plan') : txt(`允许向 ${activeProvider} 发送目标、数据摘要和当前方案`, `Allow ${activeProvider} access to the goal, data summary and plan`)}</label>;
  const recommendationMode = <div className="ai-recommend-options"><label>{txt('方案生成方式', 'Recommendation method')}<select aria-label={txt('方案生成方式', 'Recommendation method')} value={preprocessMode} disabled={locked} onChange={e => setPreprocessMode(e.target.value)}><option value="local_rules">{txt('本地规则（默认）', 'Local rules (default)')}</option><option value="model">{txt(`大模型（${activeProvider}）`, `AI model (${activeProvider})`)}</option></select></label><small className="ai-muted">{preprocessMode === 'model' ? txt(`将所选波段的光谱采样数据、噪声和峰特征发送给 ${activeProvider}，推荐算法与参数；生成后可修改。`, `Send sampled spectral pairs and noise/peak features to ${activeProvider} for editable algorithm and parameter recommendations.`) : txt('根据数据诊断和固定规则快速生成基础方案，不调用大模型。', 'Quick initial plan from diagnostics and fixed rules, without model calls.')}</small>{preprocessMode === 'model' && !config?.configured && <small className="ai-inline-error">{txt('模型尚未配置；生成时将明确提示并使用本地规则。', 'Model is not configured; generation will explicitly fall back to local rules.')}</small>}</div>;
  const bandControls = task && <div className="ai-band-controls">
    <div className="ai-band-fields"><label>{txt('起始波数', 'Start wavenumber')}<input aria-label={txt('起始波数', 'Start wavenumber')} type="number" step="any" min={task.diagnostics.wavenumber_min} max={task.diagnostics.wavenumber_max} value={region.start} disabled={locked} onChange={e => changeBand({ ...region, start: e.target.value === '' ? '' : Number(e.target.value) })} /></label>
      <label>{txt('终止波数', 'End wavenumber')}<input aria-label={txt('终止波数', 'End wavenumber')} type="number" step="any" min={task.diagnostics.wavenumber_min} max={task.diagnostics.wavenumber_max} value={region.end} disabled={locked} onChange={e => changeBand({ ...region, end: e.target.value === '' ? '' : Number(e.target.value) })} /></label>
      <IconButton label={txt('使用完整波段', 'Use full range')} icon={RotateCcw} disabled={locked} onClick={() => changeBand({ start: task.diagnostics.wavenumber_min, end: task.diagnostics.wavenumber_max })} />
    </div><small className="ai-muted">cm⁻¹ · {regionPoints} {txt('个数据点', 'points')}</small>
    {!regionValid && <p className="ai-inline-error" role="alert">{txt('请选择数据范围内的有效波段，至少保留 8 个点。', 'Select an in-bounds range containing at least 8 points.')}</p>}
  </div>;

  const bandSummary = task && <><div className="ai-band-summary"><span>{txt('处理波段', 'Processing range')} <strong>{region.start}–{region.end}</strong> cm⁻¹ · {regionPoints} {txt('个点', 'points')}</span><IconButton label={txt('调整处理波段', 'Edit processing range')} icon={SlidersHorizontal} disabled={locked} aria-expanded={editingBand} onClick={() => setEditingBand(value => !value)} /></div>{editingBand && bandControls}</>;

  const planActions = needsExecution && <div className="ai-actions ai-plan-actions">
    {(dirty || !trace.length) && <button disabled={locked || !regionValid || refinement.pending} onClick={preview}><Eye size={16} />{txt('预览', 'Preview')}</button>}
    <button className="ai-primary" disabled={locked || !regionValid || refinement.pending} onClick={() => execute()}>{running ? <Loader2 className="ai-spin" size={16} /> : <Play size={16} />}{stage === 1 ? txt('开始处理', 'Start processing') : txt('应用修改', 'Apply changes')}</button>
  </div>;

  const planEditor = <section className="ai-plan">
    <div className="ai-section-heading"><h2>{txt('处理方案', 'Processing plan')}{dirty && <small className="ai-dirty">{txt('待应用', 'Not applied')}</small>}</h2><div className="ai-actions">{version && <span className="ai-provider">{providerLabel}</span>}</div></div>
    {version?.fallback_reason && <div className="ai-alert">{systemText(version.fallback_reason)}</div>}
    {version?.summary && <details className="ai-recommend-options"><summary>{txt('方案说明', 'Plan notes')}</summary><p className="ai-summary ai-muted">{['manual', 'local_rules'].includes(version.provider) ? systemText(version.summary) : version.summary}</p></details>}
    {version?.parent_id && <small className="ai-muted">{txt('基于版本', 'Based on')} V{task?.versions.findIndex(item => item.id === version.parent_id) + 1}</small>}
    <PreprocessingFlow steps={steps.filter(step => step.type !== 'cut')} txt={txt} />
    <div className="ai-step-list">{steps.map((step, index) => {
      if (step.type === 'cut') return null;
      const spec = registry.find(item => item.type === step.type && item.method === step.method), record = !dirty && trace[index];
      const stepNumber = steps.slice(0, index + 1).filter(item => item.type !== 'cut').length;
      return <article className={`ai-step ${step.enabled ? '' : 'is-skipped'}`} key={step.id}>
        <div className="ai-step-heading"><strong className="ai-step-number">{stepNumber}</strong>
          {step.type === 'despike' ? <span className="ai-step-title">{txt('去鬼峰', 'Despike')}</span> : <select aria-label={`${txt('步骤', 'Step')} ${index + 1} ${txt('算法', 'algorithm')}`} value={step.method} disabled={locked} onChange={e => { const next = registry.find(item => item.type === step.type && item.method === e.target.value); editStep(index, { method: next.method, params: defaults(next), reason: txt('用户更换算法', 'Algorithm replaced by user') }); }}>{registry.filter(item => item.type === step.type).map(item => <option key={item.method} value={item.method} disabled={item.available===false}>{systemText(item.label)}{item.available===false?`（${systemText(item.unavailable_reason)}）`:""}</option>)}</select>}
          <div className="ai-step-tools"><label className="ai-enable"><input type="checkbox" checked={step.enabled} disabled={locked} onChange={e => editStep(index, { enabled: e.target.checked })} />{txt('启用', 'On')}</label>
            <IconButton label={txt('查看该步曲线', 'Inspect step curves')} icon={Eye} disabled={!record} onClick={() => { setView(`step:${index}`); resultRef.current?.scrollIntoView({ block: 'start', behavior: 'smooth' }); }} />
          </div>
        </div><details className="ai-step-details"><summary>{txt('参数与说明', 'Parameters & rationale')}</summary><p className="ai-step-reason">{systemText(step.reason)}</p>
        {step.type === 'despike' ? <DespikeParameters params={step.params} onChange={params => editStep(index, { params })} disabled={locked || !step.enabled} /> : <div className="ai-params">{spec && Object.entries(spec.params).map(([key, field]) => <label key={key}>{systemText(field.label)}{field.options ? <select value={step.params[key]} disabled={locked || !step.enabled} onChange={e => editStep(index, { params: { ...step.params, [key]: e.target.value } })}>{field.options.map(option => <option key={option}>{option}</option>)}</select> : <input type="number" min={field.min} max={field.max} step={field.integer ? 1 : 'any'} value={step.params[key] ?? ''} disabled={locked || !step.enabled} onChange={e => editStep(index, { params: { ...step.params, [key]: e.target.value === '' ? null : Number(e.target.value) } })} />}</label>)}</div>}</details>
        {record && <div className="ai-step-compute">{record.status === 'skipped' ? txt('已跳过', 'Skipped') : record.reused ? txt('复用既有结果', 'Reused previous result') : txt('已重新计算', 'Recomputed')} · {record.duration_ms} ms{record.reused && <span> · {txt('来源版本', 'Source version')} V{task?.versions.findIndex(item => item.id === record.reused_from_version_id) + 1}</span>}</div>}
      </article>;
    })}</div>
  </section>;

  const resultPanel = <section className="ai-results" ref={resultRef}>
    <div className="ai-section-heading"><div><h2>{txt('处理结果', 'Result')}</h2><span className="ai-muted">{version ? `V${versionNumber} · ${status(version.status)}` : txt('原始数据', 'Original data')}</span></div><div className="ai-actions">
      <SpectrumExport original={task?.original} result={version?.status === 'completed' ? version.trace.at(-1)?.after : null} sourceName={task?.source_name} version={versionNumber} disabled={locked} resultDisabled={dirty || refinement.pending || version?.status !== 'completed'} onOriginalFile={() => download('original')} txt={txt} />
      <ShareResult key={version?.analysis_run_id} api={api} runId={version?.analysis_run_id} projects={projects} projectId={task?.project_id} disabled={locked || dirty || refinement.pending || version?.status !== 'completed'} txt={txt} />
    </div></div>
    {dirty && trace.length > 0 && <div className="ai-alert">{txt('当前曲线属于旧版本，方案修改尚未预览。', 'These curves belong to the previous version; edits have not been previewed.')}</div>}
    {version?.error && <div className="ai-alert error" role="alert">{systemText(version.error)}</div>}
    {running && <div className="ai-progress"><progress max={steps.length} value={trace.length} /><span>{trace.length}/{steps.length}</span><span>{systemText(steps[trace.length]?.label)}</span></div>}
    {despikeRecord?.details?.num_cosmic_rays > 0 && <div className="ai-despike-summary"><strong>{txt('去鬼峰', 'Despike')} · {despikeRecord.status === 'skipped' ? txt('已跳过', 'Skipped') : txt(`候选 ${despikeRecord.details?.num_cosmic_rays ?? 0} 处 · 修复 ${despikeRecord.details?.corrected_points ?? 0} 点 · 保留 ${despikeRecord.details?.protected_candidates ?? 0} 处`, `${despikeRecord.details?.num_cosmic_rays ?? 0} candidates · ${despikeRecord.details?.corrected_points ?? 0} points repaired · ${despikeRecord.details?.protected_candidates ?? 0} preserved`)}</strong><p className="ai-muted">{txt("请核对标记位置，避免误判真实窄峰。", "Check marked positions for real narrow peaks.")}</p><button disabled={dirty || despikeRecord.status === 'skipped'} onClick={() => setView(`step:${despikeIndex}`)}>{txt('查看去鬼峰对比', 'Inspect despiking')}</button>{despikeRecord.details?.details_truncated && <small>{txt('标记仅显示前 256 处，统计包含全部检出位置。', 'Only the first 256 candidates are marked; counts include all detections.')}</small>}</div>}
    <div className="ai-result-tools"><div className="ai-tabs"><button className={view === 'original' ? 'active' : ''} onClick={() => setView('original')}>{txt('原始', 'Original')}</button><button className={view === 'result' ? 'active' : ''} disabled={!trace.length} onClick={() => setView('result')}>{txt('结果', 'Result')}</button><button className={isResidual ? 'active' : ''} disabled={!residual} onClick={() => setView(`residual:${traceIndex ?? trace.length - 1}`)}>{txt('步骤残差', 'Step residual')}</button></div>
      {!!trace.length && <select aria-label={txt('查看处理步骤', 'View processing step')} value={selectedTrace ? `step:${traceIndex}` : ''} onChange={e => setView(e.target.value ? `${isResidual ? 'residual' : 'step'}:${e.target.value.split(':')[1]}` : 'result')}><option value="">{txt('查看每一步', 'Inspect each step')}</option>{trace.map((record, index) => <option key={index} value={`step:${index}`}>{index + 1}. {systemText(record.step.label)}{record.reused ? txt('（复用）', ' (Reused)') : record.status === 'skipped' ? txt('（跳过）', ' (Skipped)') : ''}</option>)}</select>}
    </div>
    <div className="ai-chart"><SpectralChart rawData={isResidual ? residual : view === 'original' ? task?.original : raw} processedData={view === 'original' || isResidual ? null : processed} baselineData={view === 'original' || isResidual ? null : processed?.baseline} rawLabel={isResidual ? txt('步骤残差', 'Step residual') : txt('处理前', 'Before')} processedLabel={txt('处理后', 'After')} height={350} dark={theme === 'dark'} horizontalLegend spikePoints={selectedTrace?.step.type === 'despike' && !isResidual && view !== 'original' ? selectedTrace.details?.cosmic_rays || [] : []} /></div>
    {metrics && <div className="ai-metrics"><span>{txt('数据点', 'Points')} <strong>{metrics.points}</strong></span><span>{txt('噪声比例估计', 'Noise ratio estimate')} <strong>{metrics.noise_ratio?.toFixed(4)}</strong></span><span>{txt('显著峰估计', 'Detected peaks')} <strong>{metrics.peak_count}</strong></span>{!!trace.length && <span>{txt('复用步骤', 'Reused steps')} <strong>{version?.reused_steps || 0}/{trace.length}</strong></span>}</div>}
    {!!warnings.length && <div className="ai-alert">{systemText(warnings.join(' '))}</div>}
    {version?.analysis_run_id && <Link className="ai-saved" to={`/analysis-history?run=${version.analysis_run_id}`}><CheckCircle2 size={16} />{txt('已记录 · 查看分析记录', 'Recorded · View analysis record')}</Link>}
    {version?.status === 'completed' && !dirty && !refinement.pending && <div className="ai-actions"><Link to={`/peak-fitting?task=${encodeURIComponent(task.id)}&version=${encodeURIComponent(version.id)}`}>{txt("分峰拟合", "Peak fitting")}<ArrowRight size={14} /></Link><Link to={`/spectral-unmixing?workflow=${encodeURIComponent(task.id)}&version=${encodeURIComponent(version.id)}`}><GitBranch size={15} />{txt('用于混合物解析', 'Use for mixture analysis')}<ArrowRight size={14} /></Link><Link to={`/library-matching?workflow=${encodeURIComponent(task.id)}&version=${encodeURIComponent(version.id)}`}><Database size={15} />{txt('用于库匹配', 'Use for library matching')}<ArrowRight size={14} /></Link><Link to={`/structure-generation?workflow=${encodeURIComponent(task.id)}&version=${encodeURIComponent(version.id)}`}><Sparkles size={15} />{txt('用于光谱到结构', 'Open in Spectrum to Structure')}<ArrowRight size={14} /></Link></div>}
  </section>;

  useQAExecutionInput('ai-analysis', { source: task ? { workflow_id: task.id, version_id: version?.id || '' } : null, settings: { steps, region: task && region.start !== '' && region.end !== '' ? region : undefined }, batch_id: uploadMode === 'batch' ? batch?.id : undefined, workflow_ids: uploadMode === 'batch' ? selectedTasks : undefined, project_id: task?.project_id || projectId || undefined, source_label: task?.source_name }, [], locked);

  return <div className="ai-workspace" ref={workspaceRef} data-qa-task={task?.id || ''} data-qa-version={version?.id || ''} data-qa-locked={locked || dirty || refinement.pending ? 'true' : 'false'} data-qa-state={JSON.stringify({ module: localize("智能光谱处理"), filename: task?.source_name, task_id: task?.id, version_id: version?.id, status: version?.status, stage: WORKFLOW_STAGES[stage], unsaved_changes: dirty, refinement_pending: refinement.pending, displayed_steps: steps, selected_step: selectedTrace?.step, completed_steps: trace.length, warnings: warnings.slice(0, 3), selected_band: region, view })}>
    <header className="ai-header"><div><h1><Sparkles size={22} />{txt('智能光谱处理', 'Intelligent Spectrum Processing')}</h1><span className="ai-muted">{config ? `${activeProvider} · ${config.model}` : txt('正在加载', 'Loading')} · {config?.provider === 'ollama' ? config.available ? txt('本地模型已就绪', 'Local model ready') : config.availability === 'model_missing' ? txt('模型尚未下载', 'Model not downloaded') : txt('Ollama 尚未启动', 'Ollama is offline') : config?.configured ? txt('已配置密钥', 'Key configured') : txt('本地规则', 'Local rules')}</span></div>
      <div className="ai-actions"><Link to="/analysis-history"><History size={16} />{txt('分析记录', 'Analysis records')}</Link><NewAnalysisButton disabled={Boolean(busy)} txt={txt} beforeReset={() => !(dirty || refinement.pending) || window.confirm(txt('放弃尚未应用的修改？', 'Discard unapplied changes?'))} /></div>
    </header>
    <nav className="ai-workflow-stages" aria-label={txt('分析流程', 'Analysis workflow')}>{WORKFLOW_STAGES.map(([zh, en], index) => {
      const Icon = stageIcons[index], disabled = locked || index > 0 && !task || index === 2 && !steps.length;
      return <button key={index} aria-current={stage === index ? 'step' : undefined} disabled={disabled} onClick={() => setStage(index)}><span className="ai-stage-number">{index + 1}</span><Icon size={16} /><span>{txt(zh, en)}</span></button>;
    })}</nav>
    {error && <div className="ai-alert error" role="alert">{systemText(error)}</div>}
    <div className="ai-layout"><main className="ai-main">
        {batch && batch.id === batchId && <BatchAnalysisPanel api={api} batch={batch} selected={selectedTasks.filter(id => batch.items.some(item => item.workflow_id === id))} template={version ? `${task?.source_name} · V${versionNumber}${dirty ? txt('（待应用）', ' (Not applied)') : ''}${refinement.pending ? txt('（调整待预览）', ' (Revision pending)') : ''}` : null} canExecute={regionValid} canRefine={hasCompleted && Boolean(version)} pendingRefinement={refinement.pending} txt={txt} locked={locked} busy={busy} onRefine={refineBatch} onToggle={id => setSelectedTasks(current => current.includes(id) ? current.filter(item => item !== id) : [...current, id])} onSelectAll={checked => setSelectedTasks(checked ? batch.items.filter(item => item.workflow_id).map(item => item.workflow_id) : [])} onView={selectTask} onExecute={executeBatch} onCancel={cancelBatch} />}
        {loading ? <div className="ai-empty"><Loader2 className="ai-spin" />{txt('正在加载', 'Loading')}</div> : <>
          {task && !pendingImport && <div className="ai-source-heading"><div><h2><FileText size={18} />{task.source_name}</h2><span className="ai-muted">{task.diagnostics.points} {txt('个点', 'points')} · {task.diagnostics.wavenumber_min.toFixed(1)}–{task.diagnostics.wavenumber_max.toFixed(1)} cm⁻¹</span></div><div className="ai-source-actions">{version && <select aria-label={txt('方案版本', 'Plan version')} value={version.id} disabled={locked} onChange={e => selectTask(task.id, e.target.value)}>{task.versions.map((item, index) => <option key={item.id} value={item.id}>V{index + 1} · {status(item.status)} · {item.metadata?.phase === 'preprocess' ? txt('默认预处理', 'Preprocessing') : txt('目标细调', 'Refinement')}</option>)}</select>}</div></div>}
          <div className="ai-current-stage"><span className="ai-stage-number">{stage + 1}</span><h2>{txt(...WORKFLOW_STAGES[stage])}</h2></div>
          {stage === 0 && <>
            <section className="ai-upload-stage"><div className="ai-upload-modes" role="radiogroup" aria-label={txt('上传方式', 'Upload mode')}><label><input type="radio" name="upload-mode" value="single" checked={uploadMode === 'single'} disabled={locked} onChange={() => setUploadMode('single')} /><FileText size={16} />{txt('单个数据', 'Single spectrum')}</label><label><input type="radio" name="upload-mode" value="batch" checked={uploadMode === 'batch'} disabled={locked} onChange={() => setUploadMode('batch')} /><FolderOpen size={16} />{txt('批量数据', 'Batch spectra')}</label></div>
              <div className="ai-source-controls"><input ref={fileRef} type="file" accept={SPECTRAL_ACCEPT} aria-label={txt('上传光谱', 'Upload spectrum')} hidden onChange={e => e.target.files[0] && newSource(null, e.target.files[0])} /><input ref={folderRef} type="file" webkitdirectory="" directory="" multiple aria-label={txt('上传光谱文件夹', 'Upload spectrum folder')} hidden onChange={e => e.target.files.length && uploadFolder(Array.from(e.target.files))} /><button className="ai-upload" disabled={locked || !config} onClick={() => uploadMode === 'single' ? fileRef.current.click() : folderRef.current.click()}>{busy === 'folder-upload' ? <Loader2 className="ai-spin" size={18} /> : uploadMode === 'single' ? <Upload size={18} /> : <FolderOpen size={18} />}{uploadMode === 'single' ? txt('上传光谱', 'Upload spectrum') : txt('上传文件夹', 'Upload folder')}<small>TXT · CSV · XLSX · JCAMP · WDF · WXD · L6M · NPG{uploadMode === 'batch' && ` · ${config?.max_batch_files || 100} ${txt('个文件', 'files')} / ${config?.max_batch_mb || 40} MB`}</small></button>
              {uploadMode === 'single' && <label>{txt('示例光谱', 'Demo spectrum')}<select aria-label={txt('示例光谱', 'Demo spectrum')} value="" disabled={locked || !config} onChange={e => e.target.value && newSource({ demo: e.target.value })}><option value="">{txt('选择示例', 'Select demo')}</option><option value="tutorial">Tutorial Raman</option><option value="bacteria">Bacteria</option><option value="ulf">ULF</option></select></label>}
              <label>{txt('项目', 'Project')}<select value={projectId} disabled={locked} onChange={e => setProjectId(e.target.value)}><option value="">{txt('独立分析', 'Standalone analysis')}</option>{projects.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
              {projectId && <div className="ai-project-import"><select aria-label={txt('项目光谱', 'Project spectrum')} disabled={locked} value={datasetId} onChange={e => setDatasetId(e.target.value)}><option value="">{txt('选择项目光谱', 'Select project spectrum')}</option>{datasets.map(item => <option key={item.id} value={item.id}>{item.display_name || item.filename}</option>)}</select><IconButton label={txt('导入', 'Import')} icon={Plus} disabled={locked || !datasetId} onClick={() => newSource({ dataset_id: datasetId })} /></div>}
            </div></section>
            {pendingImport && <SpectrumImportConfirmation inspection={pendingImport.inspection} isBatch={Boolean(pendingImport.files)} busy={working} txt={txt} onConfirm={confirmImport} onCancel={() => { setPendingImport(null); setError(''); }} />}
            {task && !pendingImport && <><section className="ai-source-check"><h2><CheckCircle2 size={18} />{txt('格式检查通过', 'Format check passed')}</h2><ImportReport metadata={task.diagnostics.source_check} onDownload={download} disabled={locked} /></section><section><h2>{txt('处理波段', 'Processing range')}</h2>{bandControls}{qualityPoints.length > 0 && <label className="quality-marker-toggle"><input type="checkbox" checked={showQualityMarkers} onChange={e => setShowQualityMarkers(e.target.checked)} />{txt('显示质量检查候选位置', 'Show quality screening markers')}</label>}<div className="ai-chart"><SpectralChart rawData={task.original} cutRange={regionValid ? [region.start, region.end] : null} height={350} dark={theme === 'dark'} horizontalLegend qualityPoints={showQualityMarkers ? qualityPoints : []} /></div>{recommendationMode}<div className="ai-actions ai-next"><button className="ai-primary" disabled={!regionValid || locked || !config} onClick={continueFromUpload}>{busy === 'recommend' ? <Loader2 size={16} className="ai-spin" /> : <ArrowRight size={16} />}{nextUploadStage !== null ? txt('继续当前分析', 'Continue analysis') : txt('生成预处理方案', 'Generate preprocessing plan')}</button></div></section></>}
          </>}
          {stage === 1 && task && <>
            <section className="ai-preprocess"><h2>{txt('默认预处理', 'Default preprocessing')}</h2>{(!version || phase !== 'preprocess') && <PreprocessingFlow steps={[]} txt={txt} />}{bandSummary}<div className="ai-recommend-options">{recommendationMode}{version && phase === 'preprocess' && <div className="ai-actions"><button disabled={locked || !regionValid || !config} onClick={() => recommend('preprocess')}>{busy === 'recommend' ? <Loader2 size={16} className="ai-spin" /> : <Sparkles size={16} />}{txt('重新推荐方案', 'Regenerate plan')}</button></div>}</div>{(!version || phase !== 'preprocess') && <div className="ai-actions"><button className="ai-primary" disabled={locked || !regionValid || !config} onClick={() => recommend('preprocess')}><Sparkles size={16} />{txt('生成预处理方案', 'Generate preprocessing plan')}</button></div>}</section>
            {clarification && <div className="ai-alert" role="status">{clarification}</div>}
            {version && phase === 'preprocess' && <>
              {!!candidates.length && <section className="ai-candidates"><details><summary>{txt('候选方案比较', 'Compare candidates')} · {candidates.length}</summary><p className="ai-muted">{txt("对比后选择合适参数", "Compare before choosing parameters")}</p><div className="ai-table-scroll"><table><thead><tr><th>{txt('方案', 'Candidate')}</th><th>{txt('评分', 'Score')}</th><th>{txt('峰保留率', 'Peak retention')}</th><th>{txt('降噪残差 RMS', 'Denoise residual RMS')}</th><th>{txt('噪声比例', 'Noise ratio')}</th></tr></thead><tbody>{candidates.map(item => <tr key={item.id} className={item.id === chosenCandidate?.id ? 'selected' : ''}><td><label><input type="radio" name="candidate" aria-label={systemText(`${txt('采用候选', 'Select candidate')} ${item.label}`)} checked={item.id === chosenCandidate?.id} disabled={locked || item.status !== 'valid' || dirty} onChange={() => chooseCandidate(item.id)} />{systemText(item.label)}</label>{item.error && <small className="ai-inline-error">{systemText(item.error)}</small>}</td><td>{item.score ?? '—'}</td><td>{item.peak_retention == null ? '—' : `${(item.peak_retention * 100).toFixed(0)}%`}</td><td>{item.denoise_residual_rms ?? '—'}</td><td>{item.noise_ratio?.toFixed(4) ?? '—'}</td></tr>)}</tbody></table></div></details>{chosenCandidate && !trace.length && <div className="ai-chart"><SpectralChart rawData={{ wavenumber: chosenCandidate.curves.wavenumber, intensity: chosenCandidate.curves.original }} processedData={{ wavenumber: chosenCandidate.curves.wavenumber, intensity: chosenCandidate.curves.processed }} height={350} horizontalLegend dark={theme === 'dark'} rawLabel={txt('原始', 'Original')} processedLabel={txt('候选结果', 'Candidate result')} /></div>}</section>}
              {planEditor}{(trace.length > 0 || running) && resultPanel}{planActions}
            </>}
          </>}
          {stage === 2 && task && <>
            {resultPanel}
            <div className="ai-actions ai-result-actions"><button disabled={locked || !hasCompleted} onClick={() => setRefining(value => !value)}><SlidersHorizontal size={16} />{refining ? txt('收起调整', 'Close refinement') : txt('继续调整', 'Refine result')}</button></div>
            {refining && <section className="ai-goal"><label htmlFor="analysis-goal">{txt('分析目标', 'Analysis goal')}</label><textarea id="analysis-goal" value={refinementGoal} maxLength={2000} disabled={locked} placeholder={txt('去掉背景、适度降噪、保留主要峰；也可指定禁止操作', 'Describe the desired result and prohibited operations')} onChange={e => setRefinementGoal(e.target.value)} />{bandSummary}<label htmlFor="ai-feedback">{txt('调整反馈', 'Revision feedback')}</label><textarea ref={feedbackRef} id="ai-feedback" value={feedback} maxLength={2000} disabled={locked} placeholder={txt('例如：峰变弱了，减小平滑强度，其他步骤保持不变', 'Example: peaks are weaker; reduce smoothing and keep other steps')} onChange={e => setFeedback(e.target.value)} />{consent}<div className="ai-actions"><button className="ai-primary" disabled={locked || !hasCompleted || !refinement.canSubmit || !regionValid || !refinement.pending && !dirty} onClick={() => recommend('refine')}>{busy === 'recommend' ? <Loader2 size={16} className="ai-spin" /> : <Sparkles size={16} />}{batchId ? txt('更新批量方案并预览', 'Update batch plan & preview') : txt('更新方案并预览', 'Update plan & preview')}</button><button disabled={locked} onClick={() => setRefining(false)}><Eye size={16} />{txt('收起调整', 'Close refinement')}</button></div>{clarification && <div className="ai-alert" role="status">{clarification}</div>}</section>}
            {refinement.pending && !refining && <div className="ai-alert" role="status">{txt('调整需求待应用', 'Revision not applied')}<button disabled={locked} onClick={() => setRefining(true)}>{txt('继续调整', 'Refine result')}</button></div>}
            <details className="ai-plan-details" open={dirty || needsExecution}><summary>{txt('算法与参数', 'Algorithms & parameters')} · {steps.filter(s => s.type !== 'cut').length} {txt('步', 'steps')}</summary>{planEditor}</details>
            {planActions}
          </>}
        </>}
      </main></div>
  </div>;
}
