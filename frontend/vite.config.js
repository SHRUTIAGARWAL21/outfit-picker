import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The dev server runs on http://localhost:5173. The line below forwards any
// request that starts with /api to the FastAPI backend on :8000, stripping the
// /api prefix. So the browser only ever talks to :5173 (same origin), and the
// session cookie flows normally — no CORS setup needed for local development.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
