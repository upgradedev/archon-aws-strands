import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Incoming } from '../src/Incoming';
import * as api from '../src/api';
import type { IncomingConnection } from '../src/types';

vi.mock('../src/api', async original => ({ ...await original<typeof api>(), request: vi.fn() }));
const disconnected = (): IncomingConnection => ({ enabled: false, expires_at: null, path: '/api/incoming', scope: 'fictional-intake-only', events: [] });
const connected = (): IncomingConnection => ({ ...disconnected(), enabled: true, expires_at: '2026-09-15T12:00:00Z' });
beforeEach(() => { vi.mocked(api.request).mockReset().mockResolvedValue(disconnected()); });
function show(live = true) { return render(<Incoming session="owner-session" live={live} revision={0} />); }
async function authorize() { await userEvent.click(screen.getByRole('checkbox', { name: /I authorize automatic/ })); }

test('retained synthetic mode explains why automation is unavailable without making requests', () => {
  show(false);
  expect(screen.getByText(/Live intake is unavailable/)).toBeVisible();
  expect(api.request).not.toHaveBeenCalled();
  expect(screen.queryByRole('button', { name: 'Enable incoming documents' })).not.toBeInTheDocument();
});

test('configuration requires explicit consent and never sends a source or approval', async () => {
  const user = userEvent.setup();
  show(); await screen.findByText('Not connected');
  const enable = screen.getByRole('button', { name: 'Enable incoming documents' });
  expect(enable).toBeDisabled(); expect(screen.getByRole('button', { name: 'Revoke intake key' })).toBeDisabled();
  expect(screen.getByLabelText('Webhook endpoint')).toHaveValue(`${location.origin}/api/incoming`);
  vi.mocked(api.request).mockResolvedValueOnce({ ...connected(), token: 'ci-only-intake-capability' });
  await authorize(); await user.click(enable);
  expect(api.request).toHaveBeenLastCalledWith('/incoming/connection', 'owner-session', {
    action: 'enable', consent: 'fictional-intake', request_id: expect.any(String),
  });
  expect(screen.getByLabelText('Intake-only key')).toHaveValue('ci-only-intake-capability');
  expect(screen.getByLabelText('Intake-only key')).toHaveAttribute('type', 'password');
  expect(screen.getByRole('checkbox')).not.toBeChecked();
  expect(screen.getByRole('status')).toHaveTextContent('no mailbox is connected yet');
  await user.click(screen.getByRole('button', { name: 'Copy intake key' }));
  expect(await navigator.clipboard.readText()).toBe('ci-only-intake-capability');
  expect(JSON.stringify(localStorage)).not.toContain('ci-only-intake-capability');
  await user.click(screen.getByRole('button', { name: 'Hide key' }));
  expect(screen.queryByLabelText('Intake-only key')).not.toBeInTheDocument();
  expect(vi.mocked(api.request).mock.calls.every(call => call[0] === '/incoming/connection')).toBe(true);
});

test('uncertain enable retries the identical intent and double clicks cannot race', async () => {
  show(); await screen.findByText('Not connected'); await authorize();
  let fail!: (error: Error) => void;
  vi.mocked(api.request).mockImplementationOnce(() => new Promise((_resolve, reject) => { fail = reject; }));
  const enable = screen.getByRole('button', { name: 'Enable incoming documents' });
  fireEvent.click(enable); fireEvent.click(enable);
  expect(api.request).toHaveBeenCalledTimes(2);
  const original = vi.mocked(api.request).mock.calls[1][2];
  await act(async () => fail(new Error('Response lost')));
  expect(screen.getByRole('alert')).toHaveTextContent('Retry the same action');
  vi.mocked(api.request).mockResolvedValueOnce({ ...connected(), token: 'recovered-key' });
  await userEvent.click(enable);
  expect(vi.mocked(api.request).mock.calls[2][2]).toEqual(original);
  expect(screen.getByLabelText('Intake-only key')).toHaveValue('recovered-key');
});

test('rotation replaces the key and revoke clears it without cancelling accepted work', async () => {
  vi.mocked(api.request).mockResolvedValueOnce(connected());
  show(); await screen.findByText('Key active · sender setup required');
  await authorize();
  vi.mocked(api.request).mockResolvedValueOnce({ ...connected(), token: 'rotated-ci-key' });
  await userEvent.click(screen.getByRole('button', { name: 'Rotate intake key' }));
  expect(screen.getByLabelText('Intake-only key')).toHaveValue('rotated-ci-key');
  vi.mocked(api.request).mockResolvedValueOnce(disconnected());
  await userEvent.click(screen.getByRole('button', { name: 'Revoke intake key' }));
  expect(api.request).toHaveBeenLastCalledWith('/incoming/connection', 'owner-session', {
    action: 'disable', request_id: expect.any(String),
  });
  expect(screen.queryByLabelText('Intake-only key')).not.toBeInTheDocument();
  expect(screen.getByRole('status')).toHaveTextContent('Previously accepted jobs may still finish');
});

test('a superseded intent requires fresh consent and can recover with a new request ID', async () => {
  show(); await screen.findByText('Not connected'); await authorize();
  vi.mocked(api.request).mockRejectedValueOnce(new api.ApiError('Connection changed', 409));
  await userEvent.click(screen.getByRole('button', { name: 'Enable incoming documents' }));
  const refused = vi.mocked(api.request).mock.calls[1][2];
  expect(screen.getByRole('checkbox')).not.toBeChecked();
  expect(screen.getByRole('alert')).toHaveTextContent('authorize a new action');
  vi.mocked(api.request).mockResolvedValueOnce(connected());
  await userEvent.click(screen.getByRole('button', { name: 'Refresh connection' }));
  await screen.findByText('Key active · sender setup required'); await authorize();
  vi.mocked(api.request).mockResolvedValueOnce({ ...connected(), token: 'fresh-ci-key' });
  await userEvent.click(screen.getByRole('button', { name: 'Rotate intake key' }));
  expect(vi.mocked(api.request).mock.calls[3][2]).not.toEqual(refused);
  expect(screen.getByLabelText('Intake-only key')).toHaveValue('fresh-ci-key');
});

test('clipboard failure offers a manual path, and leaving the page discards the secret', async () => {
  const user = userEvent.setup();
  const view = show(); await screen.findByText('Not connected'); await authorize();
  vi.mocked(api.request).mockResolvedValueOnce({ ...connected(), token: 'memory-only-ci-key' });
  await user.click(screen.getByRole('button', { name: 'Enable incoming documents' }));
  vi.spyOn(navigator.clipboard, 'writeText').mockRejectedValueOnce(new Error('blocked'));
  await user.click(screen.getByRole('button', { name: 'Copy intake key' }));
  expect(screen.getByRole('status')).toHaveTextContent('Select and copy');
  fireEvent.focus(screen.getByLabelText('Intake-only key'));
  view.unmount(); vi.mocked(api.request).mockResolvedValueOnce(connected()); show();
  await screen.findByText('Key active · sender setup required');
  expect(screen.queryByLabelText('Intake-only key')).not.toBeInTheDocument();
});

test('connection read failure is recoverable and refreshed arrivals are source-review links', async () => {
  vi.mocked(api.request).mockRejectedValueOnce(new Error('Connection unavailable'));
  const view = show(); await screen.findByRole('alert');
  vi.mocked(api.request).mockResolvedValueOnce(connected());
  await userEvent.click(screen.getByRole('button', { name: 'Refresh connection' }));
  await screen.findByText('Key active · sender setup required');
  vi.mocked(api.request).mockResolvedValueOnce({ ...connected(), events: [
    { event_id: 'sender-invoice-100', job_id: 'job-1', status: 'completed', created_at: '2026-09-14T11:00:00Z' },
  ] });
  view.rerender(<Incoming session="owner-session" live revision={1} />);
  await screen.findByText('sender-invoice-100');
  expect(screen.getByRole('link', { name: 'Inspect source decisions →' })).toHaveAttribute('href', '#/records');
  expect(screen.getByText(/Completed means processing finished/)).toBeVisible();
  await userEvent.click(screen.getByText('Sender setup & retry contract'));
  expect(screen.getByText(/Your sender must retain unsent events/)).toBeVisible();
});

test('a delayed earlier read cannot overwrite a newer connection action', async () => {
  let finish!: (value: IncomingConnection) => void;
  const view = show(); await screen.findByText('Not connected');
  vi.mocked(api.request).mockImplementationOnce(() => new Promise(resolve => { finish = resolve as typeof finish; }));
  view.rerender(<Incoming session="owner-session" live revision={1} />);
  vi.mocked(api.request).mockResolvedValueOnce({ ...connected(), token: 'current-ci-key' });
  await authorize(); await userEvent.click(screen.getByRole('button', { name: 'Enable incoming documents' }));
  await act(async () => finish(disconnected()));
  expect(screen.getByText('Key active · sender setup required')).toBeVisible();
  expect(screen.getByLabelText('Intake-only key')).toHaveValue('current-ci-key');
});

test('a read that finishes after unmount is ignored', async () => {
  let finish!: (value: IncomingConnection) => void;
  vi.mocked(api.request).mockImplementationOnce(() => new Promise(resolve => { finish = resolve as typeof finish; }));
  const view = show(); view.unmount();
  await act(async () => finish(connected()));
  await waitFor(() => expect(screen.queryByText('Key active · sender setup required')).not.toBeInTheDocument());
});
