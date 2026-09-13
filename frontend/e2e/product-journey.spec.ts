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
