import { createHash } from 'node:crypto';

export const PREREGISTRATION = '439e748a91e90a68bc5f2a3fea99e9e2c1890e9e';
export const PROTOCOL_SHA256 = '87d13e55e8a04b1c2f439aac52a6efe2fe041cf3835778b210a707b8c9cd4a8f';
export const APPLICATION = '3839d36ac018d52c0b9dcf2fe8e72aee9b077a91';
export const LIMIT_MS = 900000;
export const BRANCHES = ['new-payment', 'forwarded-duplicate'] as const;
export type Branch = typeof BRANCHES[number];
export type Status = 'not_started' | 'running' | 'passed' | 'failed' | 'timed_out' | 'interrupted';
export type Health = { commit: string; mode: string; live_model: boolean; live_send: boolean; model: string; provider: string; reader: string; orchestration: string };
export type Invocation = {
  elapsed_ms: number | null; exit_code: number | null; limit_reached: boolean;
  kill_requested: boolean; exit_confirmed: boolean; errors: string[];
};
export type RequestRow = {
  ordinal: number; phase: 'setup' | 'journey' | 'after_journey'; channel: 'browser' | 'diagnostic';
  method: string; path: string; status: number | null; start_offset_ms: number;
  headers_ms: number | null; body_ms: number | null; error: string | null;
  request_body_bytes: number | null; response_body_bytes: number | null;
};
export type Slot = {
  id: string; branch: Branch; ordinal: number; status: Status; started_utc: string | null;
  process_order: number; process_use: 'first-attempt' | 'reused-process'; branch_use: 'first-for-branch' | 'reused-process';
  worker_index: number | null; journey_start_offset_ms: number | null; journey_end_offset_ms: number | null;
  elapsed_ms: number | null; journey_ms: number | null; journey_censored_ms: number | null;
  runtime_verified: boolean; health: Health | null; browser_version: string | null;
  served_assets_verified: boolean; requests: RequestRow[]; errors: string[];
  evidence: { sha256: string; bytes: number; copy_verified: boolean; download_verified: boolean } | null;
};
export function sha256(bytes: string | Buffer) { return createHash('sha256').update(bytes).digest('hex'); }
export function plan(): Slot[] {
  return Array.from({ length: 10 }, (_, i) => BRANCHES.map((branch, b) => ({
    id: `${branch}-${String(i + 1).padStart(2, '0')}`, branch, ordinal: i + 1,
    process_order: i * 2 + b + 1, process_use: i === 0 && b === 0 ? 'first-attempt' as const : 'reused-process' as const,
    branch_use: i === 0 ? 'first-for-branch' as const : 'reused-process' as const,
    worker_index: null, journey_start_offset_ms: null, journey_end_offset_ms: null,
    status: 'not_started' as const, started_utc: null, elapsed_ms: null, journey_ms: null,
    journey_censored_ms: null, runtime_verified: false, health: null, browser_version: null,
    served_assets_verified: false, requests: [], errors: [], evidence: null,
  }))).flat();
}
export function assertPlan(slots: Slot[]) {
  const expected = plan();
  if (slots.length !== 20 || slots.some((slot, i) => slot.id !== expected[i].id || slot.branch !== expected[i].branch || slot.ordinal !== expected[i].ordinal)) {
    throw new Error('The frozen 20-slot order/denominator changed');
  }
}
export function assertEnvironment(env: Record<string, string | undefined>) {
  const forbidden = ['ARCHON_UI_URL', 'VITE_API_BASE_URL', 'ARCHON_STATE_BUCKET', 'AWS_ACCESS_KEY_ID',
    'AWS_SECRET_ACCESS_KEY', 'AWS_SESSION_TOKEN', 'AWS_PROFILE', 'AWS_WEB_IDENTITY_TOKEN_FILE',
    'OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'BEDROCK_API_KEY', 'AWS_BEARER_TOKEN_BEDROCK'];
  if (forbidden.some(key => Boolean(env[key]))) throw new Error('Source-only benchmark refuses live endpoints, cloud state or credentials');
}
export function allowedURL(value: string) {
  try {
    const url = new URL(value);
    return !url.username && !url.password && ['http://127.0.0.1:4173', 'http://127.0.0.1:8000'].includes(url.origin);
  } catch { return false; }
}
export function assertHealth(health: Health, candidate: string) {
  if (health.commit !== candidate || !/^[a-f0-9]{40}$/.test(candidate) || health.mode !== 'synthetic'
      || health.live_model !== false || health.live_send !== false || health.model !== 'LedgerScriptModel'
      || health.provider !== 'SimulatedProvider' || health.reader !== 'bounded-local-rules' || health.orchestration !== 'Strands') {
    throw new Error('Runtime identity/scripted safety check failed');
  }
}
export function nearestRank(values: number[], quantile: number): number | null {
  if (!(quantile > 0 && quantile <= 1) || values.some(x => !Number.isFinite(x) || x < 0)) throw new Error('Invalid percentile input');
  if (!values.length) return null;
  return [...values].sort((a, b) => a - b)[Math.ceil(quantile * values.length) - 1];
}
export function verifiedRuntime(slot: Slot) {
  if (!slot.runtime_verified || !slot.served_assets_verified || !slot.health) return false;
  try { assertHealth(slot.health, slot.health.commit); return true; } catch { return false; }
}
export function complete(slot: Slot) {
  return verifiedRuntime(slot) && !!slot.browser_version
    && slot.journey_ms !== null && Number.isFinite(slot.journey_ms) && slot.journey_ms >= 0
    && slot.journey_start_offset_ms !== null && slot.journey_end_offset_ms !== null
    && Math.abs(slot.journey_end_offset_ms - slot.journey_start_offset_ms - slot.journey_ms) < 0.000001
    && !!slot.evidence?.download_verified && slot.evidence.bytes > 0 && /^[a-f0-9]{64}$/.test(slot.evidence.sha256)
    && (slot.branch !== 'new-payment' || slot.evidence.copy_verified)
    && slot.requests.some(r => r.path === '/api/reason' && r.status === 200 && r.body_ms !== null)
    && slot.requests.every((r, i) => r.ordinal === i + 1 && r.error === null && r.body_ms !== null && Number.isFinite(r.body_ms) && r.body_ms >= 0
      && (r.headers_ms === null || (r.headers_ms >= 0 && r.headers_ms <= r.body_ms))
      && r.response_body_bytes !== null && r.request_body_bytes !== null && r.status !== null
      && (r.status >= 200 && r.status < 300 || (r.path === '/api/approve' && r.status === 409)))
    && slot.errors.length === 0;
}
export function recordResult(slot: Slot, result: { status: string; retry: number; duration: number; errors: string[] }): Slot {
  slot.elapsed_ms = result.duration;
  slot.errors.push(...result.errors);
  if (result.retry !== 0) slot.errors.push('Retry violates frozen protocol');
  slot.status = result.status === 'passed' && complete(slot) ? 'passed'
    : result.status === 'timedOut' ? 'timed_out' : result.status === 'interrupted' ? 'interrupted' : 'failed';
  if (result.status === 'passed' && !complete(slot)) slot.errors.push('Nominal pass lacks complete instrument evidence');
  return slot;
}
export function restoreSlot(expected: Slot, value: Slot): Slot {
  if (value.id !== expected.id || value.branch !== expected.branch || value.ordinal !== expected.ordinal
      || !Array.isArray(value.requests) || !Array.isArray(value.errors)) throw new Error('Invalid/misidentified raw slot');
  if (value.status === 'running') {
    value.status = 'interrupted'; value.errors.push('Snapshot captured before attempt completion; child exit may be unconfirmed');
  }
  return value;
}
export function summarize(slots: Slot[], invocation: Invocation) {
  assertPlan(slots);
  const groups = [null, ...BRANCHES].map(branch => {
    const rows = slots.filter(s => !branch || s.branch === branch);
    const passed = rows.filter(s => s.status === 'passed' && complete(s));
    const values = passed.map(s => s.journey_ms!);
    return { branch: branch ?? 'all', planned: rows.length, passed: passed.length, not_passed: rows.length - passed.length,
      statuses: Object.fromEntries(['not_started', 'running', 'passed', 'failed', 'timed_out', 'interrupted'].map(status => [status, rows.filter(s => s.status === status).length])),
      successful_latency_n: values.length, p50_ms: nearestRank(values, 0.5), p95_ms: nearestRank(values, 0.95), estimator: 'nearest-rank-ceil-p-times-n',
    };
  });
  const verified = slots.every(verifiedRuntime);
  return {
    scope: 'SOURCE_CI_SCRIPTED_BROWSER_ORCHESTRATION_NOT_AWS_MODEL_OR_HUMAN_LATENCY',
    accepted: groups[0].passed === 20 && invocation.exit_code === 0 && invocation.exit_confirmed
      && !invocation.kill_requested && !invocation.limit_reached
      && invocation.elapsed_ms !== null && invocation.elapsed_ms <= LIMIT_MS && invocation.errors.length === 0,
    invocation, groups,
    scripted_graph_http_calls: slots.flatMap(s => s.requests).filter(r => r.path === '/api/reason').length,
    costs: { model_invocations: verified ? 0 : null, model_cost_usd: verified ? 0 : null,
      model_basis: verified ? 'Verified scripted source/runtime; no paid model invocations' : 'UNVERIFIED',
      aws_infrastructure_cost_usd: null, aws_infrastructure_cost_status: 'UNKNOWN_NOT_MEASURED',
      runner_cost_usd: null, runner_cost_status: 'NOT_MEASURED', human_time_saved: 'NOT_MEASURED',
      observed_runner_seconds: invocation.elapsed_ms === null ? null : invocation.elapsed_ms / 1000,
      observed_requests: slots.reduce((n, s) => n + s.requests.length, 0),
      known_request_body_bytes: slots.flatMap(s => s.requests).reduce((n, r) => n + (r.request_body_bytes ?? 0), 0),
      known_response_body_bytes: slots.flatMap(s => s.requests).reduce((n, r) => n + (r.response_body_bytes ?? 0), 0),
      unknown_request_body_count: slots.flatMap(s => s.requests).filter(r => r.request_body_bytes === null).length,
      unknown_response_body_count: slots.flatMap(s => s.requests).filter(r => r.response_body_bytes === null).length,
    },
  };
}
