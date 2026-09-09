import { act } from '@testing-library/react';
import { empty } from './fixtures';

test('production entrypoint mounts the application', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ session: 'entry', workspace: empty() }))));
  const root = document.createElement('div'); root.id = 'root'; document.body.append(root);
  await act(async () => { await import('../src/main'); });
  expect(root).toHaveTextContent('ARCHON'); root.remove();
});
