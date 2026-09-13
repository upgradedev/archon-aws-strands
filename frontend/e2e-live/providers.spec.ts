import { test, expect, type Page } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import type { Workspace } from '../src/types';

async function saved(page: Page) {
  const session = await page.evaluate(() => localStorage.getItem('archon.demo.session.v1'));
  expect(session).toMatch(/^[a-f0-9]{64}$/);
  const response = await page.request.get('/api/workspace', { headers: { 'X-Archon-Session': session! } });
  expect(response.status()).toBe(200);
  return { session: session!, data: await response.json() as Workspace };
}
async function completed(page: Page) {
  await expect(page.locator('main')).toHaveAttribute('aria-busy', 'false');
  const result = await saved(page);
  expect(result.data.live?.job?.status).toBe('completed');
  return result;
}

test('real-provider approval is explicit, durable and not repeated after reload', async ({ page }, info) => {
  const health = await (await page.request.get('/api/health')).json();
  expect(health).toMatchObject({ mode: 'controlled-live', live_model: true, live_send: true,
    model: 'eu.anthropic.claude-opus-5', provider: 'SES-controlled-recipient', orchestration: 'Strands' });
  const fake = process.env.ARCHON_FAKE_PROVIDERS === 'true';
  if (!fake) expect(health.commit).toBe(process.env.EXPECTED_BACKEND);
  await page.goto('/');
  await expect(page.getByTestId('start-guided-example')).toBeVisible();
  await page.getByTestId('start-guided-example').click();
  const input = page.getByLabel('Email headers and plain-text body');
  await expect(input).toHaveValue(/Invoice JN-4410/);
  const offset = Number((Number((process.env.GITHUB_RUN_ID ?? '1').slice(-5)) / 100 +
    ['desktop', 'mobile', 'webkit'].indexOf(info.project.name) / 100).toFixed(2));
  const raw = await input.inputValue();
  await input.fill(raw.replace('1500.00', (1500 + offset).toFixed(2)).replace('1860.00', (1860 + offset).toFixed(2)));
  await page.getByRole('button', { name: 'Read & add invoice', exact: true }).click();
  await completed(page);
  await expect(input).toHaveValue(/Transfer ID:/);
  await page.getByRole('button', { name: 'Record payment & check balance', exact: true }).click();
  await completed(page);
  await page.getByRole('button', { name: /Run Strands & prepare draft/ }).click();
  const draft = await completed(page);
  expect(draft.data.sales[0].outstanding).toBe((1260 + offset).toFixed(2));
  expect(draft.data.draft?.subject).toContain('[Archon controlled test]');
  expect(draft.data.receipts).toHaveLength(0);
  await page.screenshot({ path: info.outputPath('live-review.png'), fullPage: true });
  const send = page.getByRole('button', { name: 'Approve exact draft · send real email', exact: true });
  await expect(send).toBeDisabled();
  const legacy = await page.request.post('/api/approve', {
    headers: { 'X-Archon-Session': draft.session },
    data: { revision: draft.data.revision, request_id: 'legacy-simulated-approval', fingerprint: draft.data.draft!.fingerprint },
  });
  expect(legacy.status()).toBe(422);
  expect((await saved(page)).data).toEqual(draft.data);
  const consent = page.getByRole('checkbox', { name: /I authorize this real email/ });
  await consent.check();
  let approval: { revision: number; request_id: string; fingerprint: string } | undefined;
  page.on('request', request => {
    if (new URL(request.url()).pathname === '/api/approve' && request.method() === 'POST') approval = request.postDataJSON();
  });
  await send.click();
  const sent = await completed(page);
  expect(sent.data.receipts).toHaveLength(1);
  const receipt = sent.data.receipts[0];
  expect(receipt.state).toBe('provider-accepted');
  expect(receipt.message_id).toBeTruthy();
  expect(receipt.message_id).not.toMatch(/^simulated-/);
  if (!fake) expect(receipt.message_id).not.toMatch(/^ci-/);
  await expect(page.getByRole('region', { name: 'Guided check outcome' })).toContainText('SES · provider-accepted');
  await page.reload();
  const retained = await saved(page);
  expect(retained.session).toBe(sent.session);
  expect(retained.data.receipts).toEqual(sent.data.receipts);
  expect(approval).toBeDefined();
  const replay = await page.request.post('/api/approve', {
    headers: { 'X-Archon-Session': sent.session }, data: approval,
  });
  expect(replay.status()).toBe(200);
  const replayed = await replay.json();
  expect(replayed.receipts).toEqual(sent.data.receipts);
  expect(replayed.live.history).toEqual(sent.data.live?.history);
  const calls = (sent.data.live?.history ?? []).flatMap(job => job.calls ?? []);
  expect(calls.length).toBeGreaterThanOrEqual(3);
  for (const call of calls) {
    expect(call.status).toBe('completed'); expect(call.model_id).toBe('eu.anthropic.claude-opus-5');
    expect(call.usage?.inputTokens).toBeGreaterThan(0); expect(call.usage?.outputTokens).toBeGreaterThan(0);
  }
  const proof = {
    scope: fake ? 'ci_fakeproviders' : 'actual_aws', origin: new URL(page.url()).origin,
    project: info.project.name, frontend_commit: process.env.EXPECTED_RELEASE ?? process.env.GITHUB_SHA,
    backend_commit: health.commit, model_calls: calls.length,
    input_tokens: calls.reduce((n, c) => n + c.usage!.inputTokens, 0),
    output_tokens: calls.reduce((n, c) => n + c.usage!.outputTokens, 0),
    email_accepted: true, message_id: receipt.message_id, replay_unchanged: true, reload_retained: true,
    legacy_consent_refused: true,
    delivery_proven: false,
  };
  await mkdir('artifacts', { recursive: true });
  await writeFile(`artifacts/live-provider-${info.project.name}.json`, JSON.stringify(proof, null, 2));
  await info.attach('provider-proof.json', { body: JSON.stringify(proof), contentType: 'application/json' });
  await page.screenshot({ path: info.outputPath('live-result.png'), fullPage: true });
});
