import { expect, type Page } from '@playwright/test';
import type { Workspace } from '../src/types';

/** Synchronize a new source, not the reusable notice left by the preceding post. */
export async function postEmailAndReadState(page: Page): Promise<Workspace> {
  const editor = page.getByLabel(/Email headers/);
  await expect(page.locator('main')).toHaveAttribute('aria-busy', 'false');
  const body = await editor.inputValue();
  expect(body.trim()).not.toBe('');
  const session = await page.evaluate(() => localStorage.getItem('archon.demo.session.v1'));
  expect(session).toBeTruthy();
  const headers = { 'X-Archon-Session': session! };
  async function readState(): Promise<Workspace> {
    const response = await page.request.get('/api/workspace', { headers });
    expect(response.status()).toBe(200);
    return response.json();
  }
  const before = await readState();
  const [response] = await Promise.all([
    page.waitForResponse(response => {
      const request = response.request();
      if (new URL(response.url()).pathname !== '/api/intake' || request.method() !== 'POST') return false;
      const payload = request.postDataJSON();
      return payload?.body === body && payload?.revision === before.revision && payload?.replace_id === null
        && request.headers()['x-archon-session'] === session;
    }),
    page.getByRole('button', { name: 'Read & post email', exact: true }).click(),
  ]);
  expect(response.status()).toBe(200);
  expect(await response.finished()).toBeNull();
  const posted: Workspace = await response.json();
  expect(posted.revision).toBe(before.revision + 1);
  expect(posted.sources).toHaveLength(before.sources.length + 1);
  const added = posted.sources.filter(source => !before.sources.some(old => old.id === source.id));
  expect(added).toHaveLength(1);
  expect(added[0].body).toBe(body);
  await expect(editor).toHaveValue('');
  await expect(page.locator('main')).toHaveAttribute('aria-busy', 'false');
  await expect(page.getByTestId('latest-source-decision')).toContainText(added[0].id);
  const fresh = await readState();
  expect(fresh.revision).toBe(posted.revision);
  expect(fresh.sources).toEqual(posted.sources);
  return fresh;
}
