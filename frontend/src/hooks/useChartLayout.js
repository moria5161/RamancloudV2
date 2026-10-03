import { usePreferences } from '../i18n';
import { useRef } from 'react';

export default function useChartLayout(base, source) {
  const { theme, t } = usePreferences();
  const revision = useRef({ source, id: 1 });
  if (revision.current.source !== source) revision.current = { source, id: revision.current.id + 1 };
  const color = theme === 'dark' ? '#dce5ef' : '#555b65';
  const gridcolor = theme === 'dark' ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.06)';
  return {
    ...base,
    uirevision: revision.current.id,
    font: { ...base.font, color },
    modebar: { bgcolor: 'rgba(0,0,0,0)', color, activecolor: '#0071e3' },
    legend: { ...base.legend, x: 0, y: 1.08, orientation: 'h', bgcolor: 'rgba(0,0,0,0)', font: { color } },
    xaxis: { ...base.xaxis, gridcolor, title: { text: t('wavenumberAxis'), font: { color } } },
    yaxis: { ...base.yaxis, gridcolor, title: { text: t('intensity'), font: { color } } },
  };
}
