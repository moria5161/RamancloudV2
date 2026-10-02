import React, { useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { usePreferences } from '../i18n';
import VisitorGlobe from './VisitorGlobe';

export default function VisitStatistics() {
  const { language, t } = usePreferences();
  const isZh = language === 'zh';
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
  const knownRegions = data?.countries.filter(item => item.code !== 'ZZ' && item.count > 0).length || 0;

  return (
    <section className="glass rounded-xl border border-white/5 p-4 sm:p-5" aria-labelledby="visit-statistics-heading">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h3 id="visit-statistics-heading" className="text-sm font-semibold text-gray-200">{t('visitStatistics')}</h3>
          <p className="mt-0.5 text-xs text-gray-500">{isZh ? '按国家或地区汇总的匿名访问' : 'Anonymous visits aggregated by country or region'}</p>
        </div>
        <button type="button" title={t('refreshStatistics')} aria-label={t('refreshStatistics')} disabled={busy}
          onClick={() => setRevision(value => value + 1)} className="flex h-8 w-8 items-center justify-center rounded-md text-gray-500 hover:bg-white/10 disabled:opacity-40">
          <RefreshCw className={`h-4 w-4 ${busy ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {failed && <p role="status" className="py-8 text-center text-sm text-gray-500">{t('statisticsUnavailable')}</p>}
      {!data && busy && <p role="status" className="py-8 text-center text-sm text-gray-500">{t('loadingStatistics')}</p>}
      {data && (
        <>
          <dl className="mt-5 grid grid-cols-2 gap-3 border-y border-white/10 py-4">
            {[
              [t('totalPageviews'), data.total.pageviews],
              [isZh ? '国家 / 地区' : 'Countries / Regions', knownRegions],
            ].map(([label, value]) => (
              <div key={label} className="min-w-0">
                <dd className="text-lg font-semibold text-gray-200 sm:text-xl">{number(value)}</dd>
                <dt className="mt-1 text-[10px] leading-tight text-gray-500">{label}</dt>
              </div>
            ))}
          </dl>
          <VisitorGlobe data={data} compact />
          <p className="mt-3 text-[10px] leading-relaxed text-gray-500">
            {isZh
              ? '历史与新增访问已合并，仅展示国家或地区级聚合数据，不保存原始 IP 或精确位置。'
              : 'Historical and new visits are combined. Only country-level aggregates are shown; no raw IP or precise location is stored.'}
          </p>
        </>
      )}
    </section>
  );
}
