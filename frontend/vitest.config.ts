import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    // Required for @testing-library/react to unmount between tests (auto-cleanup)
    globals: true,
    setupFiles: './src/test/setup.ts',
    css: true,
  },
})