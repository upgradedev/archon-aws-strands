import { test, expect } from '@playwright/test';

const front = '1'.repeat(40), back = '2'.repeat(40);
const evidence = {
  schema_version: 1, application: 'Archon', environment: 'live_aws', status: 'AUTOMATED_JOURNEYS_PASSED',
  frontend_commit: front, backend_commit: back, mode: 'synthetic', live_send: false, live_model: false,
  run_id: '123', run_attempt: '2', run_url: 'https://github.com/upgradedev/archon-aws-strands/actions/runs/123/attempts/2',
  observed_at: '2026-09-10T05:00:00Z', human_uat: 'NOT_RUN',
  checks: { preflight: 'success', journeys: 'success', postflight: 'success' },
  counts: { total: 34, passed: 34, failed: 0, skipped: 0 },
};
const health = { commit: back, status: 'ok', mode: 'synthetic', live_send: false, live_model: false,
  model: 'LedgerScriptModel', provider: 'SimulatedProvider', orchestration: 'Strands' };

for (const scenario of ['current', 'missing', 'malformed', 'stale frontend', 'stale HTML', 'missing HTML marker', 'stale backend', 'failed gate', 'skipped', 'unsafe link', 'live mode']) {
  test(`release proof renderer: ${scenario}`, async ({ page }) => {
    const record = structuredClone(evidence);
    if (scenario === 'failed gate') record.checks.postflight = 'failure';
    if (scenario === 'skipped') record.counts.skipped = 1;
    if (scenario === 'unsafe link') record.run_url = 'javascript:alert(1)';
    await page.route(url => url.pathname === '/', route => route.fulfill({ contentType: 'text/html',
      body: scenario === 'missing HTML marker' ? '<html><head></head></html>'
        : `<html><head><meta name="application-commit" content="${scenario === 'stale HTML' ? '3'.repeat(40) : front}"></head></html>` }));
    await page.route('**/release.json', route => route.fulfill({ json: { commit: scenario === 'stale frontend' ? '3'.repeat(40) : front } }));
    await page.route('**/api/health', route => route.fulfill({ json: { ...health,
      commit: scenario === 'stale backend' ? '3'.repeat(40) : back, live_send: scenario === 'live mode' } }));
    await page.route('**/acceptance.json', route => scenario === 'missing' ? route.fulfill({ status: 404 })
      : scenario === 'malformed' ? route.fulfill({ contentType: 'application/json', body: '{bad' }) : route.fulfill({ json: record }));
    await page.goto('/acceptance.html');
    const status = page.getByRole('status');
    if (scenario === 'current') {
      await expect(status).toHaveText('Automated journeys passed for this release pair');
      await expect(page.locator('#facts')).toContainText(front);
      await expect(page.locator('#facts')).toContainText(back);
      await expect(page.locator('#run')).toHaveAttribute('href', evidence.run_url);
    } else if (scenario.startsWith('stale')) {
      await expect(status).toHaveText('Historical evidence only');
    } else if (scenario === 'live mode') {
      await expect(status).toHaveText('Runtime scope does not match');
    } else {
      await expect(status).toHaveText('Current acceptance unavailable');
      await expect(page.locator('#run')).toBeHidden();
    }
    await expect(page.getByText('Human UAT: NOT_RUN.', { exact: false })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  });
}

for (const scenario of ['current', 'unmeasured model', 'invented delivery', 'wrong runtime']) {
  test(`controlled-provider proof renderer: ${scenario}`, async ({ page }) => {
    const record = { ...evidence, schema_version: 2, status: 'CONTROLLED_PROVIDER_JOURNEYS_PASSED',
      mode: 'controlled-live', live_send: true, live_model: true,
      counts: { total: 3, passed: 3, failed: 0, skipped: 0 },
      limits: 'Fictional business data; actual Bedrock and controlled SES provider acceptance. No mailbox arrival, bank settlement, independent model superiority or human UAT proven.',
      provider_checks: { model_calls: scenario === 'unmeasured model' ? 0 : 45, input_tokens: 5000,
        output_tokens: 900, emails_accepted: 3, delivery_proven: scenario === 'invented delivery' } };
    await page.route(url => url.pathname === '/', route => route.fulfill({ contentType: 'text/html',
      body: `<html><head><meta name="application-commit" content="${front}"></head></html>` }));
    await page.route('**/release.json', route => route.fulfill({ json: { commit: front } }));
    await page.route('**/api/health', route => route.fulfill({ json: scenario === 'wrong runtime' ? health : {
      ...health, mode: 'controlled-live', live_model: true, live_send: true,
      model: 'eu.anthropic.claude-opus-5', provider: 'SES-controlled-recipient' } }));
    await page.route('**/acceptance.json', route => route.fulfill({ json: record }));
    await page.goto('/acceptance.html');
    await expect(page.getByRole('status')).toHaveText(scenario === 'current'
      ? 'Controlled real-provider journeys passed for this release pair'
      : scenario === 'wrong runtime' ? 'Runtime scope does not match' : 'Current acceptance unavailable');
    if (scenario === 'current') await expect(page.locator('#detail')).toContainText('Mailbox arrival and human signoff remain unproven');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  });
}
