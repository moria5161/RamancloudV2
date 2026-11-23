import { systemText } from '../locale.js';
import React, { useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { LockKeyhole, LogIn, Mail, User, UserPlus } from 'lucide-react';
import CloudLogo from '../components/CloudLogo';
import { apiErrorMessage, useAuth } from '../auth';
import { usePreferences } from '../i18n';
import SettingsPanel from '../components/SettingsPanel';

const emptyForm = {
  username: '',
  email: '',
  displayName: '',
  identifier: '',
  password: '',
  role: 'user',
};

export default function AuthPage({ initialMode = 'login' }) {
  const { t } = usePreferences();
  const { login, register, isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const mode = initialMode;
  const [form, setForm] = useState(emptyForm);
  const [error, setError] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const from = location.state?.from;
  const returnTo = typeof from === 'string' && from.startsWith('/') && !from.startsWith('//') && !['/login', '/register'].includes(from.split('?')[0]) ? from : '/';

  useEffect(() => { setForm(emptyForm); setError(''); }, [initialMode]);

  const updateField = (key, value) => {
    setForm((current) => ({ ...current, [key]: value }));
    setError('');
  };

  const switchMode = (nextMode) => {
    navigate(nextMode === 'register' ? '/register' : '/login', { replace: true, state: location.state });
    setForm(emptyForm);
    setError('');
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setIsSubmitting(true);
    setError('');
    try {
      if (mode === 'login') {
        await login({ identifier: form.identifier, password: form.password });
      } else {
        await register({
          username: form.username,
          email: form.email || null,
          display_name: form.displayName || null,
          password: form.password,
          role: 'user',
        });
      }
      navigate(returnTo, { replace: true });
    } catch (submitError) {
      setError(apiErrorMessage(submitError, t('authFailed')));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="app-liquid-bg min-h-screen flex items-center justify-center px-6 py-10">
      <SettingsPanel />
      <div className="w-full max-w-md animate-fade-in">
        <div className="glass rounded-2xl border border-white/5 p-7 space-y-6">
          <div className="flex items-center gap-3">
            <div className="sidebar-logo w-11 h-11 rounded-xl flex items-center justify-center">
              <CloudLogo className="w-8 h-8" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-white tracking-tight">RamanCloud</h1>
              <p className="text-xs text-gray-500">{t('accountAccess')}</p>
            </div>
          </div>

          <div className="segmented-control">
            <button
              type="button"
              disabled={isSubmitting}
              onClick={() => switchMode('login')}
              className={mode === 'login' ? 'is-active' : ''}
            >
              <LogIn className="w-4 h-4" />
              {t('login')}
            </button>
            <button
              type="button"
              disabled={isSubmitting}
              onClick={() => switchMode('register')}
              className={mode === 'register' ? 'is-active' : ''}
            >
              <UserPlus className="w-4 h-4" />
              {t('register')}
            </button>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            {mode === 'login' ? (
              <label className="block space-y-1.5">
                <span className="text-xs text-gray-500">{t('usernameOrEmail')}</span>
                <div className="relative">
                  <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
                  <input
                    value={form.identifier}
                    onChange={(event) => updateField('identifier', event.target.value)}
                    className="w-full rounded-xl border border-white/10 py-2.5 pl-10 pr-3 text-sm"
                    autoComplete="username"
                    required
                  />
                </div>
              </label>
            ) : (
              <>
                <label className="block space-y-1.5">
                  <span className="text-xs text-gray-500">{t('username')}</span>
                  <div className="relative">
                    <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
                    <input
                      value={form.username}
                      onChange={(event) => updateField('username', event.target.value)}
                      className="w-full rounded-xl border border-white/10 py-2.5 pl-10 pr-3 text-sm"
                      autoComplete="username"
                      required
                    />
                  </div>
                </label>
                <label className="block space-y-1.5">
                  <span className="text-xs text-gray-500">{t('displayName')}</span>
                  <input
                    value={form.displayName}
                    onChange={(event) => updateField('displayName', event.target.value)}
                    className="w-full rounded-xl border border-white/10 px-3 py-2.5 text-sm"
                    autoComplete="name"
                  />
                </label>
                <label className="block space-y-1.5">
                  <span className="text-xs text-gray-500">{t('email')}</span>
                  <div className="relative">
                    <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
                    <input
                      type="email"
                      value={form.email}
                      onChange={(event) => updateField('email', event.target.value)}
                      className="w-full rounded-xl border border-white/10 py-2.5 pl-10 pr-3 text-sm"
                      autoComplete="email"
                    />
                  </div>
                </label>
              </>
            )}

            <label className="block space-y-1.5">
              <span className="text-xs text-gray-500">{t('password')}</span>
              <div className="relative">
                <LockKeyhole className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
                <input
                  type="password"
                  value={form.password}
                  onChange={(event) => updateField('password', event.target.value)}
                  className="w-full rounded-xl border border-white/10 py-2.5 pl-10 pr-3 text-sm"
                  autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                  minLength={mode === 'register' ? 6 : undefined}
                  required
                />
              </div>
            </label>

            {mode === 'register' && (
              <p className="text-xs text-gray-500 leading-relaxed">
                {t('accountTypeHint')}
              </p>
            )}

            {error && (
              <div role="alert" className="rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-500">
                {systemText(error)}
              </div>
            )}

            <button
              type="submit"
              disabled={isSubmitting}
              className="liquid-button w-full flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-indigo-600 to-purple-600 px-5 py-2.5 text-sm font-medium text-white disabled:opacity-50"
            >
              {isSubmitting ? t('running') : mode === 'login' ? t('login') : t('createAccount')}
              {mode === 'login' ? <LogIn className="w-4 h-4" /> : <UserPlus className="w-4 h-4" />}
            </button>
          </form>
          {isAuthenticated && <button type="button" onClick={() => navigate(returnTo, { replace: true })} className="flex w-full items-center justify-center gap-2 rounded-lg border border-white/10 px-3 py-2 text-sm text-gray-500">
            <LogIn className="w-4 h-4" />
            {t('continueCurrentAccount')}
          </button>}
        </div>
      </div>
    </div>
  );
}
