import { defineConfig, devices } from '@playwright/test';

// Renderer contracts use explicit synthetic HTTP responses, not AWS acceptance.
export default defineConfig({
  testDir: './proof-tests', workers: 1, retries: 0, timeout: 15000,
  reporter: [['list'], ['junit', { outputFile: 'artifacts/proof-junit.xml' }]],
  use: { baseURL: 'http://127.0.0.1:4173', screenshot: 'on', trace: 'retain-on-failure' },
  outputDir: 'proof-results',
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'] } },
    { name: 'mobile', use: { ...devices['iPhone 13'], defaultBrowserType: 'chromium' } },
  ],
  webServer: { command: 'npm run preview', url: 'http://127.0.0.1:4173', reuseExistingServer: false },
});
