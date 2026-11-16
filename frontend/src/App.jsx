import React, { lazy, Suspense, useEffect, useState } from 'react';
import { BrowserRouter as Router, Routes, Route, useLocation } from 'react-router-dom';
import Sidebar from './components/Sidebar';
import SettingsPanel from './components/SettingsPanel';
import { PreferencesProvider, usePreferences } from './i18n';
import HomePage from './pages/HomePage';
import ExtraTools from './pages/ExtraTools';
import Tutorial from './pages/Tutorial';
import Contributors from './pages/Contributors';
import PrivacyPolicy from './pages/PrivacyPolicy';
import useVisitTracking from './hooks/useVisitTracking';
import useSidebarLayout from './hooks/useSidebarLayout';

const SpectralProcessing = lazy(() => import('./pages/SpectralProcessing'));
const HyperspectralProcessing = lazy(() => import('./pages/HyperspectralProcessing'));
const SpectrumStructure = lazy(() => import('./pages/SpectrumStructure'));
const workspacePaths = ['/spectral', '/hyperspectral', '/spectrum-structure'];

function WelcomeScreen() {
  const { language } = usePreferences();
  const [showWelcome, setShowWelcome] = useState(true);
  const [finished, setFinished] = useState(false);

  useEffect(() => {
    if (finished) return;
    const reveal = setTimeout(() => setShowWelcome(false), 1950);
    const finish = setTimeout(() => setFinished(true), 2500);
    return () => { clearTimeout(reveal); clearTimeout(finish); };
  }, [finished]);

  if (finished) return null;
  return <div className={`welcome-screen ${showWelcome ? 'is-visible' : 'is-hidden'}`}
    role="button" tabIndex={showWelcome ? 0 : -1}
    aria-label={language === 'zh' ? '跳过欢迎动画' : 'Skip welcome animation'}
    onClick={() => setFinished(true)}
    onKeyDown={event => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        setFinished(true);
      }
    }}>
    <div className="welcome-title" aria-label="Welcome to Ramancloud">
      <span className="welcome-word" aria-hidden="true">Welcome</span>{' '}
      <span className="welcome-word" aria-hidden="true">to</span>{' '}
      <span className="welcome-word" aria-hidden="true">Ramancloud</span>
    </div>
  </div>;
}

function AppShell() {
  const { t } = usePreferences();
  const location = useLocation();
  useVisitTracking(location.pathname);
  const [visitedWorkspaces, setVisitedWorkspaces] = useState([]);
  const sidebar = useSidebarLayout();

  useEffect(() => {
    const path = location.pathname;
    if (workspacePaths.includes(path)) {
      setVisitedWorkspaces(previous => previous.includes(path) ? previous : [...previous, path]);
    }
    const frame = requestAnimationFrame(() => window.dispatchEvent(new Event('resize')));
    return () => cancelAnimationFrame(frame);
  }, [location.pathname]);

  return (
    <div className="app-liquid-bg flex h-screen overflow-hidden" style={{ '--sidebar-width': `${sidebar.width}px` }} data-sidebar-collapsed={sidebar.collapsed} data-sidebar-overlay={sidebar.overlay}>
      {sidebar.overlay && <button className="sidebar-backdrop" onClick={sidebar.closeMobile} aria-label={t('closeNavigation')} />}
      <Sidebar layout={sidebar} />
      <main className="flex-1 min-w-0 overflow-hidden">
        <Suspense fallback={<div className="h-full grid place-items-center text-sm text-gray-500" role="status">{t('loadingWorkspace')}</div>}>
        {[
          ['/spectral', SpectralProcessing],
          ['/hyperspectral', HyperspectralProcessing],
          ['/spectrum-structure', SpectrumStructure],
        ].map(([path, Workspace]) => (
          (visitedWorkspaces.includes(path) || location.pathname === path) && (
            <div key={path} hidden={location.pathname !== path} className="workspace-route h-full overflow-hidden">
              <Workspace />
            </div>
          )
        ))}
        <div key={location.pathname} hidden={workspacePaths.includes(location.pathname)} className="route-surface h-full overflow-hidden">
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/spectral" element={null} />
            <Route path="/hyperspectral" element={null} />
            <Route path="/spectrum-structure" element={null} />
            <Route path="/extra-tools" element={<ExtraTools />} />
            <Route path="/tutorial" element={<Tutorial />} />
            <Route path="/contributors" element={<Contributors />} />
            <Route path="/privacy-policy" element={<PrivacyPolicy />} />
          </Routes>
        </div>
        </Suspense>
      </main>
      <SettingsPanel />
    </div>
  );
}

function App() {
  return (
    <Router basename={import.meta.env.BASE_URL}>
      <PreferencesProvider>
        <WelcomeScreen />
        <AppShell />
      </PreferencesProvider>
    </Router>
  );
}

export default App;
