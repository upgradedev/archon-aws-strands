import type { Reporter, TestCase, TestResult } from '@playwright/test/reporter';
import { plan, recordResult, type Slot } from './model';
import { readJSON, saveSlot } from './storage';

export default class X1Reporter implements Reporter {
  onTestEnd(test: TestCase, result: TestResult) {
    const expected = plan().find(s => test.title === s.id);
    if (!expected) throw new Error(`Unregistered X1 test: ${test.title}`);
    const slot = readJSON<Slot>(`${expected.id}.json`);
    saveSlot(recordResult(slot, { status: result.status, retry: result.retry, duration: result.duration,
      errors: result.errors.map(error => error.message ?? 'Unknown Playwright failure') }));
  }
}
