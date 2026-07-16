import React from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { Home, Activity, Layers, BookOpen, Users, Github, Wrench } from 'lucide-react';
import CloudLogo from './CloudLogo';
import { usePreferences } from '../i18n';

const navItems = [
  { to: '/', icon: Home, labelKey: 'homepage' },
  { to: '/spectral', icon: Activity, labelKey: 'spectralProcessing' },
  { to: '/hyperspectral', icon: Layers, labelKey: 'hyperspectralProcessing' },
  { to: '/extra-tools', icon: Wrench, labelKey: 'extraTools' },
  { to: '/tutorial', icon: BookOpen, labelKey: 'tutorial' },
  { to: '/contributors', icon: Users, labelKey: 'contributors' },
];

export default function Sidebar() {
  const location = useLocation();
  const { t } = usePreferences();

  return (
    <aside className="sidebar-glass w-60 glass flex flex-col justify-between border-r border-white/5 shrink-0 z-10">
      <div>
        {/* Logo */}
        <div className="p-5 border-b border-white/5">
          <div className="flex items-center gap-3">
            <div className="sidebar-logo w-9 h-9 rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center">
              <CloudLogo className="w-7 h-7" />
            </div>
            <div>
              <h1 className="text-lg font-bold text-white tracking-tight">RamanCloud</h1>
              <p className="text-[10px] text-gray-500 -mt-0.5">{t('nextGen')}</p>
            </div>
          </div>
        </div>

        {/* Navigation */}
        <nav className="p-3 space-y-1">
          {navItems.map(({ to, icon: Icon, labelKey }) => {
            const isActive = location.pathname === to;
            return (
              <NavLink
                key={to}
                to={to}
                className={`nav-liquid flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-200 ${
                  isActive
                    ? 'bg-indigo-500/10 text-indigo-400 border border-indigo-500/20'
                    : 'text-gray-400 hover:text-gray-200 hover:bg-white/5'
                }`}
              >
                <Icon className={`w-4 h-4 ${isActive ? 'text-indigo-400' : ''}`} />
                {t(labelKey)}
              </NavLink>
            );
          })}
        </nav>
      </div>

      {/* Footer */}
      <div className="p-4 border-t border-white/5">
        <a
          href="https://github.com/moria5161/RamancloudV2"
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-2 text-xs text-gray-500 hover:text-gray-300 transition-colors"
        >
          <Github className="w-3.5 h-3.5" />
          <span>GitHub</span>
        </a>
        <p className="text-[10px] text-gray-600 mt-2">
          Ren Research Group, XMU
        </p>
      </div>
    </aside>
  );
}
