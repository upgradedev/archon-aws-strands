import type { Workspace } from '../src/types';

export function empty(): Workspace {
  return { revision: 0, as_of: '2026-09-09', synthetic: true,
    reader: 'Bounded local rules', provider: 'Simulated outbox',
    sources: [], holds: [], sales: [], purchases: [],
    queue: { ready: [], blocked: [], currency: 'EUR' },
    samples: { invoice: 'synthetic invoice', payment: 'synthetic payment', supplier: 'synthetic supplier', refusal: 'ambiguous post' },
    metrics: { bank: '0.00', owed_by_clients: '0.00', owed_to_suppliers: '0.00', owed_to_staff: '0.00', overdue_amount: '0.00', overdue_count: 0 },
    pnl: { sales: '0.00', purchases: '0.00', wages: '0.00', profit: '0.00' },
    cashflow: { inflow: '0.00', outflow: '0.00', net: '0.00' }, trial_balance: '0.00',
    arrangements: [], proposal: null, graph: null, draft: null, receipts: [], activity: [],
    receipt_states: { queued: 'Intent recorded', unknown: 'Do not retry', 'provider-accepted': 'Arrival unproven', delivered: 'Independent evidence required', failed: 'Confirmed refusal' },
  };
}
export function filled(): Workspace {
  const value = empty();
  value.revision = 3;
  value.sales = [{ doc_id: 'JN-4410', counterparty: 'BuildCo Ltd', contact: 'accounts@buildco.example', gross: '1860.00', settled: '600.00', outstanding: '1260.00', due: '2026-08-01' }];
  value.purchases = [{ doc_id: 'WS-77', counterparty: 'Wholesaler', contact: '', gross: '124.00', settled: '0.00', outstanding: '124.00', due: '2026-10-01' }];
  value.queue.ready = [{ invoice_id: 'JN-4410', client: 'BuildCo Ltd', recipient: 'accounts@buildco.example', outstanding: '1260.00', currency: 'EUR', days_overdue: 39, reason: '' }];
  value.metrics = { ...value.metrics, bank: '600.00', owed_by_clients: '1260.00', overdue_amount: '1260.00', overdue_count: 1 };
  value.draft = { invoice_id: 'JN-4410', recipient: 'accounts@buildco.example', subject: 'Our outstanding invoice', body: 'Invoice JN-4410 is still outstanding at 1,260.00 EUR.', fingerprint: 'a'.repeat(64), at: '2026-09-09T12:00:00Z', claims: ['1,260.00 EUR'] };
  value.graph = { at: '2026-09-09', mode: 'Real Strands graph · scripted model · no AI judgment', reports: { sales: '1,260.00 EUR', cash: '600.00 EUR' } };
  value.sources = [{ id: 'email:001', body: '<script>alert("text only")</script>', status: 'posted', error: '', kind: 'SalesInvoice', document: { doc_id: 'JN-4410', source_ref: 'email:001' }, redactions: 2, at: '2026-09-09' }];
  value.activity = [{ id: 1, at: '2026-09-09T12:00:00Z', title: 'Email posted', detail: 'email:001: JN-4410' }];
  return value;
}
export function refusal(data = filled()): Workspace {
  const source = { id: 'email:002', body: 'ambiguous payment', status: 'refused' as const, error: 'the email does not identify a document', kind: '', document: null, redactions: 0, at: '2026-09-09' };
  data.sources.push(source); data.holds = [source]; data.draft = null;
  return data;
}
export function proposal(data = filled()): Workspace {
  data.proposal = { invoice_id: 'JN-4410', outcome: 'proposed', why: 'Explicit dates and amounts', fingerprint: 'b'.repeat(64), plan: { invoice_id: 'JN-4410', agreed_on: '2026-09-09', baseline: '600.00', approved_by: 'demo visitor', instalments: [{ due: '2026-09-20', amount: '1260.00' }] } };
  return data;
}
export function received(data = filled()): Workspace {
  data.receipts = [{ fingerprint: 'a'.repeat(64), state: 'provider-accepted', invoice_id: 'JN-4410', to_address: 'accounts@buildco.example', amount: '1260.00', at: '2026-09-09T12:00:00Z', message_id: 'simulated-abc', error: null }];
  return data;
}
