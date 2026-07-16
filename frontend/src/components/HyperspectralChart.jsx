import React, { useState, useMemo, useCallback } from 'react';
import Plot from 'react-plotly.js';
import { Map, Activity, Crosshair, Thermometer } from 'lucide-react';

const darkLayout = {
  paper_bgcolor: 'rgba(0,0,0,0)',
  plot_bgcolor: 'rgba(0,0,0,0)',
  font: { color: 'rgba(0,0,0,0.58)', family: 'Inter, sans-serif', size: 11 },
  margin: { l: 50, r: 20, t: 30, b: 50 },
  dragmode: 'pan',
};

const equalPixelXAxis = {
  title: 'Pixel X',
  gridcolor: 'rgba(0,0,0,0.06)',
  zeroline: false,
  constrain: 'domain',
};

const equalPixelYAxis = {
  title: 'Pixel Y',
  gridcolor: 'rgba(0,0,0,0.06)',
  zeroline: false,
  autorange: 'reversed',
  scaleanchor: 'x',
  scaleratio: 1,
  constrain: 'domain',
};

// ============================================================
// Imaging Heatmap
// ============================================================
export function ImagingHeatmap({ previewData, wavenumber, selectedWN, onSelectWN, onHeatmapClick, title, height, colorscale }) {
  // Find closest wavenumber index
  const wnIdx = useMemo(() => {
    if (!wavenumber || !selectedWN) return 0;
    let best = 0, bestDiff = Infinity;
    wavenumber.forEach((wn, i) => {
      const diff = Math.abs(wn - selectedWN);
      if (diff < bestDiff) { bestDiff = diff; best = i; }
    });
    return best;
  }, [wavenumber, selectedWN]);

  // Extract 2D slice at selected wavenumber
  const heatmapZ = useMemo(() => {
    if (!previewData || previewData.length === 0) return [[]];
    try {
      // previewData is [h][w][spectral] or [h][w]
      if (Array.isArray(previewData[0]) && Array.isArray(previewData[0][0])) {
        return previewData.map(row => row.map(pixel => pixel[wnIdx] || 0));
      }
      return previewData;
    } catch { return [[]]; }
  }, [previewData, wnIdx]);

  const traces = [{
    z: heatmapZ,
    type: 'heatmap',
    colorscale: colorscale || 'Jet',
    colorbar: { title: 'Intensity', titleside: 'right', thickness: 12, len: 0.6 },
    hovertemplate: 'Pixel (%{x}, %{y})<br>Intensity: %{z:.2f}<extra></extra>',
  }];

  const wnRange = wavenumber ? [Math.min(...wavenumber), Math.max(...wavenumber)] : [0, 4000];
  const sliderValue = Math.min(wnRange[1], Math.max(wnRange[0], selectedWN ?? wnRange[0]));

  return (
    <div className="space-y-2">
      {/* Wavenumber selector */}
      <div className="flex items-center gap-3 px-1">
        <Crosshair className="w-3.5 h-3.5 text-purple-400" />
        <label className="text-xs text-gray-400">Select Wavenumber (cm⁻¹):</label>
        <input
          type="range"
          min={wnRange[0]}
          max={wnRange[1]}
          step={1}
          value={sliderValue}
          onChange={e => onSelectWN(parseFloat(e.target.value))}
          className="flex-1 accent-purple-500"
        />
        <span className="text-xs text-purple-400 font-mono w-16 text-right">
          {selectedWN?.toFixed(0) || '--'}
        </span>
      </div>

      <Plot
        data={traces}
        layout={{
          ...darkLayout,
          height: height || 500,
          title: title || 'Hyperspectral Imaging',
          xaxis: equalPixelXAxis,
          yaxis: equalPixelYAxis,
        }}
        config={{ displayModeBar: true, displaylogo: false, responsive: true, scrollZoom: true }}
        onClick={onHeatmapClick}
        style={{ width: '100%' }}
        useResizeHandler={true}
      />
    </div>
  );
}

// ============================================================
// Time Series Heatmap
// ============================================================
export function TimeSeriesHeatmap({ data2D, wavenumber, title, height, colorscale, onHeatmapClick }) {
  const indexAxis = useMemo(() => (
    Array.isArray(data2D) ? data2D.map((_, index) => index) : []
  ), [data2D]);
  const traces = [{
    z: data2D || [[]],
    type: 'heatmap',
    colorscale: colorscale || 'Jet',
    colorbar: { title: 'Intensity', titleside: 'right', thickness: 12, len: 0.6 },
    x: wavenumber,
    y: indexAxis,
    hovertemplate: 'Index %{y}<br>WN: %{x:.1f} cm⁻¹<br>Intensity: %{z:.2f}<extra></extra>',
  }];

  return (
    <Plot
      data={traces}
      layout={{
        ...darkLayout,
        height: height || 500,
        title: title || 'Time Series',
        xaxis: { title: 'Wavenumber (cm⁻¹)', gridcolor: 'rgba(255,255,255,0.03)', zeroline: false },
        yaxis: { title: 'Time Index', gridcolor: 'rgba(255,255,255,0.03)', zeroline: false },
      }}
      config={{ displayModeBar: true, displaylogo: false, responsive: true, scrollZoom: true }}
      onClick={onHeatmapClick}
      style={{ width: '100%' }}
      useResizeHandler={true}
    />
  );
}

// ============================================================
// Compare Time Series (Raw vs Processed stacked)
// ============================================================
export function CompareTimeSeriesHeatmap({ rawData2D, processedData2D, rawWavenumber, processedWavenumber, title, height, colorscale, onHeatmapClick }) {
  const hasProcessed = Array.isArray(processedData2D) && processedData2D.length > 0;
  const rawIndexAxis = useMemo(() => (
    Array.isArray(rawData2D) ? rawData2D.map((_, index) => index) : []
  ), [rawData2D]);
  const processedIndexAxis = useMemo(() => (
    Array.isArray(processedData2D) ? processedData2D.map((_, index) => index) : []
  ), [processedData2D]);
  const traces = [
    {
      z: rawData2D || [[]],
      type: 'heatmap',
      colorscale: colorscale || 'Jet',
      colorbar: { title: 'Raw', titleside: 'right', thickness: 10, len: hasProcessed ? 0.42 : 0.6, y: hasProcessed ? 0.75 : 0.5 },
      x: rawWavenumber,
      y: rawIndexAxis,
      name: 'Raw',
      xaxis: 'x',
      yaxis: 'y',
      hovertemplate: 'Index %{y}<br>WN: %{x:.1f} cm⁻¹<br>Raw: %{z:.2f}<extra></extra>',
    },
  ];

  if (hasProcessed) {
    traces.push({
      z: processedData2D,
      type: 'heatmap',
      colorscale: colorscale || 'Jet',
      colorbar: { title: 'Processed', titleside: 'right', thickness: 10, len: 0.42, y: 0.25 },
      x: processedWavenumber || rawWavenumber,
      y: processedIndexAxis,
      name: 'Processed',
      xaxis: 'x2',
      yaxis: 'y2',
      hovertemplate: 'Index %{y}<br>WN: %{x:.1f} cm⁻¹<br>Processed: %{z:.2f}<extra></extra>',
    });
  }

  return (
    <Plot
      data={traces}
      layout={{
        ...darkLayout,
        height: height || 600,
        title: title || (hasProcessed ? 'Raw (top) vs Processed (bottom)' : 'Time Series Heatmap'),
        ...(hasProcessed ? {
          grid: { rows: 2, columns: 1, subplots: [['xy'], ['xy2']], roworder: 'top to bottom' },
          xaxis: { title: 'Wavenumber (cm⁻¹)', gridcolor: 'rgba(0,0,0,0.06)', zeroline: false, domain: [0, 1] },
          yaxis: { title: 'Time Index', gridcolor: 'rgba(0,0,0,0.06)', zeroline: false, domain: [0.54, 1] },
          xaxis2: { title: 'Wavenumber (cm⁻¹)', gridcolor: 'rgba(0,0,0,0.06)', zeroline: false, domain: [0, 1] },
          yaxis2: { title: 'Time Index', gridcolor: 'rgba(0,0,0,0.06)', zeroline: false, domain: [0.02, 0.48] },
        } : {
          xaxis: { title: 'Wavenumber (cm⁻¹)', gridcolor: 'rgba(0,0,0,0.06)', zeroline: false },
          yaxis: { title: 'Time Index', gridcolor: 'rgba(0,0,0,0.06)', zeroline: false },
        }),
      }}
      config={{ displayModeBar: true, displaylogo: false, responsive: true, scrollZoom: true }}
      onClick={onHeatmapClick}
      style={{ width: '100%' }}
      useResizeHandler={true}
    />
  );
}

// ============================================================
// Single Pixel Spectrum
// ============================================================
export function PixelSpectrum({ previewData, wavenumber, pixelX, pixelY, rawSpectrum, processedSpectrum, processedWavenumber, title, height }) {
  const spectrum = useMemo(() => {
    if (rawSpectrum) return rawSpectrum;
    if (!previewData || !wavenumber || pixelX == null || pixelY == null) return null;
    try {
      const row = previewData[Math.min(pixelY, previewData.length - 1)];
      if (!row) return null;
      const pixel = row[Math.min(pixelX, row.length - 1)];
      return Array.isArray(pixel) ? pixel : null;
    } catch { return null; }
  }, [previewData, wavenumber, pixelX, pixelY, rawSpectrum]);

  if (!spectrum) {
    return (
      <div className="flex items-center justify-center text-gray-600 text-sm" style={{ height: height || 300 }}>
        <Crosshair className="w-4 h-4 mr-2" /> Click on the heatmap to select a pixel
      </div>
    );
  }

  const traces = [{
    x: wavenumber,
    y: spectrum,
    type: 'scatter',
    mode: 'lines',
    name: `Raw (${pixelX}, ${pixelY})`,
    line: { color: 'rgba(0,0,0,0.48)', width: 1.6 },
    hovertemplate: '%{x:.2f} cm⁻¹<br>%{y:.2f}<extra>Raw</extra>',
  }];

  if (processedSpectrum) {
    traces.push({
      x: processedWavenumber || wavenumber,
      y: processedSpectrum,
      type: 'scatter',
      mode: 'lines',
      name: 'Processed',
      line: { color: '#0071e3', width: 2.2 },
      hovertemplate: '%{x:.2f} cm⁻¹<br>%{y:.2f}<extra>Processed</extra>',
    });
  }

  return (
    <Plot
      data={traces}
      layout={{
        ...darkLayout,
        height: height || 300,
        title: title || `Spectrum at Pixel (${pixelX}, ${pixelY})`,
        xaxis: { ...darkLayout.xaxis, title: 'Wavenumber (cm⁻¹)', gridcolor: 'rgba(255,255,255,0.03)', zeroline: false },
        yaxis: { ...darkLayout.yaxis, title: 'Intensity', gridcolor: 'rgba(255,255,255,0.03)', zeroline: false },
      }}
      config={{ displayModeBar: false, displaylogo: false, responsive: true }}
      style={{ width: '100%' }}
      useResizeHandler={true}
    />
  );
}

// ============================================================
// Compare Imaging (Raw vs Processed side by side)
// ============================================================
export function CompareImaging({ rawPreview, processedPreview, wavenumber, selectedWN, onSelectWN, onHeatmapClick, height }) {
  const wnIdx = useMemo(() => {
    if (!wavenumber || !selectedWN) return 0;
    let best = 0, bestDiff = Infinity;
    wavenumber.forEach((wn, i) => {
      const diff = Math.abs(wn - selectedWN);
      if (diff < bestDiff) { bestDiff = diff; best = i; }
    });
    return best;
  }, [wavenumber, selectedWN]);

  const rawZ = useMemo(() => {
    if (!rawPreview?.length) return [[]];
    if (!Array.isArray(rawPreview[0]?.[0])) return rawPreview;
    return rawPreview.map(row => row.map(pixel => pixel[wnIdx] || 0));
  }, [rawPreview, wnIdx]);

  const procZ = useMemo(() => {
    if (!processedPreview?.length) return null;
    if (!Array.isArray(processedPreview[0]?.[0])) return processedPreview;
    return processedPreview.map(row => row.map(pixel => pixel[wnIdx] || 0));
  }, [processedPreview, wnIdx]);

  const traces = [
    {
      z: rawZ, type: 'heatmap', colorscale: 'Jet',
      colorbar: { title: 'Raw', titleside: 'right', thickness: 10, len: 0.45, y: 0.75 },
      name: 'Raw', xaxis: 'x', yaxis: 'y',
      hovertemplate: '(%{x},%{y}) Raw: %{z:.2f}<extra></extra>',
    },
  ];

  if (procZ) {
    traces.push({
      z: procZ, type: 'heatmap', colorscale: 'Jet',
      colorbar: { title: 'Processed', titleside: 'right', thickness: 10, len: 0.45, y: 0.25 },
      name: 'Processed', xaxis: 'x2', yaxis: 'y2',
      hovertemplate: '(%{x},%{y}) Proc: %{z:.2f}<extra></extra>',
    });
  }

  const wnRange = wavenumber ? [Math.min(...wavenumber), Math.max(...wavenumber)] : [0, 4000];
  const sliderValue = Math.min(wnRange[1], Math.max(wnRange[0], selectedWN ?? wnRange[0]));

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-3 px-1">
        <Crosshair className="w-3.5 h-3.5 text-purple-400" />
        <label className="text-xs text-gray-400">Wavenumber (cm⁻¹):</label>
        <input type="range" min={wnRange[0]} max={wnRange[1]} step={1}
          value={sliderValue} onChange={e => onSelectWN(parseFloat(e.target.value))}
          className="flex-1 accent-purple-500" />
        <span className="text-xs text-purple-400 font-mono w-16 text-right">{selectedWN?.toFixed(0) || '--'}</span>
      </div>
      <Plot
        data={traces}
        layout={{
          grid: procZ ? { rows: 2, columns: 1, subplots: [['xy'], ['xy2']], roworder: 'top to bottom' } : undefined,
          ...darkLayout,
          height: height || 600,
          title: procZ ? 'Raw (top) vs Processed (bottom)' : 'Raw Imaging',
          ...(procZ ? {
            xaxis: { ...equalPixelXAxis, domain: [0, 1] },
            yaxis: { ...equalPixelYAxis, domain: [0.54, 1] },
            xaxis2: { ...equalPixelXAxis, domain: [0, 1] },
            yaxis2: { ...equalPixelYAxis, scaleanchor: 'x2', domain: [0.02, 0.48] },
          } : {
            xaxis: equalPixelXAxis,
            yaxis: equalPixelYAxis,
          }),
        }}
        config={{ displayModeBar: true, displaylogo: false, responsive: true, scrollZoom: true }}
        onClick={onHeatmapClick}
        style={{ width: '100%' }}
        useResizeHandler={true}
      />
    </div>
  );
}
