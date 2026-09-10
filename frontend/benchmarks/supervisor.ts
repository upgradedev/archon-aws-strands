import { performance } from 'node:perf_hooks';
import type { ChildProcess } from 'node:child_process';
import { LIMIT_MS, type Invocation } from './model.ts';

/** The measured interval includes process/server/browser setup, not installation or aggregation. */
export async function boundedProcess(spawnChild: () => ChildProcess, killGroup: (pid: number) => void) {
  const start = performance.now();
  const outcome: Invocation = { elapsed_ms: 0, exit_code: null, limit_reached: false,
    kill_requested: false, exit_confirmed: false, errors: [] };
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    const child = spawnChild();
    const exit = new Promise<number | null>((resolve, reject) => {
      child.once('error', reject);
      child.once('exit', code => { outcome.exit_confirmed = true; resolve(code); });
    });
    const deadline = new Promise<null>(resolve => {
      timer = setTimeout(() => {
        outcome.limit_reached = true;
        outcome.errors.push('Fixed 900000 ms invocation limit reached; no additional exit wait');
        if (child.pid) {
          outcome.kill_requested = true;
          try { killGroup(child.pid); } catch (error) { outcome.errors.push(String(error)); }
        } else { outcome.errors.push('No child PID available for process-group kill request'); }
        child.unref(); resolve(null);
      }, LIMIT_MS);
    });
    outcome.exit_code = await Promise.race([exit, deadline]);
  } catch (error) { outcome.errors.push(String(error)); }
  finally { clearTimeout(timer); outcome.elapsed_ms = performance.now() - start; }
  // A late exit event must not revise the evidence returned at the fixed timing boundary.
  return { ...outcome, errors: [...outcome.errors] };
}
