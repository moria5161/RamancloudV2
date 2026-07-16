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

function AppShell() {
  const location = useLocation();
  const [showWelcome, setShowWelcome] = useState(true);

  useEffect(() => {
    const timer = setTimeout(() => setShowWelcome(false), 1550);
    return () => clearTimeout(timer);
  }, []);

  return (
    <div className="app-liquid-bg flex h-screen overflow-hidden">
      <div className={`welcome-screen ${showWelcome ? 'is-visible' : 'is-hidden'}`}>
        <div className="welcome-title">Welcome to Ramancloud</div>
      </div>
      <Sidebar />
      <main className="flex-1 overflow-hidden">
        <div key={location.pathname} className="route-surface h-full overflow-hidden">
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/spectral" element={<SpectralProcessing />} />
            <Route path="/hyperspectral" element={<HyperspectralProcessing />} />
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
        <AppShell />
      </PreferencesProvider>
    </Router>
  );
}

export default App;
