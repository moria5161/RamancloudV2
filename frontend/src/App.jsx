import React, { useEffect, useState } from 'react';
import { BrowserRouter as Router, Routes, Route, useLocation } from 'react-router-dom';
import Sidebar from './components/Sidebar';
import SettingsPanel from './components/SettingsPanel';
import { PreferencesProvider } from './i18n';
import HomePage from './pages/HomePage';
import SpectralProcessing from './pages/SpectralProcessing';
import HyperspectralProcessing from './pages/HyperspectralProcessing';
import ExtraTools from './pages/ExtraTools';
import Tutorial from './pages/Tutorial';
import Contributors from './pages/Contributors';

function WelcomeScreen() {
  const [showWelcome, setShowWelcome] = useState(true);
  const [finished, setFinished] = useState(false);

  useEffect(() => {
    const reveal = setTimeout(() => setShowWelcome(false), 1950);
    const finish = setTimeout(() => setFinished(true), 2500);
    return () => { clearTimeout(reveal); clearTimeout(finish); };
  }, []);

  if (finished) return null;
  return <div className={`welcome-screen ${showWelcome ? 'is-visible' : 'is-hidden'}`}>
    <div className="welcome-title" aria-label="Welcome to Ramancloud">
      <span className="welcome-word" aria-hidden="true">Welcome</span>{' '}
      <span className="welcome-word" aria-hidden="true">to</span>{' '}
      <span className="welcome-word" aria-hidden="true">Ramancloud</span>
    </div>
  </div>;
}

function AppShell() {
  const location = useLocation();
  const [visitedWorkspaces, setVisitedWorkspaces] = useState([]);

  useEffect(() => {
    const path = location.pathname;
    if (path === '/spectral' || path === '/hyperspectral') {
      setVisitedWorkspaces(previous => previous.includes(path) ? previous : [...previous, path]);
    }
    const frame = requestAnimationFrame(() => window.dispatchEvent(new Event('resize')));
    return () => cancelAnimationFrame(frame);
  }, [location.pathname]);

  return (
    <div className="app-liquid-bg flex h-screen overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-hidden">
        {[
          ['/spectral', SpectralProcessing],
          ['/hyperspectral', HyperspectralProcessing],
        ].map(([path, Workspace]) => (
          (visitedWorkspaces.includes(path) || location.pathname === path) && (
            <div key={path} hidden={location.pathname !== path} className="workspace-route h-full overflow-hidden">
              <Workspace />
            </div>
          )
        ))}
        <div key={location.pathname} hidden={location.pathname === '/spectral' || location.pathname === '/hyperspectral'} className="route-surface h-full overflow-hidden">
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/spectral" element={null} />
            <Route path="/hyperspectral" element={null} />
            <Route path="/extra-tools" element={<ExtraTools />} />
            <Route path="/tutorial" element={<Tutorial />} />
            <Route path="/contributors" element={<Contributors />} />
          </Routes>
        </div>
      </main>
      <SettingsPanel />
    </div>
  );
}

function App() {
  return (
    <Router basename="/preprocessing">
      <PreferencesProvider>
        <WelcomeScreen />
        <AppShell />
      </PreferencesProvider>
    </Router>
  );
}

export default App;
