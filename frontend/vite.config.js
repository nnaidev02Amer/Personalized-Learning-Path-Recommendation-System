import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// During development, /api requests are proxied to FastAPI, so the browser
// talks to a single origin and no CORS setup is needed.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const apiTarget = env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8000'
  return {
    plugins: [react(), tailwindcss()],
    server: {
      port: 5173,
      proxy: { '/api': { target: apiTarget, changeOrigin: true } },
    },
    preview: {
      port: 4173,
      proxy: { '/api': { target: apiTarget, changeOrigin: true } },
    },
  }
})
