import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Documents } from '../src/Documents';
import { EvidenceBundle, type Bundle } from '../src/EvidenceBundle';
import { Resolution } from '../src/Resolution';
import { Dashboard } from '../src/Dashboard';
import { empty, filled, refusal } from './fixtures';
import type { Source } from '../src/types';

test('three editable workflows retain a missing-identity source and require an explicit correction', async () => {
  const data = empty(); data.samples.payment = 'We paid 600 EUR\nTransfer ID: TEST-BANK-A';
  const mutate = vi.fn().mockResolvedValue(true);
  const { rerender } = render(<Documents data={data} route="/documents" busy={false} mutate={mutate} />);
  expect(screen.getByRole('button', { name: 'Correct held payment' })).toBeDisabled();
  await userEvent.click(screen.getByRole('button', { name: 'Try success' }));
  expect(screen.getByLabelText(/Email headers/)).toHaveValue(data.samples.invoice);
  await userEvent.click(screen.getByRole('button', { name: 'Try identity refusal' }));
  expect(screen.getByLabelText(/Email headers/)).toHaveValue('We paid 600 EUR');
  expect(mutate).not.toHaveBeenCalled();
  const held = refusal(data); held.holds[0].kind = 'Receipt';
  rerender(<Documents data={held} route="/documents" busy={false} mutate={mutate} />);
  await userEvent.click(screen.getByRole('button', { name: 'Correct held payment' }));
  expect(screen.getByLabelText(/Email headers/)).toHaveValue('ambiguous payment');
  await userEvent.type(screen.getByLabelText(/Email headers/), '\nTransfer ID: ACTUAL-SUPPLIED-A');
  await userEvent.click(screen.getByRole('button', { name: 'Read corrected source' }));
  expect(mutate).toHaveBeenCalledWith('/intake', { body: 'ambiguous payment\nTransfer ID: ACTUAL-SUPPLIED-A', replace_id: 'email:002' });
  expect(held.holds[0].body).toBe('ambiguous payment');
});

function heldSource(kind: string): Source {
  return { id: 'email:held', body: 'Retained original', kind, status: 'refused',
    error: 'Human reconciliation required', document: null, redactions: 0, at: '2026-09-09' };
}

test('duplicate resolution needs a selected posted receipt, reason and renewed consent', async () => {
  const data = filled(); const source = heldSource('Receipt');
  data.sources.push({ ...source, id: 'email:receipt', status: 'posted',
    document: { doc_id: 'RC-A', source_ref: 'email:receipt', amount: '600.00' } });
  const mutate = vi.fn().mockResolvedValueOnce(false).mockResolvedValueOnce(true);
  render(<Resolution source={source} data={data} busy={false} mutate={mutate} />);
  const button = screen.getByRole('button', { name: 'Record human resolution' });
  expect(button).toBeDisabled();
  await userEvent.selectOptions(screen.getByLabelText('Original posted receipt'), 'email:receipt');
  await userEvent.type(screen.getByLabelText('Resolution evidence and reason'), 'Compared the same bank event in original statement.');
  await userEvent.click(screen.getByRole('checkbox'));
  await userEvent.type(screen.getByLabelText('Resolution evidence and reason'), ' Checked.');
  expect(screen.getByRole('checkbox')).not.toBeChecked();
  await userEvent.click(screen.getByRole('checkbox')); await userEvent.click(button);
  expect(button).toBeEnabled();
  await userEvent.click(button);
  expect(mutate).toHaveBeenLastCalledWith('/resolve', expect.objectContaining({
    source_id: source.id, decision: 'duplicate-payment', duplicate_of: 'email:receipt', identities: null,
  }));
  expect(screen.getByRole('checkbox')).not.toBeChecked();
});

test('dispute resolution records an external decision without a payment dropdown', async () => {
  const mutate = vi.fn().mockResolvedValue(true);
  render(<Resolution source={heldSource('ClientReply')} data={filled()} busy={false} mutate={mutate} />);
  expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
  await userEvent.type(screen.getByLabelText('Resolution evidence and reason'), 'Client confirmed the completed work in our discussion.');
  await userEvent.click(screen.getByRole('checkbox'));
  await userEvent.click(screen.getByRole('button'));
  expect(mutate).toHaveBeenCalledWith('/resolve', expect.objectContaining({ decision: 'resume-collection' }));
});

test('generated legacy hold is visible and takes additive explicit references, never intake', async () => {
  const data = filled(); const source = heldSource('LegacyPaymentReview');
  source.legacy_documents = [{ doc_id: 'OLD-A', amount: '600.00' }, { doc_id: 'OLD-B', amount: '600.00' }];
  data.holds = [source]; const mutate = vi.fn().mockResolvedValue(true);
  render(<Documents data={data} route="/records?filter=refused" busy={false} mutate={mutate} />);
  expect(screen.getByText('Human reconciliation required')).toBeVisible();
  expect(screen.queryByRole('button', { name: 'Correct source' })).not.toBeInTheDocument();
  expect(screen.getByText(/not independently bank verified/)).toBeVisible();
  await userEvent.type(screen.getByLabelText(/Bank reference for OLD-A/), 'BANK-A');
  await userEvent.type(screen.getByLabelText(/Bank reference for OLD-B/), 'BANK-B');
  await userEvent.type(screen.getByLabelText('Resolution evidence and reason'), 'Two distinct supplied bank events checked with the operator.');
  await userEvent.click(screen.getByRole('checkbox'));
  await userEvent.click(screen.getByRole('button', { name: 'Record human resolution' }));
  expect(mutate).toHaveBeenCalledWith('/resolve', expect.objectContaining({
    decision: 'attest-legacy-payments', identities: { 'OLD-A': 'BANK-A', 'OLD-B': 'BANK-B' },
  }));
  expect(source.body).toBe('Retained original');
});

test('resolution consent is disabled during saving and reset when revision changes', async () => {
  const props = { source: heldSource('ClientReply'), data: filled(), mutate: vi.fn() };
  const { rerender } = render(<Resolution key="r1" {...props} busy={false} />);
  await userEvent.type(screen.getByLabelText('Resolution evidence and reason'), 'Human discussed the invoice and resolved the dispute.');
  await userEvent.click(screen.getByRole('checkbox'));
  rerender(<Resolution key="r1" {...props} busy={true} />);
  expect(screen.getByRole('button')).toBeDisabled();
  rerender(<Resolution key="r2" {...props} busy={false} />);
  expect(screen.getByRole('checkbox')).not.toBeChecked();
});

test('evidence export is read on demand, retryable, literal and revision scoped', async () => {
  const result: Bundle = { revision: 4, commit: 'checked-backend', text: '<script>literal evidence</script>' };
  const load = vi.fn().mockRejectedValueOnce(new Error('API unavailable')).mockResolvedValueOnce(result);
  const { rerender } = render(<EvidenceBundle revision={4} />);
  expect(screen.getByRole('button')).toBeDisabled();
  rerender(<EvidenceBundle revision={4} load={load} />);
  expect(load).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole('button'));
  expect(await screen.findByRole('alert')).toHaveTextContent('API unavailable');
  await userEvent.click(screen.getByRole('button'));
  await waitFor(() => expect(screen.getByRole('link', { name: 'Download readable evidence' })).toHaveAttribute('download', 'archon-evidence-r4.txt'));
  await userEvent.click(screen.getByText('Inspect evidence and limits'));
  expect(screen.getByText(result.text)).toBeVisible();
  expect(document.querySelector('script')).toBeNull();
  rerender(<EvidenceBundle revision={5} load={load} />);
  expect(screen.getByText(/Historical snapshot/)).toBeVisible();
});

test('a late evidence response cannot appear in a different session', async () => {
  let finish!: (value: Bundle) => void;
  const load = () => new Promise<Bundle>(resolve => { finish = resolve; });
  const { rerender } = render(<EvidenceBundle key="old-session" revision={1} load={load} />);
  await userEvent.click(screen.getByRole('button'));
  expect(screen.getByRole('button', { name: /Reading durable evidence/ })).toBeDisabled();
  rerender(<EvidenceBundle key="new-session" revision={0} load={load} />);
  await act(async () => finish({ revision: 1, commit: 'old', text: 'old session evidence' }));
  expect(screen.queryByText('old session evidence')).not.toBeInTheDocument();
  expect(screen.queryByRole('link')).not.toBeInTheDocument();
});

test('dashboard counts observed human resolutions while benefits remain unknown', () => {
  const data = filled(); data.resolutions = [{ decision: 'attest-legacy-payments', note: 'Reviewed', at: '2026-09-09' }];
  render(<Dashboard data={data} stale={false} />);
  expect(screen.getByText('Human resolutions').nextElementSibling).toHaveTextContent('1');
  expect(screen.getByText(/Human active time, time saved and money recovered: Unknown/)).toBeVisible();
});
