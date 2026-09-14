import { defineConfig, devices } from '@playwright/test';

const externalURL = process.env.ARCHON_UI_URL;
const liveLane = process.env.ARCHON_LIVE_ACCEPTANCE === 'true';
const fakeLive = process.env.ARCHON_FAKE_PROVIDERS === 'true';

export default defineConfig({
  testDir: liveLane ? './e2e-live' : './e2e', fullyParallel: false, workers: 1,
  timeout: liveLane ? 600000 : 45000, expect: { timeout: liveLane ? 180000 : 10000 },
  outputDir: fakeLive ? 'live-contract-results' : 'test-results',
  reporter: [['list'], ['html', { open: 'never', outputFolder: fakeLive ? 'live-contract-report' : 'playwright-report' }],
    ['junit', { outputFile: fakeLive ? 'artifacts/live-contract-junit.xml' : 'artifacts/browser-junit.xml' }]],
  use: { baseURL: externalURL || 'http://127.0.0.1:4173', trace: 'on', screenshot: 'on', video: 'retain-on-failure' },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 1050 } } },
    { name: 'mobile', use: { ...devices['iPhone 13'], defaultBrowserType: 'chromium' } },
    { name: 'webkit', testMatch: liveLane ? 'providers.spec.ts' : ['product-journey.spec.ts', 'business-portfolio.spec.ts'], use: { ...devices['iPhone 13'], viewport: { width: 375, height: 812 } } },
  ],
  webServer: externalURL ? undefined : [
    { command: fakeLive ? 'python -m uvicorn live_browser_server:app --app-dir ../tests --host 127.0.0.1 --port 8000' : 'python -m uvicorn archon.web.api:app --host 127.0.0.1 --port 8000', url: 'http://127.0.0.1:8000/api/health', reuseExistingServer: false },
    { command: 'npm run preview', url: 'http://127.0.0.1:4173', reuseExistingServer: false },
  ],
});
