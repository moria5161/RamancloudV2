import { systemValue, systemText } from '../locale.js';
import React, { useState } from 'react';
import { Copy, Loader2, Atom, Download } from 'lucide-react';
import { FileExport } from './ResultActions';

export default function StructureGenerationResults({ job, api, txt, onError, history = false }) {
  const [selected, setSelected] = useState('1');
  const candidates = job.result?.candidates || [];
  const candidate = candidates.find(item => item.id === selected) || candidates[0];
  const running = ['queued', 'running'].includes(job.status);
  const [exporting, setExporting] = useState(false);
  async function download(format) {
    setExporting(true);
    try {
      const { data } = await api.get(`/structure-generation/jobs/${job.id}/download`, { params: { format }, responseType: 'blob' });
      const url = URL.createObjectURL(data), link = document.createElement('a');
      link.href = url; link.download = `structure_${job.id}.${format}`; link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (err) { onError(txt('导出失败，请重试。', 'Export failed. Please retry.')); }
    finally { setExporting(false); }
  }
  return <div className="sg-live-results">
    <div className="sg-live-provenance"><strong>{job.source_name}</strong><span>{systemText(job.profile?.label || 'Vib2Mol')}</span><span>{job.settings.formula ? txt(`分子式筛选：${job.settings.formula}`, `Formula filter: ${job.settings.formula}`) : txt('未设置分子式筛选', 'No formula filter')}</span><span>{job.created_at}</span></div>
    {running && <div className="sg-empty-results" role="status"><Loader2 className="sg-spin" size={35} /><h3>{job.status === 'queued' ? txt('等待模型执行', 'Queued') : txt('正在生成并检查候选', 'Generating and validating candidates')}</h3><p>{txt("任务在后台运行，可稍后从生成记录查看。", "Running in the background; check generation history later.")}</p></div>}
    {job.status === 'failed' && <div role="alert" className="sg-alert is-error">{systemText(job.error)}</div>}
    {job.status === 'completed' && <>
      <p className="sg-help">{txt(`实际返回 ${candidates.length} 个有效候选 · ${job.result.duration_seconds} 秒`, `${candidates.length} valid candidates · ${job.result.duration_seconds} seconds`)}</p>
      {job.result.warnings?.map((warning, i) => <p className="sg-help" key={i}>{systemText(warning)}</p>)}
      <div className="sg-candidate-grid">{candidates.map(item => <button key={item.id} className={`sg-candidate ${candidate.id === item.id ? 'is-selected' : ''}`} aria-pressed={candidate.id === item.id} onClick={() => setSelected(item.id)}>
        <div className="sg-candidate-top"><span>#{item.rank}</span><small>{txt('模型候选', 'Model candidate')}</small></div>
        {item.image_png ? <img className="sg-molecule-image" src={`data:image/png;base64,${item.image_png}`} alt={`${txt('候选结构', 'Candidate structure')} ${item.rank}`} /> : <Atom size={45}/>}
        <strong>{item.formula}</strong><span className="sg-candidate-score">{txt('匹配得分', 'Matching score')} <b>{item.matching_score == null ? '—' : item.matching_score.toExponential(3)}</b></span>
      </button>)}</div>
      {candidate && <div className="sg-candidate-detail"><div className="sg-detail-illustration">{candidate.image_png ? <img className="sg-molecule-image" src={`data:image/png;base64,${candidate.image_png}`} alt={txt('选中候选结构', 'Selected structure')} /> : <Atom size={70}/>}</div><div><span className="sg-detail-eyebrow">#{candidate.rank} · {txt('候选详情', 'Candidate details')}</span><h3>{candidate.formula}</h3><label>SMILES<code>{candidate.smiles}</code></label><label>InChIKey<code>{candidate.inchikey}</code></label><button onClick={async () => { try { await navigator.clipboard.writeText(candidate.smiles); } catch { onError(txt('请选中 SMILES 手动复制。', 'Select the SMILES to copy manually.')); } }}><Copy size={14} />{txt('复制 SMILES', 'Copy SMILES')}</button></div></div>}
      {job.result.agent?.enabled && <div className="sg-agent-evidence">
        <h3>{txt('Agent 分析过程', 'Agent analysis')}</h3>
        <p>{job.settings.rerank ? txt('结构生成 → 有效性与分子式检查 → 光谱匹配 → 知识检索与辅助判断', 'Generation → validity and formula checks → matching → reference retrieval and review') : txt('结构生成 → 有效性与分子式检查 → 知识资料检索', 'Generation → validity and formula checks → reference retrieval')}</p>
        <p>{!candidates.length ? txt('没有有效候选，本次未进行知识重排。', 'No valid candidates; knowledge reranking was not performed.') : !job.settings.rerank ? txt('未启用匹配重排，本次仅展示知识参考资料。', 'Matching and reranking were disabled; references are supplementary.') : job.result.agent.knowledge_rerank_applied ? txt('参考光谱知识后调整了候选顺序；原模型匹配分数保持单独显示。', 'Spectroscopy evidence changed the order. Original matching scores remain separately displayed.') : candidates.length === 1 ? txt('本次只有一个候选，未进行二次重排；下方资料仅供参考。', 'Only one candidate was available. No second reranking was performed; references are supplementary.') : txt('已完成知识辅助检查，本次保留原候选顺序。', 'Knowledge review completed; the original candidate order was retained.')}</p>
        {!!job.result.agent.peaks?.length && <div className="sg-observed-peaks">{txt('参考峰位', 'Observed peaks')}：{job.result.agent.peaks.slice(0, 6).map(p => p.peak.toFixed(1)).join('、')} cm⁻¹</div>}
        {job.result.agent.references?.length > 0 && <details><summary>{txt(`查看检索资料（${job.result.agent.references.length} 条）`, `Retrieved references (${job.result.agent.references.length})`)}</summary>{job.result.agent.references.map((item, i) => <blockquote key={item.id || i}><strong>{item.source || txt('光谱参考资料', 'Spectroscopy reference')} · {txt('第', 'Page ')} {item.page} {txt('页', '')}</strong><p>{item.excerpt}</p></blockquote>)}</details>}
        {candidate?.agent_evidence && <details className="sg-preparation"><summary>{txt('当前候选的知识判断记录', 'Knowledge evidence for this candidate')}</summary><pre>{JSON.stringify(systemValue(candidate.agent_evidence), null, 2)}</pre></details>}

      </div>}
      <p className="sg-results-footnote">{txt("匹配得分用于排序，候选结构需结合实验确认。", "Scores indicate ranking; verify candidate structures experimentally.")}</p>
      <details className="sg-preparation"><summary>{txt('模型与输入记录', 'Model and input provenance')}</summary><pre>{JSON.stringify(systemValue({ profile: job.profile, settings: job.settings, source: job.input?.source?.reference, preparation: job.input?.model_input?.preparation, dropped: job.result.dropped }), null, 2)}</pre></details>
      {!history && <div className="sg-detail-actions"><FileExport txt={txt} disabled={exporting} actions={['json','csv','sdf'].map(format=>({label:format.toUpperCase(),run:()=>download(format)}))} /></div>}
      {history && candidate?.image_png && <button onClick={()=>{const link=document.createElement('a');link.href=`data:image/png;base64,${candidate.image_png}`;link.download=`structure_${candidate.rank}.png`;link.click();}}><Download size={14}/>{txt('下载选中结构图','Download selected structure')}</button>}
    </>}
  </div>;
}
