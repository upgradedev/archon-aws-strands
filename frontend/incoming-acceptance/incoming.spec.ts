import { test, expect } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import type { IncomingConnection, Workspace } from '../src/types';

test('actual AWS incoming event reaches checked records once and key revocation stops intake', async ({ page }, info) => {
  expect(process.env.GITHUB_ACTIONS).toBe('true');
  expect(process.env.GITHUB_REF).toBe('refs/heads/main');
  expect(process.env.ARCHON_INCOMING_AUTHORIZED).toBe('true');
  expect(process.env.ARCHON_FAKE_PROVIDERS).toBeUndefined();
  const identity = async () => {
    expect((await (await page.request.get('/release.json')).json()).commit).toBe(process.env.EXPECTED_RELEASE);
    expect(await (await page.request.get('/api/health')).json()).toMatchObject({
      commit: process.env.EXPECTED_BACKEND, mode: 'controlled-live', live_model: true,
      model: 'eu.anthropic.claude-opus-5', orchestration: 'Strands',
    });
  };
  await identity();
  await page.goto('/#/incoming');
  await expect(page.getByRole('heading', { name: 'Incoming', exact: true })).toBeVisible();
  const session = await page.evaluate(() => localStorage.getItem('archon.demo.session.v1'));
  expect(typeof session === 'string' && /^[a-f0-9]{64}$/.test(session)).toBe(true);
  const owner = { 'X-Archon-Session': session! };
  const snapshot = async (): Promise<Workspace> => {
    const response = await page.request.get('/api/workspace', { headers: owner });
    expect(response.status()).toBe(200); return response.json();
  };
  const initial = await snapshot();
  expect(initial.sources).toHaveLength(0); expect(initial.live?.job).toBeNull();
  let token = '';
  try {
    await page.getByRole('checkbox', { name: /I authorize automatic/ }).check();
    const enabledResponse = page.waitForResponse(response => new URL(response.url()).pathname === '/api/incoming/connection' && response.request().method() === 'POST');
    await page.getByRole('button', { name: 'Enable incoming documents', exact: true }).click();
    const response = await enabledResponse; expect(response.status()).toBe(200);
    const connection = await response.json() as IncomingConnection;
    token = connection.token ?? '';
    expect(/^[a-f0-9]{64}\.[a-f0-9]{64}$/.test(token)).toBe(true);
    await page.getByRole('button', { name: 'Hide key', exact: true }).click();
    const authorization = { Authorization: `Bearer ${token}` };
    const event = { event_id: `ci-incoming-${process.env.GITHUB_RUN_ID}`, body: initial.samples.invoice };
    const accepted = await page.request.post('/api/incoming', { headers: authorization, data: event });
    expect(accepted.status()).toBe(202);
    const job = await accepted.json() as { event_id: string; job_id: string; status: string };
    await expect.poll(async () => (await snapshot()).live?.job?.status, { timeout: 150000 }).toBe('completed');
    const completed = await snapshot();
    expect(completed.sources).toHaveLength(1);
    expect(completed.sources[0].status).toBe('posted');
    expect(completed.sales[0].outstanding).toBe('1860.00');
    expect(completed.draft).toBeNull(); expect(completed.receipts).toHaveLength(0);
    const calls = completed.live!.job!.calls!;
    expect(calls.length).toBe(1);
    expect(calls[0].model_id).toBe('eu.anthropic.claude-opus-5');
    expect(calls[0].usage!.inputTokens).toBeGreaterThan(0);
    expect(calls[0].usage!.outputTokens).toBeGreaterThan(0);
    const replay = await page.request.post('/api/incoming', { headers: authorization, data: event });
    expect(replay.status()).toBe(202);
    expect(await replay.json()).toEqual({ event_id: event.event_id, job_id: job.job_id, status: 'completed' });
    expect(await snapshot()).toEqual(completed);
    await expect(page.getByRole('region', { name: 'Incoming events' })).toContainText('completed');
    await page.getByRole('link', { name: 'Inspect source decisions →', exact: true }).click();
    await expect(page.locator('[data-source-id="email:001"]')).toContainText('posted');
    await page.reload();
    await expect(page.locator('[data-source-id="email:001"]')).toContainText('JN-4410');
    expect(await snapshot()).toEqual(completed);
    await page.screenshot({ path: info.outputPath('incoming-checked-records.png'), fullPage: true });
    const revoke = await page.request.post('/api/incoming/connection', { headers: owner,
      data: { action: 'disable', request_id: 'actual-incoming-revoke' } });
    expect(revoke.status()).toBe(200);
    expect((await revoke.json()).enabled).toBe(false);
    const blocked = await page.request.post('/api/incoming', { headers: authorization,
      data: { ...event, event_id: event.event_id + '-revoked' } });
    expect(blocked.status()).toBe(401);
    expect(await snapshot()).toEqual(completed);
    await identity();
    await mkdir('artifacts', { recursive: true });
    await writeFile('artifacts/incoming-aws.json', JSON.stringify({
      scope: 'actual_aws_intake_only', frontend_commit: process.env.EXPECTED_RELEASE,
      backend_commit: process.env.EXPECTED_BACKEND, run_id: process.env.GITHUB_RUN_ID,
      event_id: event.event_id, job_id: job.job_id, model_calls: calls.length,
      input_tokens: calls[0].usage!.inputTokens, output_tokens: calls[0].usage!.outputTokens,
      replay_unchanged: true, reload_retained: true, revoked_refused: true, emails_created: 0,
      human_uat: 'NOT_RUN', mailbox_connected: false,
    }, null, 2));
  } finally {
    // Revoke even if a prior assertion or provider call failed; never publish keys or traces.
    const revoked = await page.request.post('/api/incoming/connection', { headers: owner,
      data: { action: 'disable', request_id: 'actual-incoming-final-revoke' } });
    expect(revoked.status()).toBe(200);
    token = '';
  }
});
