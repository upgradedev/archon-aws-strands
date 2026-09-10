// @vitest-environment node
import { execFileSync, spawnSync, type ChildProcess } from 'node:child_process';
import { EventEmitter } from 'node:events';
import { mkdtempSync, readFileSync, readdirSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { resolve } from 'node:path';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { APPLICATION, PREREGISTRATION, PROTOCOL_SHA256, allowedURL, assertEnvironment, assertHealth,
  assertPlan, complete, nearestRank, plan, recordResult, restoreSlot, sha256, summarize, type Health, type Slot } from '../benchmarks/model';
import { boundedProcess } from '../benchmarks/supervisor';

const health: Health = { commit: APPLICATION, mode: 'synthetic', live_model: false, live_send: false,
  model: 'LedgerScriptModel', provider: 'SimulatedProvider', reader: 'bounded-local-rules', orchestration: 'Strands' };
const invocation = { elapsed_ms: 100000, exit_code: 0, limit_reached: false, errors: [] };
function successful(): Slot[] {
  return plan().map<Slot>((slot, i) => ({ ...slot, status: 'passed', journey_ms: (i + 1) * 100, elapsed_ms: 3000,
    worker_index: 0, journey_start_offset_ms: 100, journey_end_offset_ms: 100 + (i + 1) * 100,
    runtime_verified: true, served_assets_verified: true, health: { ...health }, browser_version: 'fixture-Chromium',
    evidence: { sha256: 'a'.repeat(64), bytes: 10, copy_verified: true, download_verified: true },
    requests: [{ ordinal: 1, phase: 'journey', channel: 'browser', method: 'POST', path: '/api/reason',
      status: 200, start_offset_ms: 1, headers_ms: 1, body_ms: 2, error: null, request_body_bytes: 10, response_body_bytes: 20 }],
  }));
}
afterEach(() => { vi.useRealTimers(); vi.unstubAllEnvs(); });

describe('X1 frozen source instrument', () => {
  it('binds literal protocol bytes and ordered preregistration ancestry before measurement', () => {
    const bytes = readFileSync('benchmarks/x1-protocol.json');
    expect(sha256(bytes)).toBe('87d13e55e8a04b1c2f439aac52a6efe2fe041cf3835778b210a707b8c9cd4a8f');
    expect(PROTOCOL_SHA256).toBe(sha256(bytes));
    const protocol = JSON.parse(bytes.toString());
    expect(protocol.sample_plan).toMatchObject({ attempts_per_branch: 10, total_attempts: 20, retries: 0, workers: 1,
      warmup_attempts: 0, attempt_timeout_ms: 35000, invocation_limit_ms: 900000 });
    expect(protocol.application_source_commit).toBe(APPLICATION);
    const prereg = execFileSync('git', ['show', `${PREREGISTRATION}:frontend/benchmarks/x1-protocol.json`]);
    expect(sha256(prereg)).toBe(PROTOCOL_SHA256);
    execFileSync('git', ['merge-base', '--is-ancestor', PREREGISTRATION, 'HEAD']);
    const paths = execFileSync('git', ['diff-tree', '--no-commit-id', '--name-only', '-r', PREREGISTRATION], { encoding: 'utf8' }).trim();
    expect(paths).toBe('frontend/benchmarks/x1-protocol.json');
  });
  it('preallocates exactly ten per branch in the frozen alternating order', () => {
    const slots = plan();
    expect(slots).toHaveLength(20);
    expect(slots.map(s => s.id)).toEqual(Array.from({ length: 10 }, (_, i) => [
      `new-payment-${String(i + 1).padStart(2, '0')}`, `forwarded-duplicate-${String(i + 1).padStart(2, '0')}`]).flat());
    expect(new Set(slots.map(s => s.id)).size).toBe(20);
    expect(slots.every(s => s.status === 'not_started' && s.journey_ms === null)).toBe(true);
    expect(slots[0].process_use).toBe('first-attempt'); expect(slots[1].process_use).toBe('reused-process');
    expect(() => assertPlan(slots.slice(1))).toThrow(/denominator/);
    expect(() => assertPlan([...slots].reverse())).toThrow(/order/);
    slots[1].id = slots[0].id; expect(() => assertPlan(slots)).toThrow();
  });
  it('uses nearest rank, not interpolation, and does not mutate the observations', () => {
    const values = [10, 1, 8, 5, 2, 9, 4, 6, 3, 7];
    expect(nearestRank(values, 0.5)).toBe(5); expect(nearestRank(values, 0.95)).toBe(10);
    expect(values[0]).toBe(10);
    expect(nearestRank([71], 0.95)).toBe(71); expect(nearestRank([], 0.5)).toBeNull();
    expect(() => nearestRank([NaN], 0.5)).toThrow(); expect(() => nearestRank([-1], 0.95)).toThrow();
    expect(() => nearestRank([1], 0)).toThrow();
  });
  it('retains an all-unstarted denominator and unknown cost for startup failure', () => {
    const report = summarize(plan(), { elapsed_ms: null, exit_code: null, limit_reached: false, errors: ['setup failed'] });
    expect(report.accepted).toBe(false);
    expect(report.groups.map(g => [g.planned, g.not_passed, g.successful_latency_n, g.p50_ms, g.p95_ms])).toEqual([
      [20, 20, 0, null, null], [10, 10, 0, null, null], [10, 10, 0, null, null]]);
    expect(report.costs.model_invocations).toBeNull(); expect(report.costs.model_cost_usd).toBeNull();
    expect(report.costs.aws_infrastructure_cost_usd).toBeNull(); expect(report.costs.runner_cost_usd).toBeNull();
  });
  it('reports complete successes with their fixed denominators and scripted-only zero model cost', () => {
    const report = summarize(successful(), invocation);
    expect(report.accepted).toBe(true);
    expect(report.groups.map(g => [g.planned, g.passed, g.p50_ms, g.p95_ms])).toEqual([[20, 20, 1000, 1900], [10, 10, 900, 1900], [10, 10, 1000, 2000]]);
    expect(report.costs.model_invocations).toBe(0); expect(report.costs.model_cost_usd).toBe(0);
    expect(report.scripted_graph_http_calls).toBe(20);
    expect(report.costs.aws_infrastructure_cost_status).toBe('UNKNOWN_NOT_MEASURED');
    expect(report.costs.known_request_body_bytes).toBe(200); expect(report.costs.known_response_body_bytes).toBe(400);
  });
  it('does not reinterpret censored, failed, timed-out or unstarted attempts as successful latency', () => {
    const slots = successful();
    slots[0].status = 'failed'; slots[0].journey_ms = null; slots[0].journey_censored_ms = 99999;
    slots[1].status = 'timed_out'; slots[1].journey_ms = null;
    slots[2] = plan()[2];
    const report = summarize(slots, invocation);
    expect(report.accepted).toBe(false);
    expect(report.groups[0]).toMatchObject({ planned: 20, passed: 17, not_passed: 3, successful_latency_n: 17 });
    expect(report.groups[1]).toMatchObject({ planned: 10, passed: 8, not_passed: 2, p50_ms: 1100, p95_ms: 1900 });
    expect(report.costs.model_cost_usd).toBeNull();
  });
  it('preserves interrupted partial rows and refuses cross-slot replacement', () => {
    const partial = successful()[0]; partial.status = 'running'; partial.journey_ms = null;
    const restored = restoreSlot(plan()[0], partial);
    expect(restored.status).toBe('interrupted'); expect(restored.requests).toHaveLength(1);
    expect(restored.journey_ms).toBeNull(); expect(restored.errors).toContain('Runner ended before attempt completion');
    expect(() => restoreSlot(plan()[1], partial)).toThrow(/misidentified/);
  });
  it('fails closed when a nominal pass lacks evidence, has a retry, or has incomplete request accounting', () => {
    const result = { status: 'passed', retry: 0, duration: 3000, errors: [] };
    expect(recordResult(plan()[0], result).status).toBe('failed');
    expect(recordResult(successful()[0], { ...result, retry: 1 }).status).toBe('failed');
    const partial = successful()[0]; partial.requests[0].body_ms = null;
    expect(recordResult(partial, result).status).toBe('failed');
    const unknownBytes = successful()[0]; unknownBytes.requests[0].response_body_bytes = null;
    expect(complete(unknownBytes)).toBe(false);
    expect(summarize([unknownBytes, ...successful().slice(1)], invocation).costs.unknown_response_body_count).toBe(1);
  });
  it('records test failure/timeout without fabricating a successful duration', () => {
    const slot = plan()[0]; slot.journey_censored_ms = 55;
    const result = recordResult(slot, { status: 'timedOut', duration: 35000, retry: 0, errors: ['timeout'] });
    expect(result.status).toBe('timed_out'); expect(result.elapsed_ms).toBe(35000);
    expect(result.journey_ms).toBeNull(); expect(result.journey_censored_ms).toBe(55);
  });
  it('fails the aggregate despite complete samples if process budget, exit or instrument integrity fails', () => {
    for (const modified of [{ elapsed_ms: 900001 }, { exit_code: 1 }, { limit_reached: true }, { errors: ['bad provenance'] }]) {
      expect(summarize(successful(), { ...invocation, ...modified }).accepted).toBe(false);
    }
  });
  it('refuses live modes, bad identities and credentials without exposing secret values', () => {
    assertHealth(health, APPLICATION);
    for (const modified of [{ live_model: true }, { live_send: true }, { model: 'Bedrock' }, { provider: 'SES' },
      { mode: 'live' }, { reader: 'remote' }, { orchestration: 'other' }, { commit: 'local-unversioned' }]) {
      expect(() => assertHealth({ ...health, ...modified }, APPLICATION)).toThrow(/safety/);
    }
    for (const key of ['ARCHON_UI_URL', 'VITE_API_BASE_URL', 'ARCHON_STATE_BUCKET', 'AWS_ACCESS_KEY_ID',
      'AWS_SECRET_ACCESS_KEY', 'AWS_SESSION_TOKEN', 'AWS_PROFILE', 'AWS_WEB_IDENTITY_TOKEN_FILE',
      'OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'BEDROCK_API_KEY', 'AWS_BEARER_TOKEN_BEDROCK']) {
      expect(() => assertEnvironment({ [key]: 'private-fixture-value' })).toThrow('Source-only benchmark refuses live endpoints, cloud state or credentials');
    }
    assertEnvironment({ AWS_EC2_METADATA_DISABLED: 'true' });
    const slots = successful(); slots[0].health!.live_send = true;
    expect(summarize(slots, invocation).costs.model_cost_usd).toBeNull();
  });
  it('allows only exact loopback origins, without credentials or redirects to live services', () => {
    expect(allowedURL('http://127.0.0.1:4173/api/health')).toBe(true);
    expect(allowedURL('http://127.0.0.1:8000/api/health')).toBe(true);
    for (const url of ['https://example.com', 'http://127.0.0.1.evil:4173', 'http://me@127.0.0.1:4173',
      'http://127.0.0.1:80', 'https://127.0.0.1:4173', 'invalid']) expect(allowedURL(url)).toBe(false);
  });
  it('accepts the explicit stale-approval 409 control, not unrelated HTTP failures', () => {
    const slot = successful()[0]; slot.requests.push({ ...slot.requests[0], ordinal: 2, path: '/api/approve', status: 409 });
    expect(complete(slot)).toBe(true);
    slot.requests[1].path = '/api/intake'; expect(complete(slot)).toBe(false);
    slot.requests[1].status = 500; expect(complete(slot)).toBe(false);
  });
  it('pins manual-only source CI, fixed browser limits and immutable application paths', () => {
    const config = readFileSync('playwright.x1.config.ts', 'utf8');
    expect(config).toContain('workers: 1'); expect(config).toContain('retries: 0');
    expect(config).toContain('timeout: 35000'); expect(config).toContain('repeatEach: 1');
    expect(config).not.toContain('process.env.ARCHON_UI_URL');
    const workflow = readFileSync('../.github/workflows/frontend-ci.yml', 'utf8');
    expect(workflow).toContain("github.event_name == 'workflow_dispatch' && inputs.x1_benchmark == true");
    expect(workflow).toContain('needs: [secrets, verify]'); expect(workflow).toContain('runs-on: ubuntu-24.04');
    // The manual instrument refuses a changed application; normal source CI must still permit future product work.
    const launcher = readFileSync('benchmarks/run.mjs', 'utf8');
    expect(launcher).toContain("git('diff', APPLICATION, candidate, '--', '../src', 'src', '../pyproject.toml', 'package.json', 'package-lock.json')");
  });
  it('retains twenty slots and checksums end-to-end when the launcher refuses an unsafe setup', () => {
    const folder = mkdtempSync(resolve(tmpdir(), 'archon-x1-refusal-'));
    const out = resolve(folder, 'evidence');
    try {
      const result = spawnSync(process.execPath, ['benchmarks/run.mjs'], { encoding: 'utf8',
        env: { ...process.env, X1_OUTPUT: out, ARCHON_UI_URL: 'https://forbidden.example' }, timeout: 10000 });
      expect(result.error).toBeUndefined(); expect(result.status, result.stderr).toBe(1);
      const raw = JSON.parse(readFileSync(resolve(out, 'raw-outcomes.json'), 'utf8'));
      expect(raw).toHaveLength(20); expect(raw.every((s: Slot) => s.status === 'not_started')).toBe(true);
      const summary = JSON.parse(readFileSync(resolve(out, 'summary.json'), 'utf8'));
      expect(summary.groups[0]).toMatchObject({ planned: 20, not_passed: 20, p50_ms: null });
      expect(summary.invocation.errors[0]).toContain('Source-only benchmark refuses');
      expect(readdirSync(out).filter(name => /-\d\d\.json$/.test(name))).toHaveLength(20);
      for (const line of readFileSync(resolve(out, 'SHA256SUMS'), 'utf8').trim().split('\n')) {
        const [hash, name] = line.split('  '); expect(sha256(readFileSync(resolve(out, name)))).toBe(hash);
      }
      const retained = readFileSync(resolve(out, 'raw-outcomes.json'));
      const overwrite = spawnSync(process.execPath, ['benchmarks/run.mjs'], { encoding: 'utf8', env: { ...process.env, X1_OUTPUT: out }, timeout: 10000 });
      expect(overwrite.status).toBe(1); expect(overwrite.stderr).toContain('Refusing to overwrite');
      expect(readFileSync(resolve(out, 'raw-outcomes.json'))).toEqual(retained);
    } finally { rmSync(folder, { recursive: true, force: true }); }
  });
  it('records successful and failed request events through persisted recorder and reporter fixtures', async () => {
    const folder = mkdtempSync(resolve(tmpdir(), 'archon-x1-recorder-'));
    vi.stubEnv('X1_OUTPUT', folder); vi.resetModules();
    const { saveSlot, readJSON, writeJSON } = await import('../benchmarks/storage');
    const { Recorder } = await import('../benchmarks/recorder');
    const { default: Reporter } = await import('../benchmarks/reporter');
    const asset = Buffer.from('already-spent source instrument fixture');
    writeJSON('metadata.json', { candidate_sha: APPLICATION, source_checks: true, assets: { '/index.html': sha256(asset) } });
    const page = Object.assign(new EventEmitter(), {
      context: () => ({ route: vi.fn() }),
      request: {
        fetch: vi.fn(async () => ({ status: () => 200, body: async () => Buffer.from(JSON.stringify(health)) })),
        get: vi.fn(async () => ({ status: () => 200, body: async () => asset })),
      },
    });
    try {
      const slot = plan()[0]; saveSlot(slot);
      const recorder = new Recorder(slot.id, page as never);
      await recorder.verifyRuntime('fixture-Chromium'); recorder.begin();
      const request = { url: () => 'http://127.0.0.1:4173/api/reason', method: () => 'POST',
        postDataBuffer: () => Buffer.from('{}'), response: async () => ({ body: async () => Buffer.from('{"ok":true}') }) };
      page.emit('request', request);
      page.emit('response', { request: () => request, status: () => 200 });
      page.emit('requestfinished', request);
      recorder.finish(Buffer.from('fixture evidence'), true); await recorder.close();
      new Reporter().onTestEnd({ title: slot.id } as never, { status: 'passed', retry: 0, duration: 10, errors: [] } as never);
      const saved = readJSON<Slot>(`${slot.id}.json`);
      expect(saved.status).toBe('passed'); expect(complete(saved)).toBe(true);
      expect(saved.requests[0]).toMatchObject({ phase: 'setup', channel: 'diagnostic', headers_ms: null });
      expect(saved.requests[1]).toMatchObject({ phase: 'journey', channel: 'browser', request_body_bytes: 2, response_body_bytes: 11 });
      expect(saved.evidence?.sha256).toBe(sha256('fixture evidence'));
      expect(() => new Recorder(slot.id, page as never)).toThrow(/reuse/);
      const failed = plan()[1]; saveSlot(failed);
      const failure = new Recorder(failed.id, page as never);
      await failure.verifyRuntime('fixture-Chromium'); failure.begin();
      const brokenRequest = { ...request, failure: () => ({ errorText: 'controlled connection failure' }) };
      page.emit('request', brokenRequest); page.emit('requestfailed', brokenRequest);
      await failure.close();
      new Reporter().onTestEnd({ title: failed.id } as never, { status: 'failed', retry: 0, duration: 20, errors: [{ message: 'controlled failure' }] } as never);
      const savedFailure = readJSON<Slot>(`${failed.id}.json`);
      expect(savedFailure.status).toBe('failed'); expect(savedFailure.journey_ms).toBeNull();
      expect(savedFailure.journey_censored_ms).not.toBeNull();
      expect(savedFailure.requests[1]).toMatchObject({ body_ms: null, response_body_bytes: null, error: 'controlled connection failure' });
      expect(() => new Reporter().onTestEnd({ title: 'not-registered' } as never, {} as never)).toThrow(/Unregistered/);
    } finally { rmSync(folder, { recursive: true, force: true }); }
  });
});

describe('X1 process budget', () => {
  function child() { return Object.assign(new EventEmitter(), { pid: 123, unref: vi.fn() }) as unknown as ChildProcess; }
  it('kills once at 900000 ms, without retrying or waiting for a stuck child exit', async () => {
    vi.useFakeTimers(); const process = child(), spawn = vi.fn(() => process), kill = vi.fn();
    const result = boundedProcess(spawn, kill);
    await vi.advanceTimersByTimeAsync(899999); expect(kill).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1);
    expect((await result).limit_reached).toBe(true); expect(kill).toHaveBeenCalledTimes(1); expect(kill).toHaveBeenCalledWith(123);
    expect(spawn).toHaveBeenCalledTimes(1);
  });
  it('clears the watchdog on normal completion and records the real exit status', async () => {
    vi.useFakeTimers(); const process = child(), kill = vi.fn();
    const result = boundedProcess(() => process, kill); process.emit('exit', 7);
    expect((await result).exit_code).toBe(7);
    await vi.advanceTimersByTimeAsync(900000); expect(kill).not.toHaveBeenCalled();
  });
  it('retains spawn and kill errors as failures rather than silently passing or hanging', async () => {
    expect((await boundedProcess(() => { throw new Error('spawn failed'); }, vi.fn())).errors).toEqual(['Error: spawn failed']);
    vi.useFakeTimers(); const process = child();
    const result = boundedProcess(() => process, () => { throw new Error('kill failed'); });
    await vi.advanceTimersByTimeAsync(900000);
    expect((await result).errors).toContain('Error: kill failed');
  });
});
