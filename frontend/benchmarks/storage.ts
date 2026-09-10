import { mkdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import type { Slot } from './model.ts';

export const output = resolve(process.env.X1_OUTPUT ?? 'artifacts/x1');
export function writeJSON(name: string, value: unknown) {
  mkdirSync(output, { recursive: true });
  const file = resolve(output, name);
  writeFileSync(`${file}.tmp-${process.pid}`, JSON.stringify(value, null, 2) + '\n');
  renameSync(`${file}.tmp-${process.pid}`, file);
}
export function readJSON<T>(name: string): T { return JSON.parse(readFileSync(resolve(output, name), 'utf8')); }
export function saveSlot(slot: Slot) { writeJSON(`${slot.id}.json`, slot); }
