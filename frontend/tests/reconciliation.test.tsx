import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { reconciliation, intakeLink } from '../src/decision';
import { Reconciliation, ReconciliationStart } from '../src/Reconciliation';
import { FileIntake, validateFileText } from '../src/FileIntake';
import { Documents } from '../src/Documents';
import { EvidenceBundle } from '../src/EvidenceBundle';
import { empty, filled, received, refusal } from './fixtures';

function paid() {
  const data = filled(); data.draft = null;
  data.sources.push({ id: 'email:002', kind: 'Receipt', status: 'posted', body: 'Payment with original identity',
    error: '', redactions: 0, at: '2026-09-09', document: { doc_id: 'RC-A', source_ref: 'email:002', settles: 'JN-4410', amount: '600.00', transfer_id: 'BANK-A' } });
  return data;
}
const decide = (data = paid(), stale = false) => reconciliation(data, 'JN-4410', stale, Date.now());

test('decision follows actual posted receipt and never treats a duplicate as more money', () => {
  const data = paid(); const decision = decide(data);
  expect(decision.title).toBe('Payment evidence changed the decision'); expect(decision.before).toBe('1860.00');
  data.sources.push({ ...data.sources[1], id: 'email:003', status: 'refused', error: 'Duplicate bank transfer' });
  data.holds = [data.sources[2]];
  expect(decide(data).title).toBe('Hold collection. Resolve the evidence.'); expect(decide(data).before).toBe('1860.00');
  data.holds = []; data.sources[2].status = 'resolved';
  data.sources[2].resolution = { decision: 'duplicate-payment', note: 'Compared supplied bank identity', duplicate_of: 'email:002', at: '2026-09-09' };
  expect(decide(data).balance!.outstanding).toBe('1260.00'); expect(decide(data).before).toBe('1860.00');
  render(<Reconciliation data={data} invoice="JN-4410" stale={false} />);
  expect(screen.getByTestId('payment-change')).toHaveTextContent('BANK-A');
  expect(screen.getByText(/Human resolution: duplicate-payment/)).toHaveTextContent('No additional payment posted');
});

test('change projection requires complete matching source amounts, with exact large cents', () => {
  const data = paid(); data.sources[1].document!.amount = '599.00'; expect(decide(data).before).toBeNull();
  data.sources[1].document!.amount = undefined; expect(decide(data).before).toBeNull();
  data.sources[1].document!.amount = '600.00'; data.sales[0].gross = '1859.00'; expect(decide(data).before).toBeNull();
  data.sales[0].gross = '999999999999999999.01'; data.sales[0].outstanding = '999999999999999399.01';
  expect(decide(data).before).toBe('999999999999999999.01');
});

test('stale, held, settled and arrangement decisions do not invite approval', () => {
  expect(decide(paid(), true).href).toBeNull();
  expect(decide(refusal()).href).toBe('#/records?filter=refused');
  const data = paid(); data.sales[0].outstanding = '0.00'; expect(decide(data).title).toBe('Settled in these books. No chase.');
  data.sales[0].outstanding = '1260.00'; data.queue.blocked = [{ ...data.queue.ready[0], reason: 'a payment plan is being kept' }];
  expect(decide(data).title).toBe('Collection is paused for this case');
  expect(decide(data).href).toContain('view=terms');
});

test('draft expiry and recorded outcomes retain their distinct next actions', () => {
  expect(decide(filled()).href).toBe('#collection-draft');
  expect(decide(received()).href).toBe('#/history');
  const data = filled(); data.draft!.at = new Date(Date.now() - 1800001).toISOString();
  expect(decide(data).why).toContain('expired or its time is unavailable');
  data.draft!.at = 'unknown'; expect(decide(data).href).toBe('#prepare-current-draft');
  data.draft = null; expect(decide(data).title).toBe('Prepare a decision from these books');
});

test('missing and non-priority invoices never acquire a fabricated graph target', () => {
  expect(decide(empty()).href).toBe(intakeLink('invoice'));
  const data = paid(); data.sales.push({ ...data.sales[0], doc_id: 'OLDER', due: '2026-07-01' });
  expect(decide(data).title).toBe('Inspect evidence before collection'); expect(decide(data).href).toContain('OLDER');
  data.as_of = 'unknown'; expect(decide(data).href).toBe('#/records');
});

test('landing journey resumes an existing case and preserves the synthetic disclosure', () => {
  const { rerender } = render(<ReconciliationStart data={empty()} />);
  expect(screen.getByRole('link', { name: /Start reconciliation/ })).toHaveAttribute('href', intakeLink('invoice'));
  rerender(<ReconciliationStart data={filled()} />);
  expect(screen.getByRole('link', { name: /Continue reconciliation/ })).toHaveAttribute('href', expect.stringContaining('JN-4410'));
  expect(screen.getByText(/real Strands graph with scripted model/)).toBeVisible();
});

test('decision links focus the review without replacing the application route', async () => {
  const scroll = vi.fn(); Element.prototype.scrollIntoView = scroll;
  location.hash = '/workspace';
  const { rerender } = render(<><Reconciliation data={filled()} invoice="JN-4410" stale={false} /><section id="collection-draft" tabIndex={-1}>Exact draft</section></>);
  await userEvent.click(screen.getByRole('link', { name: /Review exact draft below/ }));
  expect(document.getElementById('collection-draft')).toHaveFocus(); expect(location.hash).toBe('#/workspace'); expect(scroll).toHaveBeenCalled();
  rerender(<Reconciliation data={filled()} invoice="JN-4410" stale={false} view="terms" />);
  expect(screen.getByRole('link', { name: /Open draft review/ })).toHaveAttribute('href', expect.stringContaining('view=draft'));
  rerender(<Reconciliation data={filled()} invoice="JN-4410" stale />);
  expect(screen.getByText(/Use Refresh in the top bar/)).toBeVisible();
});

test('guided intake fills reviewable evidence and duplicate retains the original bank identity', async () => {
  const mutate = vi.fn().mockResolvedValue(true); const data = paid();
  const { rerender } = render(<Documents key="invoice" data={empty()} busy={false} mutate={mutate} route="/records?intake=open&journey=invoice" />);
  expect(screen.getByLabelText(/Email headers/)).toHaveValue('synthetic invoice');
  rerender(<Documents key="payment" data={data} busy={false} mutate={mutate} route="/records?intake=open&journey=payment&invoice=JN-4410" />);
  expect(screen.getByLabelText(/Email headers/)).toHaveValue(data.samples.payment);
  rerender(<Documents key="duplicate" data={data} busy={false} mutate={mutate} route="/records?intake=open&journey=duplicate&invoice=JN-4410" />);
  expect(screen.getByLabelText(/Email headers/)).toHaveValue('Payment with original identity\nForwarded for reference.');
  expect(mutate).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole('button', { name: 'Read & post email' }));
  expect(mutate).toHaveBeenCalledWith('/intake', { body: 'Payment with original identity\nForwarded for reference.', replace_id: null });
  expect(screen.getByRole('link', { name: /Review changed decision/ })).toHaveAttribute('href', expect.stringContaining('JN-4410'));
  rerender(<Documents key="missing" data={empty()} busy={false} mutate={mutate} route="/records?intake=open&journey=duplicate&invoice=missing" />);
  expect(screen.getByLabelText(/Email headers/)).toHaveValue('');
});

test.each([
  [' ', 'empty'], ['x'.repeat(32001), 'intake limit'], ['\\'.repeat(20000), 'intake limit'],
  ['bad\u0000bytes', 'Binary'], ['Content-Type: multipart/mixed; boundary=A', 'multipart'],
  ['Content-Type: text/html', 'HTML'], ['Content-Transfer-Encoding: base64', 'Encoded'],
  ['Content-Transfer-Encoding: quoted-printable', 'Encoded'], ['Content-Disposition: attachment', 'supported'],
])('unsupported file text refuses before posting (%#)', (body, reason) => {
  expect(validateFileText(body)).toContain(reason);
});

test('file preview preserves literal text, requires explicit use, and does not post', async () => {
  const use = vi.fn(); const user = userEvent.setup();
  const { rerender } = render(<FileIntake disabled={false} onUse={use} />);
  await user.click(screen.getByText('Open a text email file'));
  const text = 'From: me@myjoinery.example\r\n\r\nInvoice <script>literal</script> EUR';
  await user.upload(screen.getByLabelText('Choose text email'), new File([text], 'invoice.eml'));
  const preview = await screen.findByRole('region', { name: 'File preview' });
  expect(within(preview).getByText(/Invoice <script>/)).toBeVisible(); expect(document.querySelector('script')).toBeNull(); expect(use).not.toHaveBeenCalled();
  rerender(<FileIntake disabled onUse={use} />);
  expect(screen.getByRole('button', { name: 'Use file text in editor' })).toBeDisabled();
  rerender(<FileIntake disabled={false} onUse={use} />);
  await user.click(screen.getByRole('button', { name: 'Use file text in editor' }));
  expect(use).toHaveBeenCalledWith(text); expect(screen.queryByRole('region')).not.toBeInTheDocument();
});

test('file selection errors leave the editor untouched and support correction', async () => {
  const use = vi.fn(); const user = userEvent.setup({ applyAccept: false });
  render(<FileIntake disabled={false} onUse={use} />);
  await user.click(screen.getByText('Open a text email file'));
  const input = screen.getByLabelText('Choose text email');
  for (const [file, error] of [
    [new File(['PDF'], 'invoice.pdf'), '.txt or plain-text .eml'],
    [new File(['x'.repeat(32001)], 'large.txt'), 'exceeds 32 KB'],
    [new File([new Uint8Array([0xff])], 'invalid.txt'), 'not UTF-8'],
    [new File([''], 'empty.txt'), 'empty'],
  ] as const) {
    await user.upload(input, file); await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent(error));
    expect(use).not.toHaveBeenCalled(); expect(screen.queryByRole('button')).not.toBeInTheDocument();
  }
  fireEvent.change(input, { target: { files: [] } }); expect(screen.queryByRole('alert')).not.toBeInTheDocument();
});

test('late file reads cannot replace a newer preview or cross a workspace unmount', async () => {
  const readers: FileReader[] = [];
  vi.spyOn(FileReader.prototype, 'readAsArrayBuffer').mockImplementation(function (this: FileReader) { readers.push(this); });
  const user = userEvent.setup(); const use = vi.fn();
  const { rerender } = render(<FileIntake key="first" disabled={false} onUse={use} />);
  await user.click(screen.getByText('Open a text email file'));
  await user.upload(screen.getByLabelText('Choose text email'), new File(['old'], 'old.txt'));
  await user.upload(screen.getByLabelText('Choose text email'), new File(['new'], 'new.txt'));
  async function finish(reader: FileReader, value: string) {
    Object.defineProperty(reader, 'result', { value: new TextEncoder().encode(value).buffer });
    await act(async () => reader.onload!(new ProgressEvent('load') as ProgressEvent<FileReader>));
  }
  await finish(readers[1], 'New source'); await finish(readers[0], 'Old source');
  expect(screen.getByText('New source')).toBeVisible(); expect(screen.queryByText('Old source')).not.toBeInTheDocument();
  await user.upload(screen.getByLabelText('Choose text email'), new File(['third'], 'third.txt'));
  rerender(<FileIntake key="second" disabled={false} onUse={use} />);
  await finish(readers[2], 'Previous workspace'); expect(screen.queryByText('Previous workspace')).not.toBeInTheDocument();
});

test('evidence copy preserves the exact durable bytes and offers a download when clipboard fails', async () => {
  const user = userEvent.setup(); const copy = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValueOnce(undefined).mockRejectedValueOnce(new Error('denied'));
  const text = 'Source hash: abc\nNo real email sent\n<literal>';
  render(<EvidenceBundle revision={8} load={async () => ({ revision: 8, commit: 'source-sha', text })} />);
  await user.click(screen.getByRole('button', { name: 'Prepare evidence bundle' }));
  await user.click(await screen.findByRole('button', { name: 'Copy readable evidence' }));
  expect(copy).toHaveBeenCalledWith(text); expect(screen.getByRole('status')).toHaveTextContent('revision 8');
  await user.click(screen.getByRole('button', { name: 'Copy readable evidence' }));
  expect(screen.getByRole('status')).toHaveTextContent('Clipboard unavailable');
  expect(screen.getByRole('link', { name: 'Download readable evidence' })).toHaveAttribute('href', `data:text/plain;charset=utf-8,${encodeURIComponent(text)}`);
});
