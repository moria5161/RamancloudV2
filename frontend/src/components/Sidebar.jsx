import React, { useEffect, useRef, useState } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { Home, Activity, Layers, Atom, BookOpen, Users, Github, Wrench, ShieldCheck, PanelLeftClose, PanelLeftOpen } from 'lucide-react';
import CloudLogo from './CloudLogo';
import { usePreferences } from '../i18n';

const navItems = [
  { to: '/', icon: Home, labelKey: 'homepage' },
  { to: '/spectral', icon: Activity, labelKey: 'spectralProcessing' },
  { to: '/hyperspectral', icon: Layers, labelKey: 'hyperspectralProcessing' },
  { to: '/spectrum-structure', icon: Atom, labelKey: 'spectrumStructure' },
  { to: '/extra-tools', icon: Wrench, labelKey: 'extraTools' },
  { to: '/tutorial', icon: BookOpen, labelKey: 'tutorial' },
  { to: '/contributors', icon: Users, labelKey: 'contributors' },
  { to: '/privacy-policy', icon: ShieldCheck, labelKey: 'privacyPolicy' },
];

export default function Sidebar({ layout }) {
  const location = useLocation();
  const { t } = usePreferences();
  const drag = useRef(null);
  const [resizing, setResizing] = useState(false);
  const { width, collapsed, narrow, overlay, minWidth, maxWidth, toggle, resize, resetWidth, closeMobile } = layout;

  useEffect(() => {
    if (!overlay) return;
    const escape = event => { if (event.key === 'Escape') closeMobile(); };
    document.addEventListener('keydown', escape);
    return () => document.removeEventListener('keydown', escape);
  }, [overlay, closeMobile]);

  const stopResize = event => {
    drag.current = null;
    setResizing(false);
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
  };

  return (
    <aside className={`sidebar-glass glass flex flex-col border-r border-white/5 shrink-0 z-10 ${collapsed ? 'is-collapsed' : ''} ${resizing ? 'is-resizing' : ''}`}>
      <div className="sidebar-scroll flex-1 min-h-0 overflow-y-auto">
        {/* Logo */}
        <div className="sidebar-brand p-4 border-b border-white/5">
          <div className="sidebar-brand-row flex items-center gap-2">
            <div className="sidebar-logo w-9 h-9 shrink-0 rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center">
              <CloudLogo className="w-9 h-9" />
            </div>
            <div className="sidebar-label min-w-0 flex-1">
              <h1 className="text-lg font-bold text-white truncate" title="RamanCloud">RamanCloud</h1>
              <p className="text-[10px] text-gray-500 -mt-0.5 truncate">{t('nextGen')}</p>
            </div>
            <button type="button" className="sidebar-toggle shrink-0" onClick={toggle} title={t(collapsed ? 'openNavigation' : 'closeNavigation')} aria-label={t(collapsed ? 'openNavigation' : 'closeNavigation')} aria-expanded={!collapsed} aria-controls="main-navigation">
              {collapsed ? <PanelLeftOpen className="w-4 h-4" /> : <PanelLeftClose className="w-4 h-4" />}
            </button>
          </div>
        </div>

        {/* Navigation */}
        <nav id="main-navigation" aria-label={t('navigation')} className="p-3 space-y-1">
          {navItems.map(({ to, icon: Icon, labelKey }) => {
            const isActive = location.pathname === to;
            return (
              <NavLink
                key={to}
                to={to}
                title={t(labelKey)}
                aria-label={t(labelKey)}
                onClick={closeMobile}
                className={`nav-liquid flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium border ${
                  isActive
                    ? 'bg-indigo-500/10 text-indigo-400 border-indigo-500/20'
                    : 'border-transparent text-gray-400 hover:text-gray-200 hover:bg-white/5'
                }`}
              >
                <Icon className={`w-4 h-4 shrink-0 ${isActive ? 'text-indigo-400' : ''}`} />
                <span className="sidebar-label min-w-0 break-words">{t(labelKey)}</span>
              </NavLink>
            );
          })}
        </nav>
      </div>

      {/* Footer */}
      <div className="sidebar-footer shrink-0 border-t border-white/5">
        <a
          href="https://github.com/moria5161/RamancloudV2"
          target="_blank"
          rel="noopener noreferrer"
          title="GitHub" aria-label="GitHub"
          className="flex items-center gap-2 text-xs text-gray-500 hover:text-gray-300 transition-colors"
        >
          <Github className="w-3.5 h-3.5 shrink-0" />
          <span className="sidebar-label">GitHub</span>
        </a>
        <p className="sidebar-label text-[10px] text-gray-600 mt-2">
          Ren Research Group, XMU
        </p>
      </div>
      {!collapsed && !narrow && <div
        className="sidebar-resize-handle"
        role="separator" tabIndex={0} aria-orientation="vertical" aria-label={t('resizeNavigation')}
        aria-controls="main-navigation" aria-valuemin={minWidth} aria-valuemax={maxWidth} aria-valuenow={width}
        title={t('resizeNavigation')}
        onDoubleClick={resetWidth}
        onPointerDown={event => {
          if (event.button !== 0) return;
          event.preventDefault();
          event.currentTarget.focus();
          event.currentTarget.setPointerCapture(event.pointerId);
          drag.current = { startX: event.clientX, width };
          setResizing(true);
        }}
        onPointerMove={event => {
          if (drag.current) resize(drag.current.width + event.clientX - drag.current.startX);
        }}
        onPointerUp={stopResize}
        onPointerCancel={stopResize}
        onLostPointerCapture={() => { drag.current = null; setResizing(false); }}
        onKeyDown={event => {
          if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
          event.preventDefault();
          resize(event.key === 'Home' ? minWidth : event.key === 'End' ? maxWidth : width + (event.key === 'ArrowRight' ? 16 : -16));
        }}
      />}
    </aside>
  );
}
