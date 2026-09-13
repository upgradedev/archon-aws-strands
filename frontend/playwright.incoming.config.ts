import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './incoming-acceptance', workers: 1, retries: 0, timeout: 240000,
  expect: { timeout: 30000 }, outputDir: 'incoming-results',
  reporter: [['list'], ['junit', { outputFile: 'artifacts/incoming-junit.xml' }]],
  use: { baseURL: 'https://d2ssmv59q16d0b.cloudfront.net', trace: 'off', screenshot: 'off', video: 'off' },
  projects: [{ name: 'desktop', use: { ...devices['Desktop Chrome'] } }],
});
