import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8002',
        changeOrigin: true,
        // 关键：让 SSE 流式事件不被缓冲
        configure: (proxy) => {
          proxy.on('proxyRes', (proxyRes) => {
            // 对 SSE 请求禁用缓冲
            if (proxyRes.headers['content-type']?.includes('text/event-stream')) {
              proxyRes.headers['cache-control'] = 'no-cache'
              proxyRes.headers['x-accel-buffering'] = 'no'
            }
          })
        },
      },
    },
  },
})