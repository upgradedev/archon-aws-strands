import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { proxy: { '/api': 'http://127.0.0.1:8000' } },
  preview: { proxy: { '/api': 'http://127.0.0.1:8000' } },
  test: {
    globals: true,
    environment: 'jsdom', setupFiles: ['./tests/setup.ts'],
    include: ['tests/**/*.test.{ts,tsx}'],
    reporters: ['default', 'junit'], outputFile: { junit: 'artifacts/unit-junit.xml' },
    coverage: {
      provider: 'v8', include: ['src/**/*.{ts,tsx}'],
      reporter: ['text', 'html', 'json-summary', 'lcov', 'cobertura'],
      thresholds: { lines: 85, functions: 85, statements: 85, branches: 85 },
    },
  },
});
