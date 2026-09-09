import { useEffect, useRef, useState } from 'react';
import { openWorkspace, request, errorText, storageWarning } from './api';
import type { Workspace } from './types';
import { Queue } from './Queue';
import { Documents } from './Documents';
import { Approvals } from './Approvals';
import { Activity } from './Activity';
import { Icon } from './ui';

const navigation = [
  ['queue', 'Action queue'], ['documents', 'Documents & payments'],
  ['approvals', 'Approvals & arrangements'], ['activity', 'Activity & delivery'],
] as const;

export function App() {
  const [data, setData] = useState<Workspace | null>(null);
  const session = useRef<string | null>(null);
  const inFlight = useRef(false);
  const intent = useRef<{ key: string; id: string; needsRefresh: boolean } | null>(null);
  const [route, setRoute] = useState(() => location.hash.slice(1) || '/queue');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [newSession, setNewSession] = useState(false);
  const page = route.split('?')[0].slice(1);
  async function refresh(fresh = false) {
    if (inFlight.current) return;
    inFlight.current = true; setBusy(true); setError(''); setNotice('');
    try {
      const opened = await openWorkspace(fresh);
      session.current = opened.session; setData(opened.workspace); setNewSession(false);
      if (fresh) intent.current = null;
      else if (intent.current) intent.current.needsRefresh = false;
    } catch (failure) { setError(errorText(failure)); }
    finally { inFlight.current = false; setBusy(false); }
  }
  useEffect(() => {
    void refresh();
    const navigate = () => setRoute(location.hash.slice(1) || '/queue');
    window.addEventListener('hashchange', navigate);
    return () => window.removeEventListener('hashchange', navigate);
  }, []);
  useEffect(() => { document.querySelector<HTMLHeadingElement>('h1')?.focus(); }, [route]);

  async function mutate(path: string, payload: Record<string, unknown> = {}) {
    if (inFlight.current || !data || !session.current) return false;
    if (intent.current?.needsRefresh) {
      setError('Refresh durable state before retrying an uncertain action.'); return false;
    }
    const key = JSON.stringify({ path, payload });
    if (intent.current?.key !== key) intent.current = { key, id: crypto.randomUUID(), needsRefresh: false };
    inFlight.current = true; setBusy(true); setError(''); setNotice('');
    try {
      const updated = await request<Workspace>(path, session.current, {
        ...payload, revision: data.revision, request_id: intent.current.id,
      });
      intent.current = null; setData(updated); setNotice('Saved to this workspace.'); return true;
    } catch (failure) { intent.current!.needsRefresh = true; setError(errorText(failure)); return false; }
    finally { inFlight.current = false; setBusy(false); }
  }

  return <div className="app-shell">
    <a className="skip-link" href="#main" onClick={e => { e.preventDefault(); document.getElementById('main')?.focus(); }}>Skip to workspace</a>
    <aside className="sidebar"><a href="#/queue" className="brand"><span className="brand-mark" aria-hidden="true">A</span><span>ARCHON<small>THE INBOX LEDGER</small></span></a>
      <div className="workspace-name"><span className="avatar">MJ</span><div><strong>My Joinery</strong><small>Synthetic demo workspace</small></div></div>
      <p className="nav-label">WORKSPACE</p><nav aria-label="Workspace">{navigation.map(([key, label]) => <a key={key} href={`#/${key}`} aria-current={page === key ? 'page' : undefined}><Icon name={key} /><span>{label}</span>{key === 'queue' && data && data.queue.ready.length ? <span className="nav-count">{data.queue.ready.length}</span> : null}</a>)}</nav>
      <div className="sidebar-bottom"><div className="provider-dot" /><strong>Bounded by your approval</strong><p>Local rule reader<br />Real Strands orchestration<br />Scripted model · simulated outbox</p><a href="#/activity">Understand the receipt states ↗</a></div>
    </aside>
    <div className="workspace-shell"><header className="topbar"><div><span className="demo-pill">SYNTHETIC DEMO</span><span className="asof">As of {data?.as_of ?? '2026-09-09'}</span></div><div className="flex gap-2"><button className="ghost" disabled={busy} onClick={() => void refresh()}>Refresh</button><button className="secondary small" disabled={busy} onClick={() => setNewSession(true)}>New workspace</button></div></header>
      <main id="main" tabIndex={-1} aria-busy={busy}>
        {storageWarning ? <p className="notice warning">{storageWarning}</p> : null}
        {newSession ? <section className="notice" role="region" aria-label="Start a new workspace"><h2>Start an empty synthetic workspace?</h2><p>Session access expires after seven days. Stored records may be retained longer. This browser will receive a new session handle.</p><div className="flex gap-3"><button className="primary" onClick={() => void refresh(true)} disabled={busy}>Start new workspace</button><button className="secondary" onClick={() => setNewSession(false)}>Keep current workspace</button></div></section> : null}
        {error ? <div className="notice error" role="alert"><strong>We couldn't complete that action</strong><p>{error}</p><button className="secondary" onClick={() => void refresh()} disabled={busy}>Refresh durable state</button><p className="field-help">Review current evidence before approving again. An uncertain send must never be retried automatically.</p></div> : null}
        <div className="status-line" role="status" aria-live="polite">{busy ? 'Working with your ledger…' : notice}</div>
        {data ? <>{page === 'queue' ? <Queue data={data} busy={busy} mutate={mutate} /> : page === 'documents' ? <Documents data={data} busy={busy} mutate={mutate} route={route} /> : page === 'approvals' ? <Approvals key={`${data.draft?.fingerprint}-${data.proposal?.fingerprint}`} data={data} busy={busy} mutate={mutate} /> : page === 'activity' ? <Activity data={data} /> : <div className="empty"><h1>Page not found</h1><p><a href="#/queue">Return to the action queue</a></p></div>}</> : !error ? <div className="loading" role="status"><div className="loading-bar" /><h1>Opening your ledger</h1><p>Creating or reading your isolated demo session.</p></div> : null}
        <footer className="footer"><span>ARCHON / Source-backed bookkeeping</span><span>EUR only · Synthetic data only · No real messages</span></footer>
      </main>
    </div>
  </div>;
}
