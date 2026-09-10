import { spawn, execFileSync } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { resolve, relative } from 'node:path';
import { APPLICATION, PREREGISTRATION, PROTOCOL_SHA256, assertEnvironment, plan, restoreSlot, sha256, summarize } from './model.ts';
import { output, readJSON, saveSlot, writeJSON } from './storage.ts';
import { boundedProcess } from './supervisor.ts';

// One invocation, no retry or automatic replacement. A new run requires another explicit dispatch.
if (existsSync(output)) throw new Error('Refusing to overwrite retained X1 evidence');
mkdirSync(output, { recursive: true });
const slots = plan();
slots.forEach(saveSlot);
let invocation = { elapsed_ms: null, exit_code: null, limit_reached: false, errors: [] };
const git = (...args) => execFileSync('git', args, { encoding: 'utf8' }).trim();
const files = dir => readdirSync(dir, { withFileTypes: true }).flatMap(entry => entry.isDirectory() ? files(resolve(dir, entry.name)) : [resolve(dir, entry.name)]);
let metadata = { started_utc: new Date().toISOString(), candidate_sha: null, preregistration_sha: PREREGISTRATION,
  protocol_sha256: PROTOCOL_SHA256, application_source_commit: APPLICATION,
  run_url: `https://github.com/${process.env.GITHUB_REPOSITORY}/actions/runs/${process.env.GITHUB_RUN_ID}`,
  run_attempt: process.env.GITHUB_RUN_ATTEMPT, node: process.version, platform: process.platform,
  runner_os: process.env.RUNNER_OS, runner_image: process.env.ImageOS, runner_image_version: process.env.ImageVersion,
  timing_unit: 'milliseconds', timing_clock: 'Node performance.now(); request start_offset_ms is relative to Recorder construction for that attempt',
  timing_overhead: 'Journey includes in-flow instrumentation/journal I/O and browser assertions; final serialization is excluded. elapsed_ms is Playwright test duration including fixtures, not journey duration.',
  browser_http_boundary: 'request event to requestfinished event; headers_ms uses response event; scheduling/body transfer included, JSON parsing excluded',
  diagnostic_http_boundary: 'APIRequestContext invocation through buffered body and JSON parse; headers_ms null because a distinct header event is not observable',
  infrastructure_cost_status: 'UNKNOWN_NOT_MEASURED', browser_cold_warm_status: 'NOT_AWS_COLD_WARM; fresh context/session. process_use and worker_index identify first/reused worker (including automatic worker restart after a failed attempt, not an attempt retry); branch_use is ordinal only. No cache/cold-start claim.',
  source_checks: false, assets: {} };
writeJSON('metadata.json', metadata);
try {
  assertEnvironment(process.env);
  if (process.env.CI !== 'true' || process.platform !== 'linux') throw new Error('Run only in Linux source CI');
  if (process.env.GITHUB_RUN_ATTEMPT !== '1') throw new Error('Reruns are not registered samples; use a separately identified explicit dispatch');
  const protocol = readFileSync('benchmarks/x1-protocol.json');
  if (sha256(protocol) !== PROTOCOL_SHA256) throw new Error('Frozen protocol bytes changed');
  writeFileSync(resolve(output, 'x1-protocol.json'), protocol);
  const candidate = git('rev-parse', 'HEAD');
  if (candidate !== process.env.ARCHON_COMMIT_SHA || candidate !== process.env.GITHUB_SHA) throw new Error('Candidate SHA mismatch');
  git('merge-base', '--is-ancestor', PREREGISTRATION, candidate);
  git('merge-base', '--is-ancestor', APPLICATION, PREREGISTRATION);
  if (git('diff', APPLICATION, candidate, '--', '../src', 'src', '../pyproject.toml', 'package.json', 'package-lock.json')) throw new Error('Frozen application/dependencies changed');
  if (git('status', '--porcelain', '--untracked-files=no')) throw new Error('Tracked checkout is dirty');
  const assets = Object.fromEntries([resolve('dist/index.html'), ...files(resolve('dist/assets'))].map(file => [`/${relative(resolve('dist'), file).replaceAll('\\', '/')}`, sha256(readFileSync(file))]));
  metadata = { ...metadata, candidate_sha: candidate, source_checks: true, assets,
    python: execFileSync('python', ['--version'], { encoding: 'utf8' }).trim(),
    playwright: JSON.parse(readFileSync('node_modules/@playwright/test/package.json', 'utf8')).version,
    machine: execFileSync('uname', ['-a'], { encoding: 'utf8' }).trim() };
  writeJSON('metadata.json', metadata);
  invocation = await boundedProcess(() => spawn(process.execPath,
    ['node_modules/@playwright/test/cli.js', 'test', '--config', 'playwright.x1.config.ts', '--forbid-only'],
    { stdio: 'inherit', detached: true, env: process.env }), pid => process.kill(-pid, 'SIGKILL'));
} catch (error) { invocation.errors.push(String(error)); }

// Finalize only after the worker process has stopped. Missing/partial slots are failures, not omitted samples.
for (let i = 0; i < slots.length; i++) {
  try { slots[i] = restoreSlot(slots[i], readJSON(`${slots[i].id}.json`)); }
  catch (error) { slots[i].errors.push(`Unreadable slot: ${String(error)}`); }
}
writeJSON('raw-outcomes.json', slots);
const summary = summarize(slots, invocation);
writeJSON('summary.json', summary);
writeFileSync(resolve(output, 'SHA256SUMS'), files(output).sort().map(file => `${sha256(readFileSync(file))}  ${relative(output, file)}\n`).join(''));
console.log(JSON.stringify(summary, null, 2));
process.exitCode = summary.accepted ? 0 : 1;
