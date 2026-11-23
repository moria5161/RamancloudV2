import Plotly from 'plotly.js/dist/plotly';

function spectrumFigure(spectrum, title) {
  return {
    data: [{
      x: spectrum.wavenumber,
      y: spectrum.intensity,
      type: 'scatter',
      mode: 'lines',
      line: { color: '#0071e3', width: 2 },
    }],
    layout: {
      title: { text: title, x: .5, xanchor: 'center', font: { size: 20 } },
      paper_bgcolor: '#ffffff',
      plot_bgcolor: '#ffffff',
      font: { family: 'Arial, Microsoft YaHei, sans-serif', size: 15, color: '#222222' },
      margin: { l: 100, r: 40, t: 90, b: 90 },
      showlegend: false,
      xaxis: { title: { text: 'Wavenumber (cm⁻¹)', standoff: 20 }, autorange: true, showline: true, linecolor: '#555555', gridcolor: '#e8e8e8', zeroline: false, automargin: true },
      yaxis: { title: { text: 'Intensity', standoff: 20 }, autorange: true, showline: true, linecolor: '#555555', gridcolor: '#e8e8e8', zeroline: false, automargin: true },
    },
    config: { staticPlot: true, displayModeBar: false },
  };
}
export async function spectrumImageData(spectrum, {title}) {
  await document.fonts?.ready;
  return Plotly.toImage(spectrumFigure(spectrum, title), {format:'png',width:1200,height:720,scale:2});
}
export default async function downloadSpectrumImage(spectrum, { filename, title }) {
  await document.fonts?.ready;
  return Plotly.downloadImage(spectrumFigure(spectrum, title), { format: 'png', filename, width: 1200, height: 720, scale: 2 });
}
