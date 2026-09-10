import { performance } from 'node:perf_hooks';
import type { APIResponse, Page, Request, Response } from '@playwright/test';
import { allowedURL, assertHealth, sha256, type Health, type RequestRow, type Slot } from './model';
import { readJSON, saveSlot } from './storage';

type Metadata = { candidate_sha: string; source_checks: boolean; assets: Record<string, string> };
let observedWorker = false;
export class Recorder {
  slot: Slot;
  private start = performance.now();
  private journeyStart: number | null = null;
  private phase: RequestRow['phase'] = 'setup';
  private rows = new Map<Request, { row: RequestRow; start: number }>();
  private pending: Promise<void>[] = [];
  constructor(id: string, private page: Page, workerIndex = 0) {
    this.slot = readJSON<Slot>(`${id}.json`);
    if (this.slot.status !== 'not_started') throw new Error('Attempt reuse/retry forbidden');
    this.slot.worker_index = workerIndex;
    this.slot.process_use = observedWorker ? 'reused-process' : 'first-attempt'; observedWorker = true;
    this.slot.status = 'running'; this.slot.started_utc = new Date().toISOString(); this.persist();
    page.on('request', this.onRequest);
    page.on('response', this.onResponse);
    page.on('requestfinished', this.onFinished);
    page.on('requestfailed', this.onFailed);
    page.on('pageerror', this.onPageError);
  }
  private persist() { saveSlot(this.slot); }
  private row(channel: RequestRow['channel'], method: string, path: string, requestBytes: number | null): RequestRow {
    const row: RequestRow = { ordinal: this.slot.requests.length + 1, phase: this.phase, channel, method, path,
      status: null, start_offset_ms: performance.now() - this.start, headers_ms: null, body_ms: null,
      error: null, request_body_bytes: requestBytes, response_body_bytes: null };
    this.slot.requests.push(row); this.persist(); return row;
  }
  private onRequest = (request: Request) => {
    if (!new URL(request.url()).pathname.startsWith('/api/')) return;
    const start = performance.now();
    const row = this.row('browser', request.method(), new URL(request.url()).pathname, request.postDataBuffer()?.length ?? 0);
    this.rows.set(request, { row, start });
  };
  private onResponse = (response: Response) => {
    const item = this.rows.get(response.request());
    if (item) { item.row.headers_ms = performance.now() - item.start; item.row.status = response.status(); this.persist(); }
  };
  private onFinished = (request: Request) => {
    const item = this.rows.get(request); if (!item) return;
    item.row.body_ms = performance.now() - item.start;
    this.persist();
    this.pending.push((async () => {
      try { const response = await request.response(); if (response) item.row.response_body_bytes = (await response.body()).length; }
      catch (error) { item.row.error = `Body-byte accounting failed: ${String(error)}`; }
      this.persist();
    })());
  };
  private onFailed = (request: Request) => {
    const item = this.rows.get(request); if (!item) return;
    item.row.error = request.failure()?.errorText ?? 'Request failed'; this.persist();
  };
  private onPageError = (error: Error) => { this.slot.errors.push(error.message); this.persist(); };
  async diagnostic(path: string, method = 'GET', data?: object, headers?: Record<string, string>) {
    const start = performance.now();
    const row = this.row('diagnostic', method, path, data ? Buffer.byteLength(JSON.stringify(data)) : 0);
    let response: APIResponse;
    try {
      if (!allowedURL(new URL(path, 'http://127.0.0.1:4173').href)) throw new Error('External diagnostic URL refused');
      response = await this.page.request.fetch(path, { method, data, headers, maxRedirects: 0, maxRetries: 0 });
      // APIRequestContext resolves after body buffering, so it cannot observe a distinct header arrival.
      row.status = response.status();
      const bytes = await response.body(); row.response_body_bytes = bytes.length;
      const value: unknown = bytes.length ? JSON.parse(bytes.toString('utf8')) : null;
      row.body_ms = performance.now() - start; this.persist();
      return { status: response.status(), value };
    } catch (error) { row.error = String(error); this.persist(); throw error; }
  }
  async verifyRuntime(browserVersion: string) {
    const metadata = readJSON<Metadata>('metadata.json');
    if (!metadata.source_checks || !Object.keys(metadata.assets).length) throw new Error('Missing source-build verification');
    await this.page.context().route('**/*', async route => {
      if (allowedURL(route.request().url())) await route.continue();
      else {
        this.slot.errors.push('Blocked external origin'); this.persist(); await route.abort('blockedbyclient');
      }
    });
    const health = await this.diagnostic('/api/health');
    if (health.status !== 200) throw new Error('Health HTTP failure');
    assertHealth(health.value as Health, metadata.candidate_sha);
    this.slot.health = health.value as Health;
    this.slot.runtime_verified = true; this.slot.browser_version = browserVersion; this.persist();
    for (const [path, expected] of Object.entries(metadata.assets)) {
      // Build attestation reads are setup only, not application API timing rows.
      if (!path.startsWith('/') || !allowedURL(new URL(path, 'http://127.0.0.1:4173').href)) throw new Error('Invalid source-build asset path');
      const response = await this.page.request.get(path, { maxRedirects: 0, maxRetries: 0 });
      if (response.status() !== 200 || sha256(await response.body()) !== expected) throw new Error(`Served source-build bytes mismatch: ${path}`);
    }
    this.slot.served_assets_verified = true; this.persist();
  }
  begin() {
    if (this.journeyStart !== null || !this.slot.runtime_verified || !this.slot.served_assets_verified) throw new Error('Invalid journey start');
    this.journeyStart = performance.now(); this.phase = 'journey';
    this.slot.journey_start_offset_ms = this.journeyStart - this.start; this.persist();
  }
  finish(bytes: Buffer, copyVerified: boolean) {
    if (this.journeyStart === null) throw new Error('Journey never started');
    const end = performance.now();
    this.slot.journey_ms = end - this.journeyStart; this.slot.journey_end_offset_ms = end - this.start;
    this.slot.evidence = { sha256: sha256(bytes), bytes: bytes.length, download_verified: true, copy_verified: copyVerified };
    this.phase = 'after_journey'; this.persist();
  }
  async close() {
    // End timing first. Serialization and pending byte-accounting cleanup are outside a completed journey.
    if (this.journeyStart !== null && this.slot.journey_ms === null) this.slot.journey_censored_ms = performance.now() - this.journeyStart;
    this.page.off('request', this.onRequest); this.page.off('response', this.onResponse);
    this.page.off('requestfinished', this.onFinished); this.page.off('requestfailed', this.onFailed);
    this.page.off('pageerror', this.onPageError);
    await Promise.all(this.pending); this.persist();
  }
}
