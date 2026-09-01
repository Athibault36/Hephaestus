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
      '/v1': { target: 'http://127.0.0.1:8765', changeOrigin: true },
      '/agent': { target: 'http://127.0.0.1:3000', changeOrigin: true },
    },
  },
});