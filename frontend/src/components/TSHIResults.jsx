import { systemValue, systemText, localize } from '../locale.js';
import React from 'react';
import Plot from 'react-plotly.js';
import { usePreferences } from '../i18n';

const config = { displaylogo: false, responsive: true };
const number = value => Number(value.toFixed(3));
const base = { paper_bgcolor: 'transparent', plot_bgcolor: 'transparent',
  margin: { l: 44, r: 35, t: 32, b: 40 }, font: { size: 11, color: '#687984' } };

export default function TSHIResults({ records }) {
  const { theme } = usePreferences();
  const layout = { ...base, font: { ...base.font, color: theme === 'dark' ? '#bacbd1' : '#687984' } };
  return <div className="tshi-results" data-testid="tshi-results">
    {records.map((record, index) => {
      const d = record.details;
      const images = [[localize("TSHI 输入中心图像"), d.center_raw], [localize("TSHI 输出中心图像"), d.center_tshi]];
      if (d.center_bm3d) images.push([localize("BM3D 独立中心图像"), d.center_bm3d]);
      const all = images.flatMap(([, values]) => values.flat());
      const min = Math.min(...all), max = Math.max(...all);
      return <section key={index}>
        <h3>TSHI / IIALRMA{records.length > 1 ? ` · ${index + 1}` : ''}</h3>
        <dl className="tshi-summary">
          <div><dt>{localize("中心波数")}</dt><dd>{number(d.center_wavenumber)} cm⁻¹</dd></div>
          <div><dt>{localize("实际输出范围")}</dt><dd>{d.selected_range.map(number).join(' ~ ')} cm⁻¹ · {d.selected_bands}{localize(" 波段")}</dd></div>
          <div><dt>{localize("成像尺寸")}</dt><dd>{d.spatial_shape.join(' × ')}</dd></div>
          <div><dt>{localize("平滑区域")}</dt><dd>{d.actual_count} / {d.requested_count}</dd></div>
          <div><dt>{localize("保留成分（从 1 计数）")}</dt><dd>{d.selected_components.map(v => v + 1).join(', ') || localize("零值输入")}</dd></div>
          <div><dt>{localize("有效秩 / 考察成分")}</dt><dd>{d.effective_rank} / {d.considered_components}</dd></div>
          <div><dt>{localize("耗时")}</dt><dd>{(d.duration_ms / 1000).toFixed(2)} s</dd></div>
        </dl>
        <div className="tshi-images">
          {images.map(([title, values]) => <figure key={title}>
            <figcaption>{systemText(title)}</figcaption>
            <Plot data={[{ type: 'heatmap', z: values, zmin: min, zmax: max, colorscale: 'Viridis',
              colorbar: { thickness: 9 }, hovertemplate: '(%{x}, %{y})<br>%{z:.5g}<extra></extra>' }]}
              layout={{ ...layout, height: 285, xaxis: { title: `X (×${d.preview_scale})`, constrain: 'domain' },
                yaxis: { title: `Y (×${d.preview_scale})`, autorange: 'reversed', scaleanchor: 'x' } }}
              config={config} useResizeHandler style={{ width: '100%', height: 285 }} />
          </figure>)}
        </div>
        {!!d.singular_values.length && <Plot data={[
          { type: 'scatter', mode: 'lines+markers', name: localize("奇异值"), x: d.singular_values.map((_, i) => i + 1), y: d.singular_values },
          { type: 'bar', name: localize("平均 SNR 增益 (dB)"), x: d.mean_snr_gain_db.map((_, i) => i + 1), y: d.mean_snr_gain_db,
            yaxis: 'y2', marker: { color: d.mean_snr_gain_db.map((_, i) => d.selected_components.includes(i) ? '#238b68' : '#aeb9bd') } },
        ]} layout={{ ...layout, height: 280, margin: { l: 48, r: 48, t: 36, b: 50 },
          legend: { orientation: 'h', y: 1.18 }, xaxis: { title: localize("SVD 成分（从 1 计数）"), dtick: 1 },
          yaxis: { title: localize("奇异值"), type: 'log' }, yaxis2: { title: localize("增益 (dB)"), overlaying: 'y', side: 'right' } }}
          config={config} useResizeHandler style={{ width: '100%', height: 280 }} />}
        <ul className="tshi-warnings">{d.warnings.map(w => <li key={w}>{systemText(w)}</li>)}</ul>
        <details><summary>{localize("参数与诊断记录")}</summary><pre>{JSON.stringify(systemValue({ params: record.params,
          center_index: d.center_index, selected_band_indices: d.selected_band_indices,
          curvature: d.curvature, smooth_regions: d.smooth_regions }), null, 2)}</pre></details>
      </section>;
    })}
  </div>;
}
