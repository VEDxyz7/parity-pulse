import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // No root envDir/loadEnv: the backend's .env never enters the frontend build.
  envPrefix: 'VITE_',
  server: {
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
  preview: {
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    restoreMocks: true,
    clearMocks: true,
  },
})
