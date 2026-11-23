import { systemText, getLocale, localize } from '../locale.js';
import { usePreferences } from '../i18n';
import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, FileText } from 'lucide-react';

export const recordStatus = value => ({draft:localize("待处理"),preview:localize("待应用"),queued:localize("排队中"),running:localize("处理中"),previewing:localize("预览中"),completed:localize("已完成"),failed:localize("失败"),cancelled:localize("已停止"),invalid:localize("导入失败")}[value] || value);
export function recordLink(item) {
  if (item.kind === 'batch') return `/ai-analysis?batch=${encodeURIComponent(item.batch_id)}`;
  if (item.kind === 'batch_item') return `/ai-analysis?batch=${encodeURIComponent(item.batch_id)}`;
  if (item.kind === 'workflow') return `/ai-analysis?task=${item.workflow_id}${item.version_id ? '&version=' + item.version_id : ''}${item.batch_id ? '&batch=' + item.batch_id : ''}`;
  return `/${item.module === 'ssnet' ? 'spectral-unmixing' : item.module}?job=${encodeURIComponent(item.job_id)}`;
}
export default function PendingAnalysisRecord({ item, api, onDeleted }) {
  usePreferences();
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  async function remove() { setBusy(true); try { await api.delete(`/ai-workflows/${item.workflow_id}`); await onDeleted(); } catch (err) {setError(err.response?.data?.detail || err.message);} finally {setBusy(false);} }
  return <section className="record-resume"><FileText size={28} /><h2>{item.kind === 'batch' ? item.batch_name : item.title}</h2><p>{item.kind === 'batch' ? `${item.total - (item.counts.deleted || 0)}${localize(" 个文件 · 已处理 ")}${item.counts.completed || 0}` : recordStatus(item.status)} · {new Date(item.updated_at).toLocaleString(getLocale())}</p>{item.error && <p className="dw-error" role="status">{systemText(item.error)}</p>}<Link className="record-primary" to={recordLink(item)}>{item.kind === 'batch' ? localize("打开批量处理") : item.status === 'completed' ? localize("打开结果") : localize("继续处理")}<ArrowRight size={16} /></Link>{item.kind === 'workflow' && <button disabled={busy || ['queued','running','previewing'].includes(item.status)} onClick={remove}>{localize("删除任务")}</button>}{error && <p role="alert" className="dw-error">{systemText(error)}</p>}</section>;
}
