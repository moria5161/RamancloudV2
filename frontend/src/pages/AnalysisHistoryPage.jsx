import { API_BASE as BASE } from '../apiBase';
import { systemText, getLocale, localize } from '../locale.js';
import { useQAExecutionInput } from '../components/qaExecution';
import ModelHistoryResult, {MODEL_ANALYSIS_TYPES,historyTabs,ModelHistorySettings} from '../components/ModelHistoryResult';
import HyperspectralHistoryResult from '../components/HyperspectralHistoryResult';
import React, { useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import SpectralChart from '../components/SpectralChart';
import AnalysisRecordSteps, {recordMethodLabel,recordStepLabel} from '../components/AnalysisRecordSteps';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowLeft, Download, History, RefreshCw, Search, RotateCcw, Trash2, CheckCircle2 } from 'lucide-react';
import { apiErrorMessage, useAuth } from '../auth';
import { usePreferences } from '../i18n';
import { libraryName } from '../libraryNames.js';
import HistoryRecordList, { historyRecordTitle, taskKey } from '../components/HistoryRecordList';
import PendingAnalysisRecord from '../components/PendingAnalysisRecord';
import { historyView, recordDeletionGroups } from '../analysisRecords';
import {spectrumExportTargets} from '../spectrumExport';
import BatchSpectrumExport from '../components/BatchSpectrumExport';
import { SpectrumExport, ShareResult, FileExport } from '../components/ResultActions';
import './DataWorkspace.css';
const labels = {
  spectrum: '单光谱',
  hyperspectral: '高光谱',
  library_matching: '库匹配',
  structure_generation: '光谱到结构',
  mixture_analysis: '混合物解析',
  peak_fitting: '分峰拟合',
};
export const readable = value => localize(labels[value] || String(value ?? '—'));
export function curve(value) {
  const y = value?.intensity || value?.mean_spectrum;
  return Array.isArray(value?.wavenumber) && value.wavenumber.length > 0 && Array.isArray(y) && y.length === value.wavenumber.length ? {
    x: value.wavenumber,
    y
  } : null;
}
const date = value => value ? new Date(value).toLocaleString(getLocale()) : '—';
export function saveFile(blob, name) {
  const url = URL.createObjectURL(blob),
    a = document.createElement('a');
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export default function AnalysisHistoryPage() {
  const {
      token,
      user
    } = useAuth(),
    {
      theme
    } = usePreferences(),
    navigate = useNavigate();
  const api = useMemo(() => axios.create({
    baseURL: BASE,
    headers: {
      Authorization: `Bearer ${token}`
    }
  }), [token]);
  const [params] = useSearchParams();
  const [runs, setRuns] = useState([]),
    [projects, setProjects] = useState([]),
    [selected, setSelected] = useState(params.get('run') || '');
  const [pending, setPending] = useState([]), [batches, setBatches] = useState([]), [recordFilter, setRecordFilter] = useState('all');
  const [processingMode, setProcessingMode] = useState('single');
  const [selectionMode, setSelectionMode] = useState(false), [checked, setChecked] = useState([]), [notice, setNotice] = useState('');
  const [query, setQuery] = useState(''),
    [type, setType] = useState(params.get('type') || 'spectrum'),
    [project, setProject] = useState(params.get('project') || ''),
    [tab, setTab] = useState('overview'),
    [mode, setMode] = useState('compare');
  const [error, setError] = useState(''),
    [busy, setBusy] = useState(false),
    [loading, setLoading] = useState(true);
  const request = useRef(0),
    [days, setDays] = useState(''),
    [mobileDetail, setMobileDetail] = useState(!!params.get('run'));
  const [wave, setWave] = useState(''),
    [pixel, setPixel] = useState(null), [dataPage, setDataPage] = useState(0), [detail, setDetail] = useState(null);
  const view = historyView({runs, pending, batches, type, processingMode, status: recordFilter, project, days, query});
  const {visible} = view;
  const batchView = type === 'spectrum' && processingMode === 'batch';
  const deletionGroups = recordDeletionGroups(visible, [...runs, ...pending, ...visible.filter(record => record.kind === 'batch')], user.id);
  const selectionGroups = selectionMode === 'export' ? deletionGroups.map(group => ({...group, reason:'', deletable:spectrumExportTargets(group.records).length > 0})) : deletionGroups;
  const selectable = selectionGroups.filter(group => group.deletable);
  const chosen = selectable.filter(group => checked.includes(group.key));
  useEffect(() => {setChecked([]);setNotice('');}, [type, processingMode, recordFilter, project, days, query]);
  useEffect(() => {setSelectionMode(false);}, [type, processingMode]);
  const entry = visible.find(r => r.id === selected) || visible[0];
  const run = detail?.id === entry?.id ? detail : null;
  const versions = run ? [...runs, ...pending.filter(record => record.result_available)].filter(r => taskKey(r) === taskKey(run)).sort((a, b) => b.created_at.localeCompare(a.created_at)) : [];
  async function load() {
    const sequence = ++request.current;
    setLoading(true);
    setError('');
    try {
      const r = await api.get('/analysis-runs', {
        params: {summary: true, project_id: params.get('project') || undefined}
      });
      const tasks = await api.get('/analysis-records/tasks');
      if (sequence === request.current) { setRuns(r.data.data.runs); setPending(tasks.data.items); setBatches(tasks.data.batches); }
    } catch (e) {
      if (sequence === request.current) setError(apiErrorMessage(e));
    } finally {
      if (sequence === request.current) setLoading(false);
    }
  }
  useEffect(() => {
    load();
    api.get('/projects').then(r => setProjects(r.data.data.projects)).catch(e => setError(apiErrorMessage(e)));
  }, [api, params.get('project')]);
  useEffect(() => {
    setSelected(params.get('run') || '');
    setMobileDetail(!!params.get('run'));
    setRecordFilter('all');
  }, [params.get('run')]);
  const linkedRun = runs.find(record => record.id === params.get('run'));
  useEffect(() => {
    if (!linkedRun) return;
    setType(linkedRun.analysis_type);
    setProcessingMode(linkedRun.batch_id ? 'batch' : 'single');
  }, [linkedRun?.id, linkedRun?.analysis_type, linkedRun?.batch_id]);
  useEffect(() => {
    let ignore = false;
    setDetail(null);
    if (entry && !entry.kind) api.get(`/analysis-runs/${entry.id}`).then(r => { if (!ignore) setDetail(r.data.data.run); }).catch(e => { if (!ignore) setError(apiErrorMessage(e)); });
    else if (entry?.result_available && entry.kind === 'workflow') {
      Promise.all([api.get(`/ai-workflows/${entry.workflow_id}`), api.get(`/ai-workflows/${entry.workflow_id}/versions/${entry.version_id}`)]).then(([taskResponse, versionResponse]) => {
        const task = taskResponse.data, version = versionResponse.data;
        const final = version.trace?.at(-1)?.after;
        if (!final) throw new Error(localize("此处理版本缺少光谱结果，请重新处理。"));
        if (!ignore) setDetail({...entry, from_workflow:true, user_id:user.id, input:task.original,
          steps:version.steps, history:version.trace, result:{...final,ai_workflow_id:entry.workflow_id,ai_version_id:version.id,
            ai_version_number:task.versions.findIndex(item => item.id === version.id) + 1}});
      }).catch(error => {if (!ignore) setError(apiErrorMessage(error));});
    }
    return () => { ignore = true; };
  }, [api, entry?.id, entry?.updated_at, entry?.is_shared]);
  useEffect(() => {
    if (!pending.some(item => ['queued','running','previewing'].includes(item.status)) && !batches.some(batch => batch.counts.queued || batch.counts.running)) return;
    const timer = setInterval(load, 4000); return () => clearInterval(timer);
  }, [pending.map(item => item.id + item.status).join(','), batches.map(batch => `${batch.id}:${batch.counts.queued}:${batch.counts.running}`).join(',')]);
  useEffect(() => {
    setTab('overview');
    setMode('compare');
    setPixel(null);
    setDataPage(0);
    setWave('');
  }, [run?.id]);

  async function act(fn) {
    setBusy(true);
    setError('');
    try {
      await fn();
    } catch (e) {
      if (e.response?.data instanceof Blob) {
        try {
          setError(JSON.parse(await e.response.data.text()).detail);
        } catch {
          setError(localize("文件暂不可用，请重新处理或核对源数据。"));
        }
      } else setError(apiErrorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  async function download(kind) {
    await act(async () => {
      const r = await api.get(run.from_workflow ? `/ai-workflows/${run.workflow_id}/download` : `/analysis-runs/${run.id}/resources/${kind}`, {
        responseType: 'blob', params: {wavenumber: wave || undefined, ...(run.from_workflow ? {kind,version_id:run.version_id} : {})}
      });
      const name = r.headers['content-disposition']?.match(/filename\*=UTF-8''([^;]+)/i);
      const ext = {bundle:'zip',report:'pdf',png:'png',svg:'svg',json:'json'}[kind] || (run.analysis_type === 'hyperspectral' ? 'mat' : 'csv');
      saveFile(r.data, name ? decodeURIComponent(name[1]) : `${run.title}_${kind}.${ext}`);
    });
  }
  async function deleteSelected() {
    if (!chosen.length) return;
    const targets = chosen.flatMap(group => group.targets);
    const resultCount = chosen.flatMap(group => group.records).filter(record => !record.kind || record.result_available).length;
    const taskCount = targets.filter(target => target.kind === 'workflow').length;
    const batchCount = targets.filter(target => target.kind === 'batch_member').length;
    if (!window.confirm(`${localize("删除选中的 ")}${chosen.length}${localize(" 个任务？包含 ")}${resultCount}${localize(" 条结果版本")}${taskCount ? `${localize("和 ")}${taskCount}${localize(" 个未处理任务（含上传文件）")}` : ''}${batchCount ? `；${batchCount}${localize(" 个批次文件及其处理版本也将移除")}` : ''}${localize("，删除后无法恢复。")}`)) return;
    setBusy(true); setError(''); setNotice('');
    let deleted = 0;
    const failures = [];
    try {
      for (const group of chosen) for (const target of group.targets) {
        try {await api.delete(target.path); deleted++;}
        catch (error) {failures.push(`${group.title}：${apiErrorMessage(error)}`);}
      }
      await load();
      setChecked([]);
      setSelectionMode(false);
      setNotice(`${localize("已删除 ")}${deleted}${localize(" 条记录")}${failures.length ? `，${failures.length}${localize(" 条未删除")}` : ''}`);
      if (failures.length) setError(failures.join('；'));
    } finally {setBusy(false);}
  }
  function deleteBatch(batch) {
    if (!window.confirm(`${localize("删除批次“")}${batch.name}${localize("”及其中全部光谱、处理版本？已共享结果须先取消共享，删除后无法恢复。")}`)) return;
    act(async () => {await api.delete(`/ai-workflow-batches/${batch.id}`);setSelected('');setChecked([]);await load();});
  }
  function replay() {
    act(async () => {
      if (run.analysis_type === 'spectrum' && run.user_id === user.id && run.result.ai_workflow_id) {
        navigate(`/ai-analysis?task=${run.result.ai_workflow_id}&version=${run.result.ai_version_id}`);
      } else if (run.analysis_type === 'spectrum') {
        const r = await api.post('/ai-workflows/source', {
          history_run_id: run.id
        });
        navigate(`/ai-analysis?task=${r.data.id}`);
      } else if (run.analysis_type === 'hyperspectral') {
        localStorage.setItem('ramancloud_replay_hyperspectral', JSON.stringify({
          title: run.title,
          source_name: run.source_name,
          steps: run.steps
        }));
        navigate('/hyperspectral');
      } else navigate(`/${run.analysis_type === 'peak_fitting' ? 'peak-fitting' : run.analysis_type === 'mixture_analysis' ? 'spectral-unmixing' : run.analysis_type === 'library_matching' ? 'library-matching' : 'structure-generation'}?job=${encodeURIComponent(run.result.job_id)}`);
    });
  }
  const raw = curve(run?.input), processed = curve(run?.result), steps = run?.steps || [];
  const candidates = run?.result?.candidates || [];
  const modelResult = MODEL_ANALYSIS_TYPES.includes(run?.analysis_type);
  const qaExportRefs = chosen.length ? (type === 'spectrum' ? spectrumExportTargets(chosen.flatMap(g => g.records), selected) : chosen.flatMap(g => g.records.filter(r => !r.kind).map(r => ({ run_id: r.id })))) : [];
  useQAExecutionInput('analysis-history', { source: chosen.length ? null : run?.from_workflow ? { workflow_id: entry?.workflow_id, version_id: entry?.version_id || '' } : run?.id ? { run_id: run.id } : null, run_ids: chosen.length ? qaExportRefs.filter(r=>r.run_id).map(r=>r.run_id) : run && !run.from_workflow ? [run.id] : [], export_refs: qaExportRefs, settings: { analysis_type: type }, project_id: project || run?.project_id || undefined, source_label: run?.source_name }, [], busy || loading);

  return <div className={`dw-page history-page ${mobileDetail ? 'dw-mobile-detail' : ''}`} data-qa-run={run?.from_workflow ? '' : run?.id || ''} data-qa-task={entry?.kind === 'workflow' ? entry.workflow_id : ''} data-qa-version={entry?.version_id || ''} data-qa-state={JSON.stringify({ module: localize("分析记录"), record_filter: recordFilter, analysis_type: type, processing_mode: type === 'spectrum' ? processingMode : undefined, selected_record: entry ? {id:entry.id,kind:entry.kind,status:entry.status,title:historyRecordTitle(entry)} : null, run_id: run?.from_workflow ? undefined : run?.id, source_name: run?.source_name, tab, mode: modelResult ? undefined : mode, selected_wavenumber: wave, selected_pixel: pixel ? {x:pixel.x,y:pixel.y} : null, loading, error: error?.slice(0, 200) })}><header className="dw-header"><h1><History size={25} />{localize("分析记录 ")}<small>{view.count}{localize(" 个任务")}</small></h1><button title={localize("刷新")} aria-label={localize("刷新")} onClick={load}><RefreshCw size={17} /></button></header>
    <div className="dw-toolbar"><label className="dw-search"><Search size={16} /><input aria-label={localize("搜索分析记录")} placeholder={localize("搜索样品或文件")} value={query} onChange={e => setQuery(e.target.value)} /></label><select aria-label={localize("项目筛选")} value={project} onChange={e => setProject(e.target.value)}><option value="">{localize("全部项目")}</option>{projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select><select aria-label={localize("分析类型")} value={type} onChange={e => {setType(e.target.value);setSelected('');setRecordFilter('all');setMobileDetail(false);}}>{['spectrum', 'hyperspectral', 'peak_fitting', 'mixture_analysis', 'library_matching', 'structure_generation'].map(k => <option key={k} value={k}>{readable(k)}</option>)}</select><select aria-label={localize("时间范围")} value={days} onChange={e => setDays(e.target.value)}><option value="">{localize("全部时间")}</option><option value="7">{localize("近 7 天")}</option><option value="30">{localize("近 30 天")}</option><option value="90">{localize("近 90 天")}</option></select></div>
    {error && <p className="dw-error" role="alert">{systemText(error)}</p>}
    {notice && <p className="dw-muted" role="status">{systemText(notice)}</p>}
    {type === 'spectrum' && <nav className="record-processing-modes" aria-label={localize("单光谱处理方式")}>{[['single',localize("单个处理")],['batch',localize("批量处理")]].map(([key,label]) => <button key={key} aria-pressed={processingMode === key} onClick={() => {setProcessingMode(key);setSelected('');setMobileDetail(false);}}>{systemText(label)}</button>)}</nav>}
    <div className="record-list-controls"><nav className="record-filters" aria-label={localize("记录状态")}>{[['all',localize("全部")],['completed',localize("已处理")],['pending',localize("未处理")]].map(([key,label])=><button key={key} aria-pressed={recordFilter===key} onClick={()=>{setRecordFilter(key);setSelected('');setMobileDetail(false);}}>{systemText(label)}</button>)}</nav>
      {!selectionMode ? <div className="dw-actions">{batchView && <button disabled={busy || !spectrumExportTargets(visible).length} onClick={() => {setChecked([]);setSelectionMode('export');}}><Download size={15}/>{localize("批量导出")}</button>}<button disabled={busy || !selectable.length} onClick={() => setSelectionMode('delete')}><Trash2 size={15} />{localize("批量删除")}</button></div> : <div className="dw-bulk-actions"><label><input type="checkbox" aria-label={localize("全选当前筛选记录")} checked={!!selectable.length && chosen.length === selectable.length} ref={node => {if (node) node.indeterminate = chosen.length > 0 && chosen.length < selectable.length;}} disabled={busy || !selectable.length} onChange={event => setChecked(event.target.checked ? selectable.map(group => group.key) : [])} />{localize("全选当前筛选")}</label><span>{localize("已选 ")}{chosen.length}{localize(" 个任务")}</span>{selectionMode === 'export' ? <BatchSpectrumExport api={api} targets={spectrumExportTargets(visible.filter(record => chosen.some(group => group.key === taskKey(record))),selected)} name="selected_spectra" disabled={busy} label={localize("导出所选")} /> : <button className="dw-delete-selected" disabled={busy || !chosen.length} onClick={deleteSelected}><Trash2 size={15} />{busy ? localize("正在删除…") : localize("删除所选")}</button>}<button disabled={busy} onClick={() => {setSelectionMode(false);setChecked([]);}}>{localize("取消")}</button></div>}
    </div>
    <div className="dw-history-layout"><aside className="dw-history-list" aria-label={localize("分析记录")}>{loading && <p>{localize("正在加载…")}</p>}{!loading && !visible.length && <p>{localize("暂无符合条件的记录")}</p>}<HistoryRecordList runs={visible} batches={batchView ? view.batches : []} selectionMode={selectionMode} checked={chosen.map(group => group.key)} deletionGroups={selectionGroups} disabled={busy} exportApi={api} onDeleteBatch={deleteBatch} onCheck={(key, value) => setChecked(previous => value ? [...new Set([...previous, key])] : previous.filter(item => item !== key))} selected={entry?.id} onSelect={id => {
          setSelected(id);
          setMobileDetail(true);
        }} /></aside>
      <main className="dw-detail"><button className="dw-mobile-back" onClick={() => setMobileDetail(false)}><ArrowLeft size={16} />{localize("返回记录")}</button>{run ? <><header className="dw-result-heading"><div><h2>{historyRecordTitle(run)}</h2><p>{run.project_name || localize("个人分析")} · {run.source_name} · {date(run.created_at)}</p></div><div className="dw-actions">{['spectrum','mixture_analysis'].includes(run.analysis_type) ? <SpectrumExport original={raw ? {wavenumber:raw.x,intensity:raw.y} : null} result={processed ? {wavenumber:processed.x,intensity:processed.y} : null} sourceName={run.source_name} version={run.result.ai_version_number} disabled={busy} onOriginalFile={() => download('original')} advanced={run.from_workflow ? [] : [{label:localize("过程包 ZIP"),run:()=>download('bundle')},{label:localize("报告 PDF"),run:()=>download('report')},{label:localize("SVG 图像"),run:()=>download('svg')}]} /> : <FileExport disabled={busy} actions={run.analysis_type==='peak_fitting' ? [{label:localize('峰参数 CSV'),run:()=>download('data')},{label:localize('全部曲线 TSV'),run:()=>download('curves')},{label:localize('PNG 图像'),run:()=>download('png')},{label:localize('完整记录 ZIP'),run:()=>download('bundle')},{label:localize('完整结果 JSON'),run:()=>download('json')}] : modelResult ? [{label:localize("候选数据 CSV"),run:()=>download('data')},{label:localize("完整结果 JSON"),run:()=>download('json')},{label:localize("完整记录 ZIP"),run:()=>download('bundle')}] : [{label:localize("结果数据 MAT"),run:()=>download('data')},{label:localize("原始文件"),run:()=>download('original')},{label:localize("PNG 图像"),run:()=>download('png')},{label:localize("完整记录 ZIP"),run:()=>download('bundle')},{label:localize("报告 PDF"),run:()=>download('report')}]} />}{!run.from_workflow && <ShareResult key={run.id} api={api} runId={run.id} projects={projects} projectId={run.project_id} disabled={busy || run.user_id !== user.id} onShared={load} />}<button title={localize("重新处理")} aria-label={localize("重新处理")} disabled={busy} onClick={replay}><RotateCcw size={17} /></button><button title={localize("删除记录")} aria-label={localize("删除记录")} disabled={busy || run.user_id !== user.id || run.is_shared} onClick={() => {
                if (window.confirm(entry.batch_id ? localize("删除这条光谱及其全部处理版本？批次中的其他文件会保留；已共享的结果需先取消共享。") : localize("永久删除此分析记录？已共享的结果需先取消共享。"))) act(async () => {
                  const key = run.result?.ai_workflow_id;
                  await api.delete(entry.batch_id && key ? `/ai-workflow-batches/${entry.batch_id}/items/${key}` : `/analysis-runs/${run.id}`);
                  await load();
                });
              }}><Trash2 size={17} /></button>{!run.from_workflow && run.user_id === user.id && <button disabled={busy} onClick={() => {
                const title = window.prompt(localize("修改分析记录名称"), run.title);
                if (title?.trim()) act(async () => { await api.patch(`/analysis-runs/${run.id}`, {title: title.trim()}); await load(); });
              }}>{localize("修改名称")}</button>}</div></header>
      <nav className="dw-tabs" aria-label={localize("分析详情")}>{historyTabs(run.analysis_type).map(([key, title]) => <button key={key} aria-pressed={tab === key} onClick={() => setTab(key)}>{systemText(title)}</button>)}</nav>
      {run.project_id && run.source_dataset_id && <button onClick={() => navigate(`/projects?project=${encodeURIComponent(run.project_id)}&dataset=${encodeURIComponent(run.source_dataset_id)}`)}>{localize("查看来源文件")}</button>}
      {versions.length > 1 && <label className="dw-version-select">{localize("分析版本 ")}<select aria-label={localize("分析版本")} value={run.id} onChange={e => setSelected(e.target.value)}>{versions.map((r, i) => <option key={r.id} value={r.id}>{localize("版本 ")}{versions.length - i} · {date(r.created_at)}</option>)}</select></label>}
      {tab === 'overview' && (modelResult ? <ModelHistoryResult run={run} api={api} dark={theme==='dark'} onError={setError}/> : run.analysis_type==='hyperspectral' ? <HyperspectralHistoryResult key={`${run.id}:${params.get('wavenumber') || ''}`} initialWavenumber={params.get('wavenumber')} run={run} api={api} dark={theme==='dark'} onModeChange={setMode} onWavenumberChange={setWave} onPixelChange={setPixel}/> : <>
        <div className="dw-result-grid"><section className="dw-chart"><div className="dw-heading"><h3>{localize("处理结果")}</h3><div className="dw-actions">{[['compare',localize("叠加对比")],['original',localize("原始")],['processed',localize("处理后")]].map(([key,title])=><button key={key} aria-pressed={mode===key} onClick={()=>setMode(key)}>{systemText(title)}</button>)}</div></div>
          <SpectralChart rawData={mode==='processed'||!raw?null:run.input} processedData={mode==='original'||!processed?null:run.result} baselineData={mode==='original'||!processed?null:run.result.baseline} height={390} dark={theme==='dark'} horizontalLegend rawLabel={localize("处理前")} processedLabel={localize("处理后")}/>
          {mode!=='processed' && !raw && <p className="dw-muted">{localize('此记录缺少原始光谱。')}</p>}
          {mode!=='original' && !processed && <p className="dw-muted">{localize('此记录缺少处理后光谱。')}</p>}
        </section><aside className="dw-process-summary"><h3>{localize("处理过程")}</h3>{steps.map((step,index)=><p key={index}><CheckCircle2 size={16}/><span>{recordStepLabel(step.type)}<small>{recordMethodLabel(step.method,step.type)}</small></span></p>)}<button onClick={()=>setTab('process')}>{localize("查看参数")}</button></aside></div>
        <p className="dw-facts">{localize("单光谱 · 数据点：")}{processed?.x.length || raw?.x.length || '—'}</p>
      </>)}
      {tab === 'process' && (modelResult ? <ModelHistorySettings run={run}/> : <section><h3>{localize("执行记录")}</h3><AnalysisRecordSteps steps={steps} history={run.history}/></section>)}
      {tab === 'files' && (['library_matching','structure_generation'].includes(run.analysis_type) ? <section><h3>{localize("候选数据")}</h3><div className="dw-table"><table><thead><tr><th>{localize("排序")}</th><th>{localize("名称 / 分子式")}</th><th>SMILES</th><th>{localize("得分")}</th></tr></thead><tbody>{candidates.map((candidate,index)=><tr key={candidate.id || candidate.class_id || index}><td>{candidate.rank || index+1}</td><td>{run.analysis_type === 'library_matching' ? libraryName(candidate) : candidate.name || candidate.formula || '—'}</td><td>{candidate.smiles || '—'}</td><td>{candidate.model_score ?? candidate.matching_score ?? candidate.generation_score ?? '—'}</td></tr>)}</tbody></table></div></section> : <section><h3>{localize("数值预览（每页 100 点）")}</h3>{processed ? <><div className="dw-table"><table><thead><tr><th>{localize("拉曼位移 (cm⁻¹)")}</th><th>{localize("处理后强度")}</th></tr></thead><tbody>{processed.x.slice(dataPage*100, (dataPage+1)*100).map((x, i) => <tr key={i}><td>{x}</td><td>{processed.y[dataPage*100+i]}</td></tr>)}</tbody></table></div><div className="dw-actions"><button disabled={!dataPage} onClick={() => setDataPage(p => p-1)}>{localize("上一页")}</button><span>{localize("第 ")}{dataPage+1} / {Math.max(1,Math.ceil(processed.x.length/100))}{localize(" 页")}</span><button disabled={(dataPage+1)*100 >= processed.x.length} onClick={() => setDataPage(p => p+1)}>{localize("下一页")}</button></div></> : <p>{localize("请下载结果文件查看完整数据。")}</p>}{run.analysis_type==='hyperspectral' && <p className="dw-muted">{localize("此处为平均光谱，完整数组可导出 MAT 文件。")}</p>}</section>)}


      </> : entry?.kind ? <PendingAnalysisRecord item={entry} api={api} onDeleted={load} /> : <p className="dw-empty">{entry ? localize("正在读取结果…") : localize("暂无记录。上传并处理光谱后可在此继续或查看。")}</p>}</main></div></div>;
}
