import type { Source, Workspace } from './types';

// Keep money exact even beyond Number.MAX_SAFE_INTEGER. Missing is never zero.
export function cents(value: unknown): bigint | null {
  if (typeof value !== 'string' || !/^-?\d+(\.\d{1,2})?$/.test(value)) return null;
  const negative = value.startsWith('-');
  const [whole, fraction = ''] = value.replace(/^-/, '').split('.');
  return (BigInt(whole) * 100n + BigInt(fraction.padEnd(2, '0'))) * (negative ? -1n : 1n);
}
export function decimal(value: bigint): string {
  const absolute = value < 0n ? -value : value;
  return `${value < 0n ? '-' : ''}${absolute / 100n}.${String(absolute % 100n).padStart(2, '0')}`;
}
export function sumMoney(values: unknown[]): string | null {
  let total = 0n;
  for (const value of values) { const amount = cents(value); if (amount === null) return null; total += amount; }
  return decimal(total);
}
export function unique<T>(rows: T[], key: (row: T) => string): T[] {
  return [...new Map(rows.map(row => [key(row), row])).values()];
}
export function linkedSources(data: Workspace, invoice: string): Source[] {
  return unique(data.sources.filter(s => s.status === 'posted' &&
    (s.document?.doc_id === invoice || s.document?.settles === invoice)), s => s.id);
}
export function validDay(day: string): boolean {
  return /^\d{4}-\d{2}-\d{2}$/.test(day) && Number.isFinite(Date.parse(day)) && new Date(day).toISOString().slice(0, 10) === day;
}

/** Display projection of books.worst_overdue, including its recipient-blind selection.
 * Never an authorization gate: every mutation still revalidates on the existing API.
 * The blocked queue reports arrangement holds, but a missing address can mask that
 * reason. In that ambiguous case we refuse to identify an actionable target.
 */
export function reasonTarget(data: Workspace): { id: string | null; issue: string } {
  if (!validDay(data.as_of)) return { id: null, issue: 'The ledger date is unavailable. Refresh before preparing a draft.' };
  if (new Set(data.sales.map(s => s.doc_id)).size !== data.sales.length || data.sales.some(s => cents(s.outstanding) === null || !validDay(s.due)))
    return { id: null, issue: 'Invoice evidence is incomplete or duplicated. Refresh before preparing a draft.' };
  const candidates = data.sales.filter(s => cents(s.outstanding)! > 0n && s.due < data.as_of)
    .filter(s => !data.queue.blocked.some(q => q.invoice_id === s.doc_id && q.reason === 'a payment plan is being kept'))
    .sort((a, b) => a.due.localeCompare(b.due) || (cents(a.outstanding)! > cents(b.outstanding)! ? -1 : cents(a.outstanding)! < cents(b.outstanding)! ? 1 : 0));
  if (candidates.some(s => !s.contact && data.arrangements.some(a => a.invoice_id === s.doc_id)))
    return { id: null, issue: 'A missing recipient masks an arrangement status. This API cannot establish a safe target for review.' };
  const target = candidates[0];
  return { id: target?.doc_id ?? null, issue: target ? (!target.contact ? 'The backend priority invoice has no recipient. Collections require a valid address.' : '') : 'Available when an invoice is overdue and chaseable.' };
}
export function draftState(data: Workspace, now: number): 'none' | 'recorded' | 'unavailable' | 'expired' | 'held' | 'pending' {
  if (!data.draft) return 'none';
  if (data.receipts.some(r => r.fingerprint === data.draft!.fingerprint)) return 'recorded';
  const at = Date.parse(data.draft.at);
  if (!Number.isFinite(at) || at > now) return 'unavailable';
  if (now >= at + 30 * 60 * 1000) return 'expired';
  if (data.holds.length) return 'held';
  return 'pending';
}
export function dashboardMetrics(data: Workspace, now: number) {
  const status = draftState(data, now);
  const duplicate = new Set(data.sales.map(s => s.doc_id)).size !== data.sales.length;
  const payments = unique(data.sources.filter(s => s.status === 'posted' && s.kind === 'Receipt'), s => s.document?.doc_id ?? s.id);
  return [
    { id: 'outstanding', label: 'Outstanding', amount: duplicate ? null : sumMoney(data.sales.map(s => s.outstanding)), note: 'All open client balances', href: '#/records?view=sales&filter=outstanding' },
    { id: 'overdue', label: 'Overdue', amount: duplicate || !validDay(data.as_of) || data.sales.some(s => !validDay(s.due) || cents(s.outstanding) === null) ? null : sumMoney(data.sales.filter(s => s.due < data.as_of && cents(s.outstanding)! > 0n).map(s => s.outstanding)), note: 'Includes balances held by arrangements', href: '#/records?view=sales&filter=overdue' },
    { id: 'payments', label: 'Recorded receipts', amount: sumMoney(payments.map(s => s.document?.amount)), note: 'All posted client receipts · no bank connection', href: '#/records?view=payments' },
    { id: 'drafts', label: 'Pending exact drafts', count: status === 'unavailable' ? null : status === 'pending' ? 1 : 0, note: status === 'expired' ? 'Stored draft expired · review again' : 'Unexpired, without a recorded attempt', href: '#/workspace?view=draft' },
    { id: 'holds', label: 'Source holds', count: unique(data.holds, s => s.id).length, note: 'Refused evidence requiring attention', href: '#/records?filter=refused' },
  ];
}
export function routeInfo(route: string) {
  const [path, query] = route.split('?');
  const params = new URLSearchParams(query);
  const aliases: Record<string, string> = { '/queue': 'workspace', '/approvals': 'workspace', '/documents': 'records', '/activity': 'history' };
  return { page: aliases[path] ?? (path.slice(1) || 'dashboard'), params };
}
export function workspaceLink(invoice?: string | null, source?: string | null, view = 'draft') {
  const params = new URLSearchParams({ view });
  if (invoice) params.set('invoice', invoice);
  if (source) params.set('source', source);
  return `#/workspace?${params}`;
}
