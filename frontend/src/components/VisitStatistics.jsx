import React, { useEffect, useState } from 'react';
import { Download, RefreshCw } from 'lucide-react';
import { usePreferences } from '../i18n';
import { saveBlob } from '../utils/processingRecord';
import VisitorGlobe from './VisitorGlobe';

const labels = { '/': 'homepage', '/spectral': 'spectralProcessing', '/hyperspectral': 'hyperspectralProcessing',
  '/extra-tools': 'extraTools', '/tutorial': 'tutorial', '/contributors': 'contributors' };

export default function VisitStatistics() {
  const { language, t } = usePreferences();
  const [data, setData] = useState(null);
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setBusy(true);
    fetch(`${import.meta.env.BASE_URL}api/visits/summary`, { signal: controller.signal })
      .then(response => { if (!response.ok) throw new Error(); return response.json(); })
      .then(result => { setData(result); setFailed(false); })
      .catch(error => { if (error.name !== 'AbortError') setFailed(true); })
      .finally(() => { if (!controller.signal.aborted) setBusy(false); });
    return () => controller.abort();
  }, [revision]);
  useEffect(() => {
    const update = () => setRevision(value => value + 1);
    window.addEventListener('ramancloud:pageview-recorded', update);
    return () => window.removeEventListener('ramancloud:pageview-recorded', update);
  }, []);
  const number = value => new Intl.NumberFormat(language).format(value);
  const exportStats = () => saveBlob(new Blob([JSON.stringify(data, null, 2)],
    { type: 'application/json' }), 'ramancloud-visit-statistics.json');
  return <section className="space-y-5" aria-labelledby="visit-statistics-heading">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <h2 id="visit-statistics-heading" className="text-lg font-semibold text-gray-200">{t('visitStatistics')}</h2>
      <div className="flex gap-2">
        <button type="button" title={t('refreshStatistics')} aria-label={t('refreshStatistics')} disabled={busy}
          onClick={() => setRevision(value => value + 1)} className="w-8 h-8 flex items-center justify-center rounded-md text-gray-500 hover:bg-white/10 disabled:opacity-40">
          <RefreshCw className={`w-4 h-4 ${busy ? 'animate-spin' : ''}`} />
        </button>
        <button type="button" title={t('exportStatistics')} aria-label={t('exportStatistics')} onClick={exportStats} disabled={!data}
          className="w-8 h-8 flex items-center justify-center rounded-md text-gray-500 hover:bg-white/10 disabled:opacity-40"><Download className="w-4 h-4" /></button>
      </div>
    </div>
    <>
      {failed && <p role="status" className="text-sm text-gray-500">{t('statisticsUnavailable')}</p>}
      {!data && busy && <p role="status" className="text-sm text-gray-500">{t('loadingStatistics')}</p>}
      {data && <>
        <dl className="grid grid-cols-2 md:grid-cols-4 gap-4 border-b border-white/10 pb-5">
          {[[t('totalPageviews'), data.total.pageviews], [t('newAnonymousSessions'), data.total.sessions],
            [t('todayPageviews'), data.today.pageviews], [t('last30Days'), data.daily.reduce((sum, day) => sum + day.pageviews, 0)]].map(([label, value]) =>
            <div key={label}><dt className="text-xs text-gray-500">{label}</dt><dd className="mt-2 text-2xl font-semibold text-gray-200">{number(value)}</dd></div>)}
        </dl>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="space-y-2">
            <h3 className="text-sm font-medium text-gray-200">{t('dailyPageviews')}</h3>
            <div className="h-32 flex items-end gap-1 border-b border-white/10" aria-label={t('dailyPageviews')}>
              {data.daily.map(day => <div key={day.day} title={`${day.day}: ${day.pageviews}`} className="flex-1 min-w-0 bg-blue-500/70"
                style={{ height: `${day.pageviews ? Math.max(2, day.pageviews / Math.max(1, ...data.daily.map(item => item.pageviews)) * 100) : 0}%` }} />)}
            </div>
            <div className="flex justify-between text-[10px] text-gray-500"><span>{data.daily[0].day}</span><span>{data.daily.at(-1).day} · UTC</span></div>
            <details className="text-xs text-gray-500"><summary className="cursor-pointer">{t('dailyCounts')}</summary>
              <div className="max-h-40 overflow-y-auto mt-2"><table className="w-full"><tbody>{data.daily.map(day => <tr key={day.day}><td className="py-1">{day.day}</td><td className="text-right">{number(day.pageviews)}</td></tr>)}</tbody></table></div>
            </details>
          </div>
          <div className="space-y-2">
            <h3 className="text-sm font-medium text-gray-200">{t('pagesLast30Days')}</h3>
            {data.pages.length ? data.pages.map(page => <div key={page.path} className="flex justify-between gap-3 text-xs text-gray-500 py-1.5 border-b border-white/5">
              <span>{t(labels[page.path])}</span><span>{number(page.pageviews)}</span></div>) : <p className="text-xs text-gray-500">{t('noVisitsYet')}</p>}
          </div>
        </div>
        <div className="space-y-1 text-xs text-gray-500">
          <p>{t('inheritedPageviews')}: {number(data.historical.pageviews)} · {t('newPageviews')}: {number(data.recorded.pageviews)}</p>
          <p>{language === 'zh' ? '历史浏览量于 2026 年 5 月手工记录；遗失时段的访问记录无法恢复。MapMyVisitors 重新计数与 V2 新增统计分别记录。' : 'Historical pageviews were recorded manually in May 2026; the missing period cannot be recovered. MapMyVisitors restarts and new V2 counts are tracked separately.'}</p>
          <p>{t('statisticsSince')} {data.historical.since || data.started_at.slice(0, 10)} · {t('newStatisticsSince')} {data.started_at.slice(0, 10)} · UTC</p>
        </div>
        <VisitorGlobe data={data} />
        {!data.geolocation.enabled && <p className="text-xs text-gray-500" role="status">{t('countryLookupUnavailable')}</p>}
      </>}
      <p className="text-xs text-gray-500">{t('statisticsPrivacy')}</p>
    </>
  </section>;
}
