import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  base: '/preprocessing/',
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    allowedHosts: ['ramancloud.xmu.edu.cn', '219.229.100.24'],
    proxy: {
      '/preprocessing/api': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: true,
        rewrite: path => path.replace(/^\/preprocessing/, ''),
      },
      '/api': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: true,
      },
    },
  },
});
