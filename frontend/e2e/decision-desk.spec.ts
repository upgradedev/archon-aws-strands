import { test, expect, type Locator, type Page } from '@playwright/test';
import type { Workspace } from '../src/types';
import { postEmailAndReadState } from './intake';

async function readState(page: Page): Promise<Workspace> {
  const session = await page.evaluate(() => localStorage.getItem('archon.demo.session.v1'));
  expect(session).toBeTruthy();
  const response = await page.request.get('/api/workspace', { headers: { 'X-Archon-Session': session! } });
  expect(response.status()).toBe(200);
  return response.json();
}

// Walk the actual tab order, including after an async page transition.
async function keyboardActivate(page: Page, target: Locator, key = 'Enter') {
  await expect(target).toBeVisible();
  for (let step = 0; step < 70; step++) {
    if (await target.evaluate(element => element === document.activeElement)) break;
    await page.keyboard.press('Tab');
  }
  await expect(target).toBeFocused();
  await page.keyboard.press(key);
}

async function keyboardPost(page: Page) {
  const body = await page.getByLabel(/Email headers/).inputValue();
  expect(body).not.toBe('');
  const response = page.waitForResponse(response => new URL(response.url()).pathname === '/api/intake'
    && response.request().method() === 'POST' && response.request().postDataJSON().body === body);
  await keyboardActivate(page, page.getByRole('button', { name: 'Read & post email', exact: true }));
  expect((await response).status()).toBe(200);
  await expect(page.getByLabel(/Email headers/)).toHaveValue('');
  await expect(page.locator('main')).toHaveAttribute('aria-busy', 'false');
}

test.beforeEach(async ({ page }, info) => {
  if (info.project.name === 'mobile') await page.setViewportSize({ width: 375, height: 812 });
  const response = await page.request.get('/api/health');
  expect(response.status()).toBe(200);
  const health = await response.json();
  expect(health).toMatchObject({ mode: 'synthetic', live_send: false, live_model: false, model: 'LedgerScriptModel', provider: 'SimulatedProvider' });
  await info.attach('source-and-runtime.json', { contentType: 'application/json', body: JSON.stringify({
    source: process.env.GITHUB_SHA ?? null, expectedRelease: process.env.EXPECTED_RELEASE ?? null,
    runtime: health, project: info.project.name, humanComprehension: 'NOT_RUN',
  }, null, 2) });
});

test('decision desk keyboard journey returns to changed evidence and explicitly simulates one approval', async ({ page }, info) => {
  const errors: string[] = []; page.on('pageerror', error => errors.push(error.message));
  await page.goto('/#/dashboard');
  await expect(page.getByRole('heading', { name: 'Dashboard', exact: true })).toBeFocused();
  const desk = page.getByRole('region', { name: 'Reconciliation journey' });
  await expect(desk).toContainText("ALEX'S COLLECTIONS DESK");
  await expect(desk).toContainText('self-employed joiner');
  const start = desk.getByRole('link', { name: 'Start reconciliation', exact: true });
  const bounds = await start.boundingBox();
  expect(bounds!.height).toBeGreaterThanOrEqual(44);
  expect(bounds!.y + bounds!.height).toBeLessThanOrEqual(page.viewportSize()!.height);
  await page.screenshot({ path: info.outputPath('desk-cold-start.png') });
  await page.keyboard.press('Tab'); await expect(start).toBeFocused(); await page.keyboard.press('Enter');
  await expect(page.getByLabel(/Email headers/)).toHaveValue(/Invoice JN-4410/);
  expect((await readState(page)).sources).toEqual([]);
  await keyboardPost(page);
  await keyboardActivate(page, page.getByRole('link', { name: 'Review changed decision →', exact: true }));
  await keyboardActivate(page, page.getByRole('link', { name: 'Prepare current draft below', exact: true }));
  await expect(page.locator('#prepare-current-draft')).toBeFocused();
  await keyboardActivate(page, page.getByRole('button', { name: /Run Strands/ }));
  await expect(page.locator('.email > pre')).toContainText('1,860.00 EUR');
  const old = await readState(page);
  await keyboardActivate(page, page.getByLabel(/I reviewed this recipient/), 'Space');
  await expect(page.getByRole('button', { name: /Approve exact draft/ })).toBeEnabled();
  await keyboardActivate(page, page.getByText('Try new evidence before approving', { exact: true }));
  await keyboardActivate(page, page.getByRole('link', { name: 'Add payment evidence →', exact: true }));
  await keyboardPost(page);
  await page.goto('/#/dashboard');
  await expect(desk).toContainText('Payment evidence changed the decision');
  await expect(desk).toContainText('1,260.00 EUR');
  await page.screenshot({ path: info.outputPath('desk-returning-payment.png') });
  await keyboardActivate(page, desk.getByRole('link', { name: 'Continue reconciliation', exact: true }));
  await expect(page.getByRole('complementary', { name: 'Previous review invalidated' })).toContainText('Previous draft cannot be approved');
  await expect(page.locator('.email > pre')).toHaveCount(0);
  const paid = await readState(page); expect(paid.draft).toBeNull(); expect(paid.receipts).toEqual([]);
  await page.reload();
  await expect(page.getByRole('complementary', { name: 'Previous review invalidated' })).toBeVisible();
  await expect(page.getByTestId('payment-change')).toContainText('1,860.00 EUR');
  await expect(page.getByTestId('payment-change')).toContainText('1,260.00 EUR');
  await page.screenshot({ path: info.outputPath('desk-invalidated-draft.png'), fullPage: true });
  await keyboardActivate(page, page.getByRole('link', { name: 'Prepare current draft below', exact: true }));
  await keyboardActivate(page, page.getByRole('button', { name: /Run Strands/ }));
  await expect(page.locator('.email > pre')).toContainText('1,260.00 EUR');
  const consent = page.getByRole('checkbox', { name: /I authorize a simulated send only/ });
  await expect(consent).not.toBeChecked();
  expect((await readState(page)).draft!.fingerprint).not.toBe(old.draft!.fingerprint);
  await keyboardActivate(page, consent, 'Space');
  await keyboardActivate(page, page.getByRole('button', { name: /Approve exact draft/ }));
  const outcome = page.getByRole('region', { name: 'Recorded collection outcome' });
  await expect(outcome).toContainText('provider-accepted');
  await expect(outcome).toContainText('No real email was sent');
  await page.screenshot({ path: info.outputPath('desk-completed-simulation.png') });
  await page.reload(); await expect(outcome).toBeVisible();
  const completed = await readState(page);
  expect(completed.receipts).toHaveLength(1); expect(completed.sales[0].outstanding).toBe('1260.00');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect(errors).toEqual([]);
});

test('returning held desk keeps the posted amount visible and requires offline recovery before action', async ({ page, context }, info) => {
  await page.goto('/#/dashboard'); await page.getByRole('link', { name: 'Start reconciliation', exact: true }).click();
  await postEmailAndReadState(page);
  await page.getByRole('button', { name: 'Sample refusal', exact: true }).click();
  const held = await postEmailAndReadState(page); expect(held.holds).toHaveLength(1);
  await page.goto('/#/dashboard');
  const desk = page.getByRole('region', { name: 'Reconciliation journey' });
  await expect(desk).toContainText('Hold collection. Resolve the evidence.');
  await expect(desk).toContainText('1,860.00 EUR');
  await expect(desk.getByRole('link', { name: 'Continue reconciliation', exact: true })).toHaveAttribute('href', '#/records?filter=refused');
  await page.screenshot({ path: info.outputPath('desk-held-evidence.png') });
  await context.setOffline(true);
  await page.getByRole('button', { name: 'Refresh', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Decision paused');
  await expect(desk).toContainText('LAST KNOWN BALANCE');
  await page.screenshot({ path: info.outputPath('desk-offline-recovery.png') });
  await context.setOffline(false);
  await keyboardActivate(page, desk.getByRole('link', { name: /Refresh before continuing/ }));
  await expect(page.getByRole('button', { name: 'Refresh', exact: true })).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('alert')).toHaveCount(0);
  await expect(desk).toContainText('Hold collection');
  await desk.getByRole('link', { name: 'Continue reconciliation', exact: true }).click();
  await expect(page.getByText('the email does not identify a document', { exact: true })).toBeVisible();
  expect((await readState(page)).receipts).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test('full payment returns a no-chase decision with the prior draft unusable', async ({ page }, info) => {
  await page.goto('/#/dashboard'); await page.getByRole('link', { name: 'Start reconciliation', exact: true }).click();
  await postEmailAndReadState(page);
  await page.getByRole('link', { name: 'Review changed decision →', exact: true }).click();
  await page.getByRole('button', { name: /Run Strands/ }).click();
  await expect(page.locator('.email > pre')).toContainText('1,860.00 EUR');
  await page.getByText('Try new evidence before approving', { exact: true }).click();
  await page.getByRole('link', { name: 'Add payment evidence →', exact: true }).click();
  const editor = page.getByLabel(/Email headers/);
  await editor.fill((await editor.inputValue()).replace('600.00', '1860.00').replace('DEMO-BANK-600-A', 'DESK-FULL-PAYMENT'));
  await postEmailAndReadState(page);
  await page.goto('/#/dashboard');
  const desk = page.getByRole('region', { name: 'Reconciliation journey' });
  await expect(desk).toContainText('Settled in these books. No chase.');
  await expect(desk).toContainText('0.00 EUR');
  await page.screenshot({ path: info.outputPath('desk-settled-no-chase.png') });
  await desk.getByRole('link', { name: 'Inspect invoice and receipt sources →', exact: true }).click();
  await page.reload();
  await expect(page.getByRole('complementary', { name: 'Previous review invalidated' })).toBeVisible();
  await expect(page.getByRole('button', { name: /Run Strands/ })).toBeDisabled();
  expect((await readState(page)).receipts).toEqual([]);
  await expect(page.getByRole('button', { name: /Approve exact draft/ })).toHaveCount(0);
});

test('unavailable desk never invents zero balances and offers explicit empty-workspace recovery', async ({ page }, info) => {
  await page.goto('/#/dashboard'); await expect(page.getByRole('link', { name: 'Start reconciliation', exact: true })).toBeVisible();
  await page.evaluate(() => localStorage.setItem('archon.demo.session.v1', 'e'.repeat(64)));
  const response = page.waitForResponse(response => new URL(response.url()).pathname === '/api/workspace');
  await page.reload(); expect((await response).status()).toBe(401);
  await expect(page.getByRole('alert')).toContainText('No balance is available');
  await expect(page.getByTestId('metric-outstanding')).toHaveCount(0);
  await page.screenshot({ path: info.outputPath('desk-unavailable-session.png') });
  await keyboardActivate(page, page.getByRole('button', { name: 'New workspace', exact: true }));
  await expect(page.getByRole('region', { name: 'Start a new workspace' })).toContainText('does not delete its stored records');
  await keyboardActivate(page, page.getByRole('button', { name: 'Start new workspace', exact: true }));
  await expect(page.getByRole('link', { name: 'Start reconciliation', exact: true })).toBeVisible();
  expect((await readState(page)).sources).toEqual([]);
});
