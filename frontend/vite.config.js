import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig(() => {
  const base = process.env.RAMANCLOUD_BASE_PATH || '/preprocessing/';
  if (!/^\/(?:[a-zA-Z0-9_-]+\/)*$/.test(base)) {
    throw new Error('RAMANCLOUD_BASE_PATH must be a path such as /alpha/.');
  }
  const apiBase = process.env.VITE_RAMANCLOUD_API_BASE || `${base}api`;
  if (!/^\/(?:[a-zA-Z0-9_-]+\/)*[a-zA-Z0-9_-]+$/.test(apiBase)) {
    throw new Error('VITE_RAMANCLOUD_API_BASE must be a same-origin path such as /ramancloud-api.');
  }
  const proxy = {
    target: process.env.RAMANCLOUD_DEV_API_URL || 'http://127.0.0.1:5000',
    changeOrigin: true,
    proxyTimeout: 600000,
    timeout: 600000,
  };
  return {
    base,
    plugins: [react(), tailwindcss()],
    server: {
      port: 5173,
      allowedHosts: ['ramancloud.xmu.edu.cn', '219.229.100.24'],
      proxy: {
        [`${apiBase}/`]: { ...proxy, rewrite: path => '/api' + path.slice(apiBase.length) },
        '/api': proxy,
      },
    },
  };
});
