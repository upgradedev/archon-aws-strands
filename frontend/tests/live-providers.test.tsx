import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ProviderJob, Workspace } from '../src/types';
import { ProviderStatus } from '../src/ProviderStatus';
import { Approvals } from '../src/Approvals';
import { Activity } from '../src/Activity';
import { Journey } from '../src/Journey';
import { Documents } from '../src/Documents';
import { Reconciliation, ReconciliationStart } from '../src/Reconciliation';
import { Dashboard } from '../src/Dashboard';
import { Welcome } from '../src/Welcome';
import { App } from '../src/App';
import { filled, received } from './fixtures';
import * as api from '../src/api';

vi.mock('../src/api', async importOriginal => ({ ...await importOriginal<typeof api>(),
  openWorkspace: vi.fn(), request: vi.fn(), storageWarning: '' }));

function withLive(value = filled(), status?: ProviderJob['status']): Workspace {
  value.live = { model: true, mail: true, data: 'fictional business examples',
    job: status ? { id: 'job-id', operation: 'reason', status, created_at: new Date().toISOString() } : null };
  return value;
}
beforeEach(() => {
  vi.mocked(api.openWorkspace).mockReset().mockResolvedValue({ session: 'handle', workspace: withLive() });
  vi.mocked(api.request).mockReset().mockResolvedValue({ live: true });
});
afterEach(() => vi.useRealTimers());

test.each(['queued', 'running', 'failed', 'unknown', 'completed'] as const)('provider state %s is explicit and never promises delivery', status => {
  const value = withLive(filled(), status);
  if (status === 'failed' || status === 'unknown') value.live!.job!.error = 'Manual review needed';
  if (status === 'completed') value.live!.job!.calls = [
    { call_id: 'one', status: 'completed', model_id: 'Bedrock', reserved_usd: '0.01', usage: { inputTokens: 100, outputTokens: 20 } },
    { call_id: 'two', status: 'unknown', model_id: 'Bedrock', reserved_usd: '0.02' },
  ];
  render(<ProviderStatus live={value.live!} />);
  expect(screen.getByRole('status')).toHaveTextContent(status);
  if (status === 'unknown') expect(screen.getByText(/Do not resend/)).toBeInTheDocument();
  if (status === 'completed') expect(screen.getByText(/100 input/)).toBeInTheDocument();
});

test('no job is honestly different from a completed model call', () => {
  render(<ProviderStatus live={withLive().live!} />);
  expect(screen.getByText(/No model call or send has been performed/)).toBeInTheDocument();
});

test('real approval requires fresh exact consent and shows actual action', async () => {
  const value = withLive();
  const mutate = vi.fn().mockResolvedValue(false);
  render(<Approvals data={value} busy={false} mutate={mutate} mode="draft" />);
  const button = screen.getByRole('button', { name: /send real email/ });
  expect(button).toBeDisabled();
  await userEvent.click(screen.getByLabelText(/I authorize this real email/));
  expect(button).toBeEnabled();
  expect(screen.getByText('Ready for your explicit real-email approval.')).toBeInTheDocument();
  await userEvent.click(button);
  expect(mutate).toHaveBeenCalledWith('/approve', { fingerprint: value.draft!.fingerprint, live_send_consent: 'real-email' });
});

test('history, guided result and operating pages use actual provider labels', () => {
  const value = withLive(received());
  const components = [
    <Activity key="history" data={value} />,
    <Journey key="journey" data={value} busy={false} stale={false} mutate={vi.fn()} route="/journey" reviewEpoch={0} loadEvidence={vi.fn()} />,
    <Dashboard key="dashboard" data={value} stale={false} />,
    <ReconciliationStart key="start" data={value} />,
    <Reconciliation key="case" data={value} invoice="JN-4410" stale={false} />,
    <Documents key="post" data={value} busy={false} mutate={vi.fn()} route="/records?intake=open" />,
  ];
  for (const component of components) {
    const view = render(component);
    expect(view.container).not.toHaveTextContent('No real email was sent');
    expect(view.container).not.toHaveTextContent('No live model call');
    view.unmount();
  }
});

test('live intake and draft preparation explain the semantic reader and real graph', () => {
  const value = withLive();
  value.draft = null;
  const view = render(<Journey data={value} busy={false} stale={false} mutate={vi.fn()} route="/journey?step=review" reviewEpoch={0} loadEvidence={vi.fn()} />);
  expect(view.container).toHaveTextContent('Runs real Bedrock and Strands');
  view.unmount();
  value.sales = [];
  render(<Journey data={value} busy={false} stale={false} mutate={vi.fn()} route="/journey" reviewEpoch={0} loadEvidence={vi.fn()} />);
  expect(screen.getByText(/Real semantic extraction/)).toBeInTheDocument();
});

test.each([true, false])('welcome reads real deployment mode %s without creating a session', async live => {
  vi.mocked(api.request).mockResolvedValue({ live });
  render(<Welcome />);
  await waitFor(() => expect(screen.queryByText(/Checking provider availability/)).not.toBeInTheDocument());
  expect(api.openWorkspace).not.toHaveBeenCalled();
  expect(screen.getByText(live ? /Real Bedrock AI · controlled real email/ : /Synthetic demo · scripted model/)).toBeInTheDocument();
});

test('unknown welcome status cannot silently claim a synthetic or live success', async () => {
  vi.mocked(api.request).mockRejectedValue(new Error('Offline'));
  const view = render(<Welcome />);
  await act(async () => {});
  expect(screen.getByText(/Provider status has not been confirmed/)).toBeInTheDocument();
  view.unmount();
});

test('a restored pending job is polled without another mutation', async () => {
  vi.useFakeTimers();
  location.hash = '/dashboard';
  vi.mocked(api.openWorkspace)
    .mockResolvedValueOnce({ session: 'handle', workspace: withLive(filled(), 'running') })
    .mockResolvedValueOnce({ session: 'handle', workspace: withLive(filled(), 'completed') });
  render(<App />);
  await act(async () => {});
  expect(screen.getByTestId('provider-status')).toHaveTextContent('running');
  await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
  expect(screen.getByTestId('provider-status')).toHaveTextContent('completed');
  expect(api.request).not.toHaveBeenCalled();
});

test.each(['completed', 'failed', 'unknown'] as const)('async mutation resolves as %s without replay', async status => {
  vi.useFakeTimers();
  location.hash = '/workspace?invoice=JN-4410';
  const initial = withLive();
  initial.draft = null;
  vi.mocked(api.openWorkspace).mockResolvedValue({ session: 'handle', workspace: initial });
  vi.mocked(api.request).mockResolvedValueOnce(withLive(filled(), 'queued'))
    .mockResolvedValueOnce(withLive(filled(), status));
  render(<App />);
  await act(async () => {});
  fireEvent.click(screen.getByRole('button', { name: /Run Strands/ }));
  await act(async () => {});
  expect(api.request).toHaveBeenCalledTimes(1);
  await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
  expect(api.request).toHaveBeenCalledTimes(2);
  expect(vi.mocked(api.request).mock.calls[1]).toEqual(['/workspace', 'handle']);
  expect(screen.getByTestId('provider-status')).toHaveTextContent(status);
});
