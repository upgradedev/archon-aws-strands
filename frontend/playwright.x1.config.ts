import { defineConfig, devices } from '@playwright/test';
import { assertEnvironment } from './benchmarks/model';

assertEnvironment(process.env);
export default defineConfig({
  testDir: './benchmarks', testMatch: 'hero.spec.ts', fullyParallel: false, workers: 1,
  retries: 0, repeatEach: 1, timeout: 35000, expect: { timeout: 10000 },
  // The external launcher bounds this entire invocation, including server/browser startup, to 900000 ms.
  reporter: [['list'], ['./benchmarks/reporter.ts'], ['junit', { outputFile: 'artifacts/x1/browser-junit.xml' }]],
  outputDir: 'artifacts/x1/playwright',
  use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 1050 },
    baseURL: 'http://127.0.0.1:4173', serviceWorkers: 'block', trace: 'off', screenshot: 'off', video: 'off' },
  webServer: [
    { command: 'python -m uvicorn archon.web.api:app --host 127.0.0.1 --port 8000', url: 'http://127.0.0.1:8000/api/health', reuseExistingServer: false },
    { command: 'npm run preview', url: 'http://127.0.0.1:4173', reuseExistingServer: false },
  ],
});
