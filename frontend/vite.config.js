import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The dev server proxies /api to the FastAPI service on port 8000.
//
// WHY A PROXY RATHER THAN CORS: without it the browser blocks requests
// from localhost:5173 to localhost:8000 as cross-origin, and the usual
// fix is to open CORS on the API. That means shipping a permissive
// CORS policy to production to solve a development-only problem. The
// proxy keeps the browser seeing one origin and leaves the API alone.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})