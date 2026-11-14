import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const api = process.env.LAB_API ?? 'http://127.0.0.1:8790'   // another lab server, such as a separate harness copy
export default defineConfig({
  plugins: [react()],
  server: { port: 5174, proxy: { '/tools': api, '/out': api, '/files': api, '/thumb': api, '/agent': api, '/datasets': api, '/api': api, '/dashboard': api, '/events': { target: api, ws: true } } },
})
