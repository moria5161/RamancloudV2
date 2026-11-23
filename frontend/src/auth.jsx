import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';

const API_BASE = import.meta.env.BASE_URL.replace(/\/$/, '');
const TOKEN_KEY = API_BASE === '/preprocessing' ? 'ramancloud_auth_token' : `ramancloud_auth_token:${API_BASE}`;

const AuthContext = createContext(null);

export { apiErrorMessage } from './authErrors';

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY));
  const [user, setUser] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const currentToken = useRef(token);

  const authHeaders = useCallback((nextToken = token) => ({
    Authorization: `Bearer ${nextToken}`,
  }), [token]);

  const clearSession = useCallback(() => {
    currentToken.current = null;
    localStorage.removeItem(TOKEN_KEY);
    setToken(null);
    setUser(null);
    setIsLoading(false);
  }, []);

  const saveSession = useCallback((nextToken, nextUser) => {
    currentToken.current = nextToken;
    localStorage.setItem(TOKEN_KEY, nextToken);
    setToken(nextToken);
    setUser(nextUser);
    setIsLoading(false);
  }, []);

  const refreshUser = useCallback(async (nextToken = token) => {
    if (!nextToken) {
      setIsLoading(false);
      return null;
    }
    try {
      const { data } = await axios.get(`${API_BASE}/api/auth/me`, {
        headers: authHeaders(nextToken),
        timeout: 10000,
      });
      if (currentToken.current !== nextToken) return null;
      setUser(data.data.user);
      return data.data.user;
    } catch (error) {
      if (currentToken.current === nextToken) clearSession();
      return null;
    } finally {
      if (currentToken.current === nextToken) setIsLoading(false);
    }
  }, [authHeaders, clearSession, token]);

  useEffect(() => {
    refreshUser();
  }, [refreshUser]);

  const login = useCallback(async ({ identifier, password }) => {
    const { data } = await axios.post(`${API_BASE}/api/auth/login`, { identifier, password }, { timeout: 15000 });
    saveSession(data.data.token, data.data.user);
    return data.data.user;
  }, [saveSession]);

  const register = useCallback(async (payload) => {
    const { data } = await axios.post(`${API_BASE}/api/auth/register`, payload, { timeout: 15000 });
    saveSession(data.data.token, data.data.user);
    return data.data.user;
  }, [saveSession]);

  const logout = useCallback(async () => {
    if (token) {
      try {
        await axios.post(`${API_BASE}/api/auth/logout`, {}, { headers: authHeaders(), timeout: 5000 });
      } catch (error) {
        // The local session should still be cleared if the server already forgot it.
      }
    }
    clearSession();
  }, [authHeaders, clearSession, token]);

  const changePassword = useCallback(async ({ oldPassword, newPassword }) => {
    await axios.post(
      `${API_BASE}/api/auth/change-password`,
      { old_password: oldPassword, new_password: newPassword },
      { headers: authHeaders() }
    );
    clearSession();
  }, [authHeaders, clearSession]);

  const loadSpace = useCallback(async () => {
    const { data } = await axios.get(`${API_BASE}/api/account/space`, { headers: authHeaders() });
    return data.data;
  }, [authHeaders]);

  const listUsers = useCallback(async () => {
    const { data } = await axios.get(`${API_BASE}/api/users`, { headers: authHeaders() });
    return data.data.users;
  }, [authHeaders]);

  const updateUser = useCallback(async (userId, payload) => {
    const { data } = await axios.patch(`${API_BASE}/api/users/${userId}`, payload, { headers: authHeaders() });
    if (data.data.user.id === user?.id) {
      setUser(data.data.user);
    }
    return data.data.user;
  }, [authHeaders, user?.id]);

  const value = useMemo(() => ({
    token,
    user,
    isAuthenticated: Boolean(user && token),
    isLoading,
    login,
    register,
    logout,
    changePassword,
    loadSpace,
    listUsers,
    updateUser,
    refreshUser,
  }), [token, user, isLoading, login, register, logout, changePassword, loadSpace, listUsers, updateUser, refreshUser]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}
