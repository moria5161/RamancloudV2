import axios from 'axios';
import { API_BASE } from './apiBase';

const bootstrap = axios.create();
let pending = null;
let csrfToken;

function workspaceRequest(config) {
  const url = new URL(config.url, window.location.href);
  return url.origin === window.location.origin && url.pathname.startsWith(`${API_BASE}/`)
    && !url.pathname.startsWith(`${API_BASE}/visits/`) && url.pathname !== `${API_BASE}/health`;
}

async function sessionToken() {
  if (csrfToken !== undefined) return csrfToken;
  if (!pending) {
    pending = bootstrap.get(`${API_BASE}/session`, { withCredentials: true }).then(({ data }) => {
      if (typeof data.csrf_token !== 'string') throw new Error('Invalid workspace session response');
      csrfToken = data.csrf_token;
      return csrfToken;
    }).catch(error => {
      // The offline desktop and local development API do not require web sessions.
      if (error.response?.status === 404 && ['localhost', '127.0.0.1', '[::1]'].includes(window.location.hostname)) {
        csrfToken = null;
        return null;
      }
      throw error;
    }).finally(() => { pending = null; });
  }
  return pending;
}

axios.interceptors.request.use(async config => {
  if (!workspaceRequest(config)) return config;
  const token = await sessionToken();
  config.withCredentials = true;
  if (token) config.headers.set('X-RamanCloud-CSRF', token);
  return config;
});

axios.interceptors.response.use(response => response, async error => {
  const config = error.config;
  if (config && workspaceRequest(config) && error.response?.status === 401 && !config.__workspaceRetried) {
    config.__workspaceRetried = true;
    csrfToken = undefined;
    await sessionToken();
    return axios(config);
  }
  throw error;
});
