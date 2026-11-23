import { localize } from './locale.js';
// A batch upload remains a batch even when a member is processed separately.
export const recordTaskKey = record => record.result?.ai_workflow_id || record.workflow_id || record.id;
export const isProcessed = record => record.status === 'completed';
export const matchesRecordStatus = (record, status) => status === 'all' || (status === 'completed' ? isProcessed(record) : !isProcessed(record));

export function recordDeletionGroups(visible, all, userId) {
  const keys = [...new Set(visible.map(recordTaskKey))];
  return keys.map(key => {
    const records = all.filter(record => recordTaskKey(record) === key);
    let reason = '';
    if (records.some(record => record.kind === 'batch')) reason = localize("请勾选批次内的光谱记录");
    else if (records.some(record => !record.kind && record.user_id !== userId)) reason = localize("不能删除他人的记录");
    else if (records.some(record => record.is_shared)) reason = localize("请先取消项目共享");
    else if (records.some(record => ['queued','running','previewing'].includes(record.status))) reason = localize("任务正在运行");
    else if (records.some(record => record.kind === 'module')) reason = localize("此任务需在对应功能中处理");
    let targets = records.filter(record => !record.kind || record.kind === 'workflow').map(record => ({
      id: record.id,
      path: record.kind === 'workflow' ? `/ai-workflows/${record.workflow_id}` : `/analysis-runs/${record.id}`,
      kind: record.kind || 'result'
    }));
    const batchMember = records.find(record => record.batch_id && record.kind !== 'batch');
    if (batchMember && batchMember.batch_owned !== false) {
      const id = batchMember.item_id || batchMember.workflow_id || batchMember.result?.ai_workflow_id;
      if (id) targets = [{id, path:`/ai-workflow-batches/${batchMember.batch_id}/items/${id}`, kind:'batch_member'}];
    }
    return {key, title: records[0]?.title, records, targets, reason, deletable: !reason && targets.length > 0};
  });
}

export function historyView({runs, pending, batches, type, processingMode, status, project, days, query, now = Date.now()}) {
  const batchMode = type === 'spectrum' && processingMode === 'batch';
  const needle = query.trim().toLowerCase();
  const recent = item => !days || Date.parse(item.updated_at || item.created_at) >= now - Number(days) * 86400000;
  const batchMap = new Map(batches.map(batch => [batch.id, batch]));
  const all = [...runs.map(run => ({...run, status: 'completed'})), ...pending];
  const scoped = all.filter(record => record.analysis_type === type && (!project || record.project_id === project) && recent(record)
    && (type !== 'spectrum' || Boolean(record.batch_id) === batchMode));
  const visible = scoped.filter(record => matchesRecordStatus(record, status)
    && `${record.title} ${record.source_name} ${record.batch_name || batchMap.get(record.batch_id)?.name || ''}`.toLowerCase().includes(needle));
  const visibleBatches = [];
  if (batchMode) {
    // Keep batches whose files could not be imported reachable without a separate status tab.
    for (const batch of batches) {
      if (project && batch.project_id !== project || !recent(batch)) continue;
      const members = visible.filter(record => record.batch_id === batch.id);
      const completed = batch.counts.completed || 0;
      const remaining = Math.max(0, batch.total - completed - (batch.counts.deleted || 0));
      const matchesStatus = status === 'all' || (status === 'completed' ? completed > 0 : remaining > 0);
      if (!members.length && (!batch.name.toLowerCase().includes(needle) || !matchesStatus)) continue;
      visibleBatches.push(batch);
    }
  }
  visible.sort((a, b) => (b.updated_at || b.created_at).localeCompare(a.updated_at || a.created_at));
  return {visible, batches: visibleBatches, count: new Set(visible.filter(record => record.kind !== 'batch').map(recordTaskKey)).size};
}
