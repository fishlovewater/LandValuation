import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

const devPort = Number(process.env.VITE_DEV_PORT || 5173)
// Local FastAPI uses APP_PORT=8000.  Keeping the development proxy on the
// same port prevents Vite from silently calling a stale Demo API on 18000.
const devApiTarget = process.env.VITE_DEV_API_TARGET || 'http://127.0.0.1:8000'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  server: {
    host: '127.0.0.1',
    port: devPort,
    strictPort: true,
    proxy: {
      '/api': {
        target: devApiTarget,
        changeOrigin: false,
      },
    },
  },
})
