import { mkdirSync, readFileSync, readdirSync, renameSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { plan, restoreSlot, sha256, summarize, type Invocation, type Slot } from './model.ts';

export const output = resolve(process.env.X1_OUTPUT ?? 'artifacts/x1');
export const journal = resolve(output, 'journal');
export const finalized = resolve(output, 'final');
export function writeJSON(name: string, value: unknown) {
  mkdirSync(journal, { recursive: true });
  const file = resolve(journal, name);
  writeFileSync(`${file}.tmp-${process.pid}`, JSON.stringify(value, null, 2) + '\n');
  renameSync(`${file}.tmp-${process.pid}`, file);
}
export function readJSON<T>(name: string): T { return JSON.parse(readFileSync(resolve(journal, name), 'utf8')); }
export function saveSlot(slot: Slot) { writeJSON(`${slot.id}.json`, slot); }

/** One-time byte capture, not an atomic multi-file snapshot or proof that descendants stopped. */
export function finalizeEvidence(invocation: Invocation) {
  mkdirSync(finalized); // Exclusive: never overwrite or revise a previously finalized dataset.
  const started = new Date().toISOString();
  const captured = new Map<string, Buffer>();
  const errors: string[] = [];
  function capture(path = '') {
    try {
      for (const entry of readdirSync(resolve(journal, path), { withFileTypes: true })) {
        const name = path ? `${path}/${entry.name}` : entry.name;
        if (/\.tmp-\d+$/.test(entry.name)) continue; // In-flight atomic-write scratch, not a registered slot.
        if (entry.isDirectory()) capture(name);
        else if (entry.isFile()) {
          try { captured.set(name, readFileSync(resolve(journal, name))); }
          catch (error) { errors.push(`Unreadable journal file ${name}: ${String(error)}`); }
        } else { errors.push(`Unsupported journal entry ${name}`); }
      }
    } catch (error) { errors.push(`Unreadable journal directory ${path}: ${String(error)}`); }
  }
  capture();
  const finished = new Date().toISOString();
  const slots = plan().map(expected => {
    try {
      const bytes = captured.get(`${expected.id}.json`);
      if (!bytes) throw new Error('Registered slot missing from captured journal');
      return restoreSlot(expected, JSON.parse(bytes.toString('utf8')));
    } catch (error) { expected.errors.push(`Unreadable slot: ${String(error)}`); return expected; }
  });
  const summary = summarize(slots, { ...invocation, errors: [...invocation.errors, ...errors] });
  const finalBytes = new Map<string, Buffer>([...captured].map(([name, bytes]) => [`journal-snapshot/${name}`, bytes]));
  const json = (value: unknown) => Buffer.from(JSON.stringify(value, null, 2) + '\n');
  finalBytes.set('raw-outcomes.json', json(slots));
  finalBytes.set('summary.json', json(summary));
  finalBytes.set('snapshot.json', json({ capture_started_utc: started, capture_finished_utc: finished,
    source: 'child-writable journal/', destination: 'final/journal-snapshot/',
    kill_requested: invocation.kill_requested, exit_confirmed: invocation.exit_confirmed,
    exit_confirmation_scope: 'Spawned Playwright process exit event observed before supervisor returned; not proof all descendants stopped',
    capture_scope: 'Each journal file read once during the stated interval, not an atomic multi-file snapshot. Raw outcomes derive only from captured bytes. Late child writes remain in journal/ and cannot revise final/.',
    excluded_scratch: '*.tmp-<pid> atomic-write scratch only; all 20 registered slots remain in raw outcomes',
    errors }));
  for (const [name, bytes] of finalBytes) {
    const file = resolve(finalized, name);
    mkdirSync(dirname(file), { recursive: true });
    writeFileSync(file, bytes, { flag: 'wx', mode: 0o444 });
  }
  // Hash exactly the copied bytes; never reread child-writable paths during finalization/upload.
  writeFileSync(resolve(finalized, 'SHA256SUMS'), [...finalBytes].sort(([a], [b]) => a.localeCompare(b))
    .map(([name, bytes]) => `${sha256(bytes)}  ${name}\n`).join(''), { flag: 'wx', mode: 0o444 });
  return summary;
}
