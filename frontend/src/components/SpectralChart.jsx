import React, { useEffect, useRef } from 'react';
import Plot from 'react-plotly.js';

const darkLayout = {
  paper_bgcolor: 'rgba(0,0,0,0)',
  plot_bgcolor: 'rgba(0,0,0,0)',
  modebar: {
    bgcolor: 'rgba(255,255,255,0.42)',
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
  const traces = [];

  if (rawData && showRaw) {
    traces.push({
      x: rawData.wavenumber,
      y: rawData.intensity,
      type: 'scatter',
      mode: 'lines',
      name: 'Raw',
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
      name: 'Processed',
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
      name: 'Baseline',
      line: { color: '#30d158', width: 1.5, dash: 'dash' },
      hovertemplate: '%{x:.2f} cm⁻¹<br>%{y:.2f}<extra>Baseline</extra>',
    });
  }

  // Cut range shaded area
  const shapes = [];
  if (cutRange && rawData) {
    shapes.push({
      type: 'rect',
      x0: cutRange[0],
      x1: cutRange[1],
      y0: 0,
      y1: 1,
      yref: 'paper',
      fillcolor: 'rgba(129,140,248,0.05)',
      line: { width: 1, color: 'rgba(129,140,248,0.2)', dash: 'dot' },
    });
  }

  return (
    <Plot
      data={traces}
      layout={{
        ...darkLayout,
        height,
        shapes,
        xaxis: {
          ...darkLayout.xaxis,
          autorange: true,
        },
        yaxis: {
          ...darkLayout.yaxis,
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
  const traces = [
    {
      x: rawData?.wavenumber || [],
      y: rawData?.intensity || [],
      type: 'scatter',
      mode: 'lines',
      name: 'Raw Spectrum',
      line: { color: 'rgba(0,0,0,0.48)', width: 1.5 },
      xaxis: 'x',
      yaxis: 'y',
    },
    {
      x: processedData?.wavenumber || [],
      y: processedData?.intensity || [],
      type: 'scatter',
      mode: 'lines',
      name: 'Processed Spectrum',
      line: { color: '#0071e3', width: 2 },
      xaxis: 'x2',
      yaxis: 'y2',
    },
  ];

  return (
    <Plot
      data={traces}
      layout={{
        grid: { rows: 2, columns: 1, subplots: [['xy'], ['xy2']], roworder: 'top to bottom' },
        ...darkLayout,
        height,
        xaxis: { ...darkLayout.xaxis, title: 'Wavenumber (cm⁻¹)', domain: [0, 1] },
        yaxis: { ...darkLayout.yaxis, title: 'Intensity', domain: [0.52, 1] },
        xaxis2: { ...darkLayout.xaxis, title: 'Wavenumber (cm⁻¹)', domain: [0, 1] },
        yaxis2: { ...darkLayout.yaxis, title: 'Intensity', domain: [0, 0.43] },
        annotations: [
          { x: 0.5, y: 1, xref: 'paper', yref: 'paper', text: 'Raw Spectrum', showarrow: false, font: { size: 11, color: 'rgba(0,0,0,0.48)' } },
          { x: 0.5, y: 0.48, xref: 'paper', yref: 'paper', text: 'Processed Spectrum', showarrow: false, font: { size: 11, color: '#0071e3' } },
        ],
      }}
      config={{ displayModeBar: true, displaylogo: false, responsive: true, scrollZoom: true }}
      style={{ width: '100%', height: '100%' }}
      useResizeHandler={true}
    />
  );
}
