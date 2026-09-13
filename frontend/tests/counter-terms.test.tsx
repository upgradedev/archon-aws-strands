import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { CounterTerms, TermsHistory } from '../src/CounterTerms';
import { proposal, empty } from './fixtures';

test('counterproposal requires fresh consent and retains input after a refused request', async () => {
  const data = proposal(); const mutate = vi.fn().mockResolvedValueOnce(false).mockResolvedValue(true);
  const { rerender } = render(<CounterTerms data={data} disabled={false} mutate={mutate} />);
  await userEvent.click(screen.getByText('Offer different payment dates'));
  const input = screen.getByLabelText('Your counterproposal'); const confirm = screen.getByRole('checkbox');
  const record = screen.getByRole('button', { name: /Record counterproposal/ });
  expect(record).toBeDisabled(); await userEvent.type(input, '2026-09-25: 1260.00 EUR');
  await userEvent.click(confirm); expect(record).toBeEnabled();
  await userEvent.type(input, '\n'); expect(record).toBeDisabled();
  await userEvent.click(confirm); await userEvent.click(record);
  expect(input).toHaveValue('2026-09-25: 1260.00 EUR\n');
  expect(mutate).toHaveBeenCalledWith('/arrangements/counter', { fingerprint: data.proposal!.fingerprint, body: '2026-09-25: 1260.00 EUR\n' });
  rerender(<CounterTerms data={{ ...data, revision: 4 }} disabled={false} mutate={mutate} />);
  expect(confirm).not.toBeChecked(); expect(record).toBeDisabled();
  await userEvent.click(confirm); await userEvent.click(record); expect(input).toHaveValue('');
  rerender(<CounterTerms data={data} disabled={true} mutate={mutate} />);
  expect(input).toBeDisabled(); expect(record).toBeDisabled();
  rerender(<CounterTerms data={empty()} disabled={false} mutate={mutate} />);
  expect(screen.queryByText('Offer different payment dates')).not.toBeInTheDocument();
});

test('history distinguishes a counteroffer from agreement and retains literal original text', () => {
  const data = proposal();
  data.terms_history = [
    { decision: 'client-proposal', invoice_id: 'JN-4410', at: '2026-09-13', body: '2026-09-20: 1260.00 EUR' },
    { decision: 'owner-counterproposal', invoice_id: 'JN-4410', at: '2026-09-13', fingerprint: 'c'.repeat(64), body: '2026-09-25: 1260.00 EUR', original: { invoice_id: 'JN-4410', fingerprint: 'b'.repeat(64), body: '<script>original reply</script>' } },
    { decision: 'arrangement-approved', at: '2026-09-13', original: { invoice_id: 'OTHER-1', fingerprint: 'd'.repeat(64) } },
  ];
  const { rerender } = render(<TermsHistory data={data} invoice="JN-4410" />);
  expect(screen.getByText(/Counterproposal recorded/)).toBeInTheDocument();
  expect(screen.getByText('<script>original reply</script>')).toBeInTheDocument();
  expect(screen.queryByText(/Client terms approved/)).not.toBeInTheDocument();
  rerender(<TermsHistory data={data} />); expect(screen.getByText(/Client terms approved/)).toBeInTheDocument();
  expect(screen.getByText(/Original text unavailable/)).toBeInTheDocument();
  rerender(<TermsHistory data={data} invoice="absent" />); expect(screen.queryByRole('region')).not.toBeInTheDocument();
  rerender(<TermsHistory data={empty()} />); expect(screen.queryByRole('region')).not.toBeInTheDocument();
});
