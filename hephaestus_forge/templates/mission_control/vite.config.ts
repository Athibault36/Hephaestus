import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 3000,
    host: '127.0.0.1',
    proxy: {
      '/ue-bridge': {
        target: process.env.VITE_UE_BRIDGE_PROXY || 'http://127.0.0.1:8099',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/ue-bridge/, ''),
      },
      '/api': {
        target: 'http://127.0.0.1:8084',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://127.0.0.1:8081',
        ws: true,
      },
    },
  },
});