import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { fileURLToPath } from 'node:url';

export default defineConfig({
  base: '/',
  plugins: [react(), tailwindcss()],
  build: {
    commonjsOptions: { transformMixedEsModules: true },
    rollupOptions: {
      input: {
        main: fileURLToPath(new URL('./index.html', import.meta.url)),
        structureEditor: fileURLToPath(new URL('./structure-editor.html', import.meta.url)),
      },
    },
  },
  server: {
    host: '127.0.0.1',
    port: 5173,
    allowedHosts: ['ramancloud.xmu.edu.cn', '219.229.100.24'],
    proxy: {
      '/ramancloud-api': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: true,
        rewrite: path => path.replace(/^\/ramancloud-api/, '/api'),
      },
    },
  },
});
