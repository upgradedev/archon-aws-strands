export interface Source {
  id: string; body: string; at: string; status: 'posted' | 'refused' | 'corrected' | 'resolved';
  error: string; kind: string; redactions: number; corrected_by?: string;
  legacy_documents?: { doc_id: string; amount: string }[];
  resolution?: { decision: string; note: string; at: string; duplicate_of: string | null };
  document: { doc_id: string; source_ref: string; settles?: string; amount?: string; transfer_id?: string } | null;
}
export interface Settlement {
  doc_id: string; counterparty: string; contact: string; gross: string; settled: string; due: string;
  outstanding: string;
}
export interface QueueItem {
  invoice_id: string; client: string; recipient: string; outstanding: string;
  currency: string; days_overdue: number; reason: string;
}
export interface Arrangement {
  invoice_id: string; agreed_on: string; baseline: string; approved_by: string;
  instalments: { due: string; amount: string }[];
}
export interface Receipt {
  fingerprint: string; state: string; to_address: string; invoice_id: string;
  amount: string; at: string; message_id: string | null; error: string | null;
}
export interface Workspace {
  revision: number; as_of: string; synthetic: true; reader: string; provider: string;
  business?: { name: string; email: string; source: string };
  resolutions?: { decision: string; note: string; at: string }[];
  sources: Source[]; holds: Source[]; sales: Settlement[]; purchases: Settlement[];
  queue: { ready: QueueItem[]; blocked: QueueItem[]; currency: string };
  samples: Record<'invoice' | 'payment' | 'supplier' | 'refusal', string>;
  metrics: { bank: string; owed_by_clients: string; owed_to_suppliers: string;
    owed_to_staff: string; overdue_amount: string; overdue_count: number };
  pnl: { sales: string; purchases: string; wages: string; profit: string };
  cashflow: { inflow: string; outflow: string; net: string };
  trial_balance: string; arrangements: Arrangement[];
  proposal: { invoice_id: string; outcome: string; why: string; fingerprint: string;
    at?: string; body?: string; plan: Arrangement | null } | null;
  graph: { at: string; mode: string; reports: Record<string, string> } | null;
  draft: { invoice_id: string; recipient: string; subject: string; body: string;
    fingerprint: string; at: string; claims: string[] } | null;
  receipts: Receipt[]; receipt_states: Record<string, string>;
  activity: { id: number; at: string; title: string; detail: string }[];
}
export type Mutate = (path: string, payload?: Record<string, unknown>) => Promise<boolean>;
