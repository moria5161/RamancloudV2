import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig(() => {
  const base = process.env.RAMANCLOUD_BASE_PATH || '/preprocessing/';
  if (!/^\/(?:[a-zA-Z0-9_-]+\/)+$/.test(base)) {
    throw new Error('RAMANCLOUD_BASE_PATH must be a path such as /alpha/.');
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
        [`${base}api`]: { ...proxy, rewrite: path => path.slice(base.length - 1) },
        '/api': proxy,
      },
    },
  };
});
