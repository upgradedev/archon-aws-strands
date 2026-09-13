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
  const opened = vi.fn(); render(<DemoSetup onOpened={opened} />);
  expect(api.openWorkspace).not.toHaveBeenCalled();
  await userEvent.dblClick(screen.getByRole('button', { name: 'Load demo workspace' }));
  expect(api.openWorkspace).toHaveBeenCalledExactlyOnceWith(true, 'joinery');
  expect(screen.getByRole('button')).toBeDisabled();
  const result = { session: 'demo', workspace: empty() };
  await act(async () => finish(result));
  expect(opened).toHaveBeenCalledExactlyOnceWith(result);
});

test('failed demo load retains a retry and does not claim success', async () => {
  vi.mocked(api.openWorkspace).mockRejectedValue(new Error('Unavailable'));
  const opened = vi.fn(); render(<DemoSetup onOpened={opened} />);
  await userEvent.click(screen.getByRole('button', { name: 'Load demo workspace' }));
  expect(screen.getByRole('alert')).toHaveTextContent('Unavailable');
  expect(opened).not.toHaveBeenCalled();
  expect(screen.getByRole('button')).toBeEnabled();
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
