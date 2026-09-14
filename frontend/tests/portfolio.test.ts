import { ageBucket, barPercent, businessPortfolio, documentDay, documentParty, pageOf, partyIndex, postedDocuments, recordDay, sourceOrigin } from '../src/portfolio';
import { businessFixture } from './business-fixture';
import { empty } from './fixtures';

test('quarter totals count typed postings once, deduct net credits, and keep cash separate', () => {
  const data = businessFixture();
  data.sources.push(data.sources[0], { ...data.sources[0], id: 'refused', status: 'refused' });
  data.receipts.push({ fingerprint: 'approval', state: 'provider-accepted', amount: '99999.00', invoice_id: 'SI-001', to_address: 'fiction@example.test', at: data.as_of, message_id: null, error: null });
  const result = businessPortfolio(data);
  expect(result.totals).toEqual({ sales: '8000.00', purchases: '5000.00', salesCredits: '200.00', purchaseCredits: '100.00', netSales: '7800.00', netPurchases: '4900.00', cashIn: '2500.00', cashOut: '1500.00' });
  expect(result.mix.map(r => r.count)).toEqual([80, 50, 20, 10, 50, 30]);
  expect(result.months.map(m => [m.cashIn, m.cashOut])).toEqual([['850.00', '500.00'], ['850.00', '500.00'], ['800.00', '500.00']]);
  expect(result.months[2].through).toBe('2026-09-09');
  expect(result.clients).toHaveLength(5); expect(result.suppliers).toHaveLength(5);
  expect(postedDocuments(data.sources)).toHaveLength(240);
});

test('financial dates, not ingestion time, bound quarter reporting and unobserved months', () => {
  const data = businessFixture();
  const receipt = data.sources.find(s => s.kind === 'Receipt')!;
  receipt.document!.received_on = '2026-06-30';
  data.sources.find(s => s.kind === 'Payment')!.document!.paid_on = '2026-09-10';
  expect(businessPortfolio(data).totals.cashIn).toBe('2450.00');
  expect(businessPortfolio(data).totals.cashOut).toBe('1450.00');
  data.as_of = '2026-07-31';
  const result = businessPortfolio(data);
  expect(result.months[0].cashIn).toBe('800.00');
  expect(result.months[1]).toMatchObject({ observed: false, cashIn: null, cashOut: null });
  data.as_of = '2026-10-05';
  expect(businessPortfolio(data).end).toBe('2026-09-30');
  data.as_of = '2026-02-30';
  expect(businessPortfolio(data)).toMatchObject({ validAsOf: false, totals: { sales: null, cashIn: null } });
});

test('incomplete source amounts and dates are unknown rather than fabricated zero', () => {
  const data = businessFixture();
  delete data.sources[0].document!.issued;
  data.sources[80].document!.net = 'not-money';
  const result = businessPortfolio(data);
  expect(result).toMatchObject({ undated: 1, unknownAmounts: 1 });
  expect(result.totals).toMatchObject({ sales: null, netSales: null, purchases: null, netPurchases: null, cashIn: '2500.00' });
  delete data.sources.find(s => s.kind === 'Receipt')!.document!.received_on;
  expect(businessPortfolio(data).months.map(m => m.cashIn)).toEqual([null, null, null]);
  expect(businessPortfolio(empty()).totals.cashIn).toBe('0.00');
});

test('money remains exact beyond Number range; only bounded chart ratios are converted', () => {
  const data = empty(); const source = businessFixture().sources[0];
  source.document!.net = '12345678901234567890.01'; data.sources = [source];
  expect(businessPortfolio(data).totals.netSales).toBe('12345678901234567890.01');
  expect(barPercent('12345678901234567890.01', ['12345678901234567890.01'])).toBe(100);
  expect(barPercent('50.00', ['100.00', null, '1.00'])).toBe(50);
  for (const value of [null, '-1.00', '0.00']) expect(barPercent(value, [null, '0.00'])).toBe(0);
});

test('aging uses server outstanding after credits, with exact day boundaries and unknowns', () => {
  const row = businessFixture().sales[0];
  const dates = ['2026-09-10', '2026-09-09', '2026-09-08', '2026-08-10', '2026-08-09', '2026-07-11', '2026-07-10', 'bad'];
  expect(dates.map(due => ageBucket({ ...row, due }, '2026-09-09'))).toEqual(['current', 'current', '1-30', '1-30', '31-60', '31-60', '61-plus', 'unknown']);
  expect(ageBucket(row, 'bad')).toBe('unknown');
  const data = empty(); data.sales = [{ ...row, outstanding: '61.60', credited: '12.40' }];
  expect(businessPortfolio(data).aging.find(r => r.id === '31-60')!.clients).toBe('61.60');
  data.sales[0].outstanding = 'bad'; data.sales[0].due = 'bad';
  expect(businessPortfolio(data).aging.find(r => r.id === 'unknown')!.clients).toBeNull();
});

test('party ranking shows unknown balances explicitly and stable names for equal amounts', () => {
  const row = businessFixture().sales[0], data = empty();
  data.sales = ['Zulu', 'Alpha', 'Missing', 'Largest', 'Smallest'].map((counterparty, i) => ({ ...row, doc_id: String(i), counterparty, outstanding: ['10.00', '10.00', 'bad', '500.00', '1.00'][i] }));
  data.sales.push({ ...data.sales[2], doc_id: 'missing-2', counterparty: 'Absent', outstanding: 'bad' });
  expect(businessPortfolio(data).clients.map(r => r.party)).toEqual(['Absent', 'Missing', 'Largest', 'Alpha', 'Zulu']);
});

test('record dates, party references and provenance never imply an unrecorded AI extraction', () => {
  const data = businessFixture(), source = data.sources[0], receipt = data.sources.find(s => s.kind === 'Receipt')!;
  expect(documentDay(source)).toBe('2026-07-15');
  expect(documentDay(receipt)).toBe('2026-07-15');
  expect(documentParty(source, partyIndex(data))).toBe('Client 1');
  delete receipt.document!.client;
  expect(documentParty(receipt, partyIndex(data))).toBe('Client 1');
  expect(documentParty({ ...source, document: null }, new Map())).toBe('');
  expect(sourceOrigin(source)).toContain('no AI extraction');
  expect(sourceOrigin({ ...source, origin: 'fictional-demo-template' })).toContain('local rule');
  expect(sourceOrigin({ ...source, origin: 'bedrock-source-checks' })).toBe('Source origin: bedrock-source-checks');
  expect(sourceOrigin({ ...source, origin: undefined })).toContain('not recorded');
  expect(recordDay({ ...source, document: null })).toBe('2026-09-14');
});

test('pagination starts from independent offsets, clamps bad pages, and opens selected sources', () => {
  const rows = Array.from({ length: 80 }, (_, i) => `record-${101 + i}`);
  expect(pageOf(rows, '2')).toMatchObject({ start: 25, page: 2, pages: 4, total: 80 });
  expect(pageOf(rows, '2').rows[0]).toBe('record-126');
  expect(pageOf(rows, '99').rows).toEqual(['record-176', 'record-177', 'record-178', 'record-179', 'record-180']);
  expect(pageOf(rows, null, 79).page).toBe(4);
  for (const input of ['bad', '-2', '0', '1.5', '999999999999999999999999999999']) expect(pageOf(rows, input).page).toBe(1);
  expect(pageOf([], null)).toMatchObject({ page: 1, pages: 1, total: 0 });
});
