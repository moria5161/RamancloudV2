import { systemText, getLocale, localize } from '../locale.js';
import { useQAExecutionInput } from '../components/qaExecution';
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import Plot from 'react-plotly.js';
import { Database, Download, FolderKanban, Plus, Pencil, RefreshCw, Search, Trash2, Upload, Users, X, Play, History } from 'lucide-react';
import { apiErrorMessage, useAuth } from '../auth';
import { usePreferences } from '../i18n';
import QualityReport from '../components/QualityReport';
import SpectrumImportConfirmation from '../components/SpectrumImportConfirmation';
import ProjectCollaboration, { ProjectInvitations } from '../components/ProjectCollaboration';
import './DataWorkspace.css';
import './ProjectWarehouse.css';
const BASE = `${import.meta.env.BASE_URL.replace(/\/$/, '')}/api`;
const blank = {
  name: '',
  description: '',
  category: ''
};
function Modal({
  title,
  close,
  children
}) {
  usePreferences();
  const ref = useRef(null);
  useEffect(() => {
    const previous = document.activeElement,
      dialog = ref.current;
    dialog.showModal();
    return () => {
      dialog.close();
      previous?.focus();
    };
  }, []);
  return <dialog ref={ref} className="pw-modal" onCancel={e => {
    e.preventDefault();
    close();
  }} aria-labelledby="pw-modal-title"><div className="dw-heading"><h2 id="pw-modal-title">{systemText(title)}</h2><button onClick={close} title={localize("Close / 关闭")} aria-label={localize("Close / 关闭")}><X size={18} /></button></div>{children}</dialog>;
}
export default function ProjectDataPage() {
  const {
    token,
    user
  } = useAuth();
  const {
    language,
    theme
  } = usePreferences();
  const navigate = useNavigate();
  const txt = (zh, en) => language === 'zh' ? zh : en;
  const api = useMemo(() => axios.create({
    baseURL: BASE,
    headers: {
      Authorization: `Bearer ${token}`
    }
  }), [token]);
  const [routeParams] = useSearchParams();
  const [projects, setProjects] = useState([]),
    [pid, setPid] = useState(routeParams.get('project') || '');
  const [assets, setAssets] = useState([]),
    [runs, setRuns] = useState([]);
  const [query, setQuery] = useState(''),
    [search, setSearch] = useState(''),
    [type, setType] = useState(''),
    [uploader, setUploader] = useState('');
  const [tab, setTab] = useState('raw'),
    [selected, setSelected] = useState(null);
  const [modal, setModal] = useState(''),
    [draft, setDraft] = useState(blank),
    [edit, setEdit] = useState(null);
  const [files, setFiles] = useState([]),
    [uploadType, setUploadType] = useState('auto');
  const [busy, setBusy] = useState(false),
    [loading, setLoading] = useState(false),
    [error, setError] = useState('');
  const [preview, setPreview] = useState(null),
    [previewError, setPreviewError] = useState(''),
    [previewLoading, setPreviewLoading] = useState(false);
  const [picked, setPicked] = useState([]),
    [pendingImport, setPendingImport] = useState(null);
  const request = useRef(0);
  const project = projects.find(p => p.id === pid);
  const manager = project?.my_role === 'admin' || project?.owner_id === user.id;
  const loadProjects = useCallback(async () => {
    const {
      data
    } = await api.get('/projects');
    setProjects(data.data.projects);
    setPid(current => data.data.projects.some(p => p.id === current) ? current : data.data.projects[0]?.id || '');
  }, [api]);
  const loadAssets = useCallback(async () => {
    const version = ++request.current;
    if (!pid) {
      setAssets([]);
      setRuns([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    const results = await Promise.allSettled([api.get(`/projects/${pid}/datasets`), api.get('/analysis-runs', {
      params: {
        project_id: pid, summary: true
      }
    })]);
    if (request.current !== version) return;
    setAssets(results[0].status === 'fulfilled' ? results[0].value.data.data.datasets : []);
    if (results[0].status === 'fulfilled') setPicked(old => old.filter(id => results[0].value.data.data.datasets.some(asset => asset.id === id)));
    setRuns(results[1].status === 'fulfilled' ? results[1].value.data.data.runs : []);
    const failed = results.find(r => r.status === 'rejected');
    if (failed) setError(apiErrorMessage(failed.reason));
    setLoading(false);
  }, [api, pid]);
  useEffect(() => {
    loadProjects().catch(e => setError(apiErrorMessage(e)));
  }, [loadProjects]);
  useEffect(() => {
    setModal('');
    setSelected(routeParams.get('dataset') || null);
    setSearch('');
    setType('');
    setUploader('');
    setAssets([]);
    setRuns([]);
    loadAssets();
    return () => {
      request.current++;
    };
  }, [loadAssets]);
  async function act(fn) {
    if (busy) return;
    setBusy(true);
    setError('');
    try {
      await fn();
    } catch (e) {
      setError(apiErrorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  const historyLink = rid => `/analysis-history?project=${encodeURIComponent(pid)}&run=${encodeURIComponent(rid)}`;
  const storedRuns = new Set(assets.map(a => a.metadata?.analysis_run_id).filter(Boolean).map(String));
  const allRows = [...assets.filter(a => a.data_kind === tab), ...(tab === 'processed' ? runs.filter(r => !storedRuns.has(String(r.id))).map(r => ({
    ...r,
    id: `legacy-${r.id}`,
    runId: r.id,
    display_name: r.title,
    owner_username: r.username,
    owner_id: r.user_id,
    data_type: r.analysis_type,
    metadata: {
      analysis_run_id: r.id,
      source_name: r.source_name
    },
    legacy: true
  })) : [])];
  const rows = allRows.filter(a => (!search || `${a.display_name} ${a.filename || ''} ${a.metadata?.source_name || ''}`.toLowerCase().includes(search.toLowerCase())) && (!type || a.data_type === type) && (!uploader || a.owner_username === uploader));
  const current = selected && allRows.find(a => a.id === selected);
  useEffect(() => {
    setPicked([]);
  }, [pid, tab]);
  useEffect(() => {
    let ignore = false;
    setPreview(null);
    setPreviewError('');
    if (!current) return;
    setPreviewLoading(true);
    const request = current.legacy ? api.get(`/analysis-runs/${current.runId}`).then(r => r.data.data.run.result) : api.get(`/datasets/${current.id}/preview`).then(r => r.data);
    request.then(data => {
      if (!ignore) setPreview(data);
    }).catch(e => {
      if (!ignore) setPreviewError(apiErrorMessage(e));
    }).finally(() => {
      if (!ignore) setPreviewLoading(false);
    });
    return () => {
      ignore = true;
    };
  }, [api, pid, current?.id]);
  const check = a => a.legacy ? txt('旧记录', 'Legacy record') : a.metadata?.analysis_run_id ? txt('平台结果', 'Saved result') : a.metadata?.parse_status === 'failed' ? txt('无法解析', 'Cannot parse') : a.metadata?.parse_status !== 'ok' ? txt('未检查', 'Not screened') : a.metadata?.quality_check?.issues?.length || a.metadata?.warnings?.length ? txt('需确认', 'Review needed') : txt('格式通过', 'Format checked');
  const typeName = value => ({
    spectrum: txt('单光谱', 'Spectrum'),
    mapping: txt('高光谱', 'Hyperspectral'),
    hyperspectral: txt('高光谱', 'Hyperspectral'),
    unknown: txt('未知', 'Unknown')
  })[value] || value || '—';
  async function download(a, standardized = false) {
    const response = await api.get(standardized ? `/datasets/${a.id}/preview?download=true` : a.legacy ? `/analysis-runs/${a.runId}/download` : `/datasets/${a.id}/download`, {
      responseType: 'blob'
    });
    const url = URL.createObjectURL(response.data),
      link = document.createElement('a');
    link.href = url;
    link.download = standardized ? (a.data_type === 'spectrum' ? 'standardized.csv' : 'standardized.mat') : a.filename || a.result_filename || a.display_name;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  function startSingle(asset, confirmed = false) {
    act(async () => {
      const r = await api.post('/ai-workflows/source', {
        dataset_id: asset.id,
        confirm_conversion: confirmed
      });
      if (r.data.requires_confirmation) setPendingImport({
        inspection: r.data,
        asset
      });else {
        setPendingImport(null);
        navigate(`/ai-analysis?task=${r.data.id}`);
      }
    });
  }
  function startBatch(chosen, confirmed = false) {
    act(async () => {
      if (chosen.some(a => a.file_size > 4 * 1024 * 1024) || chosen.reduce((n, a) => n + a.file_size, 0) > 40 * 1024 * 1024) throw new Error(localize("批量处理每个文件最多 4 MB，总计最多 40 MB。"));
      const form = new FormData();
      for (const [index, asset] of chosen.entries()) {
        const r = await api.get(`/datasets/${asset.id}/download`, {
          responseType: 'blob'
        });
        form.append('files', r.data, asset.filename);
        form.append('paths', `project_batch/${index + 1}_${asset.filename}`);
        form.append('dataset_ids', asset.id);
      }
      form.append('project_id', pid);
      form.append('confirm_conversion', String(confirmed));
      const r = await api.post('/ai-workflow-batches/upload', form);
      if (r.data.requires_confirmation) setPendingImport({
        inspection: r.data,
        isBatch: true,
        assets: chosen
      });else {
        setPendingImport(null);
        const first = r.data.items.find(i => i.workflow_id);
        navigate(`/ai-analysis?batch=${r.data.id}${first ? `&task=${first.workflow_id}` : ''}`);
      }
    });
  }
  function downloadPicked() {
    act(async () => {
      const r = await api.get(`/projects/${pid}/archive`, {
        params: {
          ids: picked.join(',')
        },
        responseType: 'blob'
      });
      const url = URL.createObjectURL(r.data),
        a = document.createElement('a');
      a.href = url;
      a.download = `${project.name}_${tab}.zip`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    });
  }
  function remove(a) {
    const rid = a.metadata?.analysis_run_id;
    if (!window.confirm(rid ? txt('取消此结果的项目共享？保留个人记录和已有处理所需的来源文件。', 'Remove this result from the project warehouse? Private analysis history and original data are retained. Members lose this warehouse entry.') : txt('永久删除此文件？已被处理记录引用的文件不能删除。', 'Permanently delete this file? Referenced files cannot be deleted.'))) return;
    act(async () => {
      await api.delete(rid ? `/analysis-runs/${rid}/warehouse` : `/datasets/${a.id}`);
      setSelected(null);
      await loadAssets();
      await loadProjects();
    });
  }
  async function saveProject(e) {
    e.preventDefault();
    await act(async () => {
      if (modal === 'new') {
        const {
          data
        } = await api.post('/projects', draft);
        await loadProjects();
        setPid(data.data.project.id);
      } else {
        await api.patch(`/projects/${pid}`, draft);
        await loadProjects();
      }
      setModal('');
    });
  }
  useQAExecutionInput('projects', { source: picked.length ? null : current?.data_kind === 'raw' ? { dataset_asset_id: current.id } : current?.metadata?.analysis_run_id ? { run_id: current.metadata.analysis_run_id } : null, run_ids: picked.length ? allRows.filter(r=>picked.includes(r.id)&&r.metadata?.analysis_run_id).map(r=>r.metadata.analysis_run_id) : current?.metadata?.analysis_run_id ? [current.metadata.analysis_run_id] : [], asset_ids: tab === 'raw' && picked.length ? picked : [], settings: { warehouse: tab }, project_id: pid || undefined, source_label: current?.filename }, [], busy || loading);

  return <div className="dw-page pw-page" data-qa-state={JSON.stringify({ module: localize("项目与数据"), project_id: pid, section: tab === 'raw' ? localize("原始文件") : tab === 'processed' ? localize("共享结果") : localize("活动"), selected_file: current ? { id: current.id, filename: current.filename, data_kind: current.data_kind } : null, file_count: rows.length, loading, error: error?.slice(0, 200) })}>
    <header className="dw-header"><div><h1><FolderKanban size={24} />{txt('项目与数据', 'Projects & data')}</h1><p className="dw-muted">{txt('团队文件、处理结果与来源记录', 'Team files, processed data and provenance')}</p></div><button disabled={busy || loading} title={txt('刷新', 'Refresh')} onClick={() => act(async () => {
        await loadProjects();
        await loadAssets();
      })}><RefreshCw size={16} />{txt('刷新', 'Refresh')}</button></header>
    {error && <p className="dw-error" role="alert">{systemText(error)}</p>}
    <div className="dw-project-layout">
      <aside className="dw-project-list"><button onClick={() => {
          setDraft(blank);
          setModal('new');
        }}><Plus size={16} />{txt('新建项目', 'New project')}</button>
        <label className="dw-search"><Search size={16} /><input aria-label={txt('搜索项目', 'Search projects')} placeholder={txt('搜索项目', 'Search projects')} value={query} onChange={e => setQuery(e.target.value)} /></label>
        <nav aria-label={txt('项目列表', 'Projects')}>{projects.filter(p => p.name.toLowerCase().includes(query.toLowerCase())).map(p => <button key={p.id} aria-pressed={pid === p.id} onClick={() => setPid(p.id)}><span>{p.name}</span><small>{p.dataset_count}</small></button>)}</nav>
        {!projects.length && <p className="dw-empty">{txt('暂无项目', 'No projects')}</p>}
        <details className="pw-invitations"><summary>{txt('项目邀请', 'Project invitations')}</summary><ProjectInvitations onChanged={loadProjects} /></details>
      </aside>
      <main className="dw-project-content">{project ? <>
        <div className="dw-heading"><div><h2>{project.name}</h2><p className="dw-muted">{project.description || txt('暂无说明', 'No description')}</p><small>{txt('负责人', 'Owner')} · {project.owner_username || '—'}{project.category && ` · ${project.category}`}</small></div><div className="dw-actions"><button onClick={() => setModal('members')}><Users size={16} />{txt('成员管理', 'Members')}</button>{manager && <button onClick={() => {
                setDraft({
                  name: project.name,
                  description: project.description,
                  category: project.category
                });
                setModal('edit');
              }}><Pencil size={16} />{txt('项目设置', 'Settings')}</button>}</div></div>
        <div className="dw-tabs" role="tablist" aria-label={txt('项目内容', 'Project contents')}>{[['raw', txt('原始文件', 'Original files')], ['processed', txt('共享结果', 'Shared results')], ['events', txt('活动', 'Activity')]].map(([key, label]) => <button key={key} role="tab" aria-selected={tab === key} onClick={() => {
              setTab(key);
              setSelected(null);
              setEdit(null);
              setType('');
              setUploader('');
            }}>{systemText(label)}</button>)}</div>
        {tab === 'events' ? <ProjectCollaboration key={pid} project={project} initialTab="events" onChanged={loadProjects} /> : <>
          <div className="dw-toolbar"><label className="dw-search"><Search size={16} /><input aria-label={txt('搜索文件', 'Search files')} placeholder={txt('搜索文件或来源', 'Search files or source')} value={search} onChange={e => setSearch(e.target.value)} /></label>
            <select aria-label={txt('数据类型', 'Data type')} value={type} onChange={e => setType(e.target.value)}><option value="">{txt('全部类型', 'All types')}</option>{Array.from(new Set(allRows.map(a => a.data_type))).filter(Boolean).map(v => <option key={v} value={v}>{typeName(v)}</option>)}</select>
            <select aria-label={txt('上传者', 'Uploader')} value={uploader} onChange={e => setUploader(e.target.value)}><option value="">{txt('全部上传者', 'All uploaders')}</option>{Array.from(new Set(allRows.map(a => a.owner_username))).filter(Boolean).map(v => <option key={v}>{v}</option>)}</select>
            {tab === 'raw' && <button className="pw-primary" onClick={() => {
                setFiles([]);
                setModal('upload');
              }}><Upload size={16} />{txt('上传原始文件', 'Upload originals')}</button>}<span className="dw-muted">{rows.length} {txt('项', 'items')}</span>
          </div>
          {tab === 'processed' && <p className="dw-muted">{txt("从分析记录共享到本项目的结果会显示在这里。", "Results shared to this project appear here.")}</p>}
          <div className="dw-toolbar"><label><input type="checkbox" aria-label={localize("选择当前列表文件")} checked={rows.filter(a => !a.legacy).length > 0 && rows.filter(a => !a.legacy).every(a => picked.includes(a.id))} onChange={e => setPicked(e.target.checked ? rows.filter(a => !a.legacy).map(a => a.id) : [])} />{localize(" 选择当前列表")}</label><span>{localize("已选 ")}{picked.length}{localize(" 项")}</span><button disabled={busy || !picked.length} onClick={downloadPicked}><Download size={16} />{localize("批量下载")}</button><button disabled={busy || !picked.length || allRows.filter(a => picked.includes(a.id)).some(a => a.data_type !== 'spectrum' || a.metadata?.parse_status === 'failed')} onClick={() => startBatch(allRows.filter(a => picked.includes(a.id)))}><Play size={16} />{localize("批量处理")}</button></div>
          <div className="dw-table"><table><thead><tr><th>{localize("选择")}</th><th>{txt('文件名', 'Name')}</th><th>{tab === 'raw' ? txt('数据类型', 'Type') : txt('来源文件 / 版本', 'Source / version')}</th><th>{txt('检查状态', 'Screening')}</th><th>{txt('上传者', 'Contributor')}</th><th>{txt('保存时间', 'Saved')}</th><th>{txt('操作', 'Actions')}</th></tr></thead><tbody>
            {loading ? <tr><td colSpan={7}>{txt('正在加载…', 'Loading…')}</td></tr> : !rows.length ? <tr><td colSpan={7} className="dw-empty">{txt('仓库暂无匹配数据', 'No matching data')}</td></tr> : rows.map(a => <tr key={a.id} className={current?.id === a.id ? 'pw-selected' : ''}><td><input type="checkbox" disabled={a.legacy} aria-label={`${localize("选择 ")}${a.display_name || a.filename}`} checked={picked.includes(a.id)} onChange={e => setPicked(old => e.target.checked ? [...old, a.id] : old.filter(id => id !== a.id))} /></td><td><button className="pw-file" aria-label={`${localize("预览 ")}${a.display_name || a.filename}`} onClick={() => {
                        setSelected(a.id);
                        setEdit(null);
                      }}><Database size={15} />{a.display_name || a.filename}</button><small>{a.category}</small></td><td>{tab === 'raw' ? typeName(a.data_type) : <>{a.metadata?.source_name || txt('来源待补充', 'Source unavailable')}<small>{a.legacy ? txt('旧记录', 'Legacy record') : a.metadata?.analysis_run_id ? txt('已关联分析版本', 'Linked analysis version') : txt('来源待补充', 'Provenance unavailable')}</small></>}</td><td>{check(a)}</td><td>{a.owner_username || '—'}</td><td>{a.created_at ? new Date(a.created_at).toLocaleString(getLocale()) : '—'}</td><td><div className="dw-actions">{tab === 'processed' && (a.metadata?.analysis_run_id || a.runId) ? <Link to={historyLink(a.metadata?.analysis_run_id || a.runId)}>{txt('打开结果','Open result')}</Link> : <button disabled={busy} title={txt('下载文件', 'Download file')} aria-label={txt('下载文件', 'Download file')} onClick={() => act(() => download(a))}><Download size={16} /></button>}{tab === 'processed' && a.metadata?.analysis_run_id && (manager || a.owner_id === user.id) && <button disabled={busy} title={txt('取消共享', 'Unshare')} onClick={() => remove(a)}><Trash2 size={16} />{txt('取消共享', 'Unshare')}</button>}</div></td></tr>)}
          </tbody></table></div>
          {current && <section className="dw-preview" aria-label={txt('数据预览', 'Data preview')}><div className="dw-heading"><h3>{current.display_name || current.filename}</h3><button title={txt('关闭预览', 'Close preview')} aria-label={txt('关闭预览', 'Close preview')} onClick={() => setSelected(null)}><X size={16} /></button></div>
            <dl>{[[txt('原文件', 'File'), current.filename], [txt('类型', 'Type'), typeName(current.data_type)], [txt('大小', 'Size'), current.file_size != null ? `${(current.file_size / 1024).toFixed(1)} KB` : null], [txt('仪器', 'Instrument'), current.instrument], [txt('点数', 'Points'), current.metadata?.points], [txt('尺寸', 'Shape'), current.metadata?.shape?.join(' × ')], [txt('波数范围', 'Wavenumber range'), current.metadata?.wavenumber_min != null ? `${current.metadata.wavenumber_min} – ${current.metadata.wavenumber_max}` : null], [txt('来源', 'Source'), current.metadata?.source_name]].filter(([, value]) => value != null && value !== '').map(([label, value]) => <React.Fragment key={label}><dt>{systemText(label)}</dt><dd>{value}</dd></React.Fragment>)}</dl>
            {previewLoading && <p>{localize("正在读取预览…")}</p>}{previewError && <p className="dw-muted">{previewError}</p>}{Array.isArray(preview?.wavenumber) && Array.isArray(preview?.intensity) && <Plot data={[{
                x: preview.wavenumber,
                y: preview.intensity,
                type: 'scatter',
                mode: 'lines',
                line: {
                  color: '#087f8c'
                }
              }]} layout={{
                height: 280,
                margin: {
                  l: 60,
                  r: 20,
                  t: 10,
                  b: 50
                },
                paper_bgcolor: 'transparent',
                plot_bgcolor: 'transparent',
                font: {
                  color: theme === 'dark' ? '#d5dbe3' : '#404b59'
                },
                xaxis: {
                  title: localize("拉曼位移 (cm⁻¹)")
                },
                yaxis: {
                  title: localize("强度（原始单位）")
                }
              }} config={{
                responsive: true,
                displaylogo: false
              }} useResizeHandler style={{
                width: '100%'
              }} />}{preview?.preview && <Plot data={[{
                type: 'heatmap',
                z: preview.preview,
                colorscale: 'Viridis'
              }]} layout={{
                height: 280,
                margin: {
                  l: 40,
                  r: 20,
                  t: 10,
                  b: 40
                },
                paper_bgcolor: 'transparent',
                plot_bgcolor: 'transparent'
              }} config={{
                responsive: true,
                displaylogo: false
              }} useResizeHandler style={{
                width: '100%'
              }} />}
            {current.metadata?.parse_error && <p className="dw-error">{current.metadata.parse_error}</p>}{current.metadata?.warnings?.map(w => <p key={w}>{w}</p>)}<QualityReport report={current.metadata?.quality_check} />
            <div className="dw-actions">{!current.metadata?.analysis_run_id && <button disabled={busy} onClick={() => act(() => download(current))}><Download size={16} />{tab === 'raw' ? txt('下载原件', 'Download original') : txt('下载结果', 'Download result')}</button>}
              {!current.metadata?.analysis_run_id && !current.legacy && ['spectrum','mapping','time_series'].includes(current.data_type) && (current.metadata?.parse_status === 'ok' || current.metadata?.analysis_run_id) && <button disabled={busy} onClick={() => act(() => download(current, true))}><Download size={16} />{txt('下载标准化数据', 'Download standardized data')}</button>}
              {!current.legacy && current.data_type === 'spectrum' && (current.metadata?.parse_status === 'ok' || current.metadata?.analysis_run_id) && <button disabled={busy} onClick={() => startSingle(current)}><Play size={16} />{txt('开始处理', 'Start processing')}</button>}
              {current.metadata?.analysis_run_id && <Link to={historyLink(current.metadata.analysis_run_id)}><History size={16} />{txt('打开结果', 'Open result')}</Link>}
              {!current.legacy && (manager || current.owner_id === user.id) && <button onClick={() => setEdit({
                  display_name: current.display_name || current.filename,
                  category: current.category || ''
                })}><Pencil size={16} />{txt('编辑信息', 'Edit details')}</button>}
              {tab === 'raw' && current.owner_id === user.id && <button disabled={busy} onClick={() => remove(current)}><Trash2 size={16} />{txt('删除文件', 'Delete file')}</button>}
            </div>
            {edit && <form className="pw-edit" onSubmit={e => {
                e.preventDefault();
                act(async () => {
                  await api.patch(`/datasets/${current.id}`, edit);
                  setEdit(null);
                  await loadAssets();
                });
              }}><label>{txt('名称', 'Name')}<input required value={edit.display_name} onChange={e => setEdit({
                    ...edit,
                    display_name: e.target.value
                  })} /></label><label>{txt('分类', 'Category')}<input value={edit.category} onChange={e => setEdit({
                    ...edit,
                    category: e.target.value
                  })} /></label><button disabled={busy}>{txt('保存', 'Save')}</button><button type="button" onClick={() => setEdit(null)}>{txt('取消', 'Cancel')}</button></form>}
          </section>}
        </>}
      </> : <p className="dw-empty">{txt('选择或新建项目以管理团队数据', 'Select or create a project to manage team data')}</p>}</main>
    </div>
    {pendingImport && <Modal title={localize("格式转换确认")} close={() => {
      if (!busy) setPendingImport(null);
    }}><SpectrumImportConfirmation inspection={pendingImport.inspection} isBatch={pendingImport.isBatch} busy={busy} txt={txt} onCancel={() => setPendingImport(null)} onConfirm={() => pendingImport.isBatch ? startBatch(pendingImport.assets, true) : startSingle(pendingImport.asset, true)} /></Modal>}
    {modal && <Modal title={modal === 'members' ? txt('成员管理', 'Members') : modal === 'upload' ? txt('上传原始文件', 'Upload originals') : modal === 'new' ? txt('新建项目', 'New project') : txt('项目设置', 'Project settings')} close={() => {
      if (!busy) setModal('');
    }}>
      {error && <p className="dw-error" role="alert">{systemText(error)}</p>}
      {modal === 'members' ? <ProjectCollaboration project={project} onChanged={async () => {
        await loadProjects();
      }} /> : modal === 'upload' ? <form onSubmit={e => {
        e.preventDefault();
        act(async () => {
          const form = new FormData();
          files.forEach(f => form.append('files', f));
          form.append('data_kind', 'raw');
          form.append('data_type', uploadType);
          form.append('instrument', 'auto');
          form.append('mode', 'imaging');
          await api.post(`/projects/${pid}/datasets/upload`, form);
          setModal('');
          await loadAssets();
          await loadProjects();
        });
      }}><p>{txt("项目成员可访问上传的文件。", "Project members can access uploaded files.")}</p><input aria-label={txt('选择文件', 'Choose files')} type="file" multiple required onChange={e => setFiles(Array.from(e.target.files))} /><label>{txt('数据类型', 'Data type')}<select value={uploadType} onChange={e => setUploadType(e.target.value)}><option value="auto">{txt('自动识别', 'Auto detect')}</option><option value="spectrum">{txt('单光谱', 'Spectrum')}</option><option value="mapping">{txt('高光谱成像', 'Hyperspectral imaging')}</option></select></label><p>{files.length} {txt('个文件', 'files')}</p><button disabled={busy || !files.length}><Upload size={16} />{busy ? txt('正在上传…', 'Uploading…') : txt('上传', 'Upload')}</button></form> : <form onSubmit={saveProject}>
        {['name', 'description', 'category'].map((key, i) => <label key={key}>{[txt('项目名称', 'Project name'), txt('说明', 'Description'), txt('分类', 'Category')][i]}{key === 'description' ? <textarea value={draft[key]} onChange={e => setDraft({
            ...draft,
            [key]: e.target.value
          })} /> : <input autoFocus={key === 'name'} required={key === 'name'} value={draft[key]} onChange={e => setDraft({
            ...draft,
            [key]: e.target.value
          })} />}</label>)}
        <div className="dw-actions">{modal === 'edit' && project?.owner_id === user.id && <button type="button" disabled={busy} onClick={() => {
            if (window.confirm(txt("确认删除此项目？", "Delete this project?"))) act(async () => {
              await api.delete(`/projects/${pid}`);
              setModal('');
              await loadProjects();
            });
          }}><Trash2 size={16} />{txt('删除项目', 'Delete project')}</button>}<button disabled={busy || !draft.name.trim()}>{txt('保存', 'Save')}</button></div>
      </form>}
    </Modal>}
  </div>;
}
