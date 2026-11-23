import React, { useState } from 'react';
import { CheckCircle2, History, Pencil } from 'lucide-react';
import { Link } from 'react-router-dom';
import { apiErrorMessage } from '../auth';
import './ModuleRecords.css';

export default function ResultRecordLink({ api, module, job, txt, disabled, onError }) {
  const [busy, setBusy] = useState(false);
  const complete = job?.status === 'completed' && (module !== 'ssnet' || job.kind === 'predict');
  const type = {'ssnet':'mixture_analysis','library-matching':'library_matching','structure-generation':'structure_generation','peak-fitting':'peak_fitting'}[module];
  async function rename() {
    const title = window.prompt(txt('结果名称', 'Result name'), job.source_name || job.name || '');
    if (!title?.trim()) return;
    setBusy(true);
    try { await api.patch(`/analysis-runs/${job.analysis_run_id}`, {title: title.trim()}); }
    catch (error) { onError(apiErrorMessage(error)); }
    finally { setBusy(false); }
  }
  return <div className="module-saved-results"><div className="sg-detail-actions">
    {complete && <span className="module-save-success"><CheckCircle2 size={16} />{job.analysis_run_id ? txt('已自动记录', 'Recorded automatically') : txt('分析已完成', 'Analysis completed')}</span>}
    <Link to={`/analysis-history?${job?.analysis_run_id ? 'run=' + encodeURIComponent(job.analysis_run_id) : 'type=' + type}`}><History size={15} />{txt('分析记录', 'Analysis records')}</Link>
    {complete && job.analysis_run_id && <button disabled={disabled || busy} onClick={rename}><Pencil size={15} />{txt('重命名', 'Rename')}</button>}
  </div></div>;
}
