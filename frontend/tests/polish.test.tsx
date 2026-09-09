import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { DraftEvidence } from '../src/DraftEvidence';
import { Documents } from '../src/Documents';
import { Approvals } from '../src/Approvals';
import type { Source } from '../src/types';
import { empty, filled } from './fixtures';

function postedReceipt(): Source {
  return { id: 'mail:receipt/7', status: 'posted', kind: 'Receipt', at: '2026-09-09',
    body: 'JN-4410 remittance: 600.00 EUR', error: '', redactions: 0,
    document: { doc_id: 'PAYMENT-7', source_ref: 'mail:receipt/7', settles: 'JN-4410', amount: '600.00' } };
}

test('evidence uses explicit posted invoice and receipt relationships, not matching prose', () => {
  const data = filled();
  const receipt = postedReceipt();
  data.sources.push(receipt,
    { ...receipt, id: 'unrelated', document: { ...receipt.document!, settles: 'OTHER' } },
    { ...receipt, id: 'refused', status: 'refused' },
    { ...receipt, id: 'corrected', status: 'corrected' },
    { ...receipt, id: 'payment-out', kind: 'Payment' },
    { ...receipt, id: 'no-document', document: null },
    { ...data.sources[0], id: 'other-invoice', document: { doc_id: 'OTHER', source_ref: 'other-invoice' } });
  render(<DraftEvidence data={data} invoiceId="JN-4410" />);
  const evidence = screen.getByRole('region', { name: 'Draft ledger evidence' });
  expect(within(evidence).getAllByRole('link')).toHaveLength(2);
  expect(within(evidence).getByRole('link', { name: /Invoice source/ })).toHaveAttribute('href', '#/documents?source=email%3A001');
  expect(within(evidence).getByRole('link', { name: /Receipt source · 600.00 EUR/ })).toHaveAttribute('href', '#/documents?source=mail%3Areceipt%2F7');
  for (const amount of ['1,860.00 EUR', '600.00 EUR', '1,260.00 EUR']) expect(within(evidence).getByText(amount)).toBeInTheDocument();
  expect(within(evidence).getByText(/not independent bank verification/)).toBeInTheDocument();
});

test('missing source relationships stay unavailable and never manufacture a badge', () => {
  const { rerender } = render(<DraftEvidence data={empty()} invoiceId="MISSING" />);
  expect(screen.getByText(/No current sales balance/)).toBeInTheDocument();
  expect(screen.getByText(/No linked posted invoice/)).toBeInTheDocument();
  expect(screen.getByText(/No linked posted receipt/)).toBeInTheDocument();
  expect(screen.queryByRole('link')).not.toBeInTheDocument();
  const data = filled(); const receipt = postedReceipt(); delete receipt.document!.amount;
  data.sources.push(receipt);
  rerender(<DraftEvidence data={data} invoiceId="JN-4410" />);
  const link = screen.getByRole('link', { name: 'Receipt source PAYMENT-7 mail:receipt/7' });
  expect(link).toHaveAttribute('href', '#/documents?source=mail%3Areceipt%2F7');
  expect(within(link).getByText('↗')).toHaveAttribute('aria-hidden', 'true');
});

test('source badge does not rewrite the exact draft or supply an approval', () => {
  const data = filled(); data.sources.push(postedReceipt());
  const mutate = vi.fn();
  render(<Approvals data={data} busy={false} mutate={mutate} />);
  expect(document.querySelector('.email > pre')!.textContent).toBe(data.draft!.body);
  expect(screen.getByRole('button', { name: /Approve exact draft/ })).toBeDisabled();
  expect(screen.getByText(/No message is sent/)).toBeInTheDocument();
  expect(mutate).not.toHaveBeenCalled();
});

test('actual source handle deep link opens the receipt, including after a reload render', () => {
  const data = filled(); data.sources.push(postedReceipt());
  const view = render(<Documents data={data} busy={false} mutate={vi.fn()} route="/documents?source=mail%3Areceipt%2F7" />);
  expect(document.querySelector('[data-source-id="mail:receipt/7"]')).toHaveAttribute('open');
  expect(document.querySelector('[data-source-id="email:001"]')).not.toHaveAttribute('open');
  view.unmount();
  render(<Documents data={data} busy={false} mutate={vi.fn()} route="/documents?source=mail%3Areceipt%2F7" />);
  expect(document.querySelector('[data-source-id="mail:receipt/7"]')).toHaveAttribute('open');
});

test('sample pill selection follows current text and native keyboard without posting', async () => {
  const mutate = vi.fn().mockResolvedValue(true);
  render(<Documents data={empty()} busy={false} mutate={mutate} route="/documents" />);
  const group = screen.getByRole('group', { name: 'Load a synthetic sample' });
  expect(within(group).getAllByRole('button', { pressed: false })).toHaveLength(4);
  within(group).getByRole('button', { name: 'Sample invoice' }).focus();
  await userEvent.keyboard('{Enter}');
  expect(within(group).getByRole('button', { pressed: true })).toHaveAccessibleName('Sample invoice');
  await userEvent.tab(); await userEvent.keyboard(' ');
  expect(within(group).getByRole('button', { pressed: true })).toHaveAccessibleName('Sample payment');
  expect(mutate).not.toHaveBeenCalled();
  const input = screen.getByLabelText(/Email headers/);
  await userEvent.type(input, ' edited');
  expect(within(group).queryByRole('button', { pressed: true })).not.toBeInTheDocument();
  await userEvent.click(within(group).getByRole('button', { name: 'Sample supplier' }));
  await userEvent.click(screen.getByRole('button', { name: 'Read & post email' }));
  expect(input).toHaveValue('');
  expect(within(group).queryByRole('button', { pressed: true })).not.toBeInTheDocument();
  expect(mutate).toHaveBeenCalledWith('/intake', { body: 'synthetic supplier', replace_id: null });
});
