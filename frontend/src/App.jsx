import React, { useEffect, useState } from 'react';
import { BrowserRouter, HashRouter, Navigate, Routes, Route, useLocation } from 'react-router-dom';
import Sidebar from './components/Sidebar';
import GlobalQAAssistant from './components/GlobalQAAssistant';
import SettingsPanel from './components/SettingsPanel';
import { AuthProvider, useAuth } from './auth';
import { PreferencesProvider, usePreferences } from './i18n';
import HomePage from './pages/HomePage';
import HyperspectralProcessing from './pages/HyperspectralProcessing';
import PeakFittingPage from './pages/PeakFittingPage';
import ExtraTools from './pages/ExtraTools';
import Tutorial from './pages/Tutorial';
import Contributors from './pages/Contributors';
import AuthPage from './pages/AuthPage';
import AccountPage from './pages/AccountPage';
import ProjectDataPage from './pages/ProjectDataPage';
import AnalysisHistoryPage from './pages/AnalysisHistoryPage';
import AIAnalysisPage from './pages/AIAnalysisPage';
import LibraryMatchingPage from './pages/LibraryMatchingPage';
import StructureGenerationPage from './pages/StructureGenerationPage';
import MixtureAnalysisPage from './pages/MixtureAnalysisPage';
import FeedbackPage from './pages/FeedbackPage';
import AnalysisWorkspaces from './components/AnalysisWorkspaces';
import SSnetCompletionNotice from './components/SSnetCompletionNotice';

const ANALYSIS_PAGES = {'/ai-analysis':AIAnalysisPage,'/hyperspectral':HyperspectralProcessing,'/peak-fitting':PeakFittingPage,
  '/spectral-unmixing':MixtureAnalysisPage,'/library-matching':LibraryMatchingPage,'/structure-generation':StructureGenerationPage};

function AppShell() {
  const { t, language } = usePreferences();
  const location = useLocation();
  const { isAuthenticated, isLoading, user } = useAuth();
  const [showWelcome, setShowWelcome] = useState(true);

  useEffect(() => {
    const timer = setTimeout(() => setShowWelcome(false), 1550);
    return () => clearTimeout(timer);
  }, []);

  if (isLoading) {
    return (
      <div className="app-liquid-bg h-screen flex items-center justify-center">
        <div className="glass rounded-xl border border-white/5 px-5 py-4 text-sm text-gray-500">
          {t('loading')}
        </div>
      </div>
    );
  }

  if (location.pathname === '/login' || location.pathname === '/register') {
    return <AuthPage initialMode={location.pathname === '/register' ? 'register' : 'login'} />;
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  }

  return (
    <div className="app-liquid-bg flex h-screen overflow-hidden">
      <div className={`welcome-screen ${showWelcome ? 'is-visible' : 'is-hidden'}`}>
        <div className="welcome-title">{language === 'zh' ? '欢迎使用 RamanCloud' : 'Welcome to RamanCloud'}</div>
      </div>
      <Sidebar />
      <main data-qa-workspace className="flex flex-1 min-w-0 flex-col overflow-hidden">
        <SSnetCompletionNotice key={user.id} />
        <div className="route-surface min-h-0 flex-1 overflow-hidden">
          <AnalysisWorkspaces key={user.id} pages={ANALYSIS_PAGES}>
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/spectral" element={<Navigate to="/ai-analysis" replace />} />
            <Route path="/projects" element={<ProjectDataPage />} />
            <Route path="/analysis-history" element={<AnalysisHistoryPage />} />
            <Route path="/extra-tools" element={<ExtraTools />} />
            <Route path="/tutorial" element={<Tutorial />} />
            <Route path="/feedback" element={<FeedbackPage />} />
            <Route path="/contributors" element={<Contributors />} />
            <Route path="/account" element={<AccountPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
          </AnalysisWorkspaces>
        </div>
      </main>
      <GlobalQAAssistant key={user.id} enabled={Object.hasOwn(ANALYSIS_PAGES, location.pathname)} />
      <SettingsPanel />
    </div>
  );
}

function App() {
  const Router = import.meta.env.BASE_URL === '/' ? HashRouter : BrowserRouter;
  return (
    <Router basename={import.meta.env.BASE_URL.replace(/\/$/, '') || '/'}>
      <AuthProvider>
        <PreferencesProvider>
          <AppShell />
        </PreferencesProvider>
      </AuthProvider>
    </Router>
  );
}

export default App;
