import { test, expect, type Page } from '@playwright/test';

test('editable payment refusal correction and semantic duplicate resolution use real HTTP', async ({ page }, info) => {
  await page.goto('/#/documents');
  await page.getByRole('button', { name: 'Try success', exact: true }).click();
  await page.getByRole('button', { name: 'Read & post email', exact: true }).click();
  await expect(page.getByLabel(/Email headers/)).toHaveValue('');
  await page.getByRole('button', { name: 'Try identity refusal', exact: true }).click();
  const original = await page.getByLabel(/Email headers/).inputValue();
  expect(original).not.toContain('Transfer ID:');
  await page.getByRole('button', { name: 'Read & post email', exact: true }).click();
  await expect(page.getByTestId('latest-source-decision')).toContainText('refused');
  await expect(page.getByText(/Payment identity is missing/, { exact: false }).first()).toBeVisible();
  await page.getByRole('button', { name: 'Correct held payment', exact: true }).click();
  await expect(page.getByLabel(/Email headers/)).toHaveValue(original);
  const corrected = original + '\nTransfer ID: TEST-BANK-FLOW-A';
  await page.getByLabel(/Email headers/).fill(corrected);
  await page.getByRole('button', { name: 'Read corrected source', exact: true }).click();
  await expect(page.getByTestId('latest-source-decision')).toContainText('posted');
  await expect(page.getByText('Corrected by email:003; original evidence retained.', { exact: true })).toBeAttached();
  await page.getByLabel(/Email headers/).fill(corrected.replace('Subject: Remittance', 'Subject: Forward of same bank event'));
  await page.getByRole('button', { name: 'Read & post email', exact: true }).click();
  await expect(page.getByTestId('latest-source-decision')).toContainText('refused');
  await page.getByLabel('Original posted receipt').selectOption('email:003');
  await page.getByLabel('Resolution evidence and reason').fill('Reviewed the same supplied bank event against original remittance.');
  await page.getByLabel(/I reviewed this source/).check();
  await page.getByRole('button', { name: 'Record human resolution', exact: true }).click();
  await expect(page.getByTestId('latest-source-decision')).toContainText('resolved');
  await page.getByLabel(/Email headers/).fill(corrected.replace('FLOW-A', 'FLOW-B'));
  await page.getByRole('button', { name: 'Read & post email', exact: true }).click();
  await expect(page.getByTestId('latest-source-decision')).toContainText('posted');
  await go(page, 'Dashboard');
  await expect(page.getByTestId('metric-outstanding')).toContainText('660.00 EUR');
  await expect(page.getByText(/Human active time, time saved and money recovered: Unknown/)).toBeVisible();
  await go(page, 'History');
  await page.route('**/api/evidence', async route => {
    const response = await route.fetch(); expect(response.ok()).toBe(true);
    await route.abort('failed');
  }, { times: 1 });
  await page.getByRole('button', { name: 'Prepare evidence bundle', exact: true }).click();
  await expect(page.getByRole('alert')).toBeVisible();
  await page.getByRole('button', { name: 'Prepare evidence bundle', exact: true }).click();
  await expect(page.getByRole('link', { name: 'Download readable evidence' })).toBeVisible();
  await page.getByText('Inspect evidence and limits', { exact: true }).click();
  await expect(page.locator('.evidence-text')).toContainText('Correction: email:003');
  await expect(page.locator('.evidence-text')).not.toContainText('accounts@buildco.example');
  await expect(page.locator('.evidence-text')).toContainText('not truth');
  await page.screenshot({ path: info.outputPath('reliable-evidence-recovery.png'), fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test('supplier direction and externally resolved dispute retain evidence and require fresh review', async ({ page }, info) => {
  await books(page);
  await page.getByRole('button', { name: 'Sample supplier', exact: true }).click();
  const supplier = (await page.getByLabel(/Email headers/).inputValue()).replace('\nSubject:', '\nTo: me@myjoinery.example\nSubject:') + '\nBilled to: My Joinery';
  await page.getByLabel(/Email headers/).fill('From: me@myjoinery.example\n\n----- Forwarded message -----\n' + supplier);
  await page.getByRole('button', { name: 'Read & post email', exact: true }).click();
  await expect(page.getByTestId('latest-source-decision')).toContainText('posted');
  const session = await page.evaluate(() => localStorage.getItem('archon.demo.session.v1'));
  const headers = { 'X-Archon-Session': session! };
  const state = await (await page.request.get('/api/workspace', { headers })).json();
  expect(state.purchases).toHaveLength(1); expect(state.sales).toHaveLength(1);
  await go(page, 'Workspace'); await page.getByRole('link', { name: 'Payment arrangement', exact: true }).click();
  await page.getByLabel("Client's proposed terms").fill('I dispute this invoice.');
  await page.getByRole('button', { name: 'Read proposed terms', exact: true }).click();
  await expect(page.getByText(/Correct refused sources before proposing terms/)).toBeVisible();
  await go(page, 'Records');
  await page.getByLabel('Resolution evidence and reason').fill('Client and operator reviewed the work and confirmed collection may resume.');
  await page.getByLabel(/I reviewed this source/).check();
  await page.getByRole('button', { name: 'Record human resolution', exact: true }).click();
  await expect(page.locator('.source-list')).toContainText('Human resolution: resume-collection');
  await go(page, 'Workspace'); await page.getByRole('link', { name: 'Draft & signoff', exact: true }).click();
  await expect(page.getByRole('button', { name: /Run Strands/ })).toBeEnabled();
  await page.getByRole('button', { name: /Run Strands/ }).click();
  await expect(page.locator('.email > pre')).toContainText('1,260.00 EUR');
  await expect(page.getByRole('button', { name: /Approve exact draft/ })).toBeDisabled();
  await page.screenshot({ path: info.outputPath('resolved-dispute-fresh-review.png'), fullPage: true });
});


async function go(page: Page, name: string) {
  const legacy = name;
  name = ({ 'Action queue': 'Workspace', 'Approvals & arrangements': 'Workspace', 'Documents & payments': 'Records', 'Activity & delivery': 'History' } as Record<string, string>)[name] ?? name;
  await page.getByRole('navigation', { name: 'Workspace' }).getByRole('link', { name, exact: true }).click();
  await expect(page.getByRole('heading', { name, exact: true })).toBeVisible();
  if (legacy === 'Action queue' || legacy === 'Approvals & arrangements') {
    const tab = page.getByRole('link', { name: 'Draft & signoff', exact: true });
    if (await tab.count()) await tab.click();
  }
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
  await expect(page.getByRole('heading', { name: 'Records', exact: true })).toBeVisible();
  await sample(page, 'invoice'); await sample(page, 'payment');
}
async function draft(page: Page) {
  await books(page);
  await go(page, 'Action queue');
  const completed = page.waitForResponse(response => response.url().endsWith('/api/reason'));
  await page.getByRole('button', { name: /Run Strands/ }).click();
  expect((await completed).status()).toBe(200);
  await expect(page.getByRole('heading', { name: 'Workspace', exact: true })).toBeVisible();
  await expect(page.locator('.email > pre')).toBeVisible();
}

test('raw emails → real HTTP / Strands → exact draft → simulated durable receipt', async ({ page }, info) => {
  const errors: string[] = []; page.on('pageerror', error => errors.push(error.message));
  await draft(page);
  await expect(page.locator('.email')).toContainText('1,260.00 EUR');
  await expect(page.locator('.email')).toContainText('accounts@buildco.example');
  await page.getByText('Six domain reports · inspect', { exact: true }).click();
  await expect(page.locator('.domain-reports details')).toHaveCount(6);
  await expect(page.getByRole('button', { name: /Approve exact draft/ })).toBeDisabled();
  await page.screenshot({ path: info.outputPath('approval.png'), fullPage: true });
  await page.getByLabel(/I reviewed this recipient/).check();
  await page.getByRole('button', { name: /Approve exact draft/ }).click();
  await expect(page.getByRole('heading', { name: 'History', exact: true })).toBeVisible();
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
  await page.getByRole('link', { name: 'Payment arrangement', exact: true }).click();
  await expect(page.getByLabel('Outstanding invoice', { exact: true })).toHaveValue('JN-4410');
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
    request_id: 'parallel-tab-payment-20260909', body: state.samples.payment.replace('600.00', '200.00').replace('08-20', '09-09').replace('DEMO-BANK-600-A', 'TEST-BANK-LATE-200') } });
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
  await expect(page.getByLabel(/I reviewed this recipient/)).not.toBeChecked();
  await expect(page.getByRole('button', { name: /Approve exact draft/ })).toBeDisabled();
  await page.getByLabel(/I reviewed this recipient/).check();
  await page.getByRole('button', { name: /Approve exact draft/ }).click();
  await expect(page.getByRole('heading', { name: 'History', exact: true })).toBeVisible();
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
  await page.getByText('Linked ledger evidence', { exact: true }).click();
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
    await page.getByText('Linked ledger evidence', { exact: true }).click();
  }
  await expect(page.getByRole('button', { name: /Approve exact draft/ })).toBeDisabled();
  await go(page, 'Action queue');
  await go(page, 'Dashboard');
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
  await go(page, 'Dashboard');
  const tile = page.locator('.stat').first();
  await tile.hover();
  expect(await tile.evaluate(element => getComputedStyle(element).transform)).toBe('none');
});

test('Dashboard metrics drill into actual records and selected workspace screenshots', async ({ page }, info) => {
  await books(page); await go(page, 'Dashboard');
  await expect(page.getByTestId('metric-outstanding')).toContainText('1,260.00 EUR');
  await expect(page.getByTestId('metric-overdue')).toContainText('1,260.00 EUR');
  await expect(page.getByTestId('metric-payments')).toContainText('600.00 EUR');
  await expect(page.getByTestId('metric-drafts').locator('strong')).toHaveText('0');
  await expect(page.getByTestId('metric-holds').locator('strong')).toHaveText('0');
  for (const metric of ['outstanding', 'overdue']) {
    await page.getByTestId(`metric-${metric}`).click();
    await expect(page.getByRole('table')).toContainText('JN-4410');
    await expect(page.getByRole('table')).toContainText('1,260.00 EUR');
    await page.reload(); await expect(page.getByRole('table')).toContainText('JN-4410');
    await go(page, 'Dashboard');
  }
  await page.getByTestId('metric-payments').click();
  await expect(page.getByRole('heading', { name: 'Recorded client receipts' })).toBeVisible();
  await expect(page.locator('.hold-list')).toContainText('600.00 EUR');
  await page.getByRole('link', { name: 'Inspect linked case →', exact: true }).click();
  await expect(page.locator('.source-preview pre')).toContainText('We have paid 600.00 EUR');
  await page.getByRole('button', { name: /Run Strands/ }).click();
  await expect(page.locator('.email > pre')).toContainText('1,260.00 EUR');
  await expect(page.getByRole('button', { name: /Approve exact draft/ })).toBeDisabled();
  const workspaceShot = info.outputPath('selected-workspace.png');
  await page.screenshot({ path: workspaceShot, fullPage: true });
  await info.attach('Selected Workspace', { path: workspaceShot, contentType: 'image/png' });
  await go(page, 'Dashboard');
  await expect(page.getByTestId('metric-drafts').locator('strong')).toHaveText('1');
  const dashboardShot = info.outputPath('dashboard.png');
  await page.screenshot({ path: dashboardShot, fullPage: true });
  await info.attach('Dashboard', { path: dashboardShot, contentType: 'image/png' });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test('query typing keeps focus and case context survives navigation, browser back and reload', async ({ page }) => {
  await books(page); await go(page, 'Workspace');
  await page.getByRole('link', { name: /Recorded receipt ·/ }).click();
  const selected = page.url().split('#')[1];
  await go(page, 'Dashboard'); await page.reload(); await go(page, 'Workspace');
  expect(page.url().split('#')[1]).toBe(selected);
  await expect(page.locator('.source-preview pre')).toContainText('600.00 EUR');
  await go(page, 'Records');
  const search = page.getByRole('searchbox', { name: 'Search records' });
  await search.pressSequentially('JN-4410');
  await expect(search).toBeFocused(); await expect(search).toHaveValue('JN-4410');
  expect(page.url()).toContain('q=JN-4410');
  await search.pressSequentially('does-not-exist');
  await expect(page.getByText('No matching sources', { exact: true })).toBeVisible();
  await search.fill('JN-4410');
  await page.reload(); await expect(search).toHaveValue('JN-4410');
  await go(page, 'History'); await page.goBack();
  await expect(search).toHaveValue('JN-4410');
  await go(page, 'Workspace');
  await expect(page.locator('.source-preview pre')).toContainText('600.00 EUR');
  await page.getByRole('link', { name: /Invoice · JN-4410/ }).click();
  await expect(page.locator('.source-preview pre')).toContainText('Net 1500.00 EUR');
  await page.goBack();
  await expect(page.locator('.source-preview pre')).toContainText('600.00 EUR');
});

test('late reasoning response cannot attach a draft to another selected case', async ({ page }) => {
  await books(page);
  await page.getByRole('button', { name: 'Sample invoice', exact: true }).click();
  const raw = page.getByLabel(/Email headers/);
  await raw.fill((await raw.inputValue()).replaceAll('JN-4410', 'JN-4420').replace('due 2026-08-01', 'due 2026-08-08'));
  await page.getByRole('button', { name: 'Read & post email', exact: true }).click();
  await expect(raw).toHaveValue(''); await go(page, 'Workspace');
  await page.getByRole('link', { name: /BuildCo Ltd JN-4420/ }).click();
  await expect(page.getByRole('button', { name: /Run Strands/ })).toBeDisabled();
  await expect(page.getByRole('button', { name: /Approve exact draft/ })).toHaveCount(0);
  await page.getByRole('link', { name: /Open backend priority JN-4410/ }).click();
  let release!: () => void;
  let reached!: () => void;
  const backendDone = new Promise<void>(resolve => { reached = resolve; });
  const gate = new Promise<void>(resolve => { release = resolve; });
  await page.route('**/api/reason', async route => {
    expect(route.request().postDataJSON()).not.toHaveProperty('invoice_id');
    const response = await route.fetch(); expect(response.ok()).toBe(true); reached();
    await gate; await route.fulfill({ response });
  }, { times: 1 });
  await page.getByRole('button', { name: /Run Strands/ }).click(); await backendDone;
  await page.getByRole('link', { name: /BuildCo Ltd JN-4420/ }).click(); release();
  await expect(page.getByText('Draft belongs to another invoice', { exact: true })).toBeVisible();
  expect(page.url()).toContain('invoice=JN-4420');
  await expect(page.getByRole('button', { name: /Approve exact draft/ })).toHaveCount(0);
  await page.reload(); await expect(page.getByText('Draft belongs to another invoice', { exact: true })).toBeVisible();
  await page.getByRole('link', { name: 'Review that exact draft →', exact: true }).click();
  await expect(page.locator('.email > pre')).toContainText('JN-4410');
  await expect(page.getByRole('button', { name: /Approve exact draft/ })).toBeDisabled();
});

test('duplicate intake leaves ledger metrics intact and offline records require explicit refresh', async ({ page, context }) => {
  await books(page);
  await page.getByRole('button', { name: 'Sample payment', exact: true }).click();
  await page.getByRole('button', { name: 'Read & post email', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('already posted');
  await page.getByRole('button', { name: 'Refresh durable state', exact: true }).click();
  await go(page, 'Dashboard');
  await expect(page.getByTestId('metric-payments')).toContainText('600.00 EUR');
  await expect(page.getByTestId('metric-outstanding')).toContainText('1,260.00 EUR');
  await context.setOffline(true);
  await page.getByRole('button', { name: 'Refresh', exact: true }).click();
  await expect(page.getByRole('alert')).toBeVisible();
  await expect(page.getByTestId('metric-outstanding')).toContainText('1,260.00 EUR');
  await expect(page.getByText('Last known snapshot', { exact: true })).toBeVisible();
  await go(page, 'Workspace'); await expect(page.getByRole('button', { name: /Run Strands/ })).toBeDisabled();
  await context.setOffline(false);
  await expect(page.getByRole('button', { name: /Run Strands/ })).toBeDisabled();
  await page.getByRole('button', { name: 'Refresh durable state', exact: true }).click();
  await expect(page.getByRole('button', { name: /Run Strands/ })).toBeEnabled();
});

test('checked consent expires on an open page and no simulated receipt is created', async ({ page }) => {
  await draft(page);
  await page.clock.install({ time: new Date() });
  await page.getByLabel(/I reviewed this recipient/).check();
  await expect(page.getByRole('button', { name: /Approve exact draft/ })).toBeEnabled();
  await page.clock.fastForward(1800001);
  await page.evaluate(() => window.dispatchEvent(new Event('focus')));
  await expect(page.getByRole('button', { name: /Approve exact draft/ })).toBeDisabled();
  await expect(page.getByLabel(/I reviewed this recipient/)).not.toBeChecked();
  await expect(page.getByText(/This draft expired/)).toBeVisible();
  await go(page, 'Dashboard');
  await expect(page.getByTestId('metric-drafts').locator('strong')).toHaveText('0');
  await go(page, 'History'); await expect(page.getByText('No delivery attempts', { exact: true })).toBeVisible();
});
