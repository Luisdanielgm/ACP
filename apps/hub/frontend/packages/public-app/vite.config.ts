import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
      '@acp/shared': resolve(__dirname, '../shared/src'),
    },
  },
  server: {
    proxy: {
      '/ws': { target: 'http://localhost:8000', ws: true },
      '/health': 'http://localhost:8000',
      '/runtime': 'http://localhost:8000',
      '/agents': 'http://localhost:8000',
      '/sessions': 'http://localhost:8000',
      '/dashboard/auth': 'http://localhost:8000',
      '/dashboard/overview': 'http://localhost:8000',
      '/api': 'http://localhost:8000',
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
})
