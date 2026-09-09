import type { Workspace } from './types';

const base = import.meta.env.VITE_API_BASE_URL ?? '';
export const SESSION_KEY = 'archon.demo.session.v1';
let memorySession: string | null = null;
let opening: Promise<{ session: string; workspace: Workspace }> | null = null;
export let storageWarning = '';

export class ApiError extends Error {
  constructor(message: string, public status: number) { super(message); }
}

export async function request<T>(path: string, session: string | null, body?: object): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 35000);
  try {
  const response = await fetch(`${base}/api${path}`, {
    method: body ? 'POST' : 'GET', cache: 'no-store',
    signal: controller.signal,
    headers: { 'Content-Type': 'application/json', ...(session ? { 'X-Archon-Session': session } : {}) },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  let value: { detail?: unknown };
  try { value = await response.json(); }
  catch { throw new ApiError('The API returned an unreadable response. Refresh before retrying.', response.status); }
  if (!response.ok) {
    const detail = typeof value.detail === 'string' ? value.detail : 'The request was refused. Check the fields and try again.';
    throw new ApiError(detail, response.status);
  }
  return value as T;
  } catch (failure) {
    if (controller.signal.aborted) throw new ApiError('The request timed out. Refresh durable state before retrying.', 408);
    throw failure;
  } finally { clearTimeout(timeout); }
}

export async function openWorkspace(fresh = false): Promise<{ session: string; workspace: Workspace }> {
  if (opening) return opening;
  let stored: string | null = null;
  try { stored = localStorage.getItem(SESSION_KEY); }
  catch { storageWarning = 'Browser storage is blocked. This session handle lasts until this page closes.'; }
  const session = fresh ? null : memorySession ?? stored;
  if (session) return { session, workspace: await request<Workspace>('/workspace', session) };
  opening = request<{ session: string; workspace: Workspace }>('/sessions', null, { mode: 'synthetic' }).then(created => {
    memorySession = created.session;
    try { localStorage.setItem(SESSION_KEY, created.session); }
    catch { storageWarning = 'Browser storage is blocked. This session handle lasts until this page closes.'; }
    return created;
  });
  try { return await opening; } finally { opening = null; }
}

export function errorText(error: unknown): string {
  return error instanceof Error ? error.message : 'The workspace could not be reached. Refresh and try again.';
}
