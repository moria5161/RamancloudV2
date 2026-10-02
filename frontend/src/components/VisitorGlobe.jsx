import React, { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Pause, Play, RotateCcw, ZoomIn, ZoomOut } from 'lucide-react';
import { usePreferences } from '../i18n';

const Scene = lazy(() => import('./VisitorGlobeScene'));

export default function VisitorGlobe({ data, compact = false }) {
  const { language, theme } = usePreferences();
  const zh = language === 'zh';
  const [mode, setMode] = useState(() => data.countries.some(item => item.code !== 'ZZ' && item.recorded > 0) ? 'recorded' : 'historical');
  const [playing, setPlaying] = useState(() => !window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  const [selected, setSelected] = useState(null);
  const [hovered, setHovered] = useState(null);
  const [world, setWorld] = useState(null);
  const [nearby, setNearby] = useState(false);
  const [failed, setFailed] = useState(false);
  const container = useRef(null);
  const api = useRef(null);
  const historical = mode === 'historical';
  const regions = useMemo(() => new Intl.DisplayNames([language], { type: 'region' }), [language]);
  const number = value => new Intl.NumberFormat(language).format(value);
  const points = useMemo(() => data.countries.map(item => ({ code: item.code, count: item[mode] || 0 })).filter(item => item.count > 0).sort((a, b) => b.count - a.count || a.code.localeCompare(b.code)), [data.countries, mode]);
  const known = points.filter(point => point.code !== 'ZZ');
  const unknown = points.find(point => point.code === 'ZZ')?.count || 0;
  const active = hovered || points.find(point => point.code === selected);
  const onFailure = useCallback(() => setFailed(true), []);
  const select = useCallback(code => { setSelected(code); setPlaying(false); api.current?.focus(code); }, []);
  useEffect(() => {
    const observer = new IntersectionObserver(([entry]) => { if (entry.isIntersecting) { setNearby(true); observer.disconnect(); } }, { rootMargin: '250px' });
    observer.observe(container.current);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    if (!nearby) return;
    const controller = new AbortController();
    fetch(`${import.meta.env.BASE_URL}data/world-countries.json`, { signal: controller.signal })
      .then(response => { if (!response.ok) throw new Error('Map unavailable'); return response.json(); })
      .then(setWorld).catch(error => { if (error.name !== 'AbortError') setFailed(true); });
    return () => controller.abort();
  }, [nearby]);
  const iconButton = (name, Icon, action, pressed) => <button type="button" title={name} aria-label={name} aria-pressed={pressed} onClick={action} disabled={failed || !world} className="visitor-globe-tool"><Icon size={17} /></button>;
  return <section ref={container} className={`visitor-globe-section ${compact ? 'is-compact' : ''}`} aria-labelledby="visitor-globe-heading">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <h3 id="visitor-globe-heading" className="text-base font-semibold text-gray-200">{compact ? (zh ? '访问分布' : 'Visit distribution') : (zh ? '全球访问分布' : 'Visitors Around the World')}</h3>
      <div className="segmented-control" role="group" aria-label={zh ? '访问数据来源' : 'Visit data source'}>
        {[['recorded', compact ? (zh ? 'V2 新增' : 'New V2') : (zh ? 'V2 新增' : 'New V2 visits')], ['historical', compact ? (zh ? '2026.05 历史' : 'May 2026') : (zh ? '历史快照 · 2026.05' : 'Archive · May 2026')]].map(([value, label]) => <button type="button" key={value} aria-pressed={mode === value} className={mode === value ? 'is-active' : ''}
          onClick={() => { setMode(value); setSelected(null); setHovered(null); }}>{label}</button>)}
      </div>
    </div>
    <div className="visitor-globe-layout">
      <div className="visitor-globe-stage">
        {failed ? <div role="status" className="visitor-globe-placeholder">{zh ? '此设备暂时无法显示 3D 地球，地区统计仍可查看。' : 'The 3D globe is unavailable on this device. Region counts remain available.'}</div>
          : nearby && world ? <Suspense fallback={<div className="visitor-globe-placeholder">{zh ? '加载地球…' : 'Loading globe…'}</div>}>
            <Scene world={world} points={points} theme={theme} playing={playing} historical={historical} apiRef={api} onSelect={select} onHover={setHovered} onFailure={onFailure} label={zh ? '国家和地区访问分布 3D 地球' : '3D globe of visits by country and region'} />
          </Suspense> : <div className="visitor-globe-placeholder">{zh ? '加载地球…' : 'Loading globe…'}</div>}
        <div className="visitor-globe-tools">
          {iconButton(playing ? (zh ? '暂停旋转' : 'Pause rotation') : (zh ? '开始旋转' : 'Start rotation'), playing ? Pause : Play, () => setPlaying(value => !value), playing)}
          {iconButton(zh ? '放大地球' : 'Zoom in globe', ZoomIn, () => api.current?.zoom(.85))}
          {iconButton(zh ? '缩小地球' : 'Zoom out globe', ZoomOut, () => api.current?.zoom(1.18))}
          {iconButton(zh ? '重置地球视角' : 'Reset globe view', RotateCcw, () => { setSelected(null); api.current?.reset(); })}
        </div>
        <div className="visitor-globe-selection" aria-live="polite">
          {active && active.code !== 'ZZ' ? `${regions.of(active.code)} · ${number(active.count)} ${zh ? '次' : 'visits'}` : (historical ? (zh ? '2026 年 5 月 · 手工历史快照' : 'May 2026 · Manual historical snapshot') : `${zh ? '新增统计始于' : 'New records since'} ${data.started_at.slice(0, 10)}`)}
        </div>
      </div>
      <div className="visitor-globe-regions">
        <div className="flex items-baseline justify-between gap-3 border-b border-white/10 pb-3">
          <span className="text-sm font-medium text-gray-200">{zh ? '国家 / 地区' : 'Countries / Regions'}</span><span className="text-sm text-gray-500">{known.length}</span>
        </div>
        <div className="visitor-globe-region-list">
          {known.map(point => <button type="button" key={point.code} className="visitor-globe-region" aria-pressed={selected === point.code} onClick={() => select(point.code)}>
            <span className="visitor-globe-region-label"><span>{regions.of(point.code)}</span><span>{number(point.count)}</span></span>
            <span className="visitor-globe-region-track"><span style={{ width: `${point.count / Math.max(1, ...known.map(item => item.count)) * 100}%`, background: historical ? '#ce8a3f' : '#238ac4' }} /></span>
          </button>)}
          {!known.length && <p className="text-sm text-gray-500 py-4">{zh ? '暂时没有可定位的新增访问。' : 'No new visits with a known region yet.'}</p>}
        </div>
        {!!unknown && <p className="text-xs text-gray-500 pt-3">{zh ? '未知地区' : 'Unknown region'} · {number(unknown)}</p>}
      </div>
    </div>
    {!compact && <>
      <p className="text-xs text-gray-500 leading-relaxed">{zh ? '位置按 IP 所属国家 / 地区归类，标记位于地区代表位置，不代表访客精确坐标。历史地区计数来自截图，统计口径与 7,470 次累计浏览量可能不同。' : 'Visits are grouped by IP country or region. Markers use representative region locations, not precise visitor coordinates. Archived region counts come from screenshots and may use a different metric from the 7,470 historical pageviews.'}</p>
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-500">
        <a href="https://db-ip.com" target="_blank" rel="noopener noreferrer">{zh ? 'IP 地理定位：DB-IP' : 'IP geolocation: DB-IP'}</a>
        <a href="https://www.naturalearthdata.com/about/terms-of-use/" target="_blank" rel="noopener noreferrer">{zh ? '地图数据：Natural Earth' : 'Map data: Natural Earth'}</a>
      </div>
    </>}
  </section>;
}
