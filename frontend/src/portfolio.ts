import type { Settlement, Source, Workspace } from './types';
import { cents, decimal, sumMoney, unique, validDay } from './ledger';

export const documentViews = [
  { view: 'sales-invoices', kind: 'SalesInvoice', label: 'Sales invoices' },
  { view: 'purchase-invoices', kind: 'PurchaseInvoice', label: 'Purchase invoices' },
  { view: 'sales-credits', kind: 'SalesCreditNote', label: 'Sales credits' },
  { view: 'purchase-credits', kind: 'PurchaseCreditNote', label: 'Purchase credits' },
  { view: 'client-receipts', kind: 'Receipt', label: 'Client receipts' },
  { view: 'supplier-payments', kind: 'Payment', label: 'Supplier payments' },
] as const;
export type DocumentKind = typeof documentViews[number]['kind'];
export const QUARTER_START = '2026-07-01';
export const QUARTER_END = '2026-09-30';
export const PAGE_SIZE = 25;
export const agingBuckets = [
  { id: 'current', label: 'Not yet overdue' }, { id: '1-30', label: '1–30 days overdue' },
  { id: '31-60', label: '31–60 days overdue' }, { id: '61-plus', label: '61+ days overdue' },
  { id: 'unknown', label: 'Unknown due date' },
] as const;

export function documentDay(source: Source): string | undefined {
  const doc = source.document;
  return source.kind === 'Receipt' ? doc?.received_on : source.kind === 'Payment' ? doc?.paid_on : doc?.issued;
}
export function recordDay(source: Source): string | undefined {
  // Retained legacy sources may lack typed dates. Their intake date is labelled in Records only.
  return documentDay(source) ?? source.at?.slice(0, 10);
}
export function recordLink(params: Record<string, string>): string {
  return `#/records?${new URLSearchParams(params)}`;
}
export function sourceLink(id: string): string { return recordLink({ source: id }); }
export function duplicateReceiptMail(data: Workspace, invoice: string | null): string {
  const source = data.sources.filter(s => s.status === 'posted' && s.kind === 'Receipt' && s.document?.settles === invoice).at(-1);
  if (!source) return '';
  if (source.origin !== 'fictional-business-fixture') return source.body + '\nForwarded for reference.';
  const doc = source.document!;
  const original = data.sources.find(s => s.status === 'posted' && s.kind === 'SalesInvoice' && s.document?.doc_id === invoice)?.document;
  if (!doc.transfer_id || !doc.received_on || !doc.amount || !original?.client_email) return '';
  return `From: ${original.client_email}\nSubject: Remittance for ${invoice}\n\nWe have paid ${doc.amount} EUR on ${doc.received_on} against invoice ${invoice}.\nTransfer ID: ${doc.transfer_id}\n\nFictional remittance reconstructed from typed fixture ${source.id}; not an original email.\nForwarded for reference.`;
}
export function sourceOrigin(source: Source): string {
  if (source.origin === 'fictional-demo-template') return 'Fictional email template · local rule reader';
  if (source.origin?.includes('business') || source.origin?.includes('typed')) return 'Fictional typed demo document · deterministic books checks · no AI extraction';
  return source.origin ? `Source origin: ${source.origin}` : 'Retained submitted source · extraction provenance not recorded';
}
export function postedDocuments(sources: Source[]): Source[] {
  return unique(sources.filter(s => s.status === 'posted' && s.document), s => `${s.kind}:${s.document!.doc_id}`);
}
export function partyIndex(data: Workspace): Map<string, string> {
  return new Map([...data.sales, ...data.purchases].map(s => [s.doc_id, s.counterparty]));
}
export function documentParty(source: Source, parties: Map<string, string>): string {
  const doc = source.document;
  return doc?.client ?? doc?.supplier ?? parties.get(doc?.settles ?? doc?.doc_id ?? '') ?? '';
}
export function ageBucket(row: Settlement, asOf: string): string {
  if (!validDay(row.due) || !validDay(asOf)) return 'unknown';
  const days = Math.floor((Date.parse(asOf) - Date.parse(row.due)) / 86400000);
  return days <= 0 ? 'current' : days <= 30 ? '1-30' : days <= 60 ? '31-60' : '61-plus';
}
export function pageOf<T>(rows: T[], requested: string | null, selectedIndex = -1) {
  const pages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
  const parsed = requested && /^\d+$/.test(requested) ? Number(requested) : NaN;
  const page = Math.min(pages, Math.max(1, Number.isSafeInteger(parsed) ? parsed : Math.floor(Math.max(0, selectedIndex) / PAGE_SIZE) + 1));
  const start = (page - 1) * PAGE_SIZE;
  return { page, pages, start, rows: rows.slice(start, start + PAGE_SIZE), total: rows.length };
}
function subtract(a: string | null, b: string | null): string | null {
  const left = cents(a), right = cents(b);
  return left === null || right === null ? null : decimal(left - right);
}
function amountFor(sources: Source[], kind: DocumentKind, field: 'net' | 'amount'): string | null {
  return sumMoney(sources.filter(s => s.kind === kind).map(s => s.document?.[field]));
}
function totals(sources: Source[]) {
  const sales = amountFor(sources, 'SalesInvoice', 'net');
  const purchases = amountFor(sources, 'PurchaseInvoice', 'net');
  const salesCredits = amountFor(sources, 'SalesCreditNote', 'net');
  const purchaseCredits = amountFor(sources, 'PurchaseCreditNote', 'net');
  return { sales, purchases, salesCredits, purchaseCredits, netSales: subtract(sales, salesCredits),
    netPurchases: subtract(purchases, purchaseCredits), cashIn: amountFor(sources, 'Receipt', 'amount'),
    cashOut: amountFor(sources, 'Payment', 'amount') };
}
function rankParties(rows: Settlement[]) {
  const grouped = new Map<string, Settlement[]>();
  for (const row of rows) {
    const group = grouped.get(row.counterparty) ?? [];
    group.push(row); grouped.set(row.counterparty, group);
  }
  return [...grouped].map(([party, items]) => ({ party, count: items.length, outstanding: sumMoney(items.map(r => r.outstanding)) }))
    .sort((a, b) => {
      const left = cents(a.outstanding), right = cents(b.outstanding);
      if (left === null) return right === null ? a.party.localeCompare(b.party) : -1;
      if (right === null) return 1;
      return left === right ? a.party.localeCompare(b.party) : left > right ? -1 : 1;
    }).slice(0, 5);
}

/** Read-only projection. Money stays in BigInt cents; neither credits nor provider receipts are cash.
 * Typed financial dates determine quarter/month inclusion, never the source ingestion timestamp.
 */
export function businessPortfolio(data: Workspace) {
  const validAsOf = validDay(data.as_of);
  const end = validAsOf && data.as_of < QUARTER_END ? data.as_of : QUARTER_END;
  const supported = postedDocuments(data.sources).filter(s => documentViews.some(v => v.kind === s.kind));
  const undated = supported.filter(s => !documentDay(s) || !validDay(documentDay(s)!));
  const quarter = validAsOf ? supported.filter(s => {
    const day = documentDay(s);
    return day && validDay(day) && day >= QUARTER_START && day <= end;
  }) : [];
  const sourceDates = new Map(supported.filter(s => ['SalesInvoice', 'PurchaseInvoice'].includes(s.kind)).map(s => [s.document!.doc_id, documentDay(s)]));
  const currentBalances = (rows: Settlement[]) => unique(rows, r => r.doc_id).filter(r => {
    const day = sourceDates.get(r.doc_id);
    return !day || !validDay(day) || day <= data.as_of;
  });
  const sales = currentBalances(data.sales), purchases = currentBalances(data.purchases);
  const unknownAmounts = quarter.filter(s => cents(s.kind === 'Receipt' || s.kind === 'Payment' ? s.document?.amount : s.document?.net) === null).length;
  const amounts = totals(quarter);
  // Undated records cannot be assigned to a period; a zero would imply certainty we do not have.
  for (const view of documentViews) {
    if (!validAsOf || undated.some(s => s.kind === view.kind)) {
      const key = ({ SalesInvoice: 'sales', PurchaseInvoice: 'purchases', SalesCreditNote: 'salesCredits',
        PurchaseCreditNote: 'purchaseCredits', Receipt: 'cashIn', Payment: 'cashOut' } as const)[view.kind];
      amounts[key] = null;
    }
  }
  amounts.netSales = subtract(amounts.sales, amounts.salesCredits);
  amounts.netPurchases = subtract(amounts.purchases, amounts.purchaseCredits);
  return {
    validAsOf, end, totals: amounts, undated: undated.length, unknownAmounts,
    months: ['2026-07', '2026-08', '2026-09'].map(month => {
      const start = `${month}-01`, last = month === '2026-09' ? QUARTER_END : `${month}-31`;
      const through = end < last ? end : last;
      const values = totals(quarter.filter(s => documentDay(s)!.startsWith(month)));
      const observed = validAsOf && start <= end;
      return { month, start, through, observed,
        cashIn: observed && !undated.some(s => s.kind === 'Receipt') ? values.cashIn : null,
        cashOut: observed && !undated.some(s => s.kind === 'Payment') ? values.cashOut : null };
    }),
    aging: agingBuckets.map(bucket => ({ ...bucket,
      clients: sumMoney(sales.filter(r => ageBucket(r, data.as_of) === bucket.id && (cents(r.outstanding) ?? 1n) > 0n).map(r => r.outstanding)),
      suppliers: sumMoney(purchases.filter(r => ageBucket(r, data.as_of) === bucket.id && (cents(r.outstanding) ?? 1n) > 0n).map(r => r.outstanding)),
    })),
    clients: rankParties(sales), suppliers: rankParties(purchases),
    mix: documentViews.map(view => ({ ...view, count: quarter.filter(s => s.kind === view.kind).length })),
  };
}

/** Only the bounded visual ratio becomes a Number, never the monetary total. */
export function barPercent(value: string | null, values: (string | null)[]): number {
  const amount = cents(value);
  const max = values.reduce<bigint>((largest, v) => { const n = cents(v); return n !== null && n > largest ? n : largest; }, 0n);
  return amount === null || amount <= 0n || max === 0n ? 0 : Number(amount * 10000n / max) / 100;
}
