import React from 'react';
import { usePreferences } from '../i18n';
import './DespikeParameters.css';

export default function DespikeParameters({ params, onChange, disabled }) {
  const { language } = usePreferences();
  const txt = (zh, en) => language === 'zh' ? zh : en;
  const automatic = params.threshold == null;
  return <div className="despike-parameters">
    <p>{txt('仅自动修复孤立尖点，保留有峰形支撑的窄峰。', 'Repair isolated impulses; preserve supported narrow peaks.')}</p>
    <details><summary>{txt('高级设置', 'Advanced settings')}</summary>
      <label className="despike-auto"><input type="checkbox" checked={automatic} disabled={disabled} onChange={e => onChange({ ...params, threshold: e.target.checked ? null : 100 })} />{txt('自动检测阈值', 'Automatic detection threshold')}</label>
      <div className="despike-fields">
        <label>{txt('检测阈值', 'Detection threshold')}<input aria-label={txt('去鬼峰检测阈值', 'Despike detection threshold')} type="number" min="0" max="1000000000000" step="any" placeholder={txt('自动', 'Auto')} value={params.threshold ?? ''} disabled={disabled || automatic} onChange={e => onChange({ ...params, threshold: e.target.value === '' ? null : Number(e.target.value) })} /></label>
        <label>{txt('候选半高宽阈值（点）', 'Candidate FWHM threshold (points)')}<input aria-label={txt('去鬼峰半高宽阈值', 'Despike FWHM threshold')} type="number" min="0.1" max="50" step="0.1" value={params.fwhm_threshold ?? ''} disabled={disabled} onChange={e => onChange({ ...params, fwhm_threshold: e.target.value === '' ? null : Number(e.target.value) })} /></label>
      </div>
      <small>{txt("阈值按强度、半高宽按数据点设置；请核对真实窄峰。", "Threshold uses intensity units; width uses data points. Check real narrow peaks.")}</small>
    </details>
  </div>;
}
