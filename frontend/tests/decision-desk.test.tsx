import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Reconciliation, ReconciliationStart } from '../src/Reconciliation';
import { Approvals } from '../src/Approvals';
import { Activity } from '../src/Activity';
import { reconciliation, reviewReset } from '../src/decision';
import { empty, filled, received, refusal } from './fixtures';

test('cold desk names its invented user, outcome, empty books and first explicit action', () => {
  render(<ReconciliationStart data={empty()} />);
  const desk = screen.getByRole('region', { name: 'Reconciliation journey' });
  expect(desk).toHaveTextContent("ALEX'S COLLECTIONS DESK");
  expect(desk).toHaveTextContent('self-employed joiner');
  expect(desk).toHaveTextContent('current balance, its source evidence and one safe next action');
  expect(desk).toHaveTextContent('Your books start empty');
  expect(within(desk).getByRole('link', { name: 'Start reconciliation' })).toHaveAttribute('href', '#/records?intake=open&journey=invoice&invoice=');
  expect(desk).toHaveTextContent('No real email or payment');
  expect(desk.querySelector('details')).not.toHaveAttribute('open');
});

test('returning desk follows pending, held, recorded and settled states instead of repeating onboarding', () => {
  const { rerender } = render(<ReconciliationStart data={filled()} />);
  const desk = screen.getByRole('region', { name: 'Reconciliation journey' });
  expect(desk).toHaveTextContent('Review this exact collection draft');
  expect(desk).toHaveTextContent('1,260.00 EUR');
  expect(desk).toHaveTextContent('1,860.00 EUR invoiced − 600.00 EUR recorded receipts');
  rerender(<ReconciliationStart data={refusal()} />);
  expect(desk).toHaveTextContent('Hold collection');
  expect(within(desk).getByRole('link', { name: 'Continue reconciliation' })).toHaveAttribute('href', '#/records?filter=refused');
  rerender(<ReconciliationStart data={received()} />);
  expect(within(desk).getByRole('link', { name: 'Continue reconciliation' })).toHaveAttribute('href', '#/history');
  const settled = filled(); settled.sales[0].outstanding = '0.00'; settled.sales[0].settled = '1860.00'; settled.draft = null;
  rerender(<ReconciliationStart data={settled} />);
  expect(desk).toHaveTextContent('Settled in these books. No chase.');
  expect(within(desk).getByRole('link', { name: 'Continue reconciliation' })).toHaveAttribute('href', '#/records?view=payments&q=JN-4410');
});

test('refused first source resumes resolution and stale desk focuses refresh without changing the route', async () => {
  Element.prototype.scrollIntoView = vi.fn(); location.hash = '/dashboard';
  const { rerender } = render(<ReconciliationStart data={refusal(empty())} />);
  expect(screen.getByRole('link', { name: 'Continue reconciliation' })).toHaveAttribute('href', '#/records?filter=refused');
  rerender(<><ReconciliationStart data={filled()} stale /><button id="refresh-workspace">Refresh</button></>);
  expect(screen.getByText('LAST KNOWN BALANCE')).toBeVisible();
  await userEvent.click(screen.getByRole('link', { name: /Refresh before continuing/ }));
  expect(screen.getByRole('button', { name: 'Refresh' })).toHaveFocus();
  expect(location.hash).toBe('#/dashboard');
});

test('durable review reset requires an observed graph followed by a material change', () => {
  const data = empty();
  const event = (id: number, title: string) => ({ id, title, at: '2026-09-12', detail: 'Retained event' });
  expect(reviewReset(data)).toBeNull();
  data.activity = [event(1, 'Email posted')]; expect(reviewReset(data)).toBeNull();
  data.activity.push(event(2, 'Strands graph completed')); expect(reviewReset(data)).toBeNull();
  data.activity.push(event(3, 'Email posted'), event(4, 'Email refused'), event(5, 'Unrelated event'));
  expect(reviewReset(data)?.id).toBe(4);
  const original = JSON.stringify(data.activity); reviewReset(data); expect(JSON.stringify(data.activity)).toBe(original);
  data.activity.push(event(6, 'Strands graph completed')); expect(reviewReset(data)).toBeNull();
  data.activity.push(event(7, 'Human resolution recorded')); expect(reviewReset(data)?.id).toBe(7);
  data.draft = filled().draft; expect(reviewReset(data)).toBeNull();
});

test('withdrawal explanation survives remount and never invents an old amount or approval', () => {
  const data = filled(); data.draft = null;
  data.activity.push({ id: 2, at: '2026-09-12', title: 'Strands graph completed', detail: 'Six readers' },
    { id: 3, at: '2026-09-12', title: 'Email posted', detail: 'email:002: RC-A' });
  const { rerender } = render(<Reconciliation key="first" data={data} invoice="JN-4410" stale={false} />);
  rerender(<Reconciliation key="reloaded" data={data} invoice="JN-4410" stale={false} />);
  const reset = screen.getByRole('complementary', { name: 'Previous review invalidated' });
  expect(reset).toHaveTextContent('Previous draft cannot be approved');
  expect(reset).toHaveTextContent('email:002: RC-A');
  expect(reset).not.toHaveTextContent('EUR');
  expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
});

test('missing recipient abstention opens the source while kept arrangements open their terms', () => {
  const data = filled(); data.draft = null;
  data.queue.blocked = [{ ...data.queue.ready[0], reason: 'no recipient address' }];
  let decision = reconciliation(data, 'JN-4410', false, Date.now());
  expect(decision.why).toContain('Do not guess'); expect(decision.why).not.toContain('payment promise');
  expect(decision.href).toBe('#/records?source=JN-4410');
  data.queue.blocked[0].reason = 'a payment plan is being kept';
  decision = reconciliation(data, 'JN-4410', false, Date.now());
  expect(decision.href).toContain('view=terms'); expect(decision.why).toContain('not the ledger balance');
});

test('simulated authority must be checked anew and success never claims collection or delivery', async () => {
  const mutate = vi.fn(); const data = filled();
  const { rerender } = render(<Approvals data={data} busy={false} mutate={mutate} mode="draft" />);
  const consent = screen.getByRole('checkbox', { name: /I authorize a simulated send only/ });
  const approve = screen.getByRole('button', { name: /Approve exact draft/ });
  expect(approve).toBeDisabled(); await userEvent.click(consent);
  expect(approve).toBeEnabled(); expect(screen.getByText(/Ready for your explicit simulated approval/)).toBeVisible();
  rerender(<Approvals data={{ ...data, revision: data.revision + 1 }} busy={false} mutate={mutate} mode="draft" />);
  expect(consent).not.toBeChecked(); expect(approve).toBeDisabled(); expect(mutate).not.toHaveBeenCalled();
  rerender(<Activity data={received()} />);
  const outcome = screen.getByRole('region', { name: 'Recorded collection outcome' });
  expect(outcome).toHaveTextContent('provider-accepted'); expect(outcome).toHaveTextContent('does not reduce the amount owed');
  expect(within(outcome).getByRole('link')).toHaveAttribute('href', expect.stringContaining('invoice=JN-4410'));
});
