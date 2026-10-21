import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The FastAPI backend (repository root) runs on :8000; proxy API calls so no CORS setup is needed in dev.
const backend = 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': backend,
      '/mock': backend,
    },
  },
})
