import { test, expect, type Page } from '@playwright/test';

async function go(page: Page, name: string) {
  await page.getByRole('navigation', { name: 'Workspace' }).getByRole('link', { name, exact: true }).click();
  await expect(page.getByRole('heading', { name, exact: true })).toBeVisible();
}
async function sample(page: Page, name: string) {
  await page.getByRole('button', { name: `Sample ${name}`, exact: true }).click();
  const response = page.waitForResponse(r => r.url().endsWith('/api/intake'));
  await page.getByRole('button', { name: 'Read & post email', exact: true }).click();
  expect((await response).status()).toBe(200);
  await expect(page.getByLabel(/Email headers/)).toHaveValue('');
}
async function books(page: Page) {
  await page.goto('/#/documents');
  await expect(page.getByRole('heading', { name: 'Documents & payments', exact: true })).toBeVisible();
  await sample(page, 'invoice'); await sample(page, 'payment');
}
async function draft(page: Page) {
  await books(page);
  await go(page, 'Action queue');
  await page.getByRole('button', { name: /Run Strands/ }).click();
  await expect(page.getByRole('heading', { name: 'Approvals & arrangements', exact: true })).toBeVisible();
}

test('raw emails → real HTTP / Strands → exact draft → simulated durable receipt', async ({ page }, info) => {
  const errors: string[] = []; page.on('pageerror', error => errors.push(error.message));
  await draft(page);
  await expect(page.locator('.email')).toContainText('1,260.00 EUR');
  await expect(page.locator('.email')).toContainText('accounts@buildco.example');
  await expect(page.locator('.domain-reports details')).toHaveCount(6);
  await expect(page.getByRole('button', { name: /Approve exact draft/ })).toBeDisabled();
  await page.screenshot({ path: info.outputPath('approval.png'), fullPage: true });
  await page.getByLabel(/I reviewed this recipient/).check();
  await page.getByRole('button', { name: /Approve exact draft/ }).click();
  await expect(page.getByRole('heading', { name: 'Activity & delivery', exact: true })).toBeVisible();
  await expect(page.locator('.receipt-list')).toContainText('Simulated · provider-accepted');
  const id = await page.locator('.receipt-list dd').first().textContent();
  await page.reload();
  await expect(page.locator('.receipt-list dd').first()).toHaveText(id!);
  await expect(page.locator('.receipt-list')).toContainText('Unproven · no real email sent');
  await page.screenshot({ path: info.outputPath('receipt.png'), fullPage: true });
  expect(await page.evaluate(() => Object.keys(localStorage))).toEqual(['archon.demo.session.v1']);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect(errors).toEqual([]);
});

test('arrangement approval holds collections across reload without reducing the debt', async ({ page }, info) => {
  await books(page); await go(page, 'Approvals & arrangements');
  await page.getByLabel('Outstanding invoice', { exact: true }).selectOption('JN-4410');
  await page.getByLabel("Client's proposed terms").fill('2026-09-20: 600.00 EUR\n2026-10-05: 660.00 EUR');
  await page.getByRole('button', { name: 'Read proposed terms', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Approve arrangement', exact: true })).toBeDisabled();
  await page.getByLabel(/I approve these exact/).check();
  await page.getByRole('button', { name: 'Approve arrangement', exact: true }).click();
  await expect(page.getByText('Agreed arrangements', { exact: true })).toBeVisible();
  await page.reload(); await go(page, 'Action queue');
  await expect(page.locator('.hold-list')).toContainText('a payment plan is being kept');
  await expect(page.locator('.hold-list')).toContainText('1,260.00 EUR');
  await expect(page.getByRole('button', { name: /Run Strands/ })).toBeDisabled();
  await page.screenshot({ path: info.outputPath('arrangement-hold.png'), fullPage: true });
});

test('refused raw evidence holds collections and a corrected source releases them', async ({ page }, info) => {
  await books(page); await sample(page, 'refusal');
  await expect(page.getByText('the email does not identify a document', { exact: true })).toBeVisible();
  await go(page, 'Action queue');
  await expect(page.getByRole('button', { name: /Run Strands/ })).toBeDisabled();
  await page.screenshot({ path: info.outputPath('incomplete-evidence.png'), fullPage: true });
  await go(page, 'Documents & payments');
  await page.getByRole('button', { name: 'Correct source', exact: true }).click();
  await page.getByRole('button', { name: 'Sample supplier', exact: true }).click();
  await page.getByRole('button', { name: 'Read corrected source', exact: true }).click();
  await expect(page.getByText('Corrected by email:004; original evidence retained.', { exact: true })).toBeAttached();
  await go(page, 'Action queue');
  await expect(page.getByRole('button', { name: /Run Strands/ })).toBeEnabled();
});

test('stale approval after another tab posts payment is refused by actual API', async ({ page }) => {
  await draft(page);
  const session = await page.evaluate(() => localStorage.getItem('archon.demo.session.v1'));
  const headers = { 'X-Archon-Session': session! };
  const state = await (await page.request.get('/api/workspace', { headers })).json();
  const paid = await page.request.post('/api/intake', { headers, data: { revision: state.revision,
    request_id: 'parallel-tab-payment-20260909', body: state.samples.payment.replace('600.00', '200.00').replace('08-20', '09-09') } });
  expect(paid.ok()).toBe(true);
  await page.getByLabel(/I reviewed this recipient/).check();
  await page.getByRole('button', { name: /Approve exact draft/ }).click();
  await expect(page.getByRole('alert')).toContainText('Books changed in another tab');
  expect((await (await page.request.get('/api/workspace', { headers })).json()).receipts).toEqual([]);
  await page.getByRole('button', { name: 'Refresh durable state', exact: true }).click();
  await expect(page.getByText('No draft awaiting approval', { exact: true })).toBeVisible();
});

test('lost approval response reconciles to one durable receipt without resending', async ({ page }) => {
  await draft(page);
  await page.route('**/api/approve', async route => {
    const realResponse = await route.fetch(); expect(realResponse.ok()).toBe(true);
    await route.abort('failed');
  }, { times: 1 });
  await page.getByLabel(/I reviewed this recipient/).check();
  await page.getByRole('button', { name: /Approve exact draft/ }).click();
  await expect(page.getByRole('alert')).toBeVisible();
  await page.getByRole('button', { name: 'Refresh durable state', exact: true }).click();
  await expect(page.getByText(/already has a receipt/)).toBeVisible();
  await expect(page.getByRole('button', { name: /Approve exact draft/ })).toBeDisabled();
  await go(page, 'Activity & delivery');
  await expect(page.locator('.receipt-list article')).toHaveCount(1);
});

test('independent visitors, deep links, keyboard skip, and new workspace', async ({ page, browser }) => {
  await books(page);
  const other = await browser.newContext(); const visitor = await other.newPage();
  await visitor.goto('http://127.0.0.1:4173/#/queue');
  await expect(visitor.getByText('Nothing to chase yet', { exact: true })).toBeVisible();
  await other.close();
  await page.goto('/#/documents?source=JN-4410');
  await expect(page.locator('.source-list details').first()).toHaveAttribute('open', '');
  await page.getByText('Skip to workspace', { exact: true }).focus();
  await page.keyboard.press('Enter');
  await expect(page.locator('main')).toBeFocused();
  await page.getByRole('button', { name: 'New workspace', exact: true }).click();
  await page.getByRole('button', { name: 'Start new workspace', exact: true }).click();
  await expect(page.getByText('No matching sources', { exact: true })).toBeVisible();
});
