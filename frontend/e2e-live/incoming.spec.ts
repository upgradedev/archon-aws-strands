import { test, expect, type Page } from '@playwright/test';
import type { Workspace } from '../src/types';

async function snapshot(page: Page, session: string): Promise<Workspace> {
  const response = await page.request.get('/api/workspace', { headers: { 'X-Archon-Session': session } });
  expect(response.status()).toBe(200);
  return response.json();
}

// Register no tests (including skipped tests) in the actual-AWS acceptance lane.
if (process.env.ARCHON_FAKE_PROVIDERS === 'true') {
test('CI incoming controls post once, retain arrivals and revoke the intake key', async ({ page, baseURL }, info) => {
  test.setTimeout(60000);
  expect(process.env.GITHUB_ACTIONS).toBe('true');
  expect(process.env.ARCHON_UI_URL).toBeUndefined();
  expect(baseURL).toBe('http://127.0.0.1:4173');
  await page.goto('/#/dashboard');
  await expect(page.getByRole('heading', { name: 'Dashboard', exact: true })).toBeVisible();
  const session = await page.evaluate(() => localStorage.getItem('archon.demo.session.v1'));
  expect(session).toMatch(/^[a-f0-9]{64}$/);
  const owner = { 'X-Archon-Session': session! };
  const initial = await snapshot(page, session!);
  expect(initial.live?.model).toBe(true);
  expect(initial.sources).toEqual([]);

  const missingConsent = await page.request.post('/api/incoming/connection', {
    headers: owner, data: { action: 'enable', request_id: 'browser-missing-consent' },
  });
  expect(missingConsent.status()).toBe(422);
  const navigation = page.getByRole('navigation', { name: 'Workspace' });
  await navigation.getByRole('link', { name: 'Incoming', exact: true }).click();
  const connection = page.getByRole('region', { name: 'Incoming connection', exact: true });
  await expect(connection.getByText('Not connected', { exact: true })).toBeVisible();
  const enable = connection.getByRole('button', { name: 'Enable incoming documents', exact: true });
  await expect(enable).toBeDisabled();
  const consent = connection.getByRole('checkbox', { name: /I authorize automatic/ });
  await consent.check();
  await expect(enable).toBeEnabled();
  const enableResponse = page.waitForResponse(response =>
    new URL(response.url()).pathname === '/api/incoming/connection' && response.request().method() === 'POST');
  await enable.click();
  const enabled = await enableResponse;
  expect(enabled.status()).toBe(200);
  expect(enabled.request().postDataJSON()).toMatchObject({ action: 'enable', consent: 'fictional-intake' });
  const keyField = connection.getByLabel('Intake-only key', { exact: true });
  await expect(keyField).toBeVisible();
  await expect(keyField).toHaveAttribute('type', 'password');
  const token = await keyField.inputValue();
  expect(token).toMatch(/^[a-f0-9]{64}\.[a-f0-9]{64}$/);
  await expect(consent).not.toBeChecked();
  const stored = await page.evaluate(() => JSON.stringify({ ...localStorage, ...sessionStorage }));
  expect(stored).not.toContain(token);
  await connection.getByRole('button', { name: 'Copy intake key', exact: true }).click();
  await expect(connection.getByRole('status')).toContainText(/Intake key copied|Clipboard unavailable/);
  await connection.getByRole('button', { name: 'Hide key', exact: true }).click();
  await expect(keyField).toHaveCount(0);
  await page.reload();
  await expect(connection.getByText('Key active · sender setup required', { exact: true })).toBeVisible();
  await expect(keyField).toHaveCount(0);
  expect(await snapshot(page, session!)).toEqual(initial);
  await page.screenshot({ path: info.outputPath('incoming-ci-enabled.png'), fullPage: true });
  const authorization = { Authorization: `Bearer ${token}` };
  const event = { event_id: 'browser-incoming-0001', body: initial.samples.invoice
    .replace('accounts@buildco.example', 'controlled@example.test') };
  const accepted = await page.request.post('/api/incoming', { headers: authorization, data: event });
  expect(accepted.status()).toBe(202);
  const queued = await accepted.json() as { event_id: string; job_id: string; status: string };
  await expect.poll(async () => (await snapshot(page, session!)).live?.job?.status,
    { timeout: 30000 }).toBe('completed');
  const posted = await snapshot(page, session!);
  expect(posted.sources).toHaveLength(1);
  expect(posted.sources[0]).toMatchObject({ id: 'email:001', status: 'posted', kind: 'SalesInvoice' });
  expect(posted.sales[0].outstanding).toBe('1860.00');
  expect(posted.live?.history).toHaveLength(1);
  expect(posted.live?.history?.[0].calls).toHaveLength(1);
  expect(posted.draft).toBeNull(); expect(posted.receipts).toEqual([]);
  const arrivals = page.getByRole('region', { name: 'Incoming events', exact: true });
  await expect(arrivals.getByRole('listitem')).toHaveCount(1);
  await expect(arrivals.getByRole('listitem')).toContainText(event.event_id);
  await expect(arrivals.getByRole('listitem')).toContainText('completed');

  const replay = await page.request.post('/api/incoming', { headers: authorization, data: event });
  expect(replay.status()).toBe(202);
  expect(await replay.json()).toEqual({ event_id: event.event_id, job_id: queued.job_id, status: 'completed' });
  expect(await snapshot(page, session!)).toEqual(posted);
  await navigation.getByRole('link', { name: 'Records', exact: true }).click();
  await expect(page.locator('[data-source-id="email:001"]')).toContainText('JN-4410');
  await page.reload();
  await expect(page.locator('[data-source-id="email:001"]')).toContainText('posted');
  expect(await snapshot(page, session!)).toEqual(posted);

  const status = await page.request.get('/api/incoming/connection', { headers: owner });
  expect(status.status()).toBe(200);
  expect(await status.json()).toMatchObject({ enabled: true,
    events: [{ event_id: event.event_id, job_id: queued.job_id, status: 'completed' }] });
  expect(await status.text()).not.toContain(token);
  await navigation.getByRole('link', { name: 'Incoming', exact: true }).click();
  await expect(arrivals.getByRole('listitem')).toContainText('completed');
  await expect(keyField).toHaveCount(0);
  const revokeResponse = page.waitForResponse(response =>
    new URL(response.url()).pathname === '/api/incoming/connection' && response.request().method() === 'POST');
  await connection.getByRole('button', { name: 'Revoke intake key', exact: true }).click();
  const disabled = await revokeResponse;
  expect(disabled.status()).toBe(200);
  expect(await disabled.json()).toMatchObject({ enabled: false });
  await expect(connection.getByText('Not connected', { exact: true })).toBeVisible();
  await expect(arrivals.getByRole('listitem')).toContainText('completed');
  const revoked = await page.request.post('/api/incoming', {
    headers: authorization, data: { ...event, event_id: 'browser-incoming-0002' },
  });
  expect(revoked.status()).toBe(401);
  expect(await snapshot(page, session!)).toEqual(posted);
  await page.screenshot({ path: info.outputPath('incoming-ci-revoked.png'), fullPage: true });
});
}
