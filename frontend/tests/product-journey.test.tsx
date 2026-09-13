import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { App } from '../src/App';
import { Journey, journeyState } from '../src/Journey';
import { Welcome } from '../src/Welcome';
import { empty, filled, received, refusal } from './fixtures';
import * as api from '../src/api';

vi.mock('../src/api', async original => ({ ...await original<typeof api>(), openWorkspace: vi.fn(), request: vi.fn(), storageWarning: '' }));
beforeEach(() => { location.hash = ''; Element.prototype.scrollIntoView = vi.fn(); vi.mocked(api.openWorkspace).mockReset().mockResolvedValue({ session: 'retained', workspace: filled() }); vi.mocked(api.request).mockReset().mockResolvedValue({ live: false }); });
async function navigate(hash: string) { await act(async () => { location.hash = hash; window.dispatchEvent(new HashChangeEvent('hashchange')); }); }
const evidence = async () => ({ revision: 3, commit: 'source', text: 'Retained source evidence' });
function paid() {
  const data = filled(); data.draft = null;
  data.sources.push({ id: 'email:002', body: 'Original remittance', kind: 'Receipt', status: 'posted', at: data.as_of, error: '', redactions: 0,
    document: { doc_id: 'RC-A', source_ref: 'email:002', settles: 'JN-4410', amount: '600.00', transfer_id: 'BANK-A' } });
  return data;
}
function show(data = empty(), route = '/journey', mutate = vi.fn().mockResolvedValue(true), stale = false, busy = false) {
  return { ...render(<Journey data={data} busy={busy} stale={stale} mutate={mutate} route={route} reviewEpoch={0} loadEvidence={evidence} />), mutate };
}

test('root explains the product without opening, creating or resetting a session', async () => {
  render(<App />);
  expect(screen.getByRole('heading', { name: /Chase the balance/ })).toHaveFocus();
  expect(screen.getByTestId('start-guided-example')).toHaveAttribute('href', '#/journey');
  expect(screen.getByRole('link', { name: /Continue my workspace/ })).toHaveAttribute('href', '#/dashboard');
  expect(api.openWorkspace).not.toHaveBeenCalled();
  expect(api.request).toHaveBeenCalledExactlyOnceWith('/providers', null);
  await navigate('/journey'); await screen.findByRole('heading', { name: 'From invoice to a safe decision' });
  expect(api.openWorkspace).toHaveBeenCalledExactlyOnceWith(false);
  await navigate('/welcome'); await navigate('/dashboard');
  expect(api.openWorkspace).toHaveBeenCalledTimes(1);
});

test('landing skip is keyboard focusable and the illustrative balance is not live state', async () => {
  render(<Welcome />); await userEvent.click(screen.getByRole('link', { name: 'Skip to introduction' }));
  expect(document.getElementById('welcome-main')).toHaveFocus();
  expect(screen.getByRole('complementary')).toHaveAccessibleName('Illustrative example, not your saved balances');
  expect(screen.getByText(/No real AI judgment/)).toBeVisible();
});

test('opening failure stays recoverable after leaving the fast landing', async () => {
  vi.mocked(api.openWorkspace).mockRejectedValueOnce(new api.ApiError('Session expired', 401));
  render(<App />); await navigate('/journey');
  await screen.findByRole('alert'); expect(screen.queryByText('No invoice posted yet')).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'Refresh durable state' }));
  await screen.findByRole('heading', { name: 'From invoice to a safe decision' });
  expect(api.openWorkspace).toHaveBeenCalledTimes(2);
});

test('steps are projections of evidence, not a stored success flag or a query bypass', () => {
  expect(journeyState(empty(), '/journey?step=result').step).toBe(0);
  const data = filled(); data.draft = null;
  expect(journeyState(data, '/journey').step).toBe(1);
  expect(journeyState(data, '/journey?step=review').step).toBe(2);
  expect(journeyState(filled(), '/journey').step).toBe(2);
  expect(journeyState(paid(), '/journey').step).toBe(2);
  expect(journeyState(received(), '/journey').step).toBe(3);
  expect(journeyState(received(), '/journey?step=payment').step).toBe(1);
  expect(journeyState(received(), '/journey?invoice=MISSING').missing).toBe(true);
  data.queue.ready = []; data.sales[0].due = '2027-01-01';
  expect(journeyState(data, '/journey').invoice).toBe('JN-4410');
});

test('invoice remains editable and only the explicit submit posts its exact raw text', async () => {
  const { mutate } = show(); const input = screen.getByLabelText('Email headers and plain-text body');
  expect(input).toHaveValue('synthetic invoice'); expect(mutate).not.toHaveBeenCalled();
  await userEvent.clear(input); await userEvent.type(input, 'My edited invoice');
  await userEvent.click(screen.getByRole('button', { name: 'Read & add invoice' }));
  expect(mutate).toHaveBeenCalledExactlyOnceWith('/intake', { body: 'My edited invoice', replace_id: null });
  expect(location.hash).toBe('#/journey');
});

test('unsupported text is refused before posting and corrected text clears the error', async () => {
  const { mutate } = show(); const input = screen.getByLabelText('Email headers and plain-text body');
  fireEvent.change(input, { target: { value: 'Content-Type: multipart/mixed; boundary=x' } });
  await userEvent.click(screen.getByRole('button', { name: 'Read & add invoice' }));
  expect(screen.getByRole('alert')).toHaveTextContent('not supported'); expect(mutate).not.toHaveBeenCalled();
  fireEvent.change(input, { target: { value: ' ' } }); expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Read & add invoice' })).toBeDisabled();
});

test('file preview is explicit, inserts literal text and does not post', async () => {
  const { mutate } = show();
  await userEvent.click(screen.getByText('Open a text email file'));
  await userEvent.upload(screen.getByLabelText('Choose text email'), new File(['Original <literal> invoice'], 'invoice.eml'));
  await userEvent.click(await screen.findByRole('button', { name: 'Use file text in editor' }));
  expect(screen.getByLabelText('Email headers and plain-text body')).toHaveValue('Original <literal> invoice');
  expect(mutate).not.toHaveBeenCalled();
});

test('failed or stale intake keeps the correction text and never advances', async () => {
  const mutate = vi.fn().mockResolvedValue(false); const { rerender } = show(empty(), '/journey', mutate);
  await userEvent.click(screen.getByRole('button', { name: 'Read & add invoice' }));
  expect(screen.getByLabelText('Email headers and plain-text body')).toHaveValue('synthetic invoice');
  expect(location.hash).toBe('');
  rerender(<Journey data={empty()} busy={false} stale mutate={mutate} route="/journey" reviewEpoch={1} loadEvidence={evidence} />);
  expect(screen.getByLabelText('Email headers and plain-text body')).toHaveValue('synthetic invoice');
  expect(screen.getByRole('button', { name: 'Read & add invoice' })).toBeDisabled();
  expect(screen.getByRole('region', { name: 'Guided check paused' })).toHaveTextContent('Reconnect');
});

test('late intake does not pull the user away from a different page', async () => {
  let finish!: (value: boolean) => void;
  const mutate = vi.fn(() => new Promise<boolean>(resolve => { finish = resolve; }));
  show(empty(), '/journey', mutate);
  await userEvent.click(screen.getByRole('button', { name: 'Read & add invoice' }));
  location.hash = '/history'; await act(async () => finish(true));
  expect(location.hash).toBe('#/history');
});

test('payment step uses the sample once; new evidence on a returning case starts blank', async () => {
  const data = filled(); data.draft = null;
  const { unmount, mutate } = show(data); expect(screen.getByLabelText('Email headers and plain-text body')).toHaveValue('synthetic payment');
  await userEvent.click(screen.getByRole('button', { name: 'Record payment & check balance' }));
  expect(mutate).toHaveBeenCalledWith('/intake', { body: 'synthetic payment', replace_id: null });
  expect(location.hash).toBe('#/journey?invoice=JN-4410'); unmount();
  show(paid(), '/journey?step=payment'); expect(screen.getByLabelText('Email headers and plain-text body')).toHaveValue('');
  expect(screen.getByRole('link', { name: /No payment to add/ })).toHaveAttribute('href', '#/journey?step=review&invoice=JN-4410');
});

test('another invoice cannot inherit the sample payment or a different draft', () => {
  const data = filled(); data.sales.push({ ...data.sales[0], doc_id: 'OTHER' });
  const { rerender } = show(data, '/journey?invoice=OTHER&step=payment');
  expect(screen.getByLabelText('Email headers and plain-text body')).toHaveValue('');
  rerender(<Journey data={data} busy={false} stale={false} mutate={vi.fn()} route="/journey?invoice=OTHER&step=review" reviewEpoch={0} loadEvidence={evidence} />);
  expect(screen.queryByRole('button', { name: /Approve exact draft/ })).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: /Run Strands/ })).toBeDisabled();
  expect(screen.getByRole('link', { name: 'Open the collection desk →' })).toBeVisible();
});

test('held or unavailable case never invites posting or approval', () => {
  const { rerender } = show(refusal());
  expect(screen.getByRole('region', { name: 'Guided check paused' })).toHaveTextContent('could not be posted');
  expect(screen.queryByRole('button')).not.toBeInTheDocument();
  rerender(<Journey data={filled()} busy={false} stale={false} mutate={vi.fn()} route="/journey?invoice=absent" reviewEpoch={0} loadEvidence={evidence} />);
  expect(screen.getByRole('region', { name: 'Guided check paused' })).toHaveTextContent('No different invoice has been selected silently');
  expect(screen.getByRole('link', { name: /Return to current check/ })).toHaveAttribute('href', '#/journey');
});

test('real graph action is explicit, and unavailable target stays disabled', async () => {
  const { mutate, rerender } = show(paid());
  await userEvent.click(screen.getByRole('button', { name: /Run Strands/ })); expect(mutate).toHaveBeenCalledWith('/reason');
  const unavailable = paid(); unavailable.sales[0].contact = '';
  rerender(<Journey data={unavailable} busy={false} stale={false} mutate={mutate} route="/journey" reviewEpoch={0} loadEvidence={evidence} />);
  expect(screen.getByRole('button', { name: /Run Strands/ })).toBeDisabled(); expect(screen.getByText(/no recipient/)).toBeVisible();
});

test('approval is exact, explicit, and returns to its own guided outcome', async () => {
  const { mutate } = show(filled());
  const approve = screen.getByRole('button', { name: /Approve exact draft/ }); expect(approve).toBeDisabled();
  await userEvent.click(screen.getByLabelText(/I reviewed this recipient/));
  await userEvent.click(approve);
  expect(mutate).toHaveBeenCalledWith('/approve', { fingerprint: 'a'.repeat(64) });
  expect(location.hash).toBe('#/journey?step=result&invoice=JN-4410');
});

test('settled cases stop chasing and an expired draft has an explicit recovery action', () => {
  const settled = paid(); settled.sales[0].outstanding = '0.00';
  const { rerender } = show(settled);
  expect(screen.getByRole('heading', { name: 'Settled in these books. No chase.' })).toBeVisible();
  expect(screen.getByRole('button', { name: /Run Strands/ })).toBeDisabled();
  const expired = filled(); expired.draft!.at = new Date(Date.now() - 1800001).toISOString();
  rerender(<Journey data={expired} busy={false} stale={false} mutate={vi.fn()} route="/journey" reviewEpoch={0} loadEvidence={evidence} />);
  expect(screen.getByRole('button', { name: /Run Strands/ })).toBeEnabled();
  expect(screen.getByRole('button', { name: /Approve exact draft/ })).toBeDisabled();
});

test('new evidence explains review withdrawal without recreating the obsolete draft', () => {
  const data = paid();
  data.activity.push({ id: 2, at: data.as_of, title: 'Strands graph completed', detail: 'Reports' }, { id: 3, at: data.as_of, title: 'Email posted', detail: 'Payment' });
  show(data);
  expect(screen.getByRole('complementary', { name: 'Previous review invalidated' })).toHaveTextContent('previous confirmation does not carry');
  expect(screen.queryByRole('button', { name: /Approve exact draft/ })).not.toBeInTheDocument();
});

test('step changes focus the actual result while stable rerenders do not steal focus', () => {
  const { rerender } = show(filled());
  const done = received();
  rerender(<Journey data={done} busy={false} stale={false} mutate={vi.fn()} route="/journey" reviewEpoch={0} loadEvidence={evidence} />);
  const heading = screen.getByRole('heading', { name: 'Your decision is recorded.' });
  expect(heading).toHaveFocus(); expect(heading.scrollIntoView).toHaveBeenCalledWith({ block: 'start' });
  const link = screen.getByRole('link', { name: 'Return to overview →' }); link.focus();
  rerender(<Journey data={done} busy={false} stale={false} mutate={vi.fn()} route="/journey" reviewEpoch={0} loadEvidence={evidence} />);
  expect(link).toHaveFocus();
});

test.each(['provider-accepted', 'unknown', 'failed', 'unrecognized'])('outcome %s never claims real delivery or recovery of debt', async state => {
  const data = received(); data.receipts[0].state = state;
  const { mutate } = show(data);
  const outcome = screen.getByRole('region', { name: 'Guided check outcome' });
  expect(outcome).toHaveTextContent(`Simulated · ${state}`); expect(outcome).toHaveTextContent('No real email was sent');
  expect(outcome).toHaveTextContent('1,260.00 EUR');
  expect(screen.queryByRole('button', { name: /Approve exact draft/ })).not.toBeInTheDocument();
  await userEvent.click(within(outcome).getByRole('button', { name: 'Prepare evidence bundle' }));
  await waitFor(() => expect(screen.getByRole('link', { name: 'Download readable evidence' })).toBeVisible());
  expect(mutate).not.toHaveBeenCalled();
});
