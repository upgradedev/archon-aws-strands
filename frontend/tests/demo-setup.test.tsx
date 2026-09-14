import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { DemoSetup } from '../src/DemoSetup';
import { WorkspaceMode } from '../src/WorkspaceMode';
import * as api from '../src/api';
import { empty } from './fixtures';

vi.mock('../src/api', async original => ({ ...await original<typeof api>(), openWorkspace: vi.fn() }));
beforeEach(() => { vi.mocked(api.openWorkspace).mockReset(); });

test('demo loading is explicit and double clicks create only one workspace', async () => {
  let finish!: (result: { session: string; workspace: ReturnType<typeof empty> }) => void;
  vi.mocked(api.openWorkspace).mockImplementation(() => new Promise(resolve => { finish = resolve; }));
  const opened = vi.fn(), loading = vi.fn(); render(<DemoSetup onOpened={opened} onLoadingChange={loading} />);
  expect(api.openWorkspace).not.toHaveBeenCalled();
  await userEvent.dblClick(screen.getByRole('button', { name: 'Load demo workspace' }));
  expect(api.openWorkspace).toHaveBeenCalledExactlyOnceWith(true, 'joinery');
  expect(loading).toHaveBeenCalledExactlyOnceWith(true);
  expect(screen.getAllByRole('button')).toHaveLength(2);
  for (const button of screen.getAllByRole('button')) expect(button).toBeDisabled();
  const result = { session: 'demo', workspace: empty() };
  await act(async () => finish(result));
  expect(opened).toHaveBeenCalledExactlyOnceWith(result);
  expect(loading).toHaveBeenLastCalledWith(false);
});

test('an outstanding workspace operation prevents creating or adopting another session', async () => {
  const opened = vi.fn(), loading = vi.fn();
  render(<DemoSetup onOpened={opened} blocked onLoadingChange={loading} />);
  expect(screen.getByRole('button', { name: 'Load demo workspace' })).toBeDisabled();
  await userEvent.click(screen.getByRole('button', { name: 'Load demo workspace' }));
  expect(api.openWorkspace).not.toHaveBeenCalled();
  expect(opened).not.toHaveBeenCalled(); expect(loading).not.toHaveBeenCalled();
  expect(screen.getByRole('status')).toHaveTextContent('before switching');
});

test('failed demo load retains a retry and does not claim success', async () => {
  vi.mocked(api.openWorkspace).mockRejectedValue(new Error('Unavailable'));
  const opened = vi.fn(); render(<DemoSetup onOpened={opened} />);
  await userEvent.click(screen.getByRole('button', { name: 'Load demo workspace' }));
  expect(screen.getByRole('alert')).toHaveTextContent('Unavailable');
  expect(opened).not.toHaveBeenCalled();
  expect(screen.getByRole('button', { name: 'Load demo workspace' })).toBeEnabled();
  expect(screen.getByRole('button', { name: 'Load business portfolio' })).toBeEnabled();
});

test('legacy warning is based on actual workspace and provider availability', () => {
  const { rerender } = render(<WorkspaceMode live={false} available />);
  expect(screen.getByRole('region', { name: 'Older simulation workspace' })).toBeVisible();
  expect(screen.getByRole('link')).toHaveAttribute('href', '#/demo');
  rerender(<WorkspaceMode live available />);
  expect(screen.queryByRole('region')).not.toBeInTheDocument();
  rerender(<WorkspaceMode live={false} available={false} />);
  expect(screen.queryByRole('region')).not.toBeInTheDocument();
});

test('business portfolio is an explicit separate choice with typed-source boundaries', async () => {
  const workspace = { ...empty(), demo_seed: 'business-v1' };
  vi.mocked(api.openWorkspace).mockResolvedValue({ session: 'business', workspace });
  const opened = vi.fn(); render(<DemoSetup onOpened={opened} />);
  expect(screen.getAllByRole('button')[0]).toHaveAccessibleName('Load business portfolio');
  expect(screen.getByRole('button', { name: 'Load business portfolio' })).toHaveClass('primary');
  expect(screen.getByRole('button', { name: 'Load demo workspace' })).toHaveClass('secondary');
  expect(screen.getByText(/those financial widgets will show zero/)).toBeVisible();
  expect(screen.getByRole('heading', { name: 'Explore a quarter · 240 records, six types' })).toBeVisible();
  expect(screen.getByText(/raw-mail reader does not yet support credit notes/)).toBeVisible();
  await userEvent.click(screen.getByRole('button', { name: 'Load business portfolio' }));
  expect(api.openWorkspace).toHaveBeenCalledExactlyOnceWith(true, 'business');
  expect(opened).toHaveBeenCalledExactlyOnceWith({ session: 'business', workspace });
});

test('only the selected dataset claims to be loading', async () => {
  let finish!: (result: { session: string; workspace: ReturnType<typeof empty> }) => void;
  vi.mocked(api.openWorkspace).mockImplementation(() => new Promise(resolve => { finish = resolve; }));
  render(<DemoSetup onOpened={vi.fn()} />);
  await userEvent.click(screen.getByRole('button', { name: 'Load business portfolio' }));
  expect(screen.getByRole('button', { name: 'Loading business portfolio…' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Load demo workspace' })).toBeDisabled();
  await act(async () => finish({ session: 'business', workspace: { ...empty(), demo_seed: 'business-v1' } }));
});
