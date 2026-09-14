import { test, expect, type Page } from '@playwright/test';
import type { Workspace } from '../src/types';

async function state(page: Page) {
  const session = await page.evaluate(() => localStorage.getItem('archon.demo.session.v1'));
  expect(session).toBeTruthy();
  const response = await page.request.get('/api/workspace', { headers: { 'X-Archon-Session': session! } });
  expect(response.status()).toBe(200);
  return { session, data: await response.json() as Workspace };
}
function eur(value: string) {
  const [whole, fraction = '00'] = value.split('.');
  return `${whole.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}.${fraction.padEnd(2, '0')} EUR`;
}
function cash(data: Workspace, kind: 'Receipt' | 'Payment') {
  const total = data.sources.filter(s => s.status === 'posted' && s.kind === kind).reduce((sum, s) => {
    const value = s.document!.amount!;
    expect(value).toMatch(/^\d+\.\d{2}$/);
    const [whole, fraction] = value.split('.');
    return sum + BigInt(whole) * 100n + BigInt(fraction);
  }, 0n);
  return eur(`${total / 100n}.${String(total % 100n).padStart(2, '0')}`);
}

test('business portfolio preserves previous books with zero AI or send requests and six paged views', async ({ page }, info) => {
  await page.goto('/#/demo');
  await page.getByRole('button', { name: 'Load demo workspace' }).click();
  await expect(page.getByRole('heading', { name: 'Dashboard', exact: true })).toBeVisible();
  const previous = await state(page);
  expect(previous.data.sources).toHaveLength(5);
  const posts: string[] = [];
  page.on('request', req => { if (req.method() === 'POST') posts.push(new URL(req.url()).pathname); });
  await page.goto('/#/demo');
  await expect(page.getByText(/240 records, six types/)).toBeVisible();
  await page.getByRole('button', { name: 'Load business portfolio' }).click();
  await expect(page.getByRole('heading', { name: 'Dashboard', exact: true })).toBeVisible();
  const seeded = await state(page);
  expect(seeded.session).not.toBe(previous.session);
  expect(seeded.data.demo_seed).toBe('business-v1');
  expect(seeded.data.sources).toHaveLength(240);
  expect(seeded.data.graph).toBeNull(); expect(seeded.data.draft).toBeNull();
  expect(seeded.data.receipts).toEqual([]); expect(seeded.data.live?.job ?? null).toBeNull();
  expect(seeded.data.sources.every(s => s.origin === 'fictional-business-fixture')).toBe(true);
  await expect(page.getByTestId('business-cash-in')).toContainText(cash(seeded.data, 'Receipt'));
  await expect(page.getByTestId('business-cash-out')).toContainText(cash(seeded.data, 'Payment'));
  await expect(page.getByRole('region', { name: 'Populated fictional demo' })).toContainText('not AI-extracted');
  await page.screenshot({ path: info.outputPath('business-dashboard.png'), fullPage: true });
  for (const [view, label, kind, count] of [
    ['sales-invoices', 'Sales invoices', 'SalesInvoice', 80], ['purchase-invoices', 'Purchase invoices', 'PurchaseInvoice', 50],
    ['sales-credits', 'Sales credits', 'SalesCreditNote', 20], ['purchase-credits', 'Purchase credits', 'PurchaseCreditNote', 10],
    ['client-receipts', 'Client receipts', 'Receipt', 50], ['supplier-payments', 'Supplier payments', 'Payment', 30],
  ] as const) {
    expect(seeded.data.sources.filter(s => s.kind === kind)).toHaveLength(count);
    await page.goto(`/#/records?view=${view}`);
    await expect(page.getByRole('table', { name: label, exact: true })).toBeVisible();
    await expect(page.locator('tbody tr')).toHaveCount(Math.min(count, 25));
    if (count > 25) {
      const firstPage = await page.locator('tbody tr').first().getAttribute('data-record-id');
      await page.getByRole('button', { name: 'Next page' }).click();
      await expect(page.locator('tbody tr')).toHaveCount(Math.min(count - 25, 25));
      expect(await page.locator('tbody tr').first().getAttribute('data-record-id')).not.toBe(firstPage);
      await page.reload();
      await expect(page.getByRole('navigation', { name: 'Record pages' })).toContainText('Page 2');
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
  await page.getByRole('button', { name: 'Return to previous workspace' }).click();
  await expect(page.getByRole('heading', { name: 'Dashboard', exact: true })).toBeVisible();
  expect((await state(page))).toEqual(previous);
  expect(posts).toEqual(['/api/sessions']);
});

test('business credits retain source origin and invoice links while filters and cash drilldowns survive reload', async ({ page }, info) => {
  await page.goto('/#/demo');
  const posts: string[] = [];
  page.on('request', req => { if (req.method() === 'POST') posts.push(new URL(req.url()).pathname); });
  await page.getByRole('button', { name: 'Load business portfolio' }).click();
  await expect(page.getByRole('heading', { name: 'Dashboard', exact: true })).toBeVisible();
  const snapshot = await state(page);
  const credit = snapshot.data.sources.find(s => s.kind === 'SalesCreditNote')!;
  const invoice = credit.document!.settles!;
  const balance = snapshot.data.sales.find(s => s.doc_id === invoice)!;
  await page.getByTestId('business-sales-credits').click();
  const search = page.getByRole('searchbox', { name: 'Search records' });
  await search.pressSequentially(credit.document!.doc_id);
  await expect(search).toBeFocused();
  await expect(page.locator('tbody tr')).toHaveCount(1);
  await page.reload(); await expect(search).toHaveValue(credit.document!.doc_id);
  await expect(page.getByLabel('To date')).toHaveValue('2026-09-09');
  await page.getByRole('link', { name: credit.document!.doc_id, exact: true }).click();
  const source = page.locator(`[data-source-id="${credit.id}"]`);
  await expect(source).toHaveAttribute('open', '');
  await expect(source).toContainText('Typed JSON fixture retained as source');
  await expect(source).toContainText('not a cash receipt or bank payment');
  await source.getByRole('link', { name: /Inspect linked invoice/ }).click();
  const invoiceSource = page.locator('details[open]').filter({ has: page.locator('summary', { hasText: invoice }) });
  await expect(invoiceSource).toHaveCount(1);
  await invoiceSource.getByRole('link', { name: 'Review this case in Workspace →' }).click();
  await expect(page.getByRole('link', { name: new RegExp(`Sales credit · not cash · ${credit.document!.doc_id}`) })).toBeVisible();
  const arithmetic = page.getByRole('definition').filter({ hasText: eur(balance.credited!) });
  await expect(arithmetic.first()).toBeVisible();
  await expect(page.locator('.arithmetic-trace')).toContainText('Credited · not cash');
  await expect(page.locator('.arithmetic-trace')).toContainText(eur(balance.outstanding));
  await page.screenshot({ path: info.outputPath('business-credit-evidence.png'), fullPage: true });
  await page.goto('/#/dashboard');
  const september = page.getByRole('table', { name: /Monthly cash records/ }).getByRole('row').filter({ hasText: 'September' });
  await september.getByRole('link').last().click();
  await expect(page.getByRole('heading', { name: 'Supplier payments', exact: true })).toBeVisible();
  await expect(page.getByLabel('From date')).toHaveValue('2026-09-01');
  await expect(page.getByLabel('To date')).toHaveValue('2026-09-09');
  await page.screenshot({ path: info.outputPath('business-filtered-records.png'), fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect((await state(page)).data).toEqual(snapshot.data);
  expect(posts).toEqual(['/api/sessions']);
});
