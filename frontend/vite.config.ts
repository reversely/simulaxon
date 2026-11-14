import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const api = 'http://127.0.0.1:8791'
export default defineConfig({
  plugins: [react()],
  server: { port: 5175, proxy: { '/api': api, '/media': api } },
})
