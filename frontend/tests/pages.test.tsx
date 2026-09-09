import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Queue } from '../src/Queue';
import { Documents } from '../src/Documents';
import { Approvals } from '../src/Approvals';
import { Activity } from '../src/Activity';
import { Badge, Icon, money } from '../src/ui';
import { empty, filled, proposal, received, refusal } from './fixtures';

test('decimal presentation preserves cents and large exact amounts', () => {
  expect(money('12345678901234567890.01')).toBe('12,345,678,901,234,567,890.01 EUR');
  expect(money('0')).toBe('0.00 EUR'); expect(money('-1.2')).toBe('-1.20 EUR');
  render(<><Badge>neutral</Badge><Icon name="queue" /></>);
  expect(screen.getByText('neutral')).toHaveClass('neutral');
});

test('empty queue explains its disabled action', () => {
  render(<Queue data={empty()} busy={false} mutate={vi.fn()} />);
  expect(screen.getByRole('button', { name: /Run Strands/ })).toBeDisabled();
  expect(screen.getByText('Nothing to chase yet')).toBeInTheDocument();
});
test('queue shows source-backed figures and navigates only after graph succeeds', async () => {
  const mutate = vi.fn().mockResolvedValueOnce(false).mockResolvedValueOnce(true);
  location.hash = '/queue';
  render(<Queue data={filled()} busy={false} mutate={mutate} />);
  expect(screen.getByText('39 days overdue')).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: /Run Strands/ }));
  expect(location.hash).toBe('#/queue');
  await userEvent.click(screen.getByRole('button', { name: /Run Strands/ }));
  expect(mutate).toHaveBeenCalledWith('/reason'); expect(location.hash).toBe('#/approvals');
});
test('incomplete evidence and arrangements stay visibly held', () => {
  const data = refusal(); data.queue.blocked = [{ ...data.queue.ready[0], reason: 'a payment plan is being kept' }];
  render(<Queue data={data} busy={true} mutate={vi.fn()} />);
  expect(screen.getByText('Evidence held')).toBeInTheDocument();
  expect(screen.getByText('a payment plan is being kept')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Working…' })).toBeDisabled();
});

test('intake samples, validation, posting and error recovery use the mutation contract', async () => {
  const mutate = vi.fn().mockResolvedValueOnce(false).mockResolvedValue(true);
  render(<Documents data={empty()} route="/documents" busy={false} mutate={mutate} />);
  expect(screen.getByRole('button', { name: 'Read & post email' })).toBeDisabled();
  for (const sample of ['invoice', 'payment', 'supplier', 'refusal']) {
    await userEvent.click(screen.getByRole('button', { name: `Sample ${sample}` }));
  }
  expect(screen.getByLabelText(/Email headers/)).toHaveValue('ambiguous post');
  await userEvent.clear(screen.getByLabelText(/Email headers/));
  await userEvent.type(screen.getByLabelText(/Email headers/), 'new email');
  await userEvent.click(screen.getByRole('button', { name: 'Read & post email' }));
  expect(screen.getByLabelText(/Email headers/)).toHaveValue('new email');
  await userEvent.click(screen.getByRole('button', { name: 'Read & post email' }));
  expect(mutate).toHaveBeenLastCalledWith('/intake', { body: 'new email', replace_id: null });
  expect(screen.getByLabelText(/Email headers/)).toHaveValue('');
});
test('source deep links, filtering, literal text and correction are usable', async () => {
  const data = refusal(); const mutate = vi.fn().mockResolvedValue(true);
  data.sources.push({ ...data.sources[0], id: 'email:003', status: 'corrected', corrected_by: 'email:004', document: null });
  render(<Documents data={data} route="/documents?source=JN-4410" busy={false} mutate={mutate} />);
  expect(screen.getAllByText('<script>alert("text only")</script>')).toHaveLength(2);
  expect(document.querySelectorAll('script')).toHaveLength(0);
  await userEvent.selectOptions(screen.getByRole('combobox'), 'refused');
  expect(screen.queryByText('Corrected by email:004; original evidence retained.')).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'Correct source' }));
  expect(screen.getByLabelText(/Email headers/)).toHaveFocus();
  await userEvent.click(screen.getByRole('button', { name: 'Cancel correction' }));
  expect(screen.getByLabelText(/Email headers/)).toHaveValue('');
  await userEvent.click(screen.getByRole('button', { name: 'Correct source' }));
  await userEvent.click(screen.getByRole('button', { name: 'Read corrected source' }));
  expect(mutate).toHaveBeenCalledWith('/intake', { body: 'ambiguous payment', replace_id: 'email:002' });
  await userEvent.selectOptions(screen.getByRole('combobox'), 'corrected');
  expect(screen.getByText(/Corrected by email:004/)).toBeInTheDocument();
});
test('intake busy state disables posting', () => {
  render(<Documents data={empty()} route="/documents" busy={true} mutate={vi.fn()} />);
  expect(screen.getByRole('button', { name: 'Reading…' })).toBeDisabled();
});

test('draft requires review and exact fingerprint, with a failed retry and success', async () => {
  const mutate = vi.fn().mockResolvedValueOnce(false).mockResolvedValueOnce(true);
  render(<Approvals data={filled()} busy={false} mutate={mutate} />);
  const button = screen.getByRole('button', { name: /Approve exact draft/ });
  expect(button).toBeDisabled();
  await userEvent.click(screen.getByLabelText(/I reviewed this recipient/));
  await userEvent.click(button); expect(button).toBeEnabled();
  await userEvent.click(button);
  expect(mutate).toHaveBeenLastCalledWith('/approve', { fingerprint: 'a'.repeat(64) });
  expect(location.hash).toBe('#/activity');
});
test('a stored receipt prevents a second draft approval', () => {
  render(<Approvals data={received()} busy={false} mutate={vi.fn()} />);
  expect(screen.getByLabelText(/I reviewed/)).toBeDisabled();
  expect(screen.getByText(/already has a receipt/)).toBeInTheDocument();
});
test('empty and held approvals explain how to recover', () => {
  const { rerender } = render(<Approvals data={empty()} busy={false} mutate={vi.fn()} />);
  expect(screen.getByRole('link', { name: 'action queue' })).toBeInTheDocument();
  rerender(<Approvals data={refusal()} busy={false} mutate={vi.fn()} />);
  expect(screen.getByText(/Unresolved source evidence holds collections/)).toBeInTheDocument();
  expect(screen.getByText('Correct refused sources before proposing terms.')).toBeInTheDocument();
});
test('terms are read before separate approval and exact amounts stay visible', async () => {
  const data = proposal(); const mutate = vi.fn().mockResolvedValue(true);
  data.arrangements = [data.proposal!.plan!];
  render(<Approvals data={data} busy={false} mutate={mutate} />);
  await userEvent.selectOptions(screen.getByLabelText('Outstanding invoice'), 'JN-4410');
  await userEvent.type(screen.getByLabelText("Client's proposed terms"), '2026-09-20: 1260.00 EUR');
  await userEvent.click(screen.getByRole('button', { name: 'Read proposed terms' }));
  expect(mutate).toHaveBeenCalledWith('/arrangements/propose', { invoice_id: 'JN-4410', body: '2026-09-20: 1260.00 EUR' });
  expect(screen.getByRole('button', { name: 'Approve arrangement' })).toBeDisabled();
  await userEvent.click(screen.getByLabelText(/I approve these exact dates/));
  await userEvent.click(screen.getByRole('button', { name: 'Approve arrangement' }));
  expect(mutate).toHaveBeenCalledWith('/arrangements/approve', { fingerprint: 'b'.repeat(64) });
  expect(screen.getByText(/Stored with the books/)).toBeInTheDocument();
});
test('disputed proposal and busy/failed approvals do not report success', async () => {
  const data = proposal(); const mutate = vi.fn().mockResolvedValue(false);
  const { rerender } = render(<Approvals data={data} busy={false} mutate={mutate} />);
  await userEvent.click(screen.getByLabelText(/I approve these exact/));
  await userEvent.click(screen.getByRole('button', { name: 'Approve arrangement' }));
  expect(screen.getByLabelText(/I approve these exact/)).toBeChecked();
  data.proposal!.plan = null; data.proposal!.outcome = 'disputed';
  rerender(<Approvals data={data} busy={true} mutate={mutate} />);
  expect(screen.getByText('disputed')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Approve arrangement' })).not.toBeInTheDocument();
});
test('receipt history is honest about acceptance and absent arrival', () => {
  const data = received(); data.receipts[0].message_id = null; data.receipts[0].error = 'Unknown result';
  const { rerender } = render(<Activity data={data} />);
  expect(screen.getByText('Unproven · no real email sent')).toBeInTheDocument();
  expect(screen.getByRole('alert')).toHaveTextContent('Unknown result');
  expect(screen.getByText('No provider identifier')).toBeInTheDocument();
  rerender(<Activity data={empty()} />);
  expect(screen.getByText('No delivery attempts')).toBeInTheDocument();
});
