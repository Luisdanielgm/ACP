import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  plugins: [vue()],
  base: '/managed/',
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
      '@acp/shared': resolve(__dirname, '../shared/src'),
      '@acp/public-app': resolve(__dirname, '../public-app/src'),
    },
  },
  server: {
    port: 5174,
    proxy: {
      '/managed/auth': 'http://localhost:8000',
      '/managed/workspaces': 'http://localhost:8000',
      '/managed/admin': 'http://localhost:8000',
      '/managed/agent': 'http://localhost:8000',
      '/managed/dashboard/auth': 'http://localhost:8000',
      '/ws': { target: 'http://localhost:8000', ws: true },
      '/health': 'http://localhost:8000',
      '/sessions': 'http://localhost:8000',
      '/api': 'http://localhost:8000',
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
})
