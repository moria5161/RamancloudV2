import { systemText } from '../locale.js';
import React, { useState } from 'react';
import { ArrowRight, FileText, Loader2 } from 'lucide-react';
import './SpectrumImportConfirmation.css';

export default function SpectrumImportConfirmation({ inspection, isBatch, busy, onConfirm, onCancel, txt }) {
  const items = isBatch ? inspection.items : [inspection];
  const invalid = items.filter(item => item.status === 'invalid').length;
  const [selectedIndex, setSelectedIndex] = useState(0);
  return <section className="spectrum-import-confirmation" aria-label={txt('格式转换确认', 'Confirm format conversion')}>
    <h2><FileText size={18} />{txt('检测到需要转换的光谱格式', 'Spectrum format conversion needed')}</h2>
    <p>{txt('将转换为波数—强度双列，保留原始文件。', 'Convert to Raman shift and intensity, keeping the original file.')}</p>

    <div className="spectrum-import-items">
      {items.map((item, index) => {
        const meta = item.source_check || {};
        const choice = meta.spectrum_choices?.find(option => option.index === selectedIndex);
        const preview = choice ? choice.preview.map(([wavenumber, intensity]) => ({ wavenumber, intensity })) : item.preview;
        const native = ['renishaw_wxd_single', 'horiba_labspec6', 'nanophoton_npg'].includes(meta.detected_format);
        const label = value => value?.replace(/\(\d{4}\/.*$/, '');
        const display = value => native && typeof value === 'number'
          ? Number(value.toPrecision(8)) : value;
        return <article key={`${item.source_name}:${index}`}>
          <h3>{item.source_name}</h3>
          {item.status === 'invalid' ? <p className="ai-inline-error">{systemText(item.error)}</p> : <>
            {meta.selection_required && <label className="spectrum-position-select">{txt(`文件含 ${meta.spectrum_count} 条光谱，选择一条导入`, `${meta.spectrum_count} spectra — select one to import`)}<select aria-label={txt('选择光谱位置', 'Select spectrum position')} value={selectedIndex} disabled={busy} onChange={event => setSelectedIndex(Number(event.target.value))}>{meta.spectrum_choices.map(option => <option key={option.index} value={option.index}>{txt('光谱', 'Spectrum')} {option.index + 1} · X {Number(option.x.toPrecision(6))} · Y {Number(option.y.toPrecision(6))} µm</option>)}</select></label>}
            {meta.axis_conversion && <p>{txt(`波长 → 拉曼位移 · 激发波长 ${Number(meta.laser_wavelength_nm.toPrecision(8))} nm`, `Wavelength → Raman shift · Excitation ${Number(meta.laser_wavelength_nm.toPrecision(8))} nm`)}</p>}
            <p className="ai-muted">{meta.instrument && `${meta.instrument} · `}{item.points} {txt('个点', 'points')} · {display(item.wavenumber_min)}–{display(item.wavenumber_max)} cm⁻¹</p>

            {meta.wavenumber_column && <p>{txt('横轴', 'X axis')}：{txt('第', 'Column ')}{meta.wavenumber_column}{txt(' 列', '')} {label(meta.wavenumber_label)} <ArrowRight size={12} /> {txt('拉曼位移', 'Raman shift')}；{txt('强度', 'Intensity')}：{txt('第', 'Column ')}{meta.intensity_column}{txt(' 列', '')} {label(meta.intensity_label)}</p>}
            {!item.requires_confirmation && <p className="ai-muted">{txt('已是双列光谱，将直接导入。', 'Already a two-column spectrum; ready to import.')}</p>}
            {!!meta.warnings?.length && <ul>{meta.warnings.map(warning => <li key={warning}>{systemText(warning)}</li>)}</ul>}
            <details open={!isBatch}>
              <summary>{txt('标准双列预览（前 5 个点）', 'Two-column preview (first 5 points)')}</summary>
              {native && <p className="ai-muted">{txt('预览已四舍五入，下载保留完整精度。', 'Preview is rounded; downloads retain full precision.')}</p>}
              <table><thead><tr><th>{txt('拉曼位移（cm⁻¹）', 'Raman shift (cm⁻¹)')}</th><th>{txt('强度', 'Intensity')}</th></tr></thead><tbody>{preview.map((row, i) => <tr key={i}><td>{display(row.wavenumber)}</td><td>{display(row.intensity)}</td></tr>)}</tbody></table>
            </details>
          </>}
        </article>;
      })}
    </div>
    {invalid > 0 && <p className="ai-muted">{txt(`${invalid} 个文件无法解析，将标记失败；其余文件可继续导入。`, `${invalid} invalid files will be marked as failed; the remaining files can be imported.`)}</p>}
    <div className="ai-actions">
      <button className="ai-primary" disabled={busy} onClick={() => onConfirm(!isBatch && inspection.source_check?.selection_required ? selectedIndex : undefined)}>{busy && <Loader2 size={16} className="ai-spin" />}{txt('确认转换并导入', 'Confirm conversion and import')}</button>
      <button disabled={busy} onClick={onCancel}>{txt('取消导入', 'Cancel import')}</button>
    </div>

  </section>;
}
