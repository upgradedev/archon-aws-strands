import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { App } from '../src/App';
import { empty, filled, received } from './fixtures';
import * as api from '../src/api';

vi.mock('../src/api', () => ({ openWorkspace: vi.fn(), request: vi.fn(), errorText: (error: Error) => error.message, storageWarning: '' }));
beforeEach(() => {
  vi.mocked(api.openWorkspace).mockReset().mockResolvedValue({ session: 'handle', workspace: filled() });
  vi.mocked(api.request).mockReset().mockResolvedValue(filled());
  location.hash = '/queue';
});
async function route(path: string) {
  await act(async () => { location.hash = path; window.dispatchEvent(new HashChangeEvent('hashchange')); });
}
test('workspace starts, navigates deep links and skip link focuses main', async () => {
  render(<App />);
  await screen.findByRole('heading', { name: 'Action queue' });
  await userEvent.click(screen.getByText('Skip to workspace'));
  expect(document.getElementById('main')).toHaveFocus(); expect(location.hash).toBe('#/queue');
  await route('/documents?source=JN-4410'); expect(screen.getByRole('heading', { name: 'Documents & payments' })).toHaveFocus();
  await route('/approvals'); expect(screen.getByRole('heading', { name: 'Approvals & arrangements' })).toBeInTheDocument();
  await route('/activity'); expect(screen.getByRole('heading', { name: 'Activity & delivery' })).toBeInTheDocument();
  await route('/missing'); expect(screen.getByRole('heading', { name: 'Page not found' })).toBeInTheDocument();
  await route(''); expect(screen.getByRole('heading', { name: 'Action queue' })).toBeInTheDocument();
});
test('initial loading and failed connection have a recoverable state', async () => {
  let reject!: (failure: Error) => void;
  vi.mocked(api.openWorkspace).mockImplementationOnce(() => new Promise((_resolve, fail) => { reject = fail; }));
  render(<App />); expect(screen.getByText('Opening your ledger')).toBeInTheDocument();
  await act(async () => reject(new Error('Network unavailable')));
  expect(screen.getByRole('alert')).toHaveTextContent('Network unavailable');
  await userEvent.click(screen.getByRole('button', { name: 'Refresh durable state' }));
  await screen.findByRole('heading', { name: 'Action queue' });
});
test('new workspace requires a concrete choice and refresh reads state', async () => {
  render(<App />); await screen.findByRole('heading', { name: 'Action queue' });
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
  render(<App />); await screen.findByRole('heading', { name: 'Approvals & arrangements' });
  await userEvent.click(screen.getByLabelText(/I reviewed this recipient/));
  await userEvent.click(screen.getByRole('button', { name: /Approve exact draft/ }));
  expect(screen.getByRole('alert')).toHaveTextContent('Response lost');
  const firstIntent = vi.mocked(api.request).mock.calls[0][2];
  await userEvent.click(screen.getByRole('button', { name: /Approve exact draft/ }));
  expect(api.request).toHaveBeenCalledTimes(1);
  expect(screen.getByRole('alert')).toHaveTextContent('Refresh durable state before retrying');
  await userEvent.click(screen.getByRole('button', { name: 'Refresh durable state' }));
  await userEvent.click(screen.getByRole('button', { name: /Approve exact draft/ }));
  expect(api.request).toHaveBeenCalledTimes(2);
  expect(vi.mocked(api.request).mock.calls[1][2]).toEqual(firstIntent);
  expect(screen.getByRole('status')).toHaveTextContent('Saved to this workspace.');
});
test('busy action cannot race with refresh or a double click', async () => {
  let resolve!: (data: ReturnType<typeof filled>) => void;
  vi.mocked(api.request).mockImplementation(() => new Promise(r => { resolve = r as typeof resolve; }));
  render(<App />); await screen.findByRole('heading', { name: 'Action queue' });
  const button = screen.getByRole('button', { name: /Run Strands/ });
  fireEvent.click(button); fireEvent.click(button);
  expect(api.request).toHaveBeenCalledTimes(1);
  expect(screen.getByRole('button', { name: 'Refresh' })).toBeDisabled();
  await act(async () => resolve(filled()));
  await waitFor(() => expect(location.hash).toBe('#/approvals'));
});
