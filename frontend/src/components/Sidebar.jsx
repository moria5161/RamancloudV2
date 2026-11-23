import { systemText } from '../locale.js';
import React from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { Home, Database, Atom, GitBranch, Layers, LineChart, BookOpen, Users, Github, Wrench, UserCircle, LogOut, FolderKanban, History, Sparkles, MessageSquare } from 'lucide-react';
import CloudLogo from './CloudLogo';
import { useAuth } from '../auth';
import { usePreferences } from '../i18n';

const navItems = [
  { to: '/', icon: Home, labelKey: 'homepage' },
  { to: '/ai-analysis', icon: Sparkles, labelKey: 'aiAnalysis' },
  { to: '/hyperspectral', icon: Layers, labelKey: 'hyperspectralProcessing' },
  { to: '/peak-fitting', icon: LineChart, labelKey: 'peakFitting' },
  { to: '/spectral-unmixing', icon: GitBranch, labelKey: 'spectralUnmixing' },
  { to: '/library-matching', icon: Database, labelKey: 'libraryMatching' },
  { to: '/structure-generation', icon: Atom, labelKey: 'structureGeneration' },
  { to: '/projects', icon: FolderKanban, labelKey: 'projectDataManagement' },
  { to: '/analysis-history', icon: History, labelKey: 'analysisHistory' },
  { to: '/extra-tools', icon: Wrench, labelKey: 'extraTools' },
  { to: '/account', icon: UserCircle, labelKey: 'personalSpace' },
  { to: '/tutorial', icon: BookOpen, labelKey: 'tutorial' },
  { to: '/feedback', icon: MessageSquare, labelKey: 'feedback' },
  { to: '/contributors', icon: Users, labelKey: 'contributors' },
];

export default function Sidebar() {
  const location = useLocation();
  const { user, logout } = useAuth();
  const { t } = usePreferences();

  return (
    <aside className="sidebar-glass w-60 glass flex flex-col justify-between border-r border-white/5 shrink-0 z-10">
      <div className="min-h-0 flex-1 flex flex-col">
        {/* Logo */}
        <div className="p-5 border-b border-white/5 shrink-0">
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
        <nav className="p-3 space-y-1 min-h-0 overflow-y-auto">
          {navItems.map(({ to, icon: Icon, labelKey }) => {
            const isActive = location.pathname === to;
            const label = t(labelKey === 'feedback' && user?.role === 'admin' ? 'feedbackManagement' : labelKey);
            return (
              <NavLink
                key={to}
                to={to}
                title={systemText(label)}
                aria-label={systemText(label)}
                className={`nav-liquid flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-200 ${
                  isActive
                    ? 'bg-indigo-500/10 text-indigo-400 border border-indigo-500/20'
                    : 'text-gray-400 hover:text-gray-200 hover:bg-white/5'
                }`}
              >
                <Icon className={`w-4 h-4 ${isActive ? 'text-indigo-400' : ''}`} />
                <span className="sidebar-nav-label">{systemText(label)}</span>
              </NavLink>
            );
          })}
        </nav>
      </div>

      {/* Footer */}
      <div className="p-4 border-t border-white/5 space-y-3 shrink-0">
        <div className="sidebar-account rounded-xl border border-white/5 p-3">
          <div className="flex items-center gap-2 min-w-0">
            <UserCircle className="w-4 h-4 shrink-0 text-indigo-400" />
            <div className="min-w-0">
              <div className="truncate text-xs font-medium text-gray-200">{user?.display_name || user?.username}</div>
              <div className="truncate text-[10px] text-gray-500">@{user?.username}</div>
            </div>
          </div>
          <button
            type="button"
            title={t('logout')}
            aria-label={t('logout')}
            onClick={logout}
            className="sidebar-account-action mt-3 flex w-full items-center justify-center gap-2 rounded-lg px-3 py-2 text-xs"
          >
            <LogOut className="w-3.5 h-3.5" />
            {t('logout')}
          </button>
          <NavLink to="/login" title={t('switchAccount')} aria-label={t('switchAccount')} className="sidebar-account-action mt-2 flex w-full items-center justify-center gap-2 rounded-lg px-3 py-2 text-xs">
            <UserCircle className="w-4 h-4 shrink-0" />
            <span className="sidebar-nav-label">{t('switchAccount')}</span>
          </NavLink>
        </div>
        <a
          href="https://github.com/hzh040518/Ramancloud"
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
