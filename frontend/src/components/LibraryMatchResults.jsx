import { systemValue, systemText } from '../locale.js';
import React, { useState } from 'react';
import { libraryName } from '../libraryNames.js';
import { Database, Loader2 } from 'lucide-react';
import { FileExport } from './ResultActions';
import SpectralChart from './SpectralChart';
import { referenceCurve, scoreText } from '../pages/libraryMatching';

export default function LibraryMatchResults({ job, api, txt, dark, onError, history = false }) {
  const [selected, setSelected] = useState(null), [exporting, setExporting] = useState(false);
  const candidates = job.result?.candidates || [];
  const candidate = candidates.find(c => c.class_id === selected) || candidates[0];
  const trace = job.result?.preprocessing;
  const active = ['queued', 'running'].includes(job.status);
  const inputCurve = job.result?.model_input || job.input?.source?.spectrum;
  async function download(format) {
    setExporting(true);
    try {
      const { data } = await api.get(`/library-matching/jobs/${job.id}/download`, { params: { format }, responseType: 'blob' });
      const url = URL.createObjectURL(data), a = document.createElement('a');
      a.href = url; a.download = format === 'input' ? 'peaknet_input.tsv' : `library_match.${format}`; a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch { onError(txt('导出失败，请稍后重试。', 'Export failed. Please retry.')); }
    finally { setExporting(false); }
  }
  return <>
    <div className="sg-live-provenance"><strong>{job.source_name}</strong><span>{systemText(job.profile?.label || 'PeakNet')}</span><span>{job.settings?.preprocessing_mode === 'auto' ? 'AirNet + PEER' : txt('使用当前处理结果', 'Use selected processed input')}</span></div>
    {active && <div className="sg-empty-results" role="status"><Loader2 size={34} className="sg-spin" /><h3>{job.status === 'queued' ? txt('等待匹配', 'Queued') : txt('正在处理并匹配光谱', 'Preparing and matching the spectrum')}</h3><p>{txt('首次运行会加载模型。任务会自动保存，离开页面后可从匹配记录中查看。', 'The first run loads the models. The job is saved and continues if you leave this page.')}</p></div>}
    {job.status === 'failed' && <div className="sg-alert is-error" role="alert">{systemText(job.error)}</div>}
    {job.status === 'completed' && <>
      <p className="sg-help">{txt(`Top ${candidates.length} 候选 · ${job.result.duration_seconds} 秒`, `Top ${candidates.length} candidates · ${job.result.duration_seconds} seconds`)}</p>
      <div className="lm-candidates" role="group" aria-label={txt('库匹配候选', 'Library match candidates')}>{candidates.map(item => <button key={item.class_id} aria-pressed={candidate?.class_id === item.class_id} className={`lm-candidate ${candidate?.class_id === item.class_id ? 'is-selected' : ''}`} onClick={() => setSelected(item.class_id)}>
        <span className="lm-rank">{String(item.rank).padStart(2, '0')}</span><span className="lm-material"><strong>{libraryName(item)}</strong><span className="lm-score-track"><span style={{ width: `${Math.max(0, Math.min(100, item.model_score * 100))}%` }} /></span></span><span className="lm-score"><small>{txt('模型得分', 'Model score')}</small><b>{scoreText(item.model_score)}</b></span>
      </button>)}</div>
      <p className="sg-help">{txt("得分用于库内排序，不是鉴定概率；库外物质也可能出现匹配。", "Scores rank library classes, not identification probabilities. Unknown substances may still produce matches.")}</p>
      {candidate && <div className="lm-comparison"><div className="sg-panel-heading"><h3><Database size={15} />{libraryName(candidate)}</h3><span className="sg-pill">220–1800 cm⁻¹</span></div><SpectralChart rawData={referenceCurve(candidate)} processedData={inputCurve} rawLabel={txt('库内参考缓存', 'Cached library reference')} processedLabel={job.result.model_input ? txt('当前光谱（模型输入）', 'Current model input') : txt('原始输入光谱','Original input')} height={300} dark={dark} horizontalLegend showToolbar={false} />{!referenceCurve(candidate) && <p className="sg-help">{txt('此旧记录未保留参考谱。','This older record has no saved reference spectrum.')}</p>}</div>}
      {trace && <details className="sg-preparation"><summary>{txt('查看本次基线校正过程', 'Inspect baseline correction')}</summary><SpectralChart rawData={{ wavenumber: trace.wavenumber, intensity: trace.denoised }} processedData={{ wavenumber: trace.wavenumber, intensity: trace.corrected }} baselineData={trace.baseline} rawLabel={txt('PEER 降噪后', 'After PEER')} processedLabel={txt('扣基线后', 'Baseline corrected')} height={270} dark={dark} showToolbar={false} horizontalLegend /></details>}
      <details className="sg-preparation"><summary>{txt('模型、输入版本与参数', 'Model, input version and parameters')}</summary><pre>{JSON.stringify(systemValue({ profile: job.profile, source: job.input?.source?.reference, settings: job.settings, preparation: job.input?.cropped?.preparation }), null, 2)}</pre></details>
      {!history && <div className="sg-detail-actions"><FileExport txt={txt} disabled={exporting} actions={[{label:'JSON',run:()=>download('json')},{label:'CSV',run:()=>download('csv')},{label:txt('模型输入','Model input'),run:()=>download('input')}]} /></div>}
    </>}
  </>;
}
