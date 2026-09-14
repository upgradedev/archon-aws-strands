import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { App } from '../src/App';
import { empty, filled, received } from './fixtures';
import * as api from '../src/api';

vi.mock('../src/api', async importOriginal => ({ ...await importOriginal<typeof api>(), openWorkspace: vi.fn(), request: vi.fn(), errorText: (error: Error) => error.message, storageWarning: '' }));
beforeEach(() => {
  vi.mocked(api.openWorkspace).mockReset().mockResolvedValue({ session: 'handle', workspace: filled() });
  vi.mocked(api.request).mockReset().mockResolvedValue(filled());
  location.hash = '/queue';
});
async function route(path: string) {
  await act(async () => { location.hash = path; window.dispatchEvent(new HashChangeEvent('hashchange')); });
}

test('tour explanations preserve unsaved input and never create a workspace or provider action', async () => {
  location.hash = '/records?intake=open';
  render(<App />);
  await screen.findByRole('heading', { name: 'Records', exact: true });
  const input = document.getElementById('raw-email') as HTMLTextAreaElement;
  await userEvent.type(input, 'My unsaved fictional invoice');
  await userEvent.click(screen.getByRole('button', { name: 'Take a tour' }));
  await userEvent.click(screen.getByRole('button', { name: 'Next stop' }));
  expect(document.getElementById('raw-email')).toHaveValue('My unsaved fictional invoice');
  expect(location.hash).toBe('#/records?intake=open');
  expect(api.openWorkspace).toHaveBeenCalledExactlyOnceWith(false);
  expect(api.request).not.toHaveBeenCalled();
  await userEvent.keyboard('{Escape}');
  expect(screen.queryByRole('region', { name: 'Product tour' })).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Take a tour' })).toHaveFocus();
  expect(document.getElementById('raw-email')).toHaveValue('My unsaved fictional invoice');
});

test.each(['queued', 'running', 'unknown'] as const)('tour stays read-only while a provider job is %s', async status => {
  location.hash = '/records';
  vi.mocked(api.openWorkspace).mockResolvedValueOnce({ session: 'handle', workspace: { ...filled(),
    live: { model: true, mail: true, data: 'fictional business examples',
      job: { id: 'pending-tour-job', operation: 'reason', status, created_at: new Date().toISOString() } } } });
  render(<App />);
  await screen.findByRole('heading', { name: 'Records', exact: true });
  await userEvent.click(screen.getByRole('button', { name: 'Take a tour' }));
  expect(screen.queryByRole('link', { name: 'Open Dashboard' })).not.toBeInTheDocument();
  expect(screen.getByText(/Page navigation is paused/)).toBeVisible();
  await userEvent.click(screen.getByRole('button', { name: 'Next stop' }));
  expect(screen.getByText(/You are on Records/)).toBeVisible();
  expect(location.hash).toBe('#/records');
  expect(api.request).not.toHaveBeenCalled();
});

test('tour removes optional navigation after the workspace becomes stale', async () => {
  location.hash = '/records';
  render(<App />);
  await screen.findByRole('heading', { name: 'Records', exact: true });
  await userEvent.click(screen.getByRole('button', { name: 'Take a tour' }));
  expect(screen.getByRole('link', { name: 'Open Dashboard' })).toBeVisible();
  fireEvent(window, new Event('offline'));
  expect(screen.queryByRole('link', { name: 'Open Dashboard' })).not.toBeInTheDocument();
  expect(screen.getByText(/Page navigation is paused/)).toBeVisible();
  expect(api.request).not.toHaveBeenCalled();
});

test('demo switching waits for old reads and keeps navigation actions locked while creating', async () => {
  let finishRead!: (result: { session: string; workspace: ReturnType<typeof empty> }) => void;
  let finishDemo!: (result: { session: string; workspace: ReturnType<typeof empty> }) => void;
  vi.mocked(api.openWorkspace).mockReset()
    .mockImplementationOnce(() => new Promise(resolve => { finishRead = resolve; }))
    .mockImplementationOnce(() => new Promise(resolve => { finishDemo = resolve; }));
  render(<App />);
  await route('/demo');
  expect(screen.getByRole('button', { name: 'Load demo workspace' })).toBeDisabled();
  await act(async () => finishRead({ session: 'old', workspace: empty() }));
  await userEvent.click(screen.getByRole('button', { name: 'Load demo workspace' }));
  expect(api.openWorkspace).toHaveBeenCalledTimes(2);
  await route('/dashboard');
  expect(screen.getByRole('button', { name: 'Refresh' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'New workspace' })).toBeDisabled();
  await act(async () => finishDemo({ session: 'demo', workspace: { ...empty(), demo_seed: 'joinery-v1' } }));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Refresh' })).toBeEnabled());
  expect(screen.getByRole('region', { name: 'Populated fictional demo' })).toBeVisible();
  expect(api.request).not.toHaveBeenCalled();
});

test('business demo notice never claims five emails or AI ingestion', async () => {
  location.hash = '/dashboard';
  vi.mocked(api.openWorkspace).mockResolvedValue({ session: 'business', workspace: { ...empty(), demo_seed: 'business-v1' } });
  render(<App />);
  const notice = await screen.findByRole('region', { name: 'Populated fictional demo' });
  expect(notice).toHaveTextContent('240 fictional typed source documents');
  expect(notice).toHaveTextContent('not AI-extracted');
  expect(notice).not.toHaveTextContent('Five fictional source emails');
  expect(api.request).not.toHaveBeenCalled();
});

test('small dashboard offers one explicit full portfolio load and never triggers a model or mail request', async () => {
  location.hash = '/dashboard';
  let finish!: (result: { session: string; workspace: ReturnType<typeof empty> }) => void;
  vi.mocked(api.openWorkspace).mockReset()
    .mockResolvedValueOnce({ session: 'small', workspace: { ...filled(), demo_seed: 'joinery-v1' } })
    .mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
  render(<App />);
  const upgrade = await screen.findByRole('button', { name: 'Load full dashboard · 240 records' });
  expect(api.openWorkspace).toHaveBeenCalledTimes(1);
  expect(screen.getByRole('region', { name: 'Full dashboard demo available' })).toHaveTextContent('current books stay available');
  await userEvent.dblClick(upgrade);
  expect(api.openWorkspace).toHaveBeenCalledTimes(2);
  expect(api.openWorkspace).toHaveBeenLastCalledWith(true, 'business');
  expect(upgrade).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Refresh' })).toBeDisabled();
  await act(async () => finish({ session: 'business', workspace: { ...empty(), demo_seed: 'business-v1' } }));
  expect(await screen.findByRole('region', { name: 'Current demo dataset' })).toHaveTextContent('Full business portfolio');
  expect(screen.queryByRole('region', { name: 'Full dashboard demo available' })).not.toBeInTheDocument();
  expect(api.request).not.toHaveBeenCalled();
});

test('a refused full portfolio load leaves the previous small books visible and retryable', async () => {
  location.hash = '/dashboard';
  vi.mocked(api.openWorkspace).mockReset()
    .mockResolvedValueOnce({ session: 'small', workspace: { ...filled(), demo_seed: 'joinery-v1' } })
    .mockRejectedValueOnce(new Error('Portfolio temporarily unavailable'));
  render(<App />);
  await userEvent.click(await screen.findByRole('button', { name: 'Load full dashboard · 240 records' }));
  expect(screen.getByRole('alert')).toHaveTextContent('Portfolio temporarily unavailable');
  expect(screen.getByTestId('metric-outstanding')).toHaveTextContent('1,260.00 EUR');
  expect(screen.getByRole('button', { name: 'Load full dashboard · 240 records' })).toBeEnabled();
  expect(screen.queryByRole('region', { name: 'Current demo dataset' })).not.toBeInTheDocument();
  expect(api.request).not.toHaveBeenCalled();
});

test.each(['queued', 'running', 'unknown'] as const)('full dashboard switching is blocked by a %s provider job', async status => {
  location.hash = '/dashboard';
  const workspace = { ...filled(), demo_seed: 'joinery-v1', live: { model: true, mail: true, data: 'fictional business examples',
    job: { id: 'pending-job', operation: 'reason', status, created_at: new Date().toISOString() } } };
  vi.mocked(api.openWorkspace).mockResolvedValueOnce({ session: 'small', workspace });
  render(<App />);
  const upgrade = await screen.findByRole('button', { name: 'Load full dashboard · 240 records' });
  expect(upgrade).toBeDisabled(); await userEvent.click(upgrade);
  expect(api.openWorkspace).toHaveBeenCalledTimes(1);
  expect(screen.getByRole('region', { name: 'Full dashboard demo available' })).toHaveTextContent('before switching');
});

test('offline small books cannot be switched and custom books are never silently seeded', async () => {
  location.hash = '/dashboard';
  vi.mocked(api.openWorkspace).mockResolvedValueOnce({ session: 'small', workspace: { ...filled(), demo_seed: 'joinery-v1' } });
  const mounted = render(<App />);
  await screen.findByRole('button', { name: 'Load full dashboard · 240 records' });
  fireEvent(window, new Event('offline'));
  expect(screen.getByRole('button', { name: 'Load full dashboard · 240 records' })).toBeDisabled();
  expect(api.openWorkspace).toHaveBeenCalledTimes(1);
  mounted.unmount();
  vi.mocked(api.openWorkspace).mockReset().mockResolvedValue({ session: 'custom', workspace: filled() });
  render(<App />); await screen.findByRole('heading', { name: 'Dashboard' });
  expect(screen.queryByRole('region', { name: 'Full dashboard demo available' })).not.toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Demo data' })).toHaveAttribute('href', '#/demo');
  expect(api.openWorkspace).toHaveBeenCalledExactlyOnceWith(false);
});

test('new workspace on History clears an existing evidence bundle at the same revision', async () => {
  location.hash = '/history';
  const state = empty();
  vi.mocked(api.openWorkspace).mockReset()
    .mockResolvedValueOnce({ session: 'old-handle', workspace: state })
    .mockResolvedValueOnce({ session: 'new-handle', workspace: empty() });
  vi.mocked(api.request).mockResolvedValueOnce({
    revision: 0, commit: 'old-backend', text: 'Evidence belonging only to old session',
  });
  render(<App />);
  await screen.findByRole('heading', { name: 'History' });
  await userEvent.click(screen.getByRole('button', { name: 'Prepare evidence bundle' }));
  await screen.findByRole('link', { name: 'Download readable evidence' });
  expect(api.request).toHaveBeenCalledWith('/evidence', 'old-handle');
  await userEvent.click(screen.getByRole('button', { name: 'New workspace' }));
  await userEvent.click(screen.getByRole('button', { name: 'Start new workspace' }));
  await waitFor(() => expect(api.openWorkspace).toHaveBeenCalledTimes(2));
  expect(screen.queryByRole('link', { name: 'Download readable evidence' })).not.toBeInTheDocument();
  expect(screen.queryByText('Evidence belonging only to old session')).not.toBeInTheDocument();
});
test('workspace starts, navigates deep links and skip link focuses main', async () => {
  render(<App />);
  await screen.findByRole('heading', { name: 'Workspace' });
  await userEvent.click(screen.getByText('Skip to workspace'));
  expect(document.getElementById('main')).toHaveFocus(); expect(location.hash).toBe('#/queue');
  await route('/documents?source=JN-4410'); expect(screen.getByRole('heading', { name: 'Records' })).toHaveFocus();
  await route('/approvals'); expect(screen.getByRole('heading', { name: 'Workspace' })).toBeInTheDocument();
  await route('/activity'); expect(screen.getByRole('heading', { name: 'History' })).toBeInTheDocument();
  await route('/missing'); expect(screen.getByRole('heading', { name: 'Page not found' })).toBeInTheDocument();
  await route(''); expect(screen.getByRole('heading', { name: /Chase the balance/ })).toBeInTheDocument();
});
test('initial loading and failed connection have a recoverable state', async () => {
  let reject!: (failure: Error) => void;
  vi.mocked(api.openWorkspace).mockImplementationOnce(() => new Promise((_resolve, fail) => { reject = fail; }));
  render(<App />); expect(screen.getByText('Opening your ledger')).toBeInTheDocument();
  await act(async () => reject(new Error('Network unavailable')));
  expect(screen.getByRole('alert')).toHaveTextContent('Network unavailable');
  await userEvent.click(screen.getByRole('button', { name: 'Refresh durable state' }));
  await screen.findByRole('heading', { name: 'Workspace' });
});
test('new workspace requires a concrete choice and refresh reads state', async () => {
  render(<App />); await screen.findByRole('heading', { name: 'Workspace' });
  await userEvent.click(screen.getByRole('button', { name: 'New workspace' }));
  await userEvent.click(screen.getByRole('button', { name: 'Keep current workspace' }));
  expect(screen.queryByText('Start an empty synthetic workspace?')).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'New workspace' }));
  vi.mocked(api.openWorkspace).mockResolvedValue({ session: 'new', workspace: empty() });
  await userEvent.click(screen.getByRole('button', { name: 'Start new workspace' }));
  expect(api.openWorkspace).toHaveBeenLastCalledWith(true);
  await userEvent.click(screen.getByRole('button', { name: 'Refresh' }));
  expect(api.openWorkspace).toHaveBeenLastCalledWith(false);
});
test('mutation failure blocks retry until refresh and then reuses the original intent id', async () => {
  location.hash = '/approvals';
  vi.mocked(api.request).mockRejectedValueOnce(new Error('Response lost')).mockResolvedValueOnce(received());
  render(<App />); await screen.findByRole('heading', { name: 'Workspace' });
  await userEvent.click(screen.getByLabelText(/I reviewed this recipient/));
  await userEvent.click(screen.getByRole('button', { name: /Approve exact draft/ }));
  expect(screen.getByRole('alert')).toHaveTextContent('Response lost');
  const firstIntent = vi.mocked(api.request).mock.calls[0][2];
  expect(screen.getByRole('button', { name: /Approve exact draft/ })).toBeDisabled();
  expect(api.request).toHaveBeenCalledTimes(1);
  await userEvent.click(screen.getByRole('button', { name: 'Refresh durable state' }));
  expect(screen.getByLabelText(/I reviewed this recipient/)).not.toBeChecked();
  await userEvent.click(screen.getByLabelText(/I reviewed this recipient/));
  await userEvent.click(screen.getByRole('button', { name: /Approve exact draft/ }));
  expect(api.request).toHaveBeenCalledTimes(2);
  expect(vi.mocked(api.request).mock.calls[1][2]).toEqual(firstIntent);
  expect(screen.getByRole('status')).toHaveTextContent('Saved to this workspace.');
});
test('busy action cannot race with refresh or a double click', async () => {
  let resolve!: (data: ReturnType<typeof filled>) => void;
  vi.mocked(api.request).mockImplementation(() => new Promise(r => { resolve = r as typeof resolve; }));
  render(<App />); await screen.findByRole('heading', { name: 'Workspace' });
  const button = screen.getByRole('button', { name: /Run Strands/ });
  fireEvent.click(button); fireEvent.click(button);
  expect(api.request).toHaveBeenCalledTimes(1);
  expect(screen.getByRole('button', { name: 'Refresh' })).toBeDisabled();
  await act(async () => resolve(filled()));
  await waitFor(() => expect(location.hash).toBe('#/workspace?view=draft&invoice=JN-4410&source=email%3A001'));
});

test.each([400, 422])('known validation refusal %s keeps intake editable and allocates a new corrected intent', async status => {
  location.hash = '/records?intake=open';
  vi.mocked(api.request).mockRejectedValueOnce(new api.ApiError('Correct the supplied field', status)).mockResolvedValueOnce(filled());
  render(<App />); await screen.findByRole('heading', { name: 'Records' });
  await userEvent.type(screen.getByLabelText(/Email headers/), 'invalid');
  await userEvent.click(screen.getByRole('button', { name: 'Read & post email' }));
  expect(screen.getByRole('alert')).toHaveTextContent('Correct the supplied field');
  expect(screen.getByLabelText(/Email headers/)).toBeEnabled();
  await userEvent.clear(screen.getByLabelText(/Email headers/));
  await userEvent.type(screen.getByLabelText(/Email headers/), 'corrected');
  await userEvent.click(screen.getByRole('button', { name: 'Read & post email' }));
  expect(api.request).toHaveBeenCalledTimes(2);
  expect(vi.mocked(api.request).mock.calls[1][2]).toMatchObject({ body: 'corrected' });
  expect((vi.mocked(api.request).mock.calls[1][2] as { request_id: string }).request_id).not.toBe((vi.mocked(api.request).mock.calls[0][2] as { request_id: string }).request_id);
});

test('search typing never remounts the field or steals focus; aliases and page changes retain context', async () => {
  location.hash = '/records?invoice=JN-4410&source=email%3A001';
  render(<App />); await screen.findByRole('heading', { name: 'Records' });
  const input = screen.getByRole('searchbox', { name: 'Search records' });
  await userEvent.type(input, 'BuildCo');
  await waitFor(() => expect(location.hash).toContain('q=BuildCo'));
  expect(screen.getByRole('searchbox')).toBe(input); expect(input).toHaveFocus();
  await route('/records?invoice=JN-4410&source=email%3A001&q=JN');
  expect(input).toHaveValue('JN'); expect(input).toHaveFocus();
  await route('/dashboard?invoice=JN-4410&source=email%3A001');
  expect(screen.getByRole('heading', { name: 'Dashboard' })).toHaveFocus();
  expect(screen.getByRole('navigation').querySelector('a[aria-label="Workspace"]')).toHaveAttribute('href', '#/workspace?view=draft&invoice=JN-4410&source=email%3A001');
  await route('/history?invoice=JN-4410&source=email%3A001&caseView=terms');
  expect(screen.getByRole('navigation').querySelector('a[aria-label="Workspace"]')).toHaveAttribute('href', '#/workspace?view=terms&invoice=JN-4410&source=email%3A001');
});

test('late reasoning completes durable state without navigating a different selected case', async () => {
  const data = filled(); data.sales.push({ ...data.sales[0], doc_id: 'OTHER', due: '2026-08-03' });
  vi.mocked(api.openWorkspace).mockResolvedValue({ session: 'handle', workspace: data });
  let finish!: (value: typeof data) => void;
  vi.mocked(api.request).mockImplementationOnce(() => new Promise(resolve => { finish = resolve as typeof finish; }));
  render(<App />); await screen.findByRole('heading', { name: 'Workspace' });
  await userEvent.click(screen.getByRole('button', { name: /Run Strands/ }));
  await route('/workspace?invoice=OTHER');
  await act(async () => finish(data));
  expect(location.hash).toBe('#/workspace?invoice=OTHER');
  expect(screen.getByText('Draft belongs to another invoice')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /Approve exact draft/ })).not.toBeInTheDocument();
});

test('offline and expired sessions show last known records and block mutations until refresh', async () => {
  render(<App />); await screen.findByRole('heading', { name: 'Workspace' });
  await act(async () => window.dispatchEvent(new Event('offline')));
  expect(screen.getByRole('alert')).toHaveTextContent('You are offline');
  expect(screen.getByRole('button', { name: /Run Strands/ })).toBeDisabled();
  vi.mocked(api.openWorkspace).mockRejectedValueOnce(new api.ApiError('Session expired', 401));
  await userEvent.click(screen.getByRole('button', { name: 'Refresh durable state' }));
  expect(screen.getByRole('alert')).toHaveTextContent('Session expired');
  await userEvent.click(screen.getByRole('button', { name: 'Refresh durable state' }));
  expect(screen.getByRole('button', { name: /Run Strands/ })).toBeEnabled();
});

test('new session clears intake text and correction context without resetting them on a query change', async () => {
  location.hash = '/records?intake=open';
  render(<App />); await screen.findByRole('heading', { name: 'Records' });
  await userEvent.type(screen.getByLabelText(/Email headers/), 'unfinished source');
  await route('/records?intake=open&q=invoice');
  expect(screen.getByLabelText(/Email headers/)).toHaveValue('unfinished source');
  vi.mocked(api.openWorkspace).mockResolvedValue({ session: 'new-handle', workspace: empty() });
  await userEvent.click(screen.getByRole('button', { name: 'New workspace' }));
  await userEvent.click(screen.getByRole('button', { name: 'Start new workspace' }));
  expect(screen.getByLabelText(/Email headers/)).toHaveValue('');
  expect(screen.getByText('No matching sources')).toBeInTheDocument();
});

test('late approval response does not navigate away from the user selected page', async () => {
  location.hash = '/workspace?invoice=JN-4410';
  let resolve!: (value: ReturnType<typeof received>) => void;
  vi.mocked(api.request).mockImplementationOnce(() => new Promise(done => { resolve = done as typeof resolve; }));
  render(<App />); await screen.findByRole('heading', { name: 'Workspace' });
  await userEvent.click(screen.getByLabelText(/I reviewed this recipient/));
  await userEvent.click(screen.getByRole('button', { name: /Approve exact draft/ }));
  await route('/records?invoice=OTHER');
  await act(async () => resolve(received()));
  expect(location.hash).toBe('#/records?invoice=OTHER');
  expect(screen.getByRole('heading', { name: 'Records' })).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /Approve exact draft/ })).not.toBeInTheDocument();
});
