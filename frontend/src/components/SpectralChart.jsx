import React from 'react';
import Plot from 'react-plotly.js';
import useChartLayout from '../hooks/useChartLayout';
import { usePreferences } from '../i18n';

const darkLayout = {
  paper_bgcolor: 'rgba(0,0,0,0)',
  plot_bgcolor: 'rgba(0,0,0,0)',
  modebar: {
    bgcolor: 'rgba(0,0,0,0)',
    color: 'rgba(0,0,0,0.34)',
    activecolor: '#0071e3',
  },
  font: { color: 'rgba(0,0,0,0.58)', family: 'Inter, sans-serif', size: 11 },
  xaxis: {
    title: { text: 'Wavenumber (cm⁻¹)', font: { size: 12, color: 'rgba(0,0,0,0.58)' } },
    gridcolor: 'rgba(0,0,0,0.06)',
    linecolor: 'rgba(0,0,0,0.1)',
    zeroline: false,
  },
  yaxis: {
    title: { text: 'Intensity', font: { size: 12, color: 'rgba(0,0,0,0.58)' } },
    gridcolor: 'rgba(0,0,0,0.06)',
    linecolor: 'rgba(0,0,0,0.1)',
    zeroline: false,
  },
  legend: {
    x: 0.99, y: 0.99,
    bgcolor: 'rgba(255,255,255,0.75)',
    bordercolor: 'rgba(0,0,0,0.1)',
    font: { size: 10, color: 'rgba(0,0,0,0.58)' }
  },
  margin: { l: 50, r: 20, t: 20, b: 50 },
  hovermode: 'closest',
  dragmode: 'pan',
};

export default function SpectralChart({
  rawData,
  processedData,
  baselineData,
  cutRange,
  height = 500,
  showRaw = true,
}) {
  const layout = useChartLayout(darkLayout, rawData);
  const { t } = usePreferences();
  const traces = [];

  if (rawData && showRaw) {
    traces.push({
      x: rawData.wavenumber,
      y: rawData.intensity,
      type: 'scatter',
      mode: 'lines',
      name: t('raw'),
      line: { color: 'rgba(148,163,184,0.5)', width: 1.5 },
      hovertemplate: '%{x:.2f} cm⁻¹<br>%{y:.2f}<extra>Raw</extra>',
    });
  }

  if (processedData) {
    traces.push({
      x: processedData.wavenumber,
      y: processedData.intensity,
      type: 'scatter',
      mode: 'lines',
      name: t('processed'),
      line: { color: '#0071e3', width: 2.2 },
      hovertemplate: '%{x:.2f} cm⁻¹<br>%{y:.2f}<extra>Processed</extra>',
    });
  }

  if (baselineData && baselineData.length > 0) {
    traces.push({
      x: processedData?.wavenumber || rawData?.wavenumber || [],
      y: baselineData,
      type: 'scatter',
      mode: 'lines',
      name: t('baseline'),
      line: { color: '#30d158', width: 1.5, dash: 'dash' },
      hovertemplate: '%{x:.2f} cm⁻¹<br>%{y:.2f}<extra>Baseline</extra>',
    });
  }

  const shapes = [];
  if (cutRange && rawData) {
    const minimum = Math.min(...rawData.wavenumber);
    const maximum = Math.max(...rawData.wavenumber);
    cutRange.forEach(boundary => {
      if (boundary > minimum && boundary < maximum) shapes.push({
        type: 'line', x0: boundary, x1: boundary,
        y0: 0, y1: 1, yref: 'paper',
        line: { width: 1, color: '#0071e3', dash: 'dot' },
      });
    });
  }

  return (
    <Plot
      data={traces}
      layout={{
        ...layout,
        height,
        shapes,
        xaxis: {
          ...layout.xaxis,
          autorange: true,
        },
        yaxis: {
          ...layout.yaxis,
          autorange: true,
        },
      }}
      config={{
        displayModeBar: true,
        modeBarButtonsToRemove: ['lasso2d', 'select2d', 'sendDataToCloud'],
        modeBarButtonsToAdd: ['resetScale2d'],
        displaylogo: false,
        responsive: true,
        scrollZoom: true,
      }}
      style={{ width: '100%', height: '100%' }}
      useResizeHandler={true}
    />
  );
}

/**
 * Compare chart: raw vs processed in 2 subplots
 */
export function CompareChart({ rawData, processedData, height = 700 }) {
  const layout = useChartLayout(darkLayout, rawData);
  const { t } = usePreferences();
  const traces = [
    {
      x: rawData?.wavenumber || [],
      y: rawData?.intensity || [],
      type: 'scatter',
      mode: 'lines',
      name: t('raw'),
      line: { color: '#8b95a5', width: 1.5 },
      xaxis: 'x',
      yaxis: 'y',
    },
    {
      x: processedData?.wavenumber || [],
      y: processedData?.intensity || [],
      type: 'scatter',
      mode: 'lines',
      name: t('processed'),
      line: { color: '#0071e3', width: 2 },
      xaxis: 'x2',
      yaxis: 'y2',
    },
  ];

  return (
    <Plot
      data={traces}
      layout={{
        grid: { rows: 2, columns: 1, subplots: [['xy'], ['x2y2']], roworder: 'top to bottom' },
        ...layout,
        height,
        xaxis: { ...layout.xaxis, domain: [0, 1], anchor: 'y' },
        margin: { l: 60, r: 30, t: 45, b: 50 },
        yaxis: { ...layout.yaxis, title: `${t('raw')} · ${t('intensity')}`, domain: [0.58, 1], anchor: 'x' },
        xaxis2: { ...layout.xaxis, domain: [0, 1], anchor: 'y2', matches: 'x' },
        yaxis2: { ...layout.yaxis, title: `${t('processed')} · ${t('intensity')}`, domain: [0, 0.42], anchor: 'x2' },
      }}
      config={{ displayModeBar: true, displaylogo: false, responsive: true, scrollZoom: true }}
      style={{ width: '100%', height: '100%' }}
      useResizeHandler={true}
    />
  );
}
