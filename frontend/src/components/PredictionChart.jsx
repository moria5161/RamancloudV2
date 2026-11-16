import React from 'react';
import Plot from 'react-plotly.js';
import ChartViewport from './ChartViewport';
import useChartLayout from '../hooks/useChartLayout';
import { usePreferences } from '../i18n';

export default function PredictionChart({ result }) {
  const { t } = usePreferences();
  const layout = useChartLayout({
    paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)',
    margin: { l: 65, r: 28, t: 30, b: 60 },
    xaxis: { zeroline: false }, yaxis: { zeroline: false },
    hovermode: 'closest', dragmode: 'pan', showlegend: false,
  }, result);
  return <ChartViewport>{height => <Plot
    data={[{ x: result.wavenumber, y: result.intensity, type: 'scatter', mode: 'lines',
      name: t('predictedSpectrum'), line: { color: '#1688ec', width: 2 },
      hovertemplate: `%{x:.0f} cm⁻¹<br>%{y:.4f}<extra>${t('predictedSpectrum')}</extra>` }]}
    layout={{ ...layout, height, yaxis: { ...layout.yaxis, title: { ...layout.yaxis.title, text: t('normalizedIntensity') } } }}
    config={{ displaylogo: false, responsive: true, scrollZoom: true, modeBarButtonsToRemove: ['lasso2d', 'select2d'] }}
    style={{ width: '100%', height: '100%' }} useResizeHandler
  />}</ChartViewport>;
}
