import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'node:path'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src')
    }
  },
  optimizeDeps: {
    exclude: ['lucide-vue-next']
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true
      },
      '/market': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true
      },
      '/npm': {
        target: 'http://127.0.0.1:4873',
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/npm/, '')
      },
      '/mcp-api/v1': {
        target: 'http://127.0.0.1:8080',
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/mcp-api\/v1/, '/api/v1')
      },
      '/mcp': {
        target: 'http://127.0.0.1:8080',
        changeOrigin: true
      }
    }
  }
})
