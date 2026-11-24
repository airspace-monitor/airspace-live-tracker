import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { loadEnv } from 'vite'
import { defineConfig } from 'vitest/config'

// The dev server proxies /api to the tailnet API so the browser stays same-origin
// (no CORS while the app runs locally). Override the target in web/.env if needed.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const proxyTarget = env.VITE_API_PROXY_TARGET ?? 'http://airspace-vm.tailf5a9a6.ts.net:8001'

  return {
    plugins: [react(), tailwindcss()],
    // MapLibre creates its worker from a URL next to its module; pre-bundling breaks it.
    optimizeDeps: { exclude: ['maplibre-gl'] },
    server: {
      proxy: {
        '/api': { target: proxyTarget, changeOrigin: true },
      },
    },
    test: {
      environment: 'jsdom',
      setupFiles: './src/test/setup.ts',
    },
  }
})
