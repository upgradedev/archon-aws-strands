import type { Workspace } from './types';
import { cents, decimal, draftState, reasonTarget, sumMoney, unique, workspaceLink } from './ledger';

export function intakeLink(journey: string, invoice = '') {
  return `#/records?${new URLSearchParams({ intake: 'open', journey, invoice })}`;
}

/** A durable explanation, not a cached draft or an authorization decision.
 * Event titles are the existing API's recorded actions. Never infer a previous
 * draft's amount, recipient or fingerprint from a graph-completion event.
 */
export function reviewReset(data: Workspace) {
  if (data.draft) return null;
  const changes = ['Email posted', 'Email refused', 'Payment terms read', 'Human resolution recorded', 'Payment arrangement approved'];
  let change: Workspace['activity'][number] | null = null;
  for (let index = data.activity.length - 1; index >= 0; index--) {
    const event = data.activity[index];
    if (event.title === 'Strands graph completed') return change;
    if (!change && changes.includes(event.title)) change = event;
  }
  return null;
}

/** Display only: the backend independently revalidates every approval. */
export function reconciliation(data: Workspace, invoice: string, stale: boolean, now: number) {
  const balance = data.sales.find(s => s.doc_id === invoice);
  const target = reasonTarget(data);
  const draft = data.draft?.invoice_id === invoice ? data.draft : null;
  const status = draft ? draftState(data, now) : 'none';
  const blocked = data.queue.blocked.find(q => q.invoice_id === invoice);
  const receipts = unique(data.sources.filter(s => s.status === 'posted' && s.kind === 'Receipt'
    && s.document?.settles === invoice), s => s.document!.doc_id);
  const latest = receipts.at(-1);
  const total = sumMoney(receipts.map(s => s.document?.amount));
  const gross = cents(balance?.gross), settled = cents(balance?.settled), outstanding = cents(balance?.outstanding);
  const amount = cents(latest?.document?.amount);
  const before = latest && amount !== null && amount > 0n && gross !== null && settled !== null && outstanding !== null
    && cents(total) === settled && gross - settled === outstanding ? decimal(outstanding + amount) : null;
  const common = { balance, latest, before, draft, status };
  if (stale) return { ...common, title: 'Refresh before deciding', why: 'This is a last known snapshot. Read durable state and review the current evidence.', action: 'Refresh', href: null };
  if (data.holds.length) return { ...common, title: 'Hold collection. Resolve the evidence.', why: 'Unresolved post may change what is owed. No collection draft can be approved, even if a posted balance remains.', action: 'Resolve source evidence', href: '#/records?filter=refused' };
  if (!balance) return { ...common, title: 'Start with the invoice evidence', why: 'Prepare a draft, then add a payment and see why the original decision must change.', action: 'Start reconciliation', href: intakeLink('invoice') };
  if (outstanding === 0n) return { ...common, title: 'Settled in these books. No chase.', why: 'Posted receipts cover this invoice. No collection draft is needed; retained remittances are not independent bank confirmation.', action: 'Inspect recorded receipts', href: `#/records?view=payments&q=${encodeURIComponent(invoice)}` };
  if (blocked) return { ...common, title: 'Collection is paused for this case', why: blocked.reason === 'a payment plan is being kept'
    ? `The queue records: ${blocked.reason}. A payment promise changes timing, not the ledger balance.`
    : `The queue records: ${blocked.reason}. Do not guess missing contact or payment evidence.`,
    action: blocked.reason === 'a payment plan is being kept' ? 'Review case terms' : 'Inspect case evidence',
    href: blocked.reason === 'a payment plan is being kept' ? workspaceLink(invoice, null, 'terms') : `#/records?source=${encodeURIComponent(invoice)}` };
  if (target.id !== invoice || target.issue) return { ...common, title: 'Inspect evidence before collection', why: target.issue || `The backend priority is ${target.id}. This selected case does not retarget the graph.`, action: target.id ? 'Open priority case' : 'Inspect records', href: target.id ? workspaceLink(target.id) : '#/records' };
  if (status === 'recorded') return { ...common, title: 'An outcome is already recorded', why: 'This exact draft has a retained receipt. Inspect its actual state before any further action; provider acceptance does not prove delivery.', action: 'Inspect durable outcome', href: '#/history' };
  if (status === 'pending') return { ...common, title: 'Review this exact collection draft', why: 'The graph has prepared a draft from current books. Confirm the recipient, text and balance below. New evidence requires fresh review.', action: 'Review exact draft below', href: '#collection-draft' };
  return { ...common, title: latest ? 'Payment evidence changed the decision' : 'Prepare a decision from these books', why: status === 'expired' || status === 'unavailable'
    ? 'The stored draft is expired or its time is unavailable. Prepare and review a fresh draft.'
    : 'Run Strands on current books. Adding or resolving evidence invalidates the previous draft and its review; consent never carries forward.', action: 'Prepare current draft below', href: '#prepare-current-draft' };
}
