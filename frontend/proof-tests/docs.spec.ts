import { test, expect } from '@playwright/test';
import { readFile } from 'node:fs/promises';
import { resolve, sep } from 'node:path';

test('README and infrastructure diagrams render without broken local assets', async ({ page }, info) => {
  const root = resolve('artifacts/docs-review');
  await page.route('**/docs-review/**', async route => {
    const relative = decodeURIComponent(new URL(route.request().url()).pathname.slice('/docs-review/'.length));
    const file = resolve(root, relative);
    if (!file.startsWith(root + sep)) return route.abort();
    const body = await readFile(file);
    return route.fulfill({ body, contentType: file.endsWith('.svg') ? 'image/svg+xml' : file.endsWith('.jpg') ? 'image/jpeg' : 'text/html' });
  });
  await page.route(url => url.origin !== 'http://127.0.0.1:4173', route => route.abort());
  await page.goto('/docs-review/README.html');
  await expect(page.locator('h1')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Judge walkthrough', exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Built with', exact: true })).toBeVisible();
  const localImages = page.locator('img[src^="docs/"]');
  expect(await localImages.count()).toBeGreaterThanOrEqual(2);
  for (const image of await localImages.all()) expect(await image.evaluate((node: HTMLImageElement) => node.complete && node.naturalWidth > 0)).toBe(true);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: info.outputPath('docs-readme.png'), fullPage: true });
  for (const name of ['architecture', 'infrastructure', 'banner']) {
    await page.goto(`/docs-review/docs/${name}.svg`);
    await expect(page.locator('svg')).toBeVisible();
    expect(await page.locator('svg title').textContent()).toBeTruthy();
    expect(await page.locator('svg desc').textContent()).toBeTruthy();
    const escaped = await page.locator('svg').evaluate((root: SVGSVGElement) => {
      const box = root.viewBox.baseVal;
      return [...root.querySelectorAll('text')].filter(node => {
        const rect = node.getBBox();
        return rect.x < box.x || rect.y < box.y || rect.x + rect.width > box.x + box.width || rect.y + rect.height > box.y + box.height;
      }).map(node => node.textContent);
    });
    expect(escaped).toEqual([]);
    // Chromium's full-page screenshot can stall on a standalone SVG document.
    // Render the same inspected vector in an HTML document for the visual artifact.
    const vector = await page.locator('svg').evaluate(node => node.outerHTML);
    await page.goto('about:blank');
    await page.setContent(`<!doctype html><html><head><meta charset="utf-8"><title>${name}</title></head><body style="margin:0;width:1200px">${vector}</body></html>`);
    await expect(page.locator('svg')).toBeVisible();
    await page.screenshot({ path: info.outputPath(`docs-${name}.png`), fullPage: true });
  }
});
