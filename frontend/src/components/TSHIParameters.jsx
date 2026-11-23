import { systemText, localize } from '../locale.js';
import { usePreferences } from '../i18n';
import React from 'react';

const FIELDS = [
  ['center_wavenumber', '中心波数 (cm⁻¹)', null, null, 'any'],
  ['half_width', '波段半宽', 2, 128, 1],
  ['windowsize', '空间窗口边长', 3, 31, 2],
  ['count', '平滑区域数量', 1, 1000, 1],
  ['thr1', 'SVD 拐点阈值 thr1', 0, 1, 'any'],
  ['thr2', '成分增益阈值 thr2 (dB)', -100, 100, 'any'],
];

export default function TSHIParameters({ params, onChange, bm3dAvailable }) {
  usePreferences();
  const update = (key, value) => onChange({ ...params, [key]: value });
  return <div className="tshi-parameters">
    {FIELDS.map(([key, label, min, max, step]) => <label key={key}>
      <span>{systemText(label)}</span>
      <input type="number" value={params[key] ?? ''} min={min ?? undefined} max={max ?? undefined} step={step}
        onChange={e => update(key, e.target.value === '' ? '' : Number(e.target.value))} />
    </label>)}
    <label className="tshi-wide"><span>{localize("平滑度公式")}</span>
      <select value={params.smoothness || 'legacy'} onChange={e => update('smoothness', e.target.value)}>
        <option value="legacy">{localize("沿用源码（矩阵乘法）")}</option><option value="variance">{localize("标准方差（对照）")}</option>
      </select>
    </label>
    <label className="tshi-wide tshi-check">
      <input type="checkbox" checked={!!params.bm3d_enabled} disabled={!bm3dAvailable && !params.bm3d_enabled}
        onChange={e => update('bm3d_enabled', e.target.checked)} />
      <span>{localize("BM3D 中心图像（仅限非商业用途）")}{!bm3dAvailable ? localize(" · 依赖未就绪") : ''}</span>
    </label>
    {params.bm3d_enabled && <label className="tshi-wide"><span>{localize("BM3D 噪声标准差（原始强度单位）")}</span>
      <input type="number" value={params.bm3d_sigma ?? 5} min="0" max="1000000" step="any"
        onChange={e => update('bm3d_sigma', e.target.value === '' ? '' : Number(e.target.value))} />
    </label>}
  </div>;
}
