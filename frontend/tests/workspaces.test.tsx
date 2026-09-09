import { act, fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Dashboard } from '../src/Dashboard';
import { Queue } from '../src/Queue';
import { Approvals } from '../src/Approvals';
import { Documents } from '../src/Documents';
import { cents, decimal, sumMoney, draftState, dashboardMetrics, linkedSources, reasonTarget, routeInfo, validDay, workspaceLink } from '../src/ledger';
import { money } from '../src/ui';
import { empty, filled, proposal, received, refusal } from './fixtures';

test('exact money rejects missing, non-finite and fractional-cent values without inventing zero', () => {
  for (const invalid of [undefined, null, '', 'NaN', 'Infinity', 0, '1.001', '1e3']) expect(cents(invalid)).toBeNull();
  expect(cents('-1.2')).toBe(-120n); expect(cents('0')).toBe(0n);
  expect(decimal(-101n)).toBe('-1.01'); expect(sumMoney([])).toBe('0.00');
  expect(sumMoney(['12345678901234567890.01', '0.09'])).toBe('12345678901234567890.10');
  expect(sumMoney(['1.00', undefined])).toBeNull();
  expect(money(null)).toBe('Unknown'); expect(money('NaN')).toBe('Unknown');
  expect(validDay('2026-02-30')).toBe(false); expect(validDay('unknown')).toBe(false);
});

test('metrics distinguish all overdue debt from held work and derive receipts only from posted documents', () => {
  const data = filled();
  const receipt = { ...data.sources[0], id: 'actual-remittance', kind: 'Receipt', document: { doc_id: 'R-7', source_ref: 'actual-remittance', settles: 'JN-4410', amount: '600.00' } };
  data.sources.push(receipt, receipt, { ...receipt, id: 'refused', status: 'refused' }, { ...receipt, id: 'outgoing', kind: 'Payment' });
  data.queue.blocked = [{ ...data.queue.ready[0], reason: 'a payment plan is being kept' }]; data.queue.ready = [];
  const metrics = dashboardMetrics(data, Date.now());
  expect(metrics.find(m => m.id === 'outstanding')?.amount).toBe('1260.00');
  expect(metrics.find(m => m.id === 'overdue')?.amount).toBe('1260.00');
  expect(metrics.find(m => m.id === 'payments')?.amount).toBe('600.00');
  expect(linkedSources(data, 'JN-4410').map(s => s.id)).toEqual(['email:001', 'actual-remittance', 'outgoing']);
  expect(reasonTarget(data).id).toBeNull();
  render(<Dashboard data={data} stale />);
  expect(screen.getByText('Last known snapshot')).toBeInTheDocument();
  expect(screen.getByTestId('metric-overdue')).toHaveAttribute('href', '#/records?view=sales&filter=overdue');
  expect(screen.getByTestId('metric-payments')).toHaveAttribute('href', '#/records?view=payments');
});

test('unknown and duplicate balances never become fabricated totals', () => {
  const data = filled(); data.sales[0].outstanding = '';
  expect(dashboardMetrics(data, Date.now())[0].amount).toBeNull();
  expect(dashboardMetrics(data, Date.now())[1].amount).toBeNull();
  expect(reasonTarget(data).issue).toMatch(/incomplete or duplicated/);
  data.sales[0].outstanding = '1260.00'; data.sales.push(data.sales[0]);
  expect(dashboardMetrics(data, Date.now())[0].amount).toBeNull();
  expect(reasonTarget(data).id).toBeNull();
  data.sales = []; data.as_of = 'unknown';
  expect(dashboardMetrics(data, Date.now())[1].amount).toBeNull();
  expect(reasonTarget(data).issue).toMatch(/date is unavailable/);
});

test('backend target includes recipient-less priority and never substitutes a ready invoice', () => {
  const data = filled();
  data.sales.push({ ...data.sales[0], doc_id: 'OLDER', due: '2026-07-01', contact: '' });
  expect(reasonTarget(data)).toEqual({ id: 'OLDER', issue: expect.stringContaining('no recipient') });
  data.arrangements = [{ invoice_id: 'OLDER', agreed_on: '2026-09-09', baseline: '0.00', approved_by: 'visitor', instalments: [{ due: '2026-09-20', amount: '1260.00' }] }];
  expect(reasonTarget(data).issue).toMatch(/masks an arrangement/);
  expect(reasonTarget(data).id).toBeNull();
  data.arrangements = []; data.sales[1].contact = 'synthetic@example.test'; data.sales[1].due = data.sales[0].due;
  data.sales[1].outstanding = '999999999999999.00'; expect(reasonTarget(data).id).toBe('OLDER');
  data.sales.reverse(); data.sales[0].outstanding = '1.00'; expect(reasonTarget(data).id).toBe('JN-4410');
  data.sales[0].outstanding = '1260.00'; expect(reasonTarget(data).id).toBe('OLDER');
});

test('pending drafts are derived from expiry, holds and durable attempts, with unknown timestamps distinct', () => {
  const data = filled(); const now = Date.now(); data.draft!.at = new Date(now).toISOString();
  expect(draftState(empty(), now)).toBe('none'); expect(draftState(data, now)).toBe('pending');
  expect(dashboardMetrics(data, now).find(m => m.id === 'drafts')?.count).toBe(1);
  expect(draftState(data, now + 1800000)).toBe('expired');
  expect(dashboardMetrics(data, now + 1800000).find(m => m.id === 'drafts')?.count).toBe(0);
  data.draft!.at = 'unknown'; expect(draftState(data, now)).toBe('unavailable');
  expect(dashboardMetrics(data, now).find(m => m.id === 'drafts')?.count).toBeNull();
  data.draft!.at = new Date(now + 1000).toISOString(); expect(draftState(data, now)).toBe('unavailable');
  data.draft!.at = new Date(now).toISOString(); data.holds = refusal().holds;
  expect(draftState(data, now)).toBe('held'); expect(draftState(received(), now)).toBe('recorded');
});

test('Dashboard presents empty, held, unknown and recent activity without fake work', () => {
  const { rerender } = render(<Dashboard data={empty()} stale={false} />);
  expect(screen.getByText('No recorded activity')).toBeInTheDocument();
  expect(screen.getByTestId('metric-payments')).toHaveTextContent('0.00 EUR');
  const held = refusal(); held.activity.push({ id: 2, at: '2026-09-09', title: 'Second event', detail: 'actual event' });
  rerender(<Dashboard data={held} stale={false} />);
  expect(screen.getByText('Partial books · collections held')).toBeInTheDocument();
  expect(screen.getByTestId('metric-holds')).toHaveTextContent('1');
  expect(document.querySelector('.timeline li')).toHaveTextContent('Second event');
  expect(screen.getByRole('link', { name: /BACKEND PRIORITY/ })).toHaveAttribute('href', workspaceLink('JN-4410'));
});

test('route aliases and encoded context are retained with no arbitrary target action', () => {
  expect(routeInfo('/documents?source=email%3A001').page).toBe('records');
  expect(routeInfo('/approvals').page).toBe('workspace'); expect(routeInfo('/queue').page).toBe('workspace');
  expect(routeInfo('/activity').page).toBe('history'); expect(routeInfo('').page).toBe('dashboard');
  expect(workspaceLink('A/B', 'email:7', 'terms')).toBe('#/workspace?view=terms&invoice=A%2FB&source=email%3A7');
  const data = filled(); data.sales.push({ ...data.sales[0], doc_id: 'OTHER', due: '2026-08-03' });
  const { rerender } = render(<Queue data={data} busy={false} mutate={vi.fn()} route="/workspace?invoice=OTHER" />);
  expect(screen.getByText('Draft belongs to another invoice')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /Approve exact draft/ })).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: /Run Strands/ })).toBeDisabled();
  rerender(<Queue data={data} busy={false} mutate={vi.fn()} route="/workspace?invoice=missing" />);
  expect(screen.getByText('Selected invoice unavailable')).toBeInTheDocument();
  rerender(<Queue data={data} busy={false} mutate={vi.fn()} route="/workspace?invoice=JN-4410&source=foreign" />);
  expect(screen.getByText(/Selected source does not belong/)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /Run Strands/ })).toBeDisabled();
  expect(screen.getByRole('button', { name: /Approve exact draft/ })).toBeDisabled();
});

test('case source, stale state and terms selection expose only the selected decision', () => {
  const data = proposal(); const mutate = vi.fn();
  data.sources.push({ ...data.sources[0], kind: 'Receipt', id: 'receipt:7', body: 'actual received source', document: { doc_id: 'R-7', source_ref: 'receipt:7', settles: 'JN-4410', amount: '600.00' } });
  const { rerender } = render(<Queue data={data} busy={false} stale mutate={mutate} route="/workspace?invoice=JN-4410&source=receipt%3A7" />);
  expect(document.querySelector('.source-preview pre')).toHaveTextContent('actual received source');
  expect(screen.getByRole('button', { name: /Run Strands/ })).toBeDisabled();
  rerender(<Queue data={data} busy={false} mutate={mutate} route="/workspace?invoice=JN-4410&view=terms" />);
  expect(screen.getByLabelText('Outstanding invoice')).toHaveValue('JN-4410');
  expect(screen.queryByRole('button', { name: /Approve exact draft/ })).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Approve arrangement' })).toBeDisabled();
});

test('draft consent resets for changed revision, words, recipient and expiry, without editing stored body', async () => {
  const data = filled(); const mutate = vi.fn();
  const { rerender } = render(<Approvals data={data} busy={false} mutate={mutate} mode="draft" />);
  await userEvent.click(screen.getByLabelText(/I reviewed/));
  expect(screen.getByRole('button', { name: /Approve exact draft/ })).toBeEnabled();
  const revised = { ...data, revision: data.revision + 1 };
  rerender(<Approvals data={revised} busy={false} mutate={mutate} mode="draft" />);
  expect(screen.getByLabelText(/I reviewed/)).not.toBeChecked();
  await userEvent.click(screen.getByLabelText(/I reviewed/));
  revised.draft = { ...data.draft!, body: 'Changed exact stored body', recipient: 'different@example.test' };
  rerender(<Approvals data={revised} busy={false} mutate={mutate} mode="draft" />);
  expect(screen.getByLabelText(/I reviewed/)).not.toBeChecked();
  expect(document.querySelector('.email>pre')).toHaveTextContent('Changed exact stored body');
  revised.draft.at = new Date(Date.now() - 1800001).toISOString();
  rerender(<Approvals data={revised} busy={false} mutate={mutate} mode="draft" />);
  expect(screen.getByRole('button', { name: /Approve exact draft/ })).toBeDisabled();
  expect(screen.getByText(/This draft expired/)).toBeInTheDocument();
  revised.draft.at = 'unknown'; rerender(<Approvals data={revised} busy={false} mutate={mutate} mode="draft" />);
  expect(screen.getByText(/draft time is unavailable/)).toBeInTheDocument();
  expect(mutate).not.toHaveBeenCalled();
});

test('expiry timer and focus re-evaluate a checked draft while the page stays open', async () => {
  vi.useFakeTimers();
  try {
    const data = filled(); data.draft!.at = new Date(Date.now() - 1799000).toISOString();
    render(<Approvals data={data} busy={false} mutate={vi.fn()} mode="draft" />);
    fireEvent.click(screen.getByLabelText(/I reviewed/));
    expect(screen.getByRole('button', { name: /Approve exact draft/ })).toBeEnabled();
    await act(async () => { vi.advanceTimersByTime(1002); window.dispatchEvent(new Event('focus')); });
    expect(screen.getByRole('button', { name: /Approve exact draft/ })).toBeDisabled();
    expect(screen.getByLabelText(/I reviewed/)).not.toBeChecked();
  } finally { vi.useRealTimers(); }
});

test('arrangement input changes invalidate consent and a different case never receives a late proposal', async () => {
  const data = proposal(); data.proposal!.at = new Date().toISOString(); data.proposal!.body = '2026-09-20: 1260.00 EUR';
  const { rerender } = render(<Approvals data={data} busy={false} mutate={vi.fn()} mode="terms" selectedInvoice="JN-4410" />);
  await userEvent.click(screen.getByLabelText(/I approve these exact/));
  await userEvent.type(screen.getByLabelText("Client's proposed terms"), 'new terms');
  expect(screen.getByLabelText(/I approve these exact/)).not.toBeChecked();
  rerender(<Approvals data={data} busy={false} mutate={vi.fn()} mode="terms" selectedInvoice="OTHER" />);
  expect(screen.queryByRole('button', { name: 'Approve arrangement' })).not.toBeInTheDocument();
  expect(screen.getByRole('link', { name: /Open the stored proposal/ })).toHaveAttribute('href', workspaceLink('JN-4410', null, 'terms'));
  data.proposal!.at = new Date(Date.now() - 1800001).toISOString();
  rerender(<Approvals data={data} busy={false} mutate={vi.fn()} mode="terms" selectedInvoice="JN-4410" />);
  expect(screen.getByText(/These terms expired/)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Approve arrangement' })).toBeDisabled();
});

test('Records filters provide actual drilldowns, missing sources and scoped reporting', async () => {
  const data = filled();
  const { rerender } = render(<Documents data={data} busy={false} mutate={vi.fn()} route="/records?view=sales&filter=overdue" />);
  expect(screen.getByRole('table')).toHaveTextContent('JN-4410');
  rerender(<Documents data={data} busy={false} mutate={vi.fn()} route="/records?view=purchases&filter=outstanding&q=missing" />);
  expect(screen.getByText('No invoices posted.')).toBeInTheDocument();
  rerender(<Documents data={data} busy={false} mutate={vi.fn()} route="/records?view=payments" />);
  expect(screen.getByText('No matching receipts')).toBeInTheDocument();
  data.sources.push({ ...data.sources[0], kind: 'Receipt', id: 'R', document: { doc_id: 'R', source_ref: 'R', settles: 'JN-4410', amount: '600.00' } });
  rerender(<Documents data={data} busy={false} mutate={vi.fn()} route="/records?view=payments" />);
  expect(screen.getByRole('link', { name: /Inspect linked case/ })).toHaveAttribute('href', workspaceLink('JN-4410', 'R'));
  rerender(<Documents data={data} busy={false} mutate={vi.fn()} route="/records?view=ledger" />);
  expect(screen.getByText('Quarter ledger · 2026-07-01 to 2026-09-09')).toBeInTheDocument();
  rerender(<Documents data={data} busy={false} mutate={vi.fn()} route="/records?source=unknown" />);
  expect(screen.getByText(/Selected source is unavailable/)).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'Add synthetic email' }));
  expect(screen.getByLabelText(/Email headers/)).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'Close intake' }));
  expect(screen.queryByLabelText(/Email headers/)).not.toBeInTheDocument();
  expect(within(screen.getByRole('group', { name: 'Record type' })).getAllByRole('link')).toHaveLength(5);
});
