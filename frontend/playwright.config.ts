import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e', fullyParallel: false, workers: 1,
  timeout: 45000, expect: { timeout: 10000 },
  reporter: [['list'], ['html', { open: 'never' }], ['junit', { outputFile: 'artifacts/browser-junit.xml' }]],
  use: { baseURL: 'http://127.0.0.1:4173', trace: 'on', screenshot: 'on', video: 'retain-on-failure' },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 1050 } } },
    { name: 'mobile', use: { ...devices['iPhone 13'], defaultBrowserType: 'chromium' } },
  ],
  webServer: [
    { command: 'python -m uvicorn archon.web.api:app --host 127.0.0.1 --port 8000', url: 'http://127.0.0.1:8000/api/health', reuseExistingServer: false },
    { command: 'npm run preview', url: 'http://127.0.0.1:4173', reuseExistingServer: false },
  ],
});
