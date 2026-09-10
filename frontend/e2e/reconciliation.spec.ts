import { test, expect, type Page } from '@playwright/test';

async function state(page: Page) {
  const session = await page.evaluate(() => localStorage.getItem('archon.demo.session.v1'));
  const headers = { 'X-Archon-Session': session! };
  const response = await page.request.get('/api/workspace', { headers });
  expect(response.ok()).toBe(true);
  return { headers, data: await response.json() };
}
async function post(page: Page) {
  const response = page.waitForResponse(r => r.url().endsWith('/api/intake'));
  await page.getByRole('button', { name: 'Read & post email', exact: true }).click();
  expect((await response).status()).toBe(200);
  await expect(page.getByLabel(/Email headers/)).toHaveValue('');
}
async function workspace(page: Page) {
  await page.getByRole('navigation', { name: 'Workspace' }).getByRole('link', { name: 'Workspace', exact: true }).click();
  await expect(page.getByTestId('reconciliation-decision')).toBeVisible();
}

test('central journey withdraws the old draft after payment and exports the fresh reviewed outcome', async ({ page, context }, info) => {
  if (info.project.name === 'mobile') await page.setViewportSize({ width: 375, height: 812 });
  const errors: string[] = []; page.on('pageerror', error => errors.push(error.message));
  await page.goto('/');
  const start = page.getByRole('link', { name: 'Start reconciliation', exact: true });
  await expect(start).toBeVisible();
  expect((await start.boundingBox())!.height).toBeGreaterThanOrEqual(44);
  await page.screenshot({ path: info.outputPath('reconciliation-start.png') });
  await start.click();
  await expect(page.getByLabel(/Email headers/)).toHaveValue(/Invoice JN-4410/);
  await post(page);
  await page.getByRole('link', { name: 'Review changed decision →', exact: true }).click();
  await page.getByRole('button', { name: /Run Strands/ }).click();
  await expect(page.locator('.email > pre')).toContainText('1,860.00 EUR');
  await page.getByLabel(/I reviewed this recipient/).check();
  const old = await state(page);
  await page.getByText('Try new evidence before approving', { exact: true }).click();
  await page.getByRole('link', { name: 'Add payment evidence →', exact: true }).click();
  await expect(page.getByLabel(/Email headers/)).toHaveValue(/Transfer ID: DEMO-BANK-600-A/);
  await post(page);
  await page.getByRole('link', { name: 'Review changed decision →', exact: true }).click();
  await expect(page.getByTestId('reconciliation-decision')).toContainText('Payment evidence changed the decision');
  await expect(page.getByTestId('payment-change')).toContainText('1,860.00 EUR');
  await expect(page.getByTestId('payment-change')).toContainText('1,260.00 EUR');
  await expect(page.locator('.email > pre')).toHaveCount(0);
  const changed = await state(page);
  expect(changed.data.draft).toBeNull(); expect(changed.data.receipts).toEqual([]);
  const stale = await page.request.post('/api/approve', { headers: changed.headers, data: {
    revision: changed.data.revision, request_id: 'reject-obsolete-payment-draft', fingerprint: old.data.draft.fingerprint,
  } });
  expect(stale.status()).toBe(409);
  await page.screenshot({ path: info.outputPath('reconciliation-payment-change.png'), fullPage: true });
  await page.getByRole('link', { name: 'Prepare current draft below', exact: true }).click();
  await expect(page.locator('#prepare-current-draft')).toBeFocused();
  await page.getByRole('button', { name: /Run Strands/ }).click();
  await expect(page.locator('.email > pre')).toContainText('1,260.00 EUR');
  await expect(page.getByLabel(/I reviewed this recipient/)).not.toBeChecked();
  const fresh = await state(page); expect(fresh.data.draft.fingerprint).not.toBe(old.data.draft.fingerprint);
  await page.getByLabel(/I reviewed this recipient/).check();
  await page.getByRole('button', { name: /Approve exact draft/ }).click();
  await expect(page.locator('.receipt-list')).toContainText('Simulated · provider-accepted');
  await workspace(page);
  await page.getByRole('button', { name: 'Prepare evidence bundle', exact: true }).click();
  await page.getByText('Inspect evidence and limits', { exact: true }).click();
  const evidence = await page.locator('.evidence-text').innerText();
  expect(evidence).toContain(fresh.data.draft.fingerprint);
  expect(evidence).toContain('email:002'); expect(evidence).not.toContain('accounts@buildco.example');
  await context.grantPermissions(['clipboard-read', 'clipboard-write']);
  await page.getByRole('button', { name: 'Copy readable evidence', exact: true }).click();
  await expect(page.getByText(/Copied evidence from revision/)).toBeVisible();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(evidence);
  const downloadEvent = page.waitForEvent('download');
  await page.getByRole('link', { name: 'Download readable evidence' }).click();
  const download = await downloadEvent;
  const stream = await download.createReadStream(); const chunks: Buffer[] = [];
  for await (const chunk of stream!) chunks.push(Buffer.from(chunk));
  expect(Buffer.concat(chunks).toString('utf8')).toBe(evidence);
  await page.reload();
  expect((await state(page)).data.receipts).toHaveLength(1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect(errors).toEqual([]);
});

test('plain text file preview leads to duplicate abstention and retained human resolution', async ({ page }, info) => {
  if (info.project.name === 'mobile') await page.setViewportSize({ width: 375, height: 812 });
  await page.goto('/#/records?intake=open');
  await expect(page.getByLabel(/Email headers/)).toBeVisible();
  const initial = await state(page);
  let posts = 0; page.on('request', request => { if (request.url().endsWith('/api/intake')) posts++; });
  await page.getByText('Open a text email file', { exact: true }).click();
  const file = page.getByLabel('Choose text email');
  await file.setInputFiles({ name: 'invoice.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF') });
  await expect(page.getByRole('alert')).toContainText('not supported');
  await file.setInputFiles({ name: 'encoded.eml', mimeType: 'message/rfc822', buffer: Buffer.from('Content-Type: multipart/mixed; boundary=example\n\nEncoded attachment') });
  await expect(page.getByRole('alert')).toContainText('multipart email is not supported');
  expect(posts).toBe(0);
  for (const name of ['invoice', 'payment']) {
    await file.setInputFiles({ name: `${name}.eml`, mimeType: 'message/rfc822', buffer: Buffer.from(initial.data.samples[name]) });
    await expect(page.getByRole('region', { name: 'File preview' })).toContainText(initial.data.samples[name]);
    await expect(page.getByLabel(/Email headers/)).toHaveValue('');
    await page.getByRole('button', { name: 'Use file text in editor', exact: true }).click();
    await expect(page.getByLabel(/Email headers/)).toHaveValue(initial.data.samples[name]);
    await post(page);
  }
  expect(posts).toBe(2);
  await workspace(page);
  await page.getByRole('button', { name: /Run Strands/ }).click();
  await expect(page.getByLabel(/I reviewed this recipient/)).toBeVisible();
  await page.getByText('Try new evidence before approving', { exact: true }).click();
  await page.getByRole('link', { name: 'Check a forwarded duplicate →', exact: true }).click();
  await expect(page.getByLabel(/Email headers/)).toHaveValue(initial.data.samples.payment + '\nForwarded for reference.');
  await post(page);
  await page.getByRole('link', { name: 'Review changed decision →', exact: true }).click();
  await expect(page.getByTestId('reconciliation-decision')).toContainText('Hold collection. Resolve the evidence.');
  await expect(page.getByRole('button', { name: /Run Strands/ })).toBeDisabled();
  expect((await state(page)).data.sales[0].settled).toBe('600.00');
  await page.screenshot({ path: info.outputPath('reconciliation-duplicate-abstention.png'), fullPage: true });
  await page.getByRole('link', { name: 'Resolve source evidence', exact: true }).click();
  await page.getByLabel('Original posted receipt').selectOption('email:002');
  await page.getByLabel('Resolution evidence and reason').fill('Compared the retained remittance and identical supplied transfer reference.');
  await page.getByLabel(/I reviewed this source/).check();
  await page.getByRole('button', { name: 'Record human resolution', exact: true }).click();
  await workspace(page); await page.reload();
  const resolved = await state(page);
  expect(resolved.data.sales[0].outstanding).toBe('1260.00'); expect(resolved.data.draft).toBeNull();
  expect(resolved.data.sources[2].resolution.duplicate_of).toBe('email:002');
  expect(resolved.data.sources[1].body).toBe(initial.data.samples.payment); expect(resolved.data.receipts).toEqual([]);
  await expect(page.getByRole('button', { name: /Run Strands/ })).toBeEnabled();
  await page.getByRole('button', { name: 'Prepare evidence bundle', exact: true }).click();
  await page.getByText('Inspect evidence and limits', { exact: true }).click();
  await expect(page.locator('.evidence-text')).toContainText('duplicate-payment');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
