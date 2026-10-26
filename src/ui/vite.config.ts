import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// In development the console runs on Vite (port 5173) and forwards /api, including the
// /api/stream WebSocket, to FastAPI. In the demo FastAPI serves the built dist/ itself.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', ws: true },
    },
  },
})
