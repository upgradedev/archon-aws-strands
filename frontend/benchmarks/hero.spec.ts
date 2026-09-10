import { test, expect, type Page } from '@playwright/test';
import type { Workspace } from '../src/types';
import { plan } from './model';
import { Recorder } from './recorder';

async function state(page: Page, recorder: Recorder) {
  const session = await page.evaluate(() => localStorage.getItem('archon.demo.session.v1'));
  expect(session).toBeTruthy();
  const headers = { 'X-Archon-Session': session! };
  const response = await recorder.diagnostic('/api/workspace', 'GET', undefined, headers);
  expect(response.status).toBe(200);
  return { headers, data: response.value as Workspace };
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
async function artifact(page: Page, recorder: Recorder, expected: string, copy: boolean) {
  await page.getByRole('button', { name: 'Prepare evidence bundle', exact: true }).click();
  await page.getByText('Inspect evidence and limits', { exact: true }).click();
  const evidence = await page.locator('.evidence-text').innerText();
  expect(evidence).toContain(expected); expect(evidence).toContain('email:002');
  expect(evidence).not.toContain('accounts@buildco.example');
  if (copy) {
    await page.getByRole('button', { name: 'Copy readable evidence', exact: true }).click();
    await expect(page.getByText(/Copied evidence from revision/)).toBeVisible();
    expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(evidence);
  }
  const event = page.waitForEvent('download');
  await page.getByRole('link', { name: 'Download readable evidence' }).click();
  const download = await event;
  const stream = await download.createReadStream(); expect(stream).not.toBeNull();
  const chunks: Buffer[] = [];
  for await (const chunk of stream!) chunks.push(Buffer.from(chunk));
  const bytes = Buffer.concat(chunks);
  expect(bytes.equals(Buffer.from(evidence, 'utf8'))).toBe(true);
  recorder.finish(bytes, copy);
}
async function newPayment(page: Page, recorder: Recorder) {
  await page.goto('/');
  const start = page.getByRole('link', { name: 'Start reconciliation', exact: true });
  await expect(start).toBeVisible();
  const initial = await state(page, recorder);
  expect(initial.data.sources).toEqual([]); expect(initial.data.receipts).toEqual([]);
  recorder.begin(); await start.click();
  await expect(page.getByLabel(/Email headers/)).toHaveValue(/Invoice JN-4410/);
  await post(page);
  await page.getByRole('link', { name: 'Review changed decision →', exact: true }).click();
  await page.getByRole('button', { name: /Run Strands/ }).click();
  await expect(page.locator('.email > pre')).toContainText('1,860.00 EUR');
  await page.getByLabel(/I reviewed this recipient/).check();
  const old = await state(page, recorder);
  await page.getByText('Try new evidence before approving', { exact: true }).click();
  await page.getByRole('link', { name: 'Add payment evidence →', exact: true }).click();
  await expect(page.getByLabel(/Email headers/)).toHaveValue(/Transfer ID: DEMO-BANK-600-A/);
  await post(page);
  await page.getByRole('link', { name: 'Review changed decision →', exact: true }).click();
  await expect(page.getByTestId('reconciliation-decision')).toContainText('Payment evidence changed the decision');
  await expect(page.getByTestId('payment-change')).toContainText('1,860.00 EUR');
  await expect(page.getByTestId('payment-change')).toContainText('1,260.00 EUR');
  await expect(page.locator('.email > pre')).toHaveCount(0);
  const changed = await state(page, recorder);
  expect(changed.data.draft).toBeNull(); expect(changed.data.receipts).toEqual([]);
  expect((await recorder.diagnostic('/api/approve', 'POST', { revision: changed.data.revision,
    request_id: `x1-stale-${recorder.slot.id}`, fingerprint: old.data.draft!.fingerprint }, changed.headers)).status).toBe(409);
  await page.getByRole('link', { name: 'Prepare current draft below', exact: true }).click();
  await expect(page.locator('#prepare-current-draft')).toBeFocused();
  await page.getByRole('button', { name: /Run Strands/ }).click();
  await expect(page.locator('.email > pre')).toContainText('1,260.00 EUR');
  await expect(page.getByLabel(/I reviewed this recipient/)).not.toBeChecked();
  const fresh = await state(page, recorder);
  expect(fresh.data.draft!.fingerprint).not.toBe(old.data.draft!.fingerprint);
  await page.getByLabel(/I reviewed this recipient/).check();
  await page.getByRole('button', { name: /Approve exact draft/ }).click();
  await expect(page.locator('.receipt-list')).toContainText('Simulated · provider-accepted');
  expect((await state(page, recorder)).data.receipts).toHaveLength(1);
  await workspace(page);
  await artifact(page, recorder, fresh.data.draft!.fingerprint, true);
}
async function duplicate(page: Page, recorder: Recorder) {
  await page.goto('/#/records?intake=open');
  await expect(page.getByLabel(/Email headers/)).toBeVisible();
  const initial = await state(page, recorder);
  expect(initial.data.sources).toEqual([]); expect(initial.data.receipts).toEqual([]);
  await page.getByText('Open a text email file', { exact: true }).click();
  const file = page.getByLabel('Choose text email');
  recorder.begin();
  for (const name of ['invoice', 'payment'] as const) {
    await file.setInputFiles({ name: `${name}.eml`, mimeType: 'message/rfc822', buffer: Buffer.from(initial.data.samples[name]) });
    await expect(page.getByRole('region', { name: 'File preview' })).toContainText(initial.data.samples[name]);
    await expect(page.getByLabel(/Email headers/)).toHaveValue('');
    await page.getByRole('button', { name: 'Use file text in editor', exact: true }).click();
    await expect(page.getByLabel(/Email headers/)).toHaveValue(initial.data.samples[name]);
    await post(page);
  }
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
  const held = await state(page, recorder);
  expect(held.data.sales[0].settled).toBe('600.00'); expect(held.data.draft).toBeNull(); expect(held.data.receipts).toEqual([]);
  await page.getByRole('link', { name: 'Resolve source evidence', exact: true }).click();
  await page.getByLabel('Original posted receipt').selectOption('email:002');
  await page.getByLabel('Resolution evidence and reason').fill('Compared the retained remittance and identical supplied transfer reference.');
  await page.getByLabel(/I reviewed this source/).check();
  await page.getByRole('button', { name: 'Record human resolution', exact: true }).click();
  await workspace(page); await page.reload();
  const resolved = await state(page, recorder);
  expect(resolved.data.sales[0].outstanding).toBe('1260.00'); expect(resolved.data.draft).toBeNull();
  expect(resolved.data.sources[2].resolution?.duplicate_of).toBe('email:002');
  expect(resolved.data.sources[1].body).toBe(initial.data.samples.payment); expect(resolved.data.receipts).toEqual([]);
  await expect(page.getByRole('button', { name: /Run Strands/ })).toBeEnabled();
  await artifact(page, recorder, 'duplicate-payment', false);
}
for (const slot of plan()) {
  test(slot.id, async ({ page, context, browser }, info) => {
    const recorder = new Recorder(slot.id, page, info.workerIndex);
    try {
      await recorder.verifyRuntime(browser.version());
      await context.grantPermissions(['clipboard-read', 'clipboard-write']);
      if (slot.branch === 'new-payment') await newPayment(page, recorder);
      else await duplicate(page, recorder);
    } finally { await recorder.close(); }
  });
}
