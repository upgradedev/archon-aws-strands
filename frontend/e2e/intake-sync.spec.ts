import { test, expect } from '@playwright/test';
import { postEmailAndReadState } from './intake';

function gate() {
  let open!: () => void;
  const promise = new Promise<void>(resolve => { open = resolve; });
  return { promise, open };
}

test('intake waits for the exact completed response and new revision despite an older posted notice', async ({ page }) => {
  await page.goto('/#/documents');
  for (const name of ['invoice', 'payment']) {
    await page.getByRole('button', { name: `Sample ${name}`, exact: true }).click();
    await postEmailAndReadState(page);
  }
  await page.getByRole('button', { name: 'Sample supplier', exact: true }).click();
  const supplier = (await page.getByLabel(/Email headers/).inputValue()).replace('\nSubject:', '\nTo: me@myjoinery.example\nSubject:') + '\nBilled to: My Joinery';
  const body = 'From: me@myjoinery.example\n\n----- Forwarded message -----\n' + supplier;
  await page.getByLabel(/Email headers/).fill(body);
  const session = await page.evaluate(() => localStorage.getItem('archon.demo.session.v1'));
  const headers = { 'X-Archon-Session': session! };
  const entered = gate(), forwardRequest = gate(), responseReady = gate(), deliverResponse = gate();
  let posts = 0, completed = false;
  await page.route('**/api/intake', async route => {
    expect(route.request().method()).toBe('POST');
    expect(route.request().postDataJSON().body).toBe(body);
    posts++; entered.open();
    await forwardRequest.promise;
    const response = await route.fetch(); // Real HTTP/backend operation, never a fabricated ledger response.
    expect(response.status()).toBe(200);
    responseReady.open();
    await deliverResponse.promise;
    await route.fulfill({ response });
  });
  const pending = postEmailAndReadState(page).then(state => { completed = true; return state; });
  try {
    await entered.promise;
    // Negative control: the old assertion passes while its subsequent durable read is still stale.
    await expect(page.getByTestId('latest-source-decision')).toContainText('email:002');
    await expect(page.getByTestId('latest-source-decision')).toContainText('posted');
    const oldResponse = await page.request.get('/api/workspace', { headers });
    expect(oldResponse.status()).toBe(200);
    const old = await oldResponse.json();
    expect(old.purchases).toHaveLength(0); expect(old.sales).toHaveLength(1);
    expect(old.sources).toHaveLength(2);
    expect(completed).toBe(false);
    forwardRequest.open();
    await responseReady.promise;
    // The API has now committed, but the browser has not consumed its delayed response.
    await expect(page.getByLabel(/Email headers/)).toHaveValue(body);
    await expect(page.locator('main')).toHaveAttribute('aria-busy', 'true');
    expect(completed).toBe(false);
    deliverResponse.open();
    const fresh = await pending;
    expect(fresh.revision).toBe(old.revision + 1);
    expect(fresh.sources[2]).toMatchObject({ id: 'email:003', body, status: 'posted', kind: 'PurchaseInvoice' });
    expect(fresh.purchases).toHaveLength(1); expect(fresh.sales).toHaveLength(1);
    await expect(page.getByLabel(/Email headers/)).toHaveValue('');
    expect(posts).toBe(1);
  } finally {
    forwardRequest.open(); deliverResponse.open();
    await pending.catch(() => undefined);
    await page.unroute('**/api/intake');
  }
});
