import { API_BASE as BASE } from '../apiBase';
import { systemText, getLocale, localize } from '../locale.js';
import { useQAExecutionInput } from '../components/qaExecution';
import MixtureResult from '../components/MixtureResult';
import {NewAnalysisButton,useWorkspaceList} from '../components/AnalysisWorkspaces';
import { FileExport } from '../components/ResultActions';
import React, { useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import { Link, useSearchParams } from 'react-router-dom';
import Plot from 'react-plotly.js';
import { ArrowRight, Check, ChevronRight, Cpu, Download, FileText, FlaskConical, GitBranch, Info, Layers, Loader2, Plus, RefreshCw, Square, Upload, Waves, X } from 'lucide-react';
import { apiErrorMessage, useAuth } from '../auth';
import { usePreferences } from '../i18n';
import SpectralChart from '../components/SpectralChart';
import SpectrumImportConfirmation from '../components/SpectrumImportConfirmation';
import ModuleUploadHistory from '../components/ModuleUploadHistory';
import SavedAnalysisRecords from '../components/SavedAnalysisRecords';
import ModuleInputActions from '../components/ModuleInputActions';
import { moduleSpectrum, spectrumReferenceKey } from '../components/moduleSpectrum';
import { SPECTRAL_ACCEPT } from '../components/ImportReport';
import { workflowSpectrum } from './structureGeneration';
import { activeTask, appendStandard, commonBand, readyModels } from './mixtureAnalysis';
import './StructureGenerationPage.css';
import './MixtureAnalysisPage.css';


function SpectrumPicker({ api, txt, tasks, title, onSelect, disabled, onError, onLoading }) {
  usePreferences();
  const ref = useRef(), sequence = useRef(0);
  const [tab, setTab] = useState('upload'), [pending, setPending] = useState(null), [busy, setBusy] = useState(false);
  const [task, setTask] = useState(null), [version, setVersion] = useState('');
  const [uploadRevision, setUploadRevision] = useState('');
  const locked = disabled || busy || !!pending;
  useEffect(() => { onLoading(busy || !!pending); }, [busy, pending, onLoading]);
  useEffect(() => () => onLoading(false), [onLoading]);
  useEffect(() => () => { sequence.current += 1; }, []);
  async function upload(file, confirmed = false, spectrumIndex) {
    if (!file) return;
    setBusy(true); onError('');
    try {
      const form = new FormData(); form.append('file', file); form.append('confirm_conversion', String(confirmed));
      if (spectrumIndex != null) form.append('spectrum_index', String(spectrumIndex));
      const { data } = await api.post('/ssnet/sources/upload', form);
      if (data.requires_confirmation) { setPending({ file, inspection: data }); return; }
      setPending(null);
      setUploadRevision(data.id); onSelect(moduleSpectrum(data, 'ssnet'));
    } catch (err) { onError(apiErrorMessage(err)); }
    finally { setBusy(false); if (ref.current) ref.current.value = ''; }
  }
  async function load(id, vid) {
    const currentSequence = ++sequence.current;
    setBusy(true); onError('');
    try {
      const current = (await api.get(`/ai-workflows/${id}`)).data;
      const completed = current.versions.filter(v => v.status === 'completed');
      if (!completed.length) throw new Error(txt('请先完成并保存预处理。', 'Complete and save preprocessing first.'));
      const chosen = vid || completed.at(-1).id;
      const result = (await api.get(`/ai-workflows/${id}/versions/${chosen}`)).data;
      if (currentSequence !== sequence.current) return;
      setTask(current); setVersion(chosen); onSelect(workflowSpectrum(current, result));
    } catch (err) { if (currentSequence === sequence.current) onError(apiErrorMessage(err, err.message)); }
    finally { if (currentSequence === sequence.current) setBusy(false); }
  }
  return <div className="mx-picker">
    <div className="sg-source-tabs" role="tablist" aria-label={systemText(title)}><button role="tab" aria-selected={tab === 'upload'} disabled={locked} onClick={() => setTab('upload')}><Upload size={14} />{txt('本地上传', 'Upload')}</button><button role="tab" aria-selected={tab === 'processed'} disabled={locked} onClick={() => setTab('processed')}><Layers size={14} />{txt('预处理结果', 'Processed result')}</button></div>
    {tab === 'upload' ? <><input hidden type="file" ref={ref} accept={SPECTRAL_ACCEPT} onChange={e => upload(e.target.files?.[0])} /><button className="sg-upload" disabled={locked} onClick={() => ref.current?.click()}>{busy ? <Loader2 className="sg-spin" size={23} /> : <Upload size={23} />}<strong>{systemText(title)}</strong><span>TXT · CSV · XLSX · JCAMP · WDF · WXD · L6M · NPG</span></button></> : <div className="sg-source-selectors"><label>{txt('预处理任务', 'Preprocessing task')}<select aria-label={`${title} · ${txt('任务', 'Task')}`} disabled={locked} value={task?.id || ''} onChange={e => e.target.value && load(e.target.value)}><option value="">{txt('选择已保存的预处理任务', 'Choose a saved preprocessing task')}</option>{tasks.map(t => <option key={t.id} value={t.id}>{t.source_name}</option>)}</select></label>{task && <label>{txt('保存版本', 'Saved version')}<select disabled={locked} aria-label={`${title} · ${txt('版本', 'Version')}`} value={version} onChange={e => load(task.id, e.target.value)}>{task.versions.filter(v => v.status === 'completed').map(v => <option key={v.id} value={v.id}>V{task.versions.findIndex(c => c.id === v.id)+1}</option>)}</select></label>}</div>}
    {tab === 'upload' && <ModuleUploadHistory api={api} module="ssnet" revision={uploadRevision} txt={txt} disabled={locked} onLoading={setBusy} onError={onError} onSelect={data => { setUploadRevision(data.id); onSelect(moduleSpectrum(data, 'ssnet')); }} />}
    {pending && <SpectrumImportConfirmation inspection={pending.inspection} busy={busy} txt={txt} onConfirm={index => upload(pending.file, true, index)} onCancel={() => setPending(null)} />}
  </div>;
}

export default function MixtureAnalysisPage() {
  const { token } = useAuth(), { language, theme } = usePreferences();
  const txt = (zh, en) => language === 'zh' ? zh : en;
  const api = useMemo(() => axios.create({ baseURL: BASE, headers: { Authorization: `Bearer ${token}` }, timeout: 30000 }), [token]);
  const [search, setSearch] = useSearchParams();
  const [mode, setMode] = useState('predict'), [config, setConfig] = useState(null), [tasks, setTasks] = useState([]), [jobs, setJobs] = useState([]), [job, setJob] = useState(null);
  const [standards, setStandards] = useState([]), [name, setName] = useState(''), [standardUnit, setStandardUnit] = useState(false);
  const [source, setSource] = useState(null), [unit, setUnit] = useState(false), [modelId, setModelId] = useState('');
  const [points, setPoints] = useState(1024), [epochs, setEpochs] = useState(100), [samples, setSamples] = useState(3200), [start, setStart] = useState(''), [end, setEnd] = useState('');
  const [prepared, setPrepared] = useState(null), [validationError, setValidationError] = useState(''), [validating, setValidating] = useState(false);
  const [error, setError] = useState(''), [busy, setBusy] = useState(false), [pickerBusy, setPickerBusy] = useState(false);
  const models = readyModels(jobs), band = commonBand(standards), requestedJob = search.get('job');
  const trainingRecords = jobs.filter(record => record.kind === 'train' && record.status !== 'failed');
  const failedTraining = job?.kind === 'train' && job.status === 'failed';
  const currentModel = models.find(m => m.id === modelId), active = activeTask(job), locked = busy || active || pickerBusy;
  const requestedWorkflow = search.get('workflow'), requestedVersion = search.get('version');
  const statusText = status => ({ queued:txt('排队中','Queued'), running:txt('运行中','Running'), completed:txt('已完成','Completed'), failed:txt('失败','Failed'), cancelled:txt('已停止','Stopped') }[status] || status);
  const stageText = stage => ({ queued:txt('等待本地算力','Waiting for local worker'), unet:txt('训练 U-Net','Training U-Net'), random_forest_samples:txt('生成随机森林样本','Generating RF samples'), random_forest_training:txt('训练随机森林','Training random forest'), saving:txt('保存模型','Saving model'), loading_model:txt('加载标准品模型','Loading model'), extracting:txt('提取目标成分','Extracting target'), completed:txt('已完成','Completed') }[stage] || txt('准备任务','Preparing task'));

  async function refresh() { const { data } = await api.get('/ssnet/jobs'); setJobs(data); return data; }
  useWorkspaceList(api,'/ai-workflows',setTasks,setError);
  useWorkspaceList(api,'/ssnet/jobs',setJobs,setError);
  useEffect(() => {
    let cancelled = false;
    api.get('/ssnet/config').then(({data}) => { if (!cancelled) setConfig(data); }).catch(err => { if (!cancelled) setError(apiErrorMessage(err)); });
    return () => { cancelled = true; };
  }, [api]);
  useEffect(() => {
    if (!requestedWorkflow) return;
    let cancelled = false;
    async function handoff() {
      try {
        const current = (await api.get(`/ai-workflows/${requestedWorkflow}`)).data;
        const selected = requestedVersion || current.versions.filter(v => v.status === 'completed').at(-1)?.id;
        if (!selected) throw new Error(txt('请先完成并保存预处理。','Complete and save preprocessing first.'));
        const version = (await api.get(`/ai-workflows/${requestedWorkflow}/versions/${selected}`)).data;
        if (!cancelled) { setMode('predict'); setSource(workflowSpectrum(current, version)); setUnit(false); }
      } catch (err) { if (!cancelled) setError(apiErrorMessage(err, err.message)); }
    }
    handoff(); return () => { cancelled = true; };
  }, [requestedWorkflow, requestedVersion, api]);
  useEffect(() => {
    if (!requestedJob) { setJob(null); return; }
    let cancelled = false;
    api.get(`/ssnet/jobs/${requestedJob}`).then(({data}) => { if (!cancelled) setJob(data); }).catch(err => { if (!cancelled) setError(apiErrorMessage(err)); });
    return () => { cancelled = true; };
  }, [requestedJob, api]);
  useEffect(() => {
    if (!failedTraining || job.id !== requestedJob) return;
    setError(job.error || txt('标准品模型训练失败。', 'Standard model training failed.'));
    setJob(null);
    const next = new URLSearchParams(search);
    next.delete('job');
    setSearch(next, {replace:true});
  }, [failedTraining, job, requestedJob, search, setSearch, language]);
  const pendingJobs = jobs.some(activeTask);
  useEffect(() => {
    if (!active && !pendingJobs) return;
    let cancelled = false, timer;
    async function poll() {
      try {
        const list = (await api.get('/ssnet/jobs')).data;
        if (!cancelled) setJobs(list);
        if (requestedJob) {
          const {data} = await api.get(`/ssnet/jobs/${requestedJob}`);
          if (!cancelled) setJob(data);
        }
      } catch (err) { if (!cancelled) setError(apiErrorMessage(err)); }
      if (!cancelled) timer = setTimeout(poll, 2000);
    }
    timer = setTimeout(poll, 1000); return () => { cancelled = true; clearTimeout(timer); };
  }, [active, pendingJobs, requestedJob, api]);
  const trainingPayload = { name:name.trim(), standards:standards.map(s => s.reference), unit_confirmed:standardUnit, points, epochs, samples_per_epoch:samples, start:start === '' ? null : Number(start), end:end === '' ? null : Number(end) };
  const predictionPayload = { ...source?.reference, model_id:modelId, unit_confirmed:unit };
  const payloadKey = JSON.stringify(mode === 'train' ? trainingPayload : predictionPayload);
  useEffect(() => {
    setPrepared(null); setValidationError('');
    const canCheck = mode === 'train' ? standards.length && name.trim() && standardUnit : source && unit && modelId;
    if (!canCheck) { setValidating(false); return; }
    let cancelled = false;
    setValidating(true);
    const timer = setTimeout(async () => {
      try { const {data} = await api.post(`/ssnet/${mode}/validate`, JSON.parse(payloadKey)); if (!cancelled) setPrepared(data); }
      catch (err) { if (!cancelled) setValidationError(apiErrorMessage(err)); }
      finally { if (!cancelled) setValidating(false); }
    }, 250);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [mode, payloadKey, api]);
  async function submit() {
    setBusy(true); setError('');
    try {
      const {data} = await api.post(`/ssnet/${mode}`, mode === 'train' ? trainingPayload : predictionPayload);
      setJob(data); setSearch({job:data.id},{replace:true}); await refresh();
    } catch (err) { setError(apiErrorMessage(err)); }
    finally { setBusy(false); }
  }
  async function cancel() {
    setBusy(true); setError('');
    try { const {data} = await api.post(`/ssnet/jobs/${job.id}/cancel`,{}); setJob(data); await refresh(); }
    catch (err) { setError(apiErrorMessage(err)); }
    finally { setBusy(false); }
  }
  async function download(format) {
    try {
      const {data} = await api.get(`/ssnet/jobs/${job.id}/download`,{params:{format},responseType:'blob'});
      const url = URL.createObjectURL(data), a=document.createElement('a'); a.href=url; a.download=`ssnet_${job.kind}.${format}`; a.click(); setTimeout(()=>URL.revokeObjectURL(url),1000);
    } catch (err) { setError(apiErrorMessage(err)); }
  }
  function chooseSource(value) { setSource(value); setUnit(false); setError(''); }
  const reason = mode === 'train' ? !standards.length ? txt('先添加同一种物质的标准品谱图。','Add standard spectra for one material first.') : !name.trim() ? txt('请填写标准品物质名称。','Enter the material name.') : !standardUnit ? txt('请确认标准品横轴单位。','Confirm the standard axis unit.') : ''
    : !models.length ? txt('尚无可用模型，请先建立一个标准品模型。','No model is available. Train a standard model first.') : !modelId ? txt('请选择标准品模型。','Choose a model.') : !source ? txt('请上传或选择待解析的混合谱。','Choose the mixture spectrum.') : !unit ? txt('请确认混合谱横轴单位。','Confirm the mixture axis unit.') : '';
  const output = job?.kind === 'predict' && job.status === 'completed' ? job.result : null;

  useQAExecutionInput('spectral-unmixing', { source: source?.reference ? { ...source.reference, module: source.reference.module || 'ssnet' } : null, standards: standards.map(s => ({ ...s.reference, module: s.reference.module || 'ssnet' })), model_id: modelId || undefined, unit_confirmed: mode === 'train' ? standardUnit : unit, settings: { ...(mode === 'train' ? { name:name.trim(), points, epochs, samples_per_epoch: samples, start: start === '' ? null : Number(start), end: end === '' ? null : Number(end) } : {}), mode, standard_unit_confirmed:standardUnit, mixture_unit_confirmed:unit }, source_label: source?.name }, [], locked);

  return <div className="sg-workspace mx-workspace" data-qa-run={job?.analysis_run_id || undefined} data-qa-state={JSON.stringify({ module: localize("混合物解析"), mode, job_id: job?.id, status: job?.status, progress: job?.progress, selected_settings: { modelId, points, epochs, samples, start, end }, standard_count: standards.length, error: error?.slice(0, 200), result: output ? { model_name: output.model_name, rf_score: output.rf_score, duration_seconds: output.duration_seconds } : null })}>
    <header className="sg-header"><div><div className="sg-eyebrow">RAMANCLOUD <ChevronRight size={12}/> SSNET</div><h1><GitBranch size={25}/>{txt('混合物解析','Mixture analysis')}</h1><p>{txt('以标准品为依据，从混合光谱中提取目标成分信号。','Extract target signals from mixture spectra using reference standards.')}</p></div><span className="mx-local"><Cpu size={14}/>{txt('本地 CPU','Local CPU')}</span><NewAnalysisButton disabled={busy} txt={txt} /></header>
    <nav className="sg-flow" aria-label={txt('混合物解析流程','Mixture analysis workflow')}>{[['标准品','Standards'],['建立模型','Train model'],['混合谱','Mixture'],['目标成分','Target signal']].map(([zh,en],i)=><div key={en}><span>{i+1}</span>{txt(zh,en)}{i<3&&<ChevronRight size={15} className="sg-flow-arrow"/>}</div>)}</nav>
    {error&&<div className="sg-alert is-error" role="alert">{systemText(error)}<button onClick={()=>setError('')} aria-label={txt('关闭错误','Dismiss error')}><X size={14}/></button></div>}
    <div className="sg-layout mx-layout"><div className="sg-input-column">
      <section className="sg-panel"><div className="mx-mode" role="tablist" aria-label={txt('混合物解析工作模式','Mixture analysis mode')}><button role="tab" aria-selected={mode==='predict'} onClick={()=>setMode('predict')}><FlaskConical size={16}/>{txt('解析混合谱','Analyze mixture')}</button><button role="tab" aria-selected={mode==='train'} onClick={()=>setMode('train')}><Plus size={16}/>{txt('建立标准品模型','Train a standard model')}</button></div>
        {mode==='train' ? <>
          <div className="sg-panel-heading"><h2><span>01</span>{txt('添加标准品','Add standards')}</h2><span className="sg-pill">{standards.length} {txt('条','spectra')}</span></div>
          <label>{txt('标准品物质名称','Standard material name')}<input aria-label={txt('标准品物质名称','Standard material name')} disabled={locked} value={name} maxLength={80} placeholder={txt('例如：乙醇；一组只放同一种物质','e.g. Ethanol; one material per model')} onChange={e=>setName(e.target.value)}/></label>
          <p className="sg-help">{txt("同一物质可添加多条重复测量谱，不同物质分别建模。","Add replicates of one substance; train separate models for different substances.")}</p>
          <SpectrumPicker key="standards" api={api} txt={txt} tasks={tasks} title={txt('添加标准品谱图','Add a standard spectrum')} disabled={locked||standards.length>=20} onError={setError} onLoading={setPickerBusy} onSelect={s=>{setStandards(old=>appendStandard(old,s));setStandardUnit(false);}}/>
          <ul className="mx-standards">{standards.map((s,i)=><li key={spectrumReferenceKey(s)}><FileText size={16}/><div><strong>{s.name}</strong><span>{s.spectrum.wavenumber.length} {txt('点','points')} · {Math.min(s.spectrum.wavenumber[0],s.spectrum.wavenumber.at(-1)).toFixed(1)}–{Math.max(s.spectrum.wavenumber[0],s.spectrum.wavenumber.at(-1)).toFixed(1)} cm⁻¹</span></div><button disabled={locked} aria-label={`${txt('移除标准品','Remove standard')} ${i+1}`} onClick={()=>{setStandards(old=>old.filter((_,n)=>n!==i));setStandardUnit(false);}}><X size={14}/></button></li>)}</ul>
          {standards.length>0&&<><label className="sg-checkbox"><input type="checkbox" disabled={locked} checked={standardUnit} onChange={e=>setStandardUnit(e.target.checked)}/>{txt('确认标准品横轴为拉曼位移 cm⁻¹','Confirm standards use Raman shift in cm⁻¹')}</label><p className="sg-help">{band?txt(`共同波段：${band.start.toFixed(1)}–${band.end.toFixed(1)} cm⁻¹。默认使用此范围。`,`Common range: ${band.start.toFixed(1)}–${band.end.toFixed(1)} cm⁻¹; used by default.`):txt('这些标准品没有共同波段，请检查文件。','These standards have no common range.')}</p></>}
          <div className="mx-subheading"><h3>{txt('训练设置','Training settings')}</h3><span><Cpu size={13}/> CPU</span></div>
          <label>{txt('模型采样点数','Model grid points')}<select aria-label={txt('SSnet 模型点数','SSnet grid points')} value={points} disabled={locked} onChange={e=>setPoints(Number(e.target.value))}>{[512,1024,2048,2500].map(n=><option key={n} value={n}>{n} {txt('点','points')}</option>)}</select></label>
          <p className="sg-help">{txt("训练波段须在所有标准谱范围内。","Choose a range covered by every standard.")}</p>
          <details className="sg-preparation"><summary>{txt('高级训练设置','Advanced training settings')}</summary><div className="mx-fields"><label>{txt('起始波数（留空自动）','Start (blank for auto)')}<input aria-label={txt('SSnet 起始波数','SSnet start')} type="number" value={start} disabled={locked} onChange={e=>setStart(e.target.value)}/></label><label>{txt('截止波数（留空自动）','End (blank for auto)')}<input aria-label={txt('SSnet 截止波数','SSnet end')} type="number" value={end} disabled={locked} onChange={e=>setEnd(e.target.value)}/></label><label>{txt('训练轮数','Epochs')}<input aria-label={txt('SSnet 训练轮数','SSnet epochs')} type="number" min="1" max="200" value={epochs} disabled={locked} onChange={e=>setEpochs(Number(e.target.value))}/></label><label>{txt('每轮增强样本数','Augmented samples / epoch')}<input aria-label={txt('SSnet 每轮样本数','SSnet samples per epoch')} type="number" min="32" max="3200" value={samples} disabled={locked} onChange={e=>setSamples(Number(e.target.value))}/></label></div></details>
        </> : <>
          <div className="sg-panel-heading"><h2><span>01</span>{txt('选择标准品模型','Select a standard model')}</h2><span className="sg-pill">{models.length} {txt('个可用','available')}</span></div>
          {models.length ? <><label>{txt('目标物质模型','Target model')}<select aria-label={txt('SSnet 标准品模型','SSnet standard model')} value={modelId} disabled={locked} onChange={e=>setModelId(e.target.value)}><option value="">{txt('请选择已训练的模型','Choose a trained model')}</option>{models.map(m=><option key={m.id} value={m.id}>{m.name} · {new Date(m.created_at).toLocaleString(getLocale())} · {m.id.slice(0,6)}</option>)}</select></label>{currentModel&&<div className="mx-model-card"><Check size={17}/><div><strong>{currentModel.name}</strong><span>{currentModel.grid.start.toFixed(1)}–{currentModel.grid.end.toFixed(1)} cm⁻¹ · {currentModel.grid.points} {txt('点','points')}</span><small>{txt("模型已保存","Model saved")}</small></div></div>}</> : <div className="mx-no-model"><Layers size={27}/><strong>{txt('还没有标准品模型','No standard models yet')}</strong><p>{txt("请先建立一个标准品模型。","Train a standard model first.")}</p><button onClick={()=>setMode('train')}><Plus size={14}/>{txt('建立第一个模型','Train the first model')}</button></div>}
          <div className="mx-subheading"><h3>{txt('上传混合谱','Choose mixture spectrum')}</h3></div>
          <SpectrumPicker key="mixture" api={api} txt={txt} tasks={tasks} title={txt('上传待解析的混合谱','Upload a mixture spectrum')} onSelect={chooseSource} disabled={locked} onError={setError} onLoading={setPickerBusy}/>
          {source&&<div className="sg-selected-source"><div className="sg-file-heading"><FileText size={18}/><div><strong>{source.name}</strong><span>{txt('输入光谱已保存','Input spectrum retained')}</span></div></div><div className="sg-spectrum"><SpectralChart rawData={source.spectrum} height={205} rawLabel={txt('待解析混合谱','Mixture input')} dark={theme==='dark'} showToolbar={false}/></div><label className="sg-checkbox"><input type="checkbox" disabled={locked} checked={unit} onChange={e=>setUnit(e.target.checked)}/>{txt('确认混合谱横轴为拉曼位移 cm⁻¹','Confirm mixture uses Raman shift in cm⁻¹')}</label><ModuleInputActions api={api} module="ssnet" source={source} txt={txt} disabled={locked} onError={setError} /></div>}
          <p className="sg-help">{txt("混合谱需覆盖所选模型的波段。","The mixture must cover the selected model’s range.")}</p>
        </>}
        {validating&&<p className="sg-help" role="status">{txt('正在检查输入…','Checking input…')}</p>}{validationError&&<p className="sg-field-error" role="alert">{systemText(validationError)}</p>}{prepared&&<p className="sg-ready">{txt(`检查通过 · ${prepared.grid.start.toFixed(1)}–${prepared.grid.end.toFixed(1)} cm⁻¹ · ${prepared.grid.points} 点`,`Checked · ${prepared.grid.start.toFixed(1)}–${prepared.grid.end.toFixed(1)} cm⁻¹ · ${prepared.grid.points} points`)}</p>}
        <div className="sg-generate-actions"><button className="sg-primary" disabled={locked||validating||!prepared||!config?.ready} onClick={submit}>{mode==='train'?<Cpu size={16}/>:<FlaskConical size={16}/>} {mode==='train'?txt('开始训练并保存模型','Train and save model'):txt('开始解析混合谱','Analyze mixture')}</button>{(reason||!config?.ready)&&<p className="sg-generation-blocker">{reason||txt('本地算法环境尚未就绪。','The local algorithm environment is not ready.')}</p>}</div>
      </section>
    </div><section className="sg-panel mx-results"><div className="sg-panel-heading"><h2><span>02</span>{txt('任务与解析结果','Tasks and results')}</h2><button className="mx-refresh" aria-label={txt('刷新 SSnet 记录','Refresh SSnet records')} disabled={busy} onClick={()=>refresh().catch(err=>setError(apiErrorMessage(err)))}><RefreshCw size={14}/></button></div>
      <SavedAnalysisRecords api={api} module="ssnet" job={job} txt={txt} disabled={locked} onError={setError} onOpen={id => setSearch({ job: id }, { replace: true })} />
      {trainingRecords.length>0&&<label>{txt('标准品模型记录','Standard model records')}<select aria-label={txt('标准品模型记录','Standard model records')} value={job?.kind==='train'&&!failedTraining?job.id:''} onChange={e=>setSearch(e.target.value?{job:e.target.value}:{},{replace:true})}><option value="">{txt('选择标准品模型','Select a reference model')}</option>{trainingRecords.map(j=><option key={j.id} value={j.id}>{txt('训练','Train')} · {j.name} · {statusText(j.status)} · {j.id.slice(0,6)}</option>)}</select></label>}
      {(!job||failedTraining)?<div className="sg-empty-results mx-empty"><div className="sg-empty-atom"><GitBranch size={53} strokeWidth={1.3}/></div><h3>{txt("暂无解析结果","No extraction results yet")}</h3><p>{txt("建立模型后，上传混合谱开始解析。","Train a model, then upload a mixture to start extraction.")}</p><div className="mx-result-legend"><span><i/>{txt('混合谱','Mixture')}</span><span><i/>{txt('目标提取谱','Extracted target')}</span><span><i/>{txt('估计背景','Estimated background')}</span></div><small>{txt('SSnet · U-Net ECA + Random Forest','SSnet · U-Net ECA + Random Forest')}</small></div>:<>
        <div className="mx-job-heading"><div><strong>{job.name}</strong><span>{job.kind==='train'?txt('标准品模型训练','Standard model training'):txt('混合谱目标提取','Mixture target extraction')} · {new Date(job.created_at).toLocaleString(getLocale())}</span></div><span className={`mx-status is-${job.status}`}>{statusText(job.status)}</span></div>
        {activeTask(job)&&<div className="mx-progress"><div><Loader2 size={16} className="sg-spin"/><strong>{stageText(job.progress.stage)}</strong><span>{Math.floor(job.progress.percent||0)}%</span></div><progress aria-label={txt('SSnet 任务进度','SSnet progress')} max="100" value={job.progress.percent||0}/>{job.progress.epoch&&<p>Epoch {job.progress.epoch}/{job.progress.epochs} · {txt('本轮样本','Epoch samples')} {job.progress.batch_samples}/{job.progress.samples_per_epoch}</p>}<p>{txt("任务在后台运行，可离开页面。","The task continues in the background.")}</p><button disabled={busy} onClick={cancel}><Square size={13}/>{txt('停止此任务','Stop this task')}</button></div>}
        {job.status==='failed'&&<div className="sg-alert is-error" role="alert">{systemText(job.error)}</div>}{job.status==='cancelled'&&<div className="mx-compute-note"><Info size={17}/><p>{txt("任务已停止，已保存的模型可继续使用。","Task stopped; saved models remain available.")}</p></div>}
        {job.kind==='train'&&job.status==='completed'&&<div className="mx-training-done"><Check size={30}/><h3>{txt('标准品模型已保存','Standard model saved')}</h3><p>{job.input.prepared.grid.start.toFixed(1)}–{job.input.prepared.grid.end.toFixed(1)} cm⁻¹ · {job.input.prepared.grid.points} {txt('点','points')}</p><p>{txt(`${job.input.sources.length} 条标准品 · ${job.input.settings.epochs} 轮训练`,`${job.input.sources.length} standards · ${job.input.settings.epochs} epochs`)}</p><button className="sg-primary" onClick={()=>{setModelId(job.id);setMode('predict');}}>{txt('使用此模型解析混合谱','Analyze a mixture with this model')}<ArrowRight size={14}/></button><details><summary>{txt('训练损失记录','Training loss record')}</summary><pre>{job.result.loss_history.map((loss,i)=>`Epoch ${i+1}: ${loss.toFixed(6)}`).join('\n')}</pre></details></div>}
        {output&&<MixtureResult result={output} dark={theme==='dark'} txt={txt}/>}
        <div className="mx-downloads"><FileExport txt={txt} actions={[{label:txt('任务记录 JSON','Job record JSON'),run:()=>download('json')},...(output?[{label:txt('解析光谱 CSV','Extracted spectra CSV'),run:()=>download('csv')}]:[])]} /></div>
      </>}
    </section></div><footer className="sg-footer"><span>SSnet</span><span>{txt("仅支持已建模目标的定向提取","Targeted extraction using trained models")}</span></footer>
  </div>;
}
