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

test('approval lost before reaching the API retries the same intent after durable refresh', async ({ page }) => {
  await draft(page);
  const attempts: { request_id: string }[] = [];
  await page.route('**/api/approve', async route => {
    attempts.push(route.request().postDataJSON());
    if (attempts.length === 1) await route.abort('failed');
    else await route.continue();
  });
  await page.getByLabel(/I reviewed this recipient/).check();
  await page.getByRole('button', { name: /Approve exact draft/ }).click();
  await expect(page.getByRole('alert')).toBeVisible();
  await page.getByRole('button', { name: 'Refresh durable state', exact: true }).click();
  await expect(page.getByRole('alert')).toHaveCount(0);
  await page.getByRole('button', { name: /Approve exact draft/ }).click();
  await expect(page.getByRole('heading', { name: 'Activity & delivery', exact: true })).toBeVisible();
  expect(attempts).toHaveLength(2);
  expect(attempts[1].request_id).toBe(attempts[0].request_id);
  await page.reload();
  await expect(page.locator('.receipt-list article')).toHaveCount(1);
});

test('unavailable session recovers by explicitly creating a new workspace', async ({ page }) => {
  await books(page);
  await page.evaluate(() => localStorage.setItem('archon.demo.session.v1', 'f'.repeat(64)));
  const unavailable = page.waitForResponse(response => response.url().endsWith('/api/workspace'));
  await page.reload();
  expect((await unavailable).status()).toBe(401);
  await expect(page.getByRole('alert')).toContainText(/Session (?:not found|unavailable or expired)/);
  await page.getByRole('button', { name: 'New workspace', exact: true }).click();
  await page.getByRole('button', { name: 'Start new workspace', exact: true }).click();
  await expect(page.getByText('No matching sources', { exact: true })).toBeVisible();
  expect(await page.evaluate(() => localStorage.getItem('archon.demo.session.v1'))).not.toBe('f'.repeat(64));
});

test('independent visitors, deep links, keyboard skip, and new workspace', async ({ page, browser }, testInfo) => {
  await books(page);
  const other = await browser.newContext(); const visitor = await other.newPage();
  await visitor.goto(new URL('/#/queue', testInfo.project.use.baseURL).href);
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

test('draft ledger badges open actual invoice and receipt sources without approving', async ({ page }, info) => {
  await draft(page);
  const session = await page.evaluate(() => localStorage.getItem('archon.demo.session.v1'));
  const state = await (await page.request.get('/api/workspace', { headers: { 'X-Archon-Session': session! } })).json();
  const evidence = page.getByRole('region', { name: 'Draft ledger evidence' });
  await expect(evidence.getByText('1,260.00 EUR', { exact: true })).toBeVisible();
  await expect(evidence.getByText(/not independent bank verification/)).toBeVisible();
  expect(await evidence.locator(':scope > p').first().evaluate(element => parseFloat(getComputedStyle(element).fontSize))).toBeGreaterThanOrEqual(16);
  expect(await evidence.getByRole('heading', { name: 'Sourced · posted invoice' }).evaluate(element => parseFloat(getComputedStyle(element).fontSize))).toBeGreaterThanOrEqual(14);
  expect(await evidence.getByRole('link', { name: /Invoice source/ }).evaluate(element => parseFloat(getComputedStyle(element).fontSize))).toBeGreaterThanOrEqual(14);
  expect(await evidence.locator('.source-badge small').first().evaluate(element => parseFloat(getComputedStyle(element).fontSize))).toBeGreaterThanOrEqual(12);
  await expect(page.locator('.email > pre')).toHaveText(state.draft.body);
  await expect(page.getByRole('button', { name: /Approve exact draft/ })).toBeDisabled();
  await page.screenshot({ path: info.outputPath('source-backed-approval.png'), fullPage: true });
  for (const [label, source] of [['Invoice source', state.sources[0]], ['Receipt source', state.sources[1]]] as const) {
    const link = evidence.getByRole('link', { name: new RegExp(label) });
    await expect(link).toHaveAttribute('href', `#/documents?source=${encodeURIComponent(source.id)}`);
    await link.click();
    const opened = page.locator(`[data-source-id="${source.id}"]`);
    await expect(opened).toHaveAttribute('open', '');
    await expect(opened.locator('pre')).toHaveText(source.body);
    await page.reload();
    await expect(opened).toHaveAttribute('open', '');
    await go(page, 'Approvals & arrangements');
  }
  await expect(page.getByRole('button', { name: /Approve exact draft/ })).toBeDisabled();
  await go(page, 'Action queue');
  await expect(page.getByRole('region', { name: 'Ledger balances' })).toContainText('1,260.00 EUR');
  expect(await page.locator('.stat p').first().evaluate(element => parseFloat(getComputedStyle(element).fontSize))).toBeGreaterThanOrEqual(14);
  expect(await page.getByRole('navigation').getByRole('link').first().evaluate(element => parseFloat(getComputedStyle(element).fontSize))).toBeGreaterThanOrEqual(14);
  await page.screenshot({ path: info.outputPath('precision-ledger-kpis.png'), fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test('sample sliding pill preserves keyboard selection and reduced-motion preferences', async ({ page }, info) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/#/documents');
  const group = page.getByRole('group', { name: 'Load a synthetic sample' });
  await expect(group.getByRole('button', { pressed: false })).toHaveCount(4);
  expect(await group.getByRole('button').first().evaluate(element => parseFloat(getComputedStyle(element).fontSize))).toBeGreaterThanOrEqual(14);
  if (page.viewportSize()!.width <= 600) {
    const boxes = await group.getByRole('button').evaluateAll(elements => elements.map(element => ({ x: element.getBoundingClientRect().x, y: element.getBoundingClientRect().y })));
    expect(boxes[0].y).toBe(boxes[1].y);
    expect(boxes[2].y).toBeGreaterThan(boxes[0].y);
    expect(boxes[2].x).toBe(boxes[0].x);
  }
  await group.getByRole('button', { name: 'Sample invoice', exact: true }).focus();
  await page.keyboard.press('Enter');
  await expect(group.getByRole('button', { pressed: true })).toHaveText('Sample invoice');
  await page.keyboard.press('Tab');
  await expect(group.getByRole('button', { name: 'Sample payment', exact: true })).toBeFocused();
  await page.keyboard.press('Space');
  await expect(group.getByRole('button', { pressed: true })).toHaveText('Sample payment');
  expect(await group.evaluate(element => getComputedStyle(element, '::before').transitionDuration)).toBe('0s');
  await page.screenshot({ path: info.outputPath('selected-sample-pill.png'), fullPage: true });
  await page.getByLabel(/Email headers/).fill('custom synthetic text');
  await expect(group.getByRole('button', { pressed: true })).toHaveCount(0);
  await go(page, 'Action queue');
  await expect(page.getByText('Nothing to chase yet', { exact: true })).toBeVisible();
  const tile = page.locator('.stat').first();
  await tile.hover();
  expect(await tile.evaluate(element => getComputedStyle(element).transform)).toBe('none');
});
