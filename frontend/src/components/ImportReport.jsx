import { systemText, localize } from '../locale.js';
import React from 'react';
import { Download } from 'lucide-react';
import { usePreferences } from '../i18n';
import QualityReport from './QualityReport';
import './ImportReport.css';

export const SPECTRAL_ACCEPT = '.txt,.csv,.tsv,.dat,.asc,.xy,.prn,.mat,.xlsx,.jdx,.dx,.wdf,.wxd,.l6m,.npg';
export const FORMAT_NAMES = {
  two_columns: '双列光谱', labelled_spectrum: '命名列光谱', labelled_long: '坐标/时间长表',
  unlabelled_long: '手动指定长表', nanophoton_columns: 'Nanophoton 像素列',
  nanophoton_paired: 'Nanophoton 交替列', horiba_rows: 'Horiba 行矩阵',
  spectra_columns: '公共波数列矩阵', spectra_rows: '公共波数行矩阵',
  mat_cube: 'MAT 数据立方体', renishaw_wdf: 'Renishaw WDF', renishaw_wxd_single: 'Renishaw WXD 单谱', jcamp_dx: 'JCAMP-DX',
  horiba_labspec6: 'Horiba LabSpec6', nanophoton_npg: 'Nanophoton NPG',
};

export default function ImportReport({ metadata, onDownload, disabled }) {
  const { language } = usePreferences();
  const txt = (zh, en) => language === 'zh' ? zh : en;
  if (!metadata) return null;
  return <div className="import-report" aria-label={localize("导入检查结果")}>
    <div><strong>{systemText(FORMAT_NAMES[metadata.detected_format] || metadata.detected_format || metadata.format)}</strong>
      {metadata.container && <span>{metadata.container}</span>}
      {metadata.shape && <span>{metadata.shape.join(' × ')}</span>}
      {metadata.axis_unit && <span>{systemText(metadata.axis_unit)}</span>}
    </div>
    {metadata.selected_position && <p>{txt('光谱', 'Spectrum')} {metadata.spectrum_index + 1}/{metadata.spectrum_count} · X {Number(metadata.selected_position.x.toPrecision(6))} · Y {Number(metadata.selected_position.y.toPrecision(6))} µm</p>}
    {!!metadata.warnings?.length && <ul>{metadata.warnings.map(warning => <li key={warning}>{systemText(warning)}</li>)}</ul>}
    {onDownload && <>
      {metadata.conversion_status === 'converted' && <p className="import-conversion-status">{txt('已转为标准双列', 'Converted to two columns')}</p>}
      <div className="ai-actions"><button disabled={disabled} onClick={() => onDownload('original')}><Download size={14} />{txt('下载原始文件', 'Download original file')}</button><button disabled={disabled} onClick={() => onDownload('standardized')}><Download size={14} />{txt('下载标准双列', 'Download two-column data')}</button></div>
    </>}
    <QualityReport report={metadata.quality_check} />
    {(metadata.encoding || metadata.delimiter || metadata.sha256 || metadata.wavenumber_column != null) && <details className="import-file-details">
      <summary>{txt('文件详情', 'File details')}</summary>
      <div>{metadata.encoding && <span>{txt('编码', 'Encoding')}：{metadata.encoding}</span>}{metadata.delimiter && <span>{txt('分隔符', 'Delimiter')}：{metadata.delimiter}</span>}{metadata.wavenumber_column != null && <span>{txt('波数列', 'Wavenumber column')} {metadata.wavenumber_column} · {txt('强度列', 'Intensity column')} {metadata.intensity_column}</span>}</div>
      {metadata.sha256 && <code>SHA-256: {metadata.sha256}</code>}
    </details>}
  </div>;
}
