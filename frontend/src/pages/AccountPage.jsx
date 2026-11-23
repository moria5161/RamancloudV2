import { systemText } from '../locale.js';
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Database, FolderKanban, History, KeyRound, Shield, UserCircle, UsersRound } from 'lucide-react';
import { apiErrorMessage, useAuth } from '../auth';
import { usePreferences } from '../i18n';

const sectionIcons = {
  projects: FolderKanban,
  datasets: Database,
  analyses: History,
};

export default function AccountPage() {
  const { t, language } = usePreferences();
  const { user, loadSpace, changePassword, listUsers, updateUser } = useAuth();
  const [space, setSpace] = useState(null);
  const [users, setUsers] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSavingPassword, setIsSavingPassword] = useState(false);
  const [isSavingUser, setIsSavingUser] = useState('');
  const [passwordForm, setPasswordForm] = useState({ oldPassword: '', newPassword: '', confirmPassword: '' });
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  const roleLabels = useMemo(() => ({
    user: t('roleUser'),
    admin: t('roleAdmin'),
    member: t('roleMember'),
  }), [t]);

  const formatDate = useCallback((value) => {
    if (!value) return t('never');
    return new Date(value).toLocaleString(language === 'zh' ? 'zh-CN' : 'en-US');
  }, [language, t]);

  const refresh = useCallback(async () => {
    setIsLoading(true);
    setError('');
    try {
      const nextSpace = await loadSpace();
      setSpace(nextSpace);
      if (user?.role === 'admin') {
        setUsers(await listUsers());
      }
    } catch (loadError) {
      setError(apiErrorMessage(loadError, t('loadFailed')));
    } finally {
      setIsLoading(false);
    }
  }, [listUsers, loadSpace, t, user?.role]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const savePassword = async (event) => {
    event.preventDefault();
    setMessage('');
    setError('');
    if (passwordForm.newPassword !== passwordForm.confirmPassword) {
      setError(t('passwordMismatch'));
      return;
    }
    setIsSavingPassword(true);
    try {
      await changePassword(passwordForm);
    } catch (passwordError) {
      setError(apiErrorMessage(passwordError, t('passwordUpdateFailed')));
    } finally {
      setIsSavingPassword(false);
    }
  };

  const saveUserField = async (targetUser, payload) => {
    setIsSavingUser(targetUser.id);
    setMessage('');
    setError('');
    try {
      await updateUser(targetUser.id, payload);
      setUsers(await listUsers());
      setMessage(t('userUpdated'));
    } catch (userError) {
      setError(apiErrorMessage(userError, t('userUpdateFailed')));
    } finally {
      setIsSavingUser('');
    }
  };

  const currentUser = space?.user || user;

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-6xl mx-auto px-8 py-10 space-y-8 animate-fade-in">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="space-y-3">
            <div className="flex items-center gap-3">
              <UserCircle className="w-7 h-7 text-indigo-400" />
              <h1 className="text-2xl font-bold text-white">{t('personalSpace')}</h1>
            </div>
            <p className="text-sm text-gray-400 max-w-2xl">
              {t('personalSpaceSubtitle')}
            </p>
          </div>
          <div className="glass rounded-xl border border-white/5 px-4 py-3 min-w-64">
            <div className="text-xs text-gray-500">{t('currentAccount')}</div>
            <div className="mt-1 flex items-center justify-between gap-4">
              <div>
                <div className="text-sm font-semibold text-gray-200">{currentUser?.display_name}</div>
                <div className="text-xs text-gray-500">@{currentUser?.username}</div>
              </div>
              <span className="rounded-full border border-indigo-500/20 bg-indigo-500/10 px-3 py-1 text-xs text-indigo-400">
                {roleLabels[currentUser?.role] || currentUser?.role}
              </span>
            </div>
          </div>
        </div>

        {(message || error) && (
          <div className={`rounded-xl border px-4 py-3 text-sm ${
            error ? 'border-red-500/20 bg-red-500/10 text-red-500' : 'border-indigo-500/20 bg-indigo-500/10 text-gray-400'
          }`}>
            {systemText(error || message)}
          </div>
        )}

        {isLoading ? (
          <div className="glass rounded-xl border border-white/5 p-8 text-sm text-gray-500">
            {t('loading')}
          </div>
        ) : (
          <>
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              {(space?.sections || []).map((section) => {
                const Icon = sectionIcons[section.key] || Database;
                return (
                  <div key={section.key} className="glass liquid-card rounded-xl border border-white/5 p-5">
                    <div className="flex items-center justify-between gap-3">
                      <div className="liquid-icon w-11 h-11 rounded-xl flex items-center justify-center">
                        <Icon className="w-5 h-5 text-indigo-400" />
                      </div>
                      <div className="text-3xl font-semibold text-white">{section.count}</div>
                    </div>
                    <div className="mt-4">
                      <h2 className="text-sm font-semibold text-gray-200">{t(section.key)}</h2>
                      <p className="mt-1 text-xs leading-relaxed text-gray-500">{t(`${section.key}Next`)}</p>
                    </div>
                  </div>
                );
              })}
            </div>

            <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_minmax(320px,420px)] gap-5">
              <div className="glass rounded-xl border border-white/5 p-6 space-y-5">
                <div className="flex items-center gap-3">
                  <Shield className="w-5 h-5 text-indigo-400" />
                  <div>
                    <h2 className="text-lg font-semibold text-gray-200">{t('accountInfo')}</h2>
                    <p className="text-xs text-gray-500">{t('accountInfoSubtitle')}</p>
                  </div>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
                  <div className="rounded-xl border border-white/5 bg-white/5 p-4">
                    <div className="text-xs text-gray-500">{t('username')}</div>
                    <div className="mt-1 font-medium text-gray-200">{currentUser?.username}</div>
                  </div>
                  <div className="rounded-xl border border-white/5 bg-white/5 p-4">
                    <div className="text-xs text-gray-500">{t('email')}</div>
                    <div className="mt-1 font-medium text-gray-200">{currentUser?.email || t('notSet')}</div>
                  </div>
                  <div className="rounded-xl border border-white/5 bg-white/5 p-4">
                    <div className="text-xs text-gray-500">{t('createdAt')}</div>
                    <div className="mt-1 font-medium text-gray-200">{formatDate(currentUser?.created_at)}</div>
                  </div>
                  <div className="rounded-xl border border-white/5 bg-white/5 p-4">
                    <div className="text-xs text-gray-500">{t('lastLogin')}</div>
                    <div className="mt-1 font-medium text-gray-200">{formatDate(currentUser?.last_login)}</div>
                  </div>
                </div>
              </div>

              <form onSubmit={savePassword} className="glass rounded-xl border border-white/5 p-6 space-y-4">
                <div className="flex items-center gap-3">
                  <KeyRound className="w-5 h-5 text-indigo-400" />
                  <h2 className="text-lg font-semibold text-gray-200">{t('changePassword')}</h2>
                </div>
                <label className="block space-y-1.5">
                  <span className="text-xs text-gray-500">{t('oldPassword')}</span>
                  <input
                    type="password"
                    value={passwordForm.oldPassword}
                    onChange={(event) => setPasswordForm((current) => ({ ...current, oldPassword: event.target.value }))}
                    className="w-full rounded-xl border border-white/10 px-3 py-2.5 text-sm"
                    autoComplete="current-password"
                    required
                  />
                </label>
                <label className="block space-y-1.5">
                  <span className="text-xs text-gray-500">{t('newPassword')}</span>
                  <input
                    type="password"
                    value={passwordForm.newPassword}
                    onChange={(event) => setPasswordForm((current) => ({ ...current, newPassword: event.target.value }))}
                    className="w-full rounded-xl border border-white/10 px-3 py-2.5 text-sm"
                    minLength={6}
                    autoComplete="new-password"
                    required
                  />
                </label>
                <label className="block space-y-1.5">
                  <span className="text-xs text-gray-500">{t('confirmPassword')}</span>
                  <input
                    type="password"
                    value={passwordForm.confirmPassword}
                    onChange={(event) => setPasswordForm((current) => ({ ...current, confirmPassword: event.target.value }))}
                    className="w-full rounded-xl border border-white/10 px-3 py-2.5 text-sm"
                    minLength={6}
                    autoComplete="new-password"
                    required
                  />
                </label>
                <button
                  type="submit"
                  disabled={isSavingPassword}
                  className="liquid-button w-full rounded-xl bg-gradient-to-r from-indigo-600 to-purple-600 px-5 py-2.5 text-sm font-medium text-white disabled:opacity-50"
                >
                  {isSavingPassword ? t('running') : t('savePassword')}
                </button>
              </form>
            </div>

            {user?.role === 'admin' && (
              <div className="glass rounded-xl border border-white/5 p-6 space-y-5">
                <div className="flex items-center gap-3">
                  <UsersRound className="w-5 h-5 text-indigo-400" />
                  <div>
                    <h2 className="text-lg font-semibold text-gray-200">{t('userManagement')}</h2>
                    <p className="text-xs text-gray-500">{t('userManagementSubtitle')}</p>
                  </div>
                </div>

                <div className="overflow-x-auto rounded-xl border border-white/5">
                  <table className="w-full min-w-[760px] text-left text-sm">
                    <thead className="bg-white/5 text-xs text-gray-500">
                      <tr>
                        <th className="px-4 py-3 font-medium">{t('account')}</th>
                        <th className="px-4 py-3 font-medium">{t('role')}</th>
                        <th className="px-4 py-3 font-medium">{t('status')}</th>
                        <th className="px-4 py-3 font-medium">{t('lastLogin')}</th>
                        <th className="px-4 py-3 font-medium text-right">{t('actions')}</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-white/5">
                      {users.map((account) => (
                        <tr key={account.id} className="text-gray-300">
                          <td className="px-4 py-3">
                            <div className="font-medium text-gray-200">{account.display_name}</div>
                            <div className="text-xs text-gray-500">@{account.username}{account.email ? ` · ${account.email}` : ''}</div>
                          </td>
                          <td className="px-4 py-3">
                            <select
                              value={account.role}
                              disabled={isSavingUser === account.id}
                              onChange={(event) => saveUserField(account, { role: event.target.value })}
                              className="rounded-lg border border-white/10 px-3 py-1.5 text-xs"
                            >
                              <option value="user">{roleLabels.user}</option>
                              <option value="admin">{roleLabels.admin}</option>
                            </select>
                          </td>
                          <td className="px-4 py-3">
                            <span className={`rounded-full px-2.5 py-1 text-xs ${
                              account.is_active ? 'bg-emerald-500/10 text-emerald-500' : 'bg-red-500/10 text-red-500'
                            }`}>
                              {account.is_active ? t('active') : t('disabled')}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-xs text-gray-500">{formatDate(account.last_login)}</td>
                          <td className="px-4 py-3 text-right">
                            <button
                              type="button"
                              disabled={isSavingUser === account.id || account.id === user?.id}
                              onClick={() => saveUserField(account, { is_active: !account.is_active })}
                              className="rounded-lg border border-white/5 bg-white/5 px-3 py-1.5 text-xs text-gray-400 disabled:cursor-not-allowed disabled:opacity-40"
                            >
                              {account.is_active ? t('disable') : t('enable')}
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
