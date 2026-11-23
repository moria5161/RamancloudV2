import { systemText, getLocale, localize } from '../locale.js';
import { usePreferences } from '../i18n';
import React, {useEffect, useState} from 'react';
import { Link } from 'react-router-dom';
import { Trash2, Atom, Database, GitBranch, FileText } from 'lucide-react';
import { recordStatus } from './PendingAnalysisRecord';
import { recordTaskKey } from '../analysisRecords';
import {spectrumExportTargets} from '../spectrumExport';
import BatchSpectrumExport from './BatchSpectrumExport';
export function taskKey(run) {
  return recordTaskKey(run);
}
export function historyRecordTitle(run) {
  if (run.analysis_type === 'structure_generation' &&
      ['结构生成', '光谱到结构'].some(label => run.title === `${run.source_name} · ${label}`)) {
    return `${run.source_name} · ${localize('光谱到结构')}`;
  }
  return run.title;
}
export function groupedTasks(runs) {
  const groups = new Map();
  for (const run of [...runs].sort((a, b) => b.created_at.localeCompare(a.created_at))) {
    const key = taskKey(run);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(run);
  }
  return [...groups.values()];
}
function Thumbnail({
  run
}) {
  usePreferences();
  const input = run.result || {},
    y = input.intensity || input.mean_spectrum;
  if (!Array.isArray(y) || !y.length) {
    const Icon={library_matching:Database,structure_generation:Atom,mixture_analysis:GitBranch}[run.analysis_type] || FileText;
    return <span className="dw-record-type-icon"><Icon size={24}/></span>;
  }
  const sample = Array.from({
    length: Math.min(60, y.length)
  }, (_, i) => y[Math.floor(i * (y.length - 1) / Math.max(1, Math.min(60, y.length) - 1))]);
  const low = Math.min(...sample),
    high = Math.max(...sample),
    range = high - low || 1;
  const points = sample.map((v, i) => `${2 + 68 * i / Math.max(1, sample.length - 1)},${40 - 36 * (v - low) / range}`).join(' ');
  return <svg className="dw-thumbnail" viewBox="0 0 72 44" role="img" aria-label={localize("结果缩略图")}><polyline points={points} fill="none" stroke="#087f8c" strokeWidth="1.5" /></svg>;
}
export default function HistoryRecordList({
  runs,
  batches: batchSummaries = [],
  selectionMode = false,
  checked = [],
  deletionGroups = [],
  onCheck,
  onDeleteBatch,
  exportApi,
  disabled = false,
  selected,
  onSelect
}) {
  usePreferences();
  const [page, setPage] = useState(0);
  const batches = new Map(),
    singles = [];
  for (const run of runs) {
    if (run.batch_id) {
      if (!batches.has(run.batch_id)) batches.set(run.batch_id, []);
      batches.get(run.batch_id).push(run);
    } else singles.push(run);
  }
  const summaries = new Map(batchSummaries.map(batch => [batch.id, batch]));
  for (const batch of batchSummaries) if (!batches.has(batch.id)) batches.set(batch.id, []);
  const buttons = records => groupedTasks(records).map(versions => {
    const active = versions.find(r => r.id === selected),
      run = active || versions[0];
    const title = historyRecordTitle(run);
    const key = taskKey(run), deletion = deletionGroups.find(group => group.key === key);
    return <div className={`dw-record-row ${selectionMode ? 'dw-record-selectable' : ''} ${['library_matching','structure_generation','mixture_analysis'].includes(run.analysis_type) ? 'dw-module-record' : ''}`} key={key}>
      {selectionMode && <label className="dw-record-check" title={systemText(deletion?.reason || localize("选择此任务及其历史版本"))}><input type="checkbox" aria-label={`${localize("选择 ")}${title}`} checked={checked.includes(key)} disabled={disabled || !deletion?.deletable} onChange={event => onCheck(key, event.target.checked)} /></label>}
      <button aria-pressed={!!active} onClick={() => onSelect(run.id)}><Thumbnail run={run} /><span className="dw-record-label"><strong>{title}</strong>{title !== run.source_name && <span>{run.source_name}</span>}<small>{run.status && `${run.status === 'completed' ? localize("已处理") : recordStatus(run.status)} · `}{new Date(run.created_at).toLocaleString(getLocale())}{versions.filter(r => !r.kind).length > 1 ? ` · ${versions.filter(r => !r.kind).length}${localize(" 个版本")}` : ''}</small></span></button>
    </div>;
  });
  const units = [...batches.entries()].map(([id, records]) => ({id, records, batch: true})).concat(groupedTasks(singles).map(records => ({id: taskKey(records[0]), records}))).sort((a,b) => (b.records[0]?.created_at || summaries.get(b.id)?.created_at || '').localeCompare(a.records[0]?.created_at || summaries.get(a.id)?.created_at || ''));
  const pages = Math.max(1, Math.ceil(units.length/20)), current = Math.min(page, pages-1);
  const ids = runs.map(r => r.id).join(',');
  useEffect(() => { const index = units.findIndex(u => u.records.some(r => r.id === selected)); setPage(index < 0 ? 0 : Math.floor(index/20)); }, [selected, ids]);
  return <>{units.slice(current*20, (current+1)*20).map(unit => {
    if (!unit.batch) return buttons(unit.records);
    const batch = summaries.get(unit.id);
    const fileCount = new Set(unit.records.filter(r => r.kind !== 'batch').map(taskKey)).size;
    return <details key={unit.id} className="dw-batch" open={unit.records.some(r => r.id === selected) || undefined}>
      <summary>{batch?.name || unit.records[0]?.batch_name || localize("批量处理")}<small>{batch ? `${batch.total - (batch.counts.deleted || 0)}${localize(" 个文件 · 已处理 ")}${batch.counts.completed || 0}` : `${fileCount}${localize(" 个文件")}`}{localize(" · 当前显示 ")}{fileCount}{localize(" 个")}</small></summary>
      <div className="dw-batch-actions">{batch && <Link className="dw-batch-open" to={`/ai-analysis?batch=${encodeURIComponent(unit.id)}`}>{localize("打开批量处理")}</Link>}{exportApi && <BatchSpectrumExport api={exportApi} targets={spectrumExportTargets(unit.records,selected)} name={batch?.name || unit.records[0]?.batch_name} disabled={disabled} ariaLabel={`${localize("导出批次 ")}${batch?.name || unit.records[0]?.batch_name || ''}`} />}{batch && <button className="dw-batch-delete" aria-label={`${localize("删除批次 ")}${batch.name}`} disabled={disabled || !!(batch.counts.queued || batch.counts.running || batch.counts.previewing)} onClick={() => onDeleteBatch(batch)}><Trash2 size={14} />{localize("删除批次")}</button>}</div>
      {buttons(unit.records)}
    </details>;
  })}{pages > 1 && <div className="dw-list-pages"><button aria-label={localize("记录上一页")} disabled={!current} onClick={() => setPage(current-1)}>{localize("上一页")}</button><span>{current+1}/{pages}</span><button aria-label={localize("记录下一页")} disabled={current+1 >= pages} onClick={() => setPage(current+1)}>{localize("下一页")}</button></div>}</>;
}
