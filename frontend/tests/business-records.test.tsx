import { render, screen, within, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Documents } from '../src/Documents';
import { Dashboard } from '../src/Dashboard';
import { DraftEvidence } from '../src/DraftEvidence';
import { Queue } from '../src/Queue';
import { Reconciliation } from '../src/Reconciliation';
import { journeyState, Journey } from '../src/Journey';
import { reconciliation } from '../src/decision';
import { businessFixture } from './business-fixture';
import { empty } from './fixtures';

const mutate = vi.fn();

test.each([
  ['sales-invoices', 'Sales invoices', 'SI-001', 25], ['purchase-invoices', 'Purchase invoices', 'PI-001', 25],
  ['sales-credits', 'Sales credits', 'SC-001', 20], ['purchase-credits', 'Purchase credits', 'PC-001', 10],
  ['client-receipts', 'Client receipts', 'RC-001', 25], ['supplier-payments', 'Supplier payments', 'PAY-001', 25],
] as const)('typed view %s is bounded and opens retained evidence', (view, title, first, count) => {
  render(<Documents data={businessFixture()} busy={false} mutate={mutate} route={`/records?view=${view}`} />);
  expect(screen.getByRole('table', { name: title })).toBeInTheDocument();
  expect(document.querySelectorAll('tbody tr')).toHaveLength(count as number);
  expect(screen.getByRole('link', { name: first })).toHaveAttribute('href', expect.stringContaining('source=demo%3A'));
  expect(within(screen.getByRole('group', { name: 'Document views' })).getAllByRole('link')).toHaveLength(6);
  expect(within(screen.getByRole('group', { name: 'Record type' })).getAllByRole('link')).toHaveLength(5);
  expect(screen.getByText(/cannot execute a bank payment/)).toBeVisible();
});

test('pagination, search, dates and route changes do not leak stale filters', async () => {
  const data = businessFixture();
  const { rerender } = render(<Documents data={data} busy={false} mutate={mutate} route="/records?view=sales-invoices" />);
  await userEvent.click(screen.getByRole('button', { name: 'Next page' }));
  expect(screen.getByRole('link', { name: 'SI-026' })).toBeInTheDocument();
  expect(screen.queryByRole('link', { name: 'SI-001' })).not.toBeInTheDocument();
  await userEvent.type(screen.getByRole('searchbox'), 'SI-080');
  expect(screen.getByRole('link', { name: 'SI-080' })).toBeInTheDocument();
  expect(screen.getByRole('navigation', { name: 'Record pages' })).toHaveTextContent('Page 1 of 1');
  await userEvent.clear(screen.getByRole('searchbox'));
  fireEvent.change(screen.getByLabelText('From date'), { target: { value: '2026-09-01' } });
  fireEvent.change(screen.getByLabelText('To date'), { target: { value: '2026-09-09' } });
  expect(screen.getByRole('navigation', { name: 'Record pages' })).toHaveTextContent('1–25 of 26');
  rerender(<Documents data={data} busy={false} mutate={mutate} route="/records?view=sales-invoices&page=4" />);
  expect(screen.getByRole('link', { name: 'SI-080' })).toBeInTheDocument();
  rerender(<Documents data={data} busy={false} mutate={mutate} route="/records?view=sales-invoices" />);
  expect(screen.getByRole('link', { name: 'SI-001' })).toBeInTheDocument();
  expect(screen.getByLabelText('From date')).toHaveValue('');
});

test('invalid date ranges and no-result searches are explicit', () => {
  const { rerender } = render(<Documents data={businessFixture()} busy={false} mutate={mutate} route="/records?view=client-receipts&from=2026-09-10&to=2026-09-01" />);
  expect(screen.getByRole('alert')).toHaveTextContent('valid dates');
  expect(screen.getByText('No matching documents')).toBeVisible();
  rerender(<Documents data={businessFixture()} busy={false} mutate={mutate} route="/records?view=sales-invoices&from=bad" />);
  expect(screen.getByRole('alert')).toBeVisible();
});

test('a late retained source deep link opens its correct page, origin and linked invoice', () => {
  render(<Documents data={businessFixture()} busy={false} mutate={mutate} route="/records?source=demo%3A240" />);
  const selected = document.querySelector<HTMLDetailsElement>('[data-source-id="demo:240"]')!;
  expect(selected.open).toBe(true); expect(document.querySelectorAll('.source-list details')).toHaveLength(15);
  expect(within(selected).getByText(/Typed JSON fixture retained/)).toBeVisible();
  expect(within(selected).getByRole('link', { name: /Inspect linked invoice PI-010/ })).toHaveAttribute('href', '#/records?source=PI-010');
  expect(within(selected).queryByRole('link', { name: /Workspace/ })).not.toBeInTheDocument();
  expect(within(selected).getByText(/not a cash receipt or bank payment/)).toBeVisible();
});

test('client and supplier balance drilldowns use exact parties, age and server credits', async () => {
  const data = businessFixture();
  const { rerender } = render(<Documents data={data} busy={false} mutate={mutate} route="/records?view=sales&party=Client+1&filter=outstanding&age=31-60" />);
  expect(screen.getByRole('table')).toHaveTextContent('61.60 EUR');
  expect(screen.getByRole('columnheader', { name: 'Credited' })).toBeInTheDocument();
  expect(screen.getByRole('columnheader', { name: 'Settled · cash' })).toBeInTheDocument();
  expect(screen.getByRole('table')).not.toHaveTextContent('Client 2');
  await userEvent.click(screen.getByRole('button', { name: 'Closed balances' }));
  expect(screen.getByText('No invoices posted.')).toBeInTheDocument();
  rerender(<Documents data={data} busy={false} mutate={mutate} route="/records?view=purchases&party=Supplier+1&from=2026-07-01&to=2026-07-31" />);
  expect(screen.getByRole('table')).toHaveTextContent('PI-001');
});

test('dashboard widgets expose exact cash, partial month, source links and incomplete data', () => {
  const data = businessFixture();
  const { rerender } = render(<Dashboard data={data} stale={false} />);
  expect(screen.getByTestId('business-net-sales')).toHaveTextContent('7,800.00 EUR');
  expect(screen.getByTestId('business-cash-in')).toHaveTextContent('2,500.00 EUR');
  expect(screen.getByTestId('business-cash-out')).toHaveTextContent('1,500.00 EUR');
  expect(screen.getByTestId('business-sales-credits')).toHaveTextContent('not cash');
  expect(screen.getByRole('img', { name: /Recorded cash in/ })).toBeInTheDocument();
  expect(screen.getByRole('table', { name: /Monthly cash records/ })).toHaveTextContent('Through 2026-09-09');
  expect(screen.getByTestId('business-cash-out')).toHaveAttribute('href', '#/records?view=supplier-payments&from=2026-07-01&to=2026-09-09');
  expect(screen.getByRole('table', { name: /Document-type counts/ })).toHaveTextContent('80');
  delete data.sources[0].document!.issued;
  rerender(<Dashboard data={{ ...data }} stale />);
  expect(screen.getByText(/Incomplete reporting evidence/)).toBeVisible();
  expect(screen.getByTestId('business-net-sales')).toHaveTextContent('Unknown');
  rerender(<Dashboard data={empty()} stale={false} />);
  expect(screen.getAllByText('No posted invoices.')).toHaveLength(2);
});

test('party and aging drilldowns preserve the as-of cutoff without excluding older or undated balances', () => {
  const data = businessFixture();
  data.sources = data.sources.filter(s => s.kind === 'SalesInvoice').slice(0, 3);
  data.sales = data.sales.slice(0, 3).map(s => ({ ...s, counterparty: 'Cutoff client', due: '2026-10-01' }));
  data.purchases = [];
  data.sources[0].document!.issued = '2026-06-01';
  data.sources[1].document!.issued = '2026-09-10';
  delete data.sources[2].document!.issued;
  const { unmount } = render(<Dashboard data={data} stale={false} />);
  const partyLink = within(screen.getByRole('table', { name: 'Top clients' })).getByRole('link', { name: 'Cutoff client' });
  const route = partyLink.getAttribute('href')!.slice(1);
  expect(route).toContain('to=2026-09-09'); expect(route).not.toContain('from=');
  const agingLink = within(screen.getByRole('table', { name: /Open client and supplier balances/ })).getAllByRole('link')[0];
  expect(agingLink.getAttribute('href')).toContain('to=2026-09-09');
  unmount();
  render(<Documents data={data} busy={false} mutate={mutate} route={route} />);
  expect(screen.getByRole('table')).toHaveTextContent('SI-001');
  expect(screen.getByRole('table')).toHaveTextContent('SI-003');
  expect(screen.getByRole('table')).not.toHaveTextContent('SI-002');
  expect(screen.getByText(/without a known invoice issue date are included/)).toBeVisible();
});

test('duplicate journey prefills editable email rather than typed JSON and explains its origin', () => {
  const data = businessFixture();
  const submit = vi.fn();
  data.sources.find(s => s.kind === 'Receipt')!.document!.transfer_id = 'FIXTURE-BANK-1';
  render(<Documents data={data} busy={false} mutate={submit} route="/records?intake=open&journey=duplicate&invoice=SI-001" />);
  expect((screen.getByLabelText(/Email headers and body/) as HTMLTextAreaElement).value).toContain('Transfer ID: FIXTURE-BANK-1');
  expect(screen.getByText(/This editable remittance was reconstructed/)).toBeVisible();
  expect(submit).not.toHaveBeenCalled();
});

test('credit evidence is separate from cash in the draft and collection decision', () => {
  const data = businessFixture(); data.sales[0].outstanding = '0.00'; data.sales[0].credited = '74.00';
  render(<DraftEvidence data={data} invoiceId="SI-001" />);
  const evidence = screen.getByRole('region', { name: 'Draft ledger evidence' });
  expect(evidence).toHaveTextContent('Credited · not cash');
  expect(within(evidence).getByRole('link', { name: /Credit source · 12.40 EUR · not cash/ })).toHaveAttribute('href', '#/documents?source=demo%3A211');
  const decision = reconciliation(data, 'SI-001', false, Date.now());
  expect(decision.title).toBe('Closed with credit. No chase.');
  expect(decision.why).not.toContain('Posted receipts cover');
  expect(decision.before).toBeNull();
  expect(decision.href).toBe('#/records?q=SI-001');
});

test('selected native credit remains a credit in Queue, Reconciliation and guided evidence', () => {
  const data = businessFixture();
  data.queue.ready = [{ invoice_id: 'SI-001', client: 'Client 1', recipient: 'client1@fiction.example', outstanding: '61.60', currency: 'EUR', days_overdue: 39, reason: '' }];
  const { unmount } = render(<Queue data={data} busy={false} mutate={mutate} route="/workspace?invoice=SI-001&source=demo%3A211" />);
  expect(screen.getByRole('link', { name: /Sales credit · not cash · SC-001/ })).toBeInTheDocument();
  expect(document.querySelector('.arithmetic-trace')).toHaveTextContent('Credited · not cash');
  expect(document.querySelector('.source-preview')).toHaveTextContent('no AI extraction');
  unmount();
  const { unmount: end } = render(<Reconciliation data={data} invoice="SI-001" stale={false} />);
  expect(screen.getByTestId('reconciliation-decision')).toHaveTextContent('12.40 EUR credited (not cash)');
  expect(screen.queryByTestId('payment-change')).not.toBeInTheDocument();
  end();
  expect(journeyState(data, '/journey?invoice=SI-001').payments).toHaveLength(1);
  render(<Journey data={data} busy={false} stale={false} mutate={mutate} route="/journey?invoice=SI-001" reviewEpoch={0} loadEvidence={vi.fn()} />);
  expect(screen.getByRole('complementary', { name: 'Current case evidence' })).toHaveTextContent('Credited · not cash');
});
