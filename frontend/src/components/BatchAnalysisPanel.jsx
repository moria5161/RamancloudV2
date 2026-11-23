import { systemText } from '../locale.js';
import React from 'react';
import { Eye, FolderOpen, Loader2, Play, SlidersHorizontal, Square } from 'lucide-react';
import BatchSpectrumExport from './BatchSpectrumExport';

const labels = {
  ready: ['待处理', 'Ready'], invalid: ['文件无效', 'Invalid file'], queued: ['排队中', 'Queued'],
  running: ['处理中', 'Running'], completed: ['已完成', 'Completed'], failed: ['失败', 'Failed'],
  cancelled: ['已停止', 'Stopped'], deleted: ['已删除', 'Deleted'],
};

export default function BatchAnalysisPanel({ api, batch, selected, template, canExecute, canRefine, pendingRefinement, txt, locked, busy, onRefine, onToggle, onSelectAll, onView, onExecute, onCancel }) {
  const eligible = batch.items.filter(item => item.workflow_id);
  const allSelected = eligible.length > 0 && eligible.every(item => selected.includes(item.workflow_id));
  const finished = batch.counts.completed + batch.counts.failed + batch.counts.cancelled;
  return <section className="ai-batch-panel" aria-label={txt('批量处理', 'Batch processing')}>
    <div className="ai-section-heading"><h2><FolderOpen size={18} />{batch.name}<span className="ai-muted">{batch.items.length} {txt('个文件', 'files')}</span></h2>
      <span className="ai-muted">{txt('已完成', 'Completed')} {batch.counts.completed} · {txt('失败', 'Failed')} {batch.counts.failed} · {txt('无效', 'Invalid')} {batch.counts.invalid}</span></div>
    <div className="ai-batch-template"><span>{txt('统一方案来源', 'Shared plan source')}</span><strong>{template || txt('尚未选择方案', 'No plan selected')}</strong></div>
    {batch.active && <div className="ai-progress"><Loader2 size={16} className="ai-spin" /><progress max={batch.items.filter(item => item.workflow_id).length} value={finished} /><span>{finished}/{batch.items.filter(item => item.workflow_id).length}</span></div>}
    <div className="ai-batch-table"><table><thead><tr><th><input type="checkbox" aria-label={txt('全选批量光谱', 'Select all batch spectra')} checked={allSelected} disabled={Boolean(busy) || batch.active || !eligible.length} onChange={e => onSelectAll(e.target.checked)} /></th><th>{txt('光谱文件', 'Spectrum file')}</th><th>{txt('状态', 'Status')}</th><th>{txt('详情', 'Details')}</th><th><span className="sr-only">{txt('查看', 'View')}</span></th></tr></thead><tbody>
      {batch.items.map(item => <tr key={item.id}>
        <td><input type="checkbox" aria-label={`${txt('选择光谱', 'Select spectrum')} ${item.relative_path}`} checked={Boolean(item.workflow_id && selected.includes(item.workflow_id))} disabled={Boolean(busy) || batch.active || !item.workflow_id} onChange={() => onToggle(item.workflow_id)} /></td>
        <td className="ai-batch-filename">{item.relative_path}</td><td><span className={`ai-batch-status is-${item.status}`}>{txt(...(labels[item.status] || [item.status, item.status]))}</span></td>
        <td className="ai-batch-error">{systemText(item.error || '—')}</td><td><button type="button" className="ai-icon" aria-label={`${txt('查看光谱', 'View spectrum')} ${item.relative_path}`} title={txt('查看光谱', 'View spectrum')} disabled={locked || !item.workflow_id} onClick={() => onView(item.workflow_id, item.version_id)}><Eye size={16} /></button></td>
      </tr>)}
    </tbody></table></div>
    <div className="ai-actions ai-batch-actions"><button className="ai-primary" disabled={locked || !canExecute || pendingRefinement || batch.active || !template || !selected.length} title={pendingRefinement ? txt('请先更新方案并预览', 'Preview the revised plan first') : undefined} onClick={onExecute}>{busy === 'batch-execute' ? <Loader2 size={16} className="ai-spin" /> : <Play size={16} />}{txt('按当前方案批量处理', 'Process batch with current plan')} ({selected.length})</button>
      <button disabled={locked || batch.active || !canRefine} onClick={onRefine}><SlidersHorizontal size={16} />{txt('调整批量方案', 'Refine batch plan')}</button>
      <button disabled={Boolean(busy) || !batch.counts.queued} onClick={onCancel} title={txt('停止待执行项，当前计算完成后结束', 'Stop queued items; the current calculation will finish')}><Square size={16} />{txt('停止待执行项', 'Stop queued items')}</button>
      <BatchSpectrumExport api={api} targets={selected.filter(id => eligible.some(item => item.workflow_id === id)).map(workflow_id => ({workflow_id}))} name={batch.name} disabled={Boolean(busy)} txt={txt} /></div>
  </section>;
}
