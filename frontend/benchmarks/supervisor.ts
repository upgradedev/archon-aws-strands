import { performance } from 'node:perf_hooks';
import type { ChildProcess } from 'node:child_process';
import { LIMIT_MS } from './model.ts';

/** The measured interval includes process/server/browser setup, not installation or aggregation. */
export async function boundedProcess(spawnChild: () => ChildProcess, killGroup: (pid: number) => void) {
  const start = performance.now();
  const outcome = { elapsed_ms: 0, exit_code: null as number | null, limit_reached: false, errors: [] as string[] };
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    const child = spawnChild();
    const exit = new Promise<number | null>((resolve, reject) => {
      child.once('error', reject); child.once('exit', code => resolve(code));
    });
    const deadline = new Promise<null>(resolve => {
      timer = setTimeout(() => {
        outcome.limit_reached = true;
        outcome.errors.push('Fixed 900000 ms invocation limit reached; process-group kill requested');
        if (child.pid) { try { killGroup(child.pid); } catch (error) { outcome.errors.push(String(error)); } }
        child.unref(); resolve(null);
      }, LIMIT_MS);
    });
    outcome.exit_code = await Promise.race([exit, deadline]);
  } catch (error) { outcome.errors.push(String(error)); }
  finally { clearTimeout(timer); outcome.elapsed_ms = performance.now() - start; }
  return outcome;
}
