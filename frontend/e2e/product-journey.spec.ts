import { test, expect, type Page } from '@playwright/test';

async function state(page: Page) {
  const session = await page.evaluate(() => localStorage.getItem('archon.demo.session.v1'));
  expect(session).toBeTruthy();
  const response = await page.request.get('/api/workspace', { headers: { 'X-Archon-Session': session! } });
  expect(response.status()).toBe(200);
  return { session, data: await response.json() };
}
async function post(page: Page, name: string) {
  const response = page.waitForResponse(response => new URL(response.url()).pathname === '/api/intake');
  await page.getByRole('button', { name, exact: true }).click();
  expect((await response).status()).toBe(200);
  await expect(page.locator('main')).toHaveAttribute('aria-busy', 'false');
}
async function invoiceAndPayment(page: Page) {
  await page.goto('/');
  await page.getByTestId('start-guided-example').click();
  await expect(page.getByLabel('Email headers and plain-text body')).toHaveValue(/Invoice JN-4410/);
  await post(page, 'Read & add invoice');
  await expect(page.getByLabel('Email headers and plain-text body')).toHaveValue(/Transfer ID: DEMO-BANK-600-A/);
  await post(page, 'Record payment & check balance');
  await expect(page.locator('.journey-progress [aria-current="step"]')).toHaveText('3Review');
}
test.beforeEach(async ({ page }, info) => {
  if (info.project.name !== 'desktop') await page.setViewportSize({ width: 375, height: 812 });
  const response = await page.request.get('/api/health'); expect(response.status()).toBe(200);
  const health = await response.json();
  expect(health).toMatchObject({ mode: 'synthetic', live_model: false, live_send: false, model: 'LedgerScriptModel', provider: 'SimulatedProvider', orchestration: 'Strands' });
  await info.attach('product-runtime.json', { contentType: 'application/json', body: JSON.stringify({ source: process.env.GITHUB_SHA, expectedRelease: process.env.EXPECTED_RELEASE, health, project: info.project.name, independentHumanUAT: 'NOT_RUN' }) });
});

test('landing paints before session access and the guided decision survives return and reload', async ({ page }, info) => {
  const errors: string[] = []; page.on('pageerror', error => errors.push(error.message));
  const mutations: string[] = [];
  page.on('request', request => { if (request.method() === 'POST') mutations.push(new URL(request.url()).pathname); });
  await page.goto('/');
  await expect(page.getByRole('heading', { name: /Chase the balance/ })).toBeFocused();
  const start = page.getByTestId('start-guided-example');
  await expect(start).toBeVisible();
  const bounds = (await start.boundingBox())!;
  expect(bounds.height).toBeGreaterThanOrEqual(44); expect(bounds.y + bounds.height).toBeLessThanOrEqual(page.viewportSize()!.height);
  expect(mutations).toEqual([]);
  expect(await page.evaluate(() => localStorage.getItem('archon.demo.session.v1'))).toBeNull();
  await page.screenshot({ path: info.outputPath('product-landing.png') });
  await page.keyboard.press('Tab'); await expect(start).toBeFocused(); await page.keyboard.press('Enter');
  await expect(page.getByLabel('Email headers and plain-text body')).toHaveValue(/Invoice JN-4410/);
  const first = await state(page); expect(first.data.sources).toEqual([]);
  await post(page, 'Read & add invoice');
  await expect(page.getByLabel('Email headers and plain-text body')).toHaveValue(/Transfer ID: DEMO-BANK-600-A/);
  await post(page, 'Record payment & check balance');
  const ledger = page.getByRole('complementary', { name: 'Current case evidence' });
  await expect(ledger).toContainText('1,260.00 EUR');
  await expect(page.getByRole('button', { name: /Approve exact draft/ })).toHaveCount(0);
  await page.getByRole('button', { name: /Run Strands/ }).click();
  await expect(page.locator('.email > pre')).toContainText('1,260.00 EUR');
  const approve = page.getByRole('button', { name: /Approve exact draft/ }); await expect(approve).toBeDisabled();
  expect((await state(page)).data.receipts).toEqual([]);
  await page.screenshot({ path: info.outputPath('product-review.png'), fullPage: true });
  await page.getByRole('checkbox', { name: /I reviewed this recipient/ }).check(); await approve.click();
  const result = page.getByRole('region', { name: 'Guided check outcome' });
  await expect(result).toContainText('Simulated · provider-accepted'); await expect(result).toContainText('No real email was sent');
  const outcomeHeading = result.getByRole('heading', { name: 'Your decision is recorded.' });
  await expect(outcomeHeading).toBeFocused();
  await expect(outcomeHeading).toBeInViewport();
  await expect(result).toContainText('1,260.00 EUR');
  await page.screenshot({ path: info.outputPath('product-outcome.png') });
  await result.getByRole('button', { name: 'Prepare evidence bundle', exact: true }).click();
  await expect(result.getByRole('link', { name: 'Download readable evidence' })).toBeVisible();
  await page.reload(); await expect(result).toBeVisible();
  await page.getByRole('link', { name: /^ARCHON/ }).click();
  await expect(page.getByRole('heading', { name: /Chase the balance/ })).toBeVisible();
  await page.getByTestId('start-guided-example').click(); await expect(result).toBeVisible();
  const saved = await state(page); expect(saved.session).toBe(first.session); expect(saved.data.receipts).toHaveLength(1);
  expect(saved.data.sales[0].outstanding).toBe('1260.00'); expect(mutations.filter(path => path === '/api/approve')).toHaveLength(1);
  await page.screenshot({ path: info.outputPath('product-return.png') });
  await result.getByRole('link', { name: 'Add new payment evidence →' }).click();
  await expect(page.getByLabel('Email headers and plain-text body')).toHaveValue('');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true); expect(errors).toEqual([]);
});

test('counterproposal retains the client reply without inventing acceptance or reducing debt', async ({ page }, info) => {
  await invoiceAndPayment(page);
  await page.goto('/#/workspace?invoice=JN-4410&view=terms');
  const original = '2026-09-20: 1260.00 EUR';
  const counter = '2026-09-25: 600.00 EUR\n2026-10-10: 660.00 EUR';
  await page.getByLabel("Client's proposed terms").fill(original);
  await page.getByRole('button', { name: 'Read proposed terms', exact: true }).click();
  await page.getByText('Offer different payment dates', { exact: true }).click();
  await page.getByLabel('Your counterproposal', { exact: true }).fill(counter);
  const record = page.getByRole('button', { name: 'Record counterproposal · no send', exact: true });
  await expect(record).toBeDisabled();
  await page.getByRole('checkbox', { name: /I reviewed my counterproposal/ }).check();
  await record.click();
  const history = page.getByRole('region', { name: 'Terms decision history' });
  await expect(history).toContainText('Counterproposal recorded · client acceptance not recorded');
  await page.reload();
  await history.getByText(/Counterproposal recorded · client acceptance not recorded/).click();
  await expect(history).toContainText(original); await expect(history).toContainText(counter);
  const saved = await state(page);
  expect(saved.data.sales[0].outstanding).toBe('1260.00'); expect(saved.data.arrangements).toEqual([]);
  expect(saved.data.receipts).toEqual([]); expect(saved.data.queue.ready).toHaveLength(1);
  await page.screenshot({ path: info.outputPath('counterproposal-retained.png'), fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.getByLabel("Client's proposed terms").fill(counter);
  await page.getByRole('button', { name: 'Read proposed terms', exact: true }).click();
  await page.getByLabel(/I approve these exact/).check();
  await page.getByRole('button', { name: 'Approve arrangement', exact: true }).click();
  await page.reload(); await expect(page.getByText('Agreed arrangements', { exact: true })).toBeVisible();
  const agreed = await state(page); expect(agreed.data.sales[0].outstanding).toBe('1260.00');
  expect(agreed.data.queue.blocked).toHaveLength(1); expect(agreed.data.terms_history[1].original.body).toBe(original);
});

test('human date and EUR notation posts explicit facts but conflicting totals stay held', async ({ page }, info) => {
  await page.goto('/#/journey');
  const source = 'From: me@myjoinery.example\nTo: owner@maple.example\nOur invoice to Maple Workshop. Invoice MP-7201 dated 3 July 2026, due August 12, 2026. Net EUR 2.400,00 VAT EUR 576,00 total EUR 2.976,00.';
  await page.getByLabel('Email headers and plain-text body').fill(source);
  await post(page, 'Read & add invoice');
  expect((await state(page)).data.sales[0].outstanding).toBe('2976.00');
  await page.getByLabel('Email headers and plain-text body').fill('From: owner@maple.example\nPaid EUR 900,00 on 22 August 2026 against invoice MP-7201.\nTransfer ID: MAPLE-BANK-900');
  await post(page, 'Record payment & check balance');
  expect((await state(page)).data.sales[0].outstanding).toBe('2076.00');
  await page.goto('/#/documents');
  await page.getByLabel(/Email headers/).fill(source.replaceAll('MP-7201', 'MP-7202') + '\nGross EUR 2.977,00');
  await page.getByRole('button', { name: 'Read & post email', exact: true }).click();
  await expect(page.locator('main')).toContainText('Conflicting invoice totals');
  const stopped = await state(page); expect(stopped.data.holds).toHaveLength(1);
  expect(stopped.data.sales).toHaveLength(1); expect(stopped.data.receipts).toEqual([]);
  await page.screenshot({ path: info.outputPath('reader-conflict-held.png'), fullPage: true });
});

test('cold landing records paint support and main visibility without a session request', async ({ page }, info) => {
  await page.addInitScript(() => {
    const observed = { lcp: null as number | null, mainVisible: null as number | null, supported: PerformanceObserver.supportedEntryTypes };
    Object.assign(window, { archonPaintObservation: observed });
    if (observed.supported.includes('largest-contentful-paint')) {
      new PerformanceObserver(list => { for (const entry of list.getEntries()) observed.lcp = entry.startTime; }).observe({ type: 'largest-contentful-paint', buffered: true });
    }
    function visible() {
      const heading = document.querySelector('main h1');
      if (heading && heading.getBoundingClientRect().height > 0 && getComputedStyle(heading).visibility !== 'hidden') {
        requestAnimationFrame(() => { observed.mainVisible = performance.now(); });
      } else requestAnimationFrame(visible);
    }
    requestAnimationFrame(visible);
  });
  await page.goto('/');
  await expect(page.getByRole('heading', { name: /Chase the balance/ })).toBeVisible();
  await page.waitForFunction(() => (window as unknown as { archonPaintObservation: { mainVisible: number | null } }).archonPaintObservation.mainVisible !== null);
  // Allow buffered paint delivery, not an API response or a warm second navigation.
  await page.waitForTimeout(500);
  const observation = await page.evaluate(() => ({
    ...(window as unknown as { archonPaintObservation: { lcp: number | null; mainVisible: number; supported: string[] } }).archonPaintObservation,
    fcp: performance.getEntriesByName('first-contentful-paint')[0]?.startTime ?? null,
    session: localStorage.getItem('archon.demo.session.v1'),
  }));
  await info.attach('cold-paint.json', { contentType: 'application/json', body: JSON.stringify({ ...observation, browser: info.project.name, url: page.url(), source: process.env.GITHUB_SHA, expectedRelease: process.env.EXPECTED_RELEASE, scope: 'Cold browser context; CDN cache not purged. Main visibility is not FCP. Unsupported paint APIs are null, not zero. Not an X1 rerun.' }) });
  await page.screenshot({ path: info.outputPath('cold-main-paint.png') });
  expect(observation.session).toBeNull(); expect(observation.mainVisible).toBeLessThan(2500);
  if (observation.supported.includes('paint')) { expect(observation.fcp).not.toBeNull(); expect(observation.fcp!).toBeLessThan(2500); }
  if (observation.supported.includes('largest-contentful-paint')) { expect(observation.lcp).not.toBeNull(); expect(observation.lcp!).toBeLessThan(2500); }
});

test('guided duplicate holds collection without adding money or automatically resolving evidence', async ({ page }, info) => {
  await invoiceAndPayment(page);
  const paid = await state(page);
  await page.getByRole('link', { name: /Add or review payment evidence/ }).click();
  await page.getByLabel('Email headers and plain-text body').fill(paid.data.samples.payment + '\nForwarded for reference.');
  await post(page, 'Record payment & check balance');
  const hold = page.getByRole('region', { name: 'Guided check paused' });
  await expect(hold).toContainText('could not be posted');
  await expect(page.getByRole('button', { name: /Approve exact draft|Run Strands/ })).toHaveCount(0);
  const stopped = await state(page); expect(stopped.data.holds).toHaveLength(1); expect(stopped.data.sales[0].outstanding).toBe('1260.00'); expect(stopped.data.receipts).toEqual([]);
  await page.screenshot({ path: info.outputPath('product-held-evidence.png'), fullPage: true });
  await hold.getByRole('link', { name: /Review sources and corrections/ }).click();
  await expect(page.getByRole('heading', { name: 'Records', exact: true })).toBeVisible();
});

test('guided source survives offline recovery and expired session never looks like empty books', async ({ page, context }, info) => {
  await page.goto('/#/journey');
  const input = page.getByLabel('Email headers and plain-text body');
  await expect(input).toHaveValue(/Invoice JN-4410/);
  const original = await input.inputValue(); await input.fill(original + '\nEditable note.');
  await context.setOffline(true);
  await expect(page.getByRole('region', { name: 'Guided check paused' })).toContainText('Reconnect');
  await expect(input).toHaveValue(original + '\nEditable note.'); await expect(input).toBeDisabled();
  await context.setOffline(false);
  await expect(input).toBeDisabled();
  await page.getByRole('button', { name: 'Refresh durable state', exact: true }).click();
  await expect(input).toBeEnabled(); await expect(input).toHaveValue(original + '\nEditable note.');
  await page.evaluate(() => localStorage.setItem('archon.demo.session.v1', 'e'.repeat(64)));
  await page.goto('/');
  await expect(page.getByRole('heading', { name: /Chase the balance/ })).toBeVisible();
  await page.getByRole('link', { name: /Continue my workspace/ }).click();
  await expect(page.getByRole('alert')).toContainText('No balance is available');
  await expect(page.getByTestId('metric-outstanding')).toHaveCount(0);
  await page.screenshot({ path: info.outputPath('product-expired-session.png') });
  await page.getByRole('button', { name: 'New workspace', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Start a new workspace' })).toContainText('does not delete its stored records');
  await page.getByRole('button', { name: 'Keep current workspace' }).click();
  await expect(page.getByRole('alert')).toBeVisible();
});
