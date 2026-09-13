import { empty } from './fixtures';

beforeEach(() => { vi.resetModules(); localStorage.clear(); });

test('populated demo keeps the previous handle and restores its records without posting', async () => {
  localStorage.setItem('archon.demo.session.v1', 'old');
  const fetcher = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ session: 'demo', workspace: { ...empty(), demo_seed: 'joinery-v1' } })))
    .mockResolvedValueOnce(new Response(JSON.stringify(empty())));
  vi.stubGlobal('fetch', fetcher);
  const api = await import('../src/api');
  await api.openWorkspace(true, 'joinery');
  expect(fetcher).toHaveBeenNthCalledWith(1, '/api/sessions', expect.objectContaining({ body: '{"seed":"joinery"}' }));
  expect(api.hasPreviousWorkspace()).toBe(true);
  expect(localStorage.getItem('archon.demo.previous.v1')).toBe('old');
  vi.resetModules();
  const reloaded = await import('../src/api');
  expect((await reloaded.restorePreviousWorkspace()).session).toBe('old');
  expect(fetcher).toHaveBeenLastCalledWith('/api/workspace', expect.objectContaining({ method: 'GET', headers: expect.objectContaining({ 'X-Archon-Session': 'old' }) }));
  expect(localStorage.getItem('archon.demo.previous.v1')).toBe('demo');
  expect(localStorage.getItem(api.SESSION_KEY)).toBe('old');
});

test('expired previous workspace does not replace the current handle', async () => {
  localStorage.setItem('archon.demo.session.v1', 'current');
  localStorage.setItem('archon.demo.previous.v1', 'expired');
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{"detail":"Session expired"}', { status: 401 })));
  const api = await import('../src/api');
  await expect(api.restorePreviousWorkspace()).rejects.toThrow('expired');
  expect(localStorage.getItem(api.SESSION_KEY)).toBe('current');
});

test('an old API cannot silently replace the workspace with an unseeded result', async () => {
  localStorage.setItem('archon.demo.session.v1', 'current');
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ session: 'unseeded', workspace: empty() }))));
  const api = await import('../src/api');
  await expect(api.openWorkspace(true, 'joinery')).rejects.toThrow('has not loaded');
  expect(localStorage.getItem(api.SESSION_KEY)).toBe('current');
});

test('a pending empty creation cannot be mistaken for the requested populated demo', async () => {
  let finish!: (response: Response) => void;
  vi.stubGlobal('fetch', vi.fn(() => new Promise(resolve => { finish = resolve; })));
  const api = await import('../src/api');
  const pending = api.openWorkspace();
  await expect(api.openWorkspace(true, 'joinery')).rejects.toThrow('finish opening');
  finish(new Response(JSON.stringify({ session: 'empty', workspace: empty() })));
  await pending;
});

test('request sends a session header and structured payload', async () => {
  const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify(empty())));
  vi.stubGlobal('fetch', fetcher);
  const { request } = await import('../src/api');
  expect(await request('/intake', 'handle', { body: 'post' })).toEqual(empty());
  expect(fetcher).toHaveBeenCalledWith('/api/intake', expect.objectContaining({ method: 'POST', headers: expect.objectContaining({ 'X-Archon-Session': 'handle' }), body: '{"body":"post"}' }));
});
test('request reports server refusal and invalid response without guessing', async () => {
  const fetcher = vi.fn().mockResolvedValueOnce(new Response('{"detail":"stale"}', { status: 409 }))
    .mockResolvedValueOnce(new Response('{"detail":[{}]}', { status: 422 }))
    .mockResolvedValueOnce(new Response('not json', { status: 502 }));
  vi.stubGlobal('fetch', fetcher);
  const { request, errorText } = await import('../src/api');
  await expect(request('/workspace', null)).rejects.toThrow('stale');
  await expect(request('/workspace', null)).rejects.toThrow('Check the fields');
  await expect(request('/workspace', null)).rejects.toThrow('unreadable response');
  expect(errorText('oops')).toContain('could not be reached');
});
test('requests abort after 35 seconds and clear their timer', async () => {
  vi.useFakeTimers();
  vi.stubGlobal('fetch', vi.fn((_url, init) => new Promise((_resolve, reject) => {
    init.signal.addEventListener('abort', () => reject(new Error('aborted')));
  })));
  const { request } = await import('../src/api');
  const assertion = expect(request('/workspace', null)).rejects.toThrow('timed out');
  await vi.advanceTimersByTimeAsync(35000); await assertion;
  expect(vi.getTimerCount()).toBe(0); vi.useRealTimers();
});
test('session creation is single-flight and reload uses only the opaque handle', async () => {
  let resolve!: (response: Response) => void;
  const fetcher = vi.fn().mockImplementationOnce(() => new Promise(r => { resolve = r; }))
    .mockResolvedValue(new Response(JSON.stringify(empty())));
  vi.stubGlobal('fetch', fetcher);
  const { openWorkspace, SESSION_KEY } = await import('../src/api');
  const first = openWorkspace(), second = openWorkspace();
  resolve(new Response(JSON.stringify({ session: 'opaque', workspace: empty() })));
  expect(await first).toEqual(await second); expect(fetcher).toHaveBeenCalledTimes(1);
  expect(localStorage.getItem(SESSION_KEY)).toBe('opaque');
  expect(Object.keys(localStorage)).toEqual([SESSION_KEY]);
  await openWorkspace(); expect(fetcher).toHaveBeenLastCalledWith('/api/workspace', expect.anything());
});
test('blocked storage still opens a session and discloses its lifetime', async () => {
  vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('blocked'); });
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('blocked'); });
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ session: 'volatile', workspace: empty() }))));
  const api = await import('../src/api');
  expect((await api.openWorkspace()).session).toBe('volatile');
  expect(api.storageWarning).toContain('page closes');
});
test('failed session creation can be retried and existing handles are read', async () => {
  localStorage.setItem('archon.demo.session.v1', 'existing');
  vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(new Response(JSON.stringify(empty())))
    .mockRejectedValueOnce(new TypeError('offline')).mockResolvedValueOnce(new Response(JSON.stringify({ session: 'new', workspace: empty() }))));
  const api = await import('../src/api');
  expect((await api.openWorkspace()).session).toBe('existing');
  await expect(api.openWorkspace(true)).rejects.toThrow('offline');
  expect((await api.openWorkspace(true)).session).toBe('new');
});
