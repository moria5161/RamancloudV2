import React from 'react';
import { AlertTriangle, ClipboardCheck } from 'lucide-react';
import { usePreferences } from '../i18n';
import { QUALITY_LABELS } from './spectralQuality';
import './QualityReport.css';

const guidance = {
  uneven_spacing: ['部分算法按数据点而非实际波数间隔计算。请核对导出设置，必要时在处理前另行评估重采样；本次未插值或排序。', 'Some algorithms operate on sample indices. Check export settings and assess resampling separately; no interpolation or sorting was performed.'],
  narrow_spike: ['窄峰可能是瞬态干扰，也可能是真实拉曼峰。请核对原始曲线、重复采集和去鬼峰候选，勿直接删除。', 'Narrow peaks can be artifacts or real Raman features. Inspect the original curve and repeat measurements before accepting any repair.'],
  flat_top: ['连续接近最大值的平顶可能与截幅有关，也可能是真实峰形。未读取探测器量程，不能确认饱和；请核对曝光时间、激光功率及仪器原始计数。', 'A flat maximum may indicate clipping or a genuine profile. Detector limits are unknown, so saturation is not confirmed. Check exposure, laser power and original counts.'],
  constant_signal: ['信号几乎不变，请核对是否为空白、无信号或导出错误；本次不判定样品有无目标物质。', 'The signal barely changes. Check for blank acquisition, missing signal or export errors; no substance-presence conclusion is made.'],
};
const format = value => Number.isFinite(value) ? Number(value.toPrecision(7)).toString() : '—';

export default function QualityReport({ report }) {
  const { language } = usePreferences();
  const txt = (zh, en) => language === 'zh' ? zh : en;
  if (!report) return <p className="quality-unchecked">{txt('此记录暂无数据质量检查，请重新导入后查看。', 'No quality screening is stored for this record. Re-import to screen it.')}</p>;
  return <div className="quality-report" role="region" aria-label={txt('数据质量检查', 'Data quality screening')}>
    <h3>{report.issues.length ? <AlertTriangle size={16} /> : <ClipboardCheck size={16} />}{txt('数据质量检查', 'Data quality screening')}<span>{report.issues.length ? txt(`${report.issues.length} 类需复核`, `${report.issues.length} categories to review`) : txt('未发现明显异常', 'No obvious issue detected')}</span></h3>
    <p>{txt("自动检查仅供参考，原始数据未修改。", "Automated checks are advisory; original data is unchanged.")}</p>
    <p>{txt(`强度检查 ${report.spectra_checked}/${report.spectra_total} 条${report.sampled ? '（均匀抽样，未检查全部像素）' : '（全部）'}；波数轴完整检查。`, `Intensity: ${report.spectra_checked}/${report.spectra_total} spectra${report.sampled ? ' (uniform sampling, not every pixel)' : ' (all)'}; full axis checked.`)}</p>
    {report.issues.map(issue => <details key={issue.code} className="quality-issue">
      <summary>{txt(...(QUALITY_LABELS[issue.code] || [issue.code, issue.code]))} · {issue.count} {issue.code === 'constant_signal' ? txt('条光谱', 'spectra') : issue.code === 'uneven_spacing' ? txt('个间隔', 'intervals') : txt('处', 'locations')}</summary>
      <p>{txt(...(guidance[issue.code] || ['请人工复核该项。', 'Review this finding manually.']))}</p>
      {issue.code === 'constant_signal' && <p>{txt('本条光谱整体近似恒定，下表以首点定位该光谱。', 'The whole spectrum is nearly constant; its first point is listed for identification.')}</p>}
      {issue.truncated && <p>{txt('数量包含所有检出位置，下表最多显示前 32 处。', 'The count includes every detection in the checked spectra; at most 32 locations are listed.')}</p>}
      <div className="quality-table"><table><thead><tr><th>{txt('数据点（从 1 起）', 'Point (1-based)')}</th><th>{txt('波数 / 区间', 'Wavenumber / range')}</th><th>{txt('原始强度', 'Original intensity')}</th>{report.spectra_total > 1 && <th>{txt('位置（从 1 起）', 'Location (1-based)')}</th>}</tr></thead><tbody>
        {issue.locations.map((point, i) => <tr key={i}><td>{point.index + 1}</td><td>{point.start_wavenumber != null ? `${format(point.start_wavenumber)}–${format(point.end_wavenumber)}` : point.end_wavenumber != null ? `${format(point.wavenumber)}–${format(point.end_wavenumber)}` : format(point.wavenumber)}</td><td>{format(point.intensity)}</td>{report.spectra_total > 1 && <td>{point.row != null ? `${txt('行', 'Row')} ${point.row + 1}, ${txt('列', 'column')} ${point.column + 1}` : point.spectrum_index != null ? point.spectrum_index + 1 : txt('公共波数轴', 'Shared axis')}</td>}</tr>)}
      </tbody></table></div>
    </details>)}
    <details className="quality-method"><summary>{txt('检查规则与阈值', 'Screening rules & thresholds')}</summary><p>{txt(`间距变异系数 > ${report.rules.spacing_cv * 100}%；尖峰半高宽 ≤ ${report.rules.spike_width_points} 个数据点，显著度 ≥ 8 倍二阶差分 MAD 噪声估计且 ≥ 强度极差的 5%；接近最大值的平顶连续 ≥ ${report.rules.plateau_min_points} 点，容差为极差的 0.01%；近常量阈值为最大绝对强度的 10⁻¹²。`, 'Spacing CV > 1%; spike width ≤ 2.5 samples with prominence ≥ 8× second-difference MAD noise estimate and ≥ 5% signal range; maximum plateau ≥ 3 samples within 0.01% of signal range; constant threshold 10⁻¹² of maximum absolute intensity.')}</p><p>{txt('宽度按数据点计算；尖峰检查包含正负峰，不检测端点。未发现异常也不能证明数据没有问题。', 'Widths are measured in samples. Positive and negative spikes are screened; endpoints are not. No detection is not proof of good data.')}</p></details>
  </div>;
}
