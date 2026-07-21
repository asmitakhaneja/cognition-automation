import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The dashboard is served by the FastAPI backend. During local development
// `npm run dev` proxies API calls (/status, /events, /trigger*, ...) to the
// backend on :8000 so the SPA and API share an origin.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/status': 'http://localhost:8000',
      '/events': { target: 'http://localhost:8000', ws: true },
      '/trigger': 'http://localhost:8000',
      '/trigger-all': 'http://localhost:8000',
      '/session': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
})
