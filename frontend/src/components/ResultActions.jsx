import { systemText, localize } from '../locale.js';
import { usePreferences } from '../i18n';
import React, { useRef, useState } from 'react';
import { Download, FolderPlus, Loader2, X } from 'lucide-react';
import downloadSpectrumImage from './downloadSpectrumImage';
import './ResultActions.css';
import { spectrumText } from '../spectrumExport';

export function Modal({ title, children, onClose }) {
  usePreferences();
  const ref = useRef();
  React.useEffect(() => { ref.current.showModal(); }, []);
  return <dialog ref={ref} className="result-dialog" onCancel={event => { event.preventDefault(); onClose(); }} onClick={event => { if (event.target === ref.current) onClose(); }}>
    <header><h2>{systemText(title)}</h2><button type="button" aria-label={localize("关闭弹窗")} onClick={onClose}><X size={18} /></button></header>{children}
  </dialog>;
}

function saveFile(content, filename) {
  const url = URL.createObjectURL(new Blob([content], {type: 'text/plain;charset=utf-8'}));
  const link = document.createElement('a'); link.href = url; link.download = filename; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function SpectrumExport({ original, result, sourceName, version, disabled, resultDisabled, onOriginalFile, advanced = [], txt: providedTxt }) {
  const { language } = usePreferences();
  const txt = providedTxt || ((zh, en) => language === 'zh' ? zh : en);
  const [open, setOpen] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState('');
  const stem = (sourceName || 'spectrum').replace(/\.[^.]+$/, '');
  async function download(spectrum, format, processed) {
    setBusy(true); setError('');
    try {
      const suffix = processed ? `processed${version ? '_V' + version : ''}` : 'original';
      const filename = `${stem}_${suffix}`;
      if (format === 'txt') saveFile(spectrumText(spectrum), filename + '.txt');
      else await downloadSpectrumImage(spectrum, {filename, title: `${sourceName || 'Spectrum'} · ${processed ? txt('处理后光谱', 'Processed spectrum') + (version ? ' V' + version : '') : txt('原始光谱', 'Original spectrum')}`});
    } catch (err) { setError(err.message || txt('导出失败，请重试。', 'Export failed. Please retry.')); }
    finally { setBusy(false); }
  }
  async function extra(action) { setBusy(true); setError(''); try { await action(); } catch (err) { setError(err.message); } finally { setBusy(false); } }
  return <><button type="button" className="result-export" disabled={disabled || !original && !result} onClick={() => setOpen(true)}><Download size={16} />{txt('导出', 'Export')}</button>
    {open && <Modal title={txt('导出光谱', 'Export spectrum')} onClose={() => { if (!busy) setOpen(false); }}>
      {[[false, original, txt('原始光谱', 'Original spectrum')], [true, result, txt('处理后光谱', 'Processed spectrum')]].map(([processed, spectrum, label]) => <section key={label}><h3>{systemText(label)}</h3><div className="result-actions-row">{['txt', 'png'].map(format => <button key={format} disabled={busy || !spectrum || processed && resultDisabled} aria-label={`${label} ${format.toUpperCase()}`} onClick={() => download(spectrum, format, processed)}><Download size={15} />{format === 'txt' ? txt('TXT 数据', 'TXT data') : txt('PNG 图片', 'PNG image')}</button>)}</div></section>)}
      {resultDisabled && <p className="result-muted">{txt('应用处理后可导出最终结果。', 'Apply processing to export the final result.')}</p>}
      {(onOriginalFile || advanced.length > 0) && <details><summary>{txt('更多格式', 'More formats')}</summary><div className="result-actions-row">{onOriginalFile && <button disabled={busy} onClick={() => extra(onOriginalFile)}>{txt('原始仪器文件', 'Original instrument file')}</button>}{advanced.map(action => <button key={action.label} disabled={busy} onClick={() => extra(action.run)}>{systemText(action.label)}</button>)}</div></details>}
      {busy && <p role="status"><Loader2 className="result-spin" size={16} />{txt('正在导出…', 'Exporting…')}</p>}{error && <p role="alert" className="result-error">{systemText(error)}</p>}
    </Modal>}
  </>;
}

export function ShareResult({ api, runId, projects, projectId, disabled, onShared, txt: providedTxt }) {
  const { language } = usePreferences();
  const txt = providedTxt || ((zh, en) => language === 'zh' ? zh : en);
  const [open, setOpen] = useState(false), [target, setTarget] = useState(''), [busy, setBusy] = useState(false), [error, setError] = useState('');
  const [shared, setShared] = useState(false), [sharedProject, setSharedProject] = useState(projectId);
  React.useEffect(() => {
    let cancelled = false; setShared(false); setSharedProject(projectId);
    if (runId) api.get(`/analysis-runs/${runId}`).then(({data}) => { if (!cancelled) { setShared(Boolean(data.data.run.is_shared)); setSharedProject(data.data.run.project_id); } }).catch(() => {});
    return () => { cancelled = true; };
  }, [api, runId, projectId]);
  async function share() {
    setBusy(true); setError('');
    try {
      await api.post(`/analysis-runs/${runId}/warehouse`, {project_id: target, confirm_sharing: true});
      setShared(true); setSharedProject(target);
      setOpen(false); await onShared?.();
    } catch (err) { setError(typeof err.response?.data?.detail === 'string' ? err.response.data.detail : err.message); }
    finally { setBusy(false); }
  }
  return <><button type="button" disabled={disabled || !runId || shared} onClick={() => { setTarget(sharedProject || projects[0]?.id || ''); setError(''); setOpen(true); }}><FolderPlus size={16} />{shared ? txt('已共享到项目', 'Shared to project') : txt('共享到项目', 'Share to project')}</button>
    {open && <Modal title={txt('共享到项目', 'Share to project')} onClose={() => { if (!busy) setOpen(false); }}>
      <p>{txt('项目成员将能查看此结果、输入数据和处理参数。', 'Project members can view this result, input data and processing settings.')}</p>
      <label>{txt('目标项目', 'Project')}<select aria-label={txt('目标项目', 'Project')} value={target} disabled={busy || Boolean(sharedProject)} onChange={e => setTarget(e.target.value)}><option value="">{txt('选择项目', 'Select project')}</option>{projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
      {!projects.length && <p className="result-muted">{txt('请先在“项目与数据”创建或加入项目。', 'Create or join a project in Projects & data first.')}</p>}
      {error && <p role="alert" className="result-error">{systemText(error)}</p>}<footer><button disabled={busy} onClick={() => setOpen(false)}>{txt('取消', 'Cancel')}</button><button className="result-primary" disabled={busy || !target} onClick={share}>{busy ? txt('正在共享…', 'Sharing…') : txt('确认共享', 'Confirm sharing')}</button></footer>
    </Modal>}
  </>;
}

export function FileExport({ actions, disabled, txt: providedTxt }) {
  const { language } = usePreferences();
  const txt = providedTxt || ((zh, en) => language === 'zh' ? zh : en);
  const [open, setOpen] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState('');
  return <><button type="button" disabled={disabled} onClick={() => setOpen(true)}><Download size={16} />{txt('导出', 'Export')}</button>{open && <Modal title={txt('导出结果', 'Export result')} onClose={() => { if (!busy) setOpen(false); }}><div className="result-actions-row">{actions.map(action => <button key={action.label} disabled={busy} onClick={async () => { setBusy(true); setError(''); try { await action.run(); } catch (err) { setError(err.message); } finally { setBusy(false); } }}>{systemText(action.label)}</button>)}</div>{error && <p role="alert" className="result-error">{systemText(error)}</p>}</Modal>}</>;
}
