import type { Source } from '../src/types';
import { empty } from './fixtures';

// Independent UI fixture, not a copy of the backend seed generator or its amounts.
export function businessFixture() {
  const data = empty(); data.demo_seed = 'business-v1';
  const plans = [
    ['SalesInvoice', 'SI', 80], ['PurchaseInvoice', 'PI', 50], ['Receipt', 'RC', 50],
    ['Payment', 'PAY', 30], ['SalesCreditNote', 'SC', 20], ['PurchaseCreditNote', 'PC', 10],
  ] as const;
  for (const [kind, prefix, count] of plans) {
    for (let i = 1; i <= count; i++) {
      const id = `demo:${String(data.sources.length + 1).padStart(3, '0')}`;
      const doc_id = `${prefix}-${String(i).padStart(3, '0')}`;
      const supplier = kind === 'PurchaseInvoice' || kind === 'PurchaseCreditNote' || kind === 'Payment';
      const credit = kind.endsWith('CreditNote'), cash = kind === 'Receipt' || kind === 'Payment';
      const date = i % 3 === 0 ? '2026-09-09' : i % 3 === 1 ? '2026-07-15' : '2026-08-15';
      const party = `${supplier ? 'Supplier' : 'Client'} ${i % 7}`;
      const document: NonNullable<Source['document']> = { doc_id, source_ref: id,
        ...(supplier ? { supplier: party } : { client: party, client_email: `client${i % 7}@fiction.example` }),
        ...(cash ? { amount: '50.00', [kind === 'Receipt' ? 'received_on' : 'paid_on']: date }
          : { issued: date, due: i % 2 ? '2026-08-01' : '2026-10-01', net: credit ? '10.00' : '100.00', vat: credit ? '2.40' : '24.00', gross: credit ? '12.40' : '124.00' }),
        ...(cash || credit ? { settles: `${supplier ? 'PI' : 'SI'}-${String(i).padStart(3, '0')}` } : {}),
      };
      data.sources.push({ id, kind, document, status: 'posted', error: '', redactions: 0,
        at: '2026-09-14T00:00:00Z', origin: 'fictional-business-fixture', body: `Fictional typed JSON fixture, not email. ${JSON.stringify(document)}` });
      if (!cash && !credit) {
        const hasCash = i <= (supplier ? 30 : 50), hasCredit = i <= (supplier ? 10 : 20);
        (supplier ? data.purchases : data.sales).push({ doc_id, counterparty: party, contact: `party${i}@fiction.example`, gross: '124.00', due: document.due!, settled: hasCash ? '50.00' : '0.00', credited: hasCredit ? '12.40' : '0.00', outstanding: hasCash ? hasCredit ? '61.60' : '74.00' : '124.00' });
      }
    }
  }
  return data;
}
