import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8005',
        changeOrigin: true,
        // �ؼ����� SSE ��ʽ�¼���������
        configure: (proxy) => {
          proxy.on('proxyRes', (proxyRes) => {
            // �� SSE ������û���
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