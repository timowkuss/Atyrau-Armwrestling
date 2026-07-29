import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
  },
  build: {
    // ArmTable3D (@google/model-viewer + three) is already code-split via
    // React.lazy/Suspense on the Home page and only downloads when someone
    // actually views the 3D table — its size is expected and doesn't block
    // the initial page load, so we raise the warning limit instead of
    // chasing a false alarm.
    chunkSizeWarningLimit: 900,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules')) {
            if (id.includes('react') || id.includes('scheduler')) {
              return 'vendor-react'
            }
            if (id.includes('@tanstack')) {
              return 'vendor-query'
            }
          }
        },
      },
    },
  },
})
