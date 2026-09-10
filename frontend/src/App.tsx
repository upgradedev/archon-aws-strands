import { useEffect, useRef, useState } from 'react';
import { ApiError, openWorkspace, request, errorText, storageWarning } from './api';
import type { Workspace } from './types';
import { Queue } from './Queue';
import { Documents } from './Documents';
import { Activity } from './Activity';
import { Icon } from './ui';
import { Dashboard } from './Dashboard';
import { reasonTarget, routeInfo, workspaceLink } from './ledger';
import type { Bundle } from './EvidenceBundle';

const navigation = [
  ['dashboard', 'Dashboard'], ['workspace', 'Workspace'], ['records', 'Records'], ['history', 'History'],
] as const;

export function App() {
  const [data, setData] = useState<Workspace | null>(null);
  const session = useRef<string | null>(null);
  const inFlight = useRef(false);
  const intent = useRef<{ key: string; id: string; needsRefresh: boolean } | null>(null);
  const [route, setRoute] = useState(() => location.hash.slice(1) || '/dashboard');
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState('Reading durable workspace…');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [newSession, setNewSession] = useState(false);
  const [stale, setStale] = useState(false);
  const [reviewEpoch, setReviewEpoch] = useState(0);
  const { page, params } = routeInfo(route);
  const linked = data?.sources.find(source => source.id === params.get('source') || source.document?.doc_id === params.get('source'));
  const selectedInvoice = params.get('invoice') ?? linked?.document?.settles ?? (linked?.kind === 'SalesInvoice' ? linked.document?.doc_id : undefined) ?? data?.draft?.invoice_id ?? (data ? reasonTarget(data).id : null);
  const selectedView = (page === 'workspace' ? params.get('view') : params.get('caseView')) ?? 'draft';
  const caseLink = workspaceLink(selectedInvoice, params.get('source'), selectedView);
  function navLink(key: string) {
    if (key === 'workspace') return caseLink;
    const context = new URLSearchParams();
    if (selectedInvoice) context.set('invoice', selectedInvoice);
    if (params.get('source')) context.set('source', params.get('source')!);
    if (selectedView === 'terms') context.set('caseView', selectedView);
    return `#/${key}${context.size ? `?${context}` : ''}`;
  }
  async function refresh(fresh = false) {
    if (inFlight.current) return;
    inFlight.current = true; setBusy(true); setProgress('Reading durable workspace…'); setError(''); setNotice('');
    try {
      const opened = await openWorkspace(fresh);
      session.current = opened.session; setData(opened.workspace); setNewSession(false); setStale(false); setReviewEpoch(e => e + 1);
      if (fresh) intent.current = null;
      else if (intent.current) intent.current.needsRefresh = false;
    } catch (failure) { setError(errorText(failure)); setStale(true); setReviewEpoch(e => e + 1); }
    finally { inFlight.current = false; setBusy(false); }
  }
  useEffect(() => {
    void refresh();
    const navigate = () => setRoute(location.hash.slice(1) || '/dashboard');
    const offline = () => { setStale(true); setReviewEpoch(e => e + 1); setError('You are offline. These are last known records. Reconnect and refresh durable state.'); };
    window.addEventListener('hashchange', navigate);
    window.addEventListener('offline', offline);
    return () => { window.removeEventListener('hashchange', navigate); window.removeEventListener('offline', offline); };
  }, []);
  useEffect(() => { document.querySelector<HTMLHeadingElement>('h1')?.focus(); }, [page]);

  async function mutate(path: string, payload: Record<string, unknown> = {}) {
    if (inFlight.current || !data || !session.current) return false;
    if (intent.current?.needsRefresh) {
      setError('Refresh durable state before retrying an uncertain action.'); return false;
    }
    const key = JSON.stringify({ path, payload });
    setProgress(path === '/reason' ? 'Running Strands and waiting for all six reports…' : path === '/intake' ? 'Reading source and checking ledger rules…' : path === '/resolve' ? 'Recording human resolution and invalidating old drafts…' : 'Saving the reviewed decision…');
    if (intent.current?.key !== key) intent.current = { key, id: crypto.randomUUID(), needsRefresh: false };
    inFlight.current = true; setBusy(true); setError(''); setNotice('');
    try {
      const updated = await request<Workspace>(path, session.current, {
        ...payload, revision: data.revision, request_id: intent.current.id,
      });
      intent.current = null; setData(updated); setStale(false); setNotice('Saved to this workspace.'); return true;
    } catch (failure) {
      const refused = failure instanceof ApiError && (failure.status === 400 || failure.status === 422);
      if (refused) intent.current = null;
      else intent.current!.needsRefresh = true;
      setError(errorText(failure)); setStale(!refused);
      if (!refused) setReviewEpoch(e => e + 1);
      return false;
    }
    finally { inFlight.current = false; setBusy(false); }
  }

  return <div className="app-shell">
    <a className="skip-link" href="#main" onClick={e => { e.preventDefault(); document.getElementById('main')?.focus(); }}>Skip to workspace</a>
    <aside className="sidebar"><a href={navLink('dashboard')} className="brand"><span className="brand-mark" aria-hidden="true">A</span><span>ARCHON<small>THE INBOX LEDGER</small></span></a>
      <div className="workspace-name"><span className="avatar">MJ</span><div><strong>My Joinery</strong><small>Synthetic demo workspace</small></div></div>
      <p className="nav-label">WORKSPACE</p><nav aria-label="Workspace">{navigation.map(([key, label]) => <a key={key} href={navLink(key)} aria-label={label} aria-current={page === key ? 'page' : undefined}><Icon name={key} /><span>{label}</span>{key === 'workspace' && data && data.queue.ready.length ? <span className="nav-count" aria-hidden="true">{data.queue.ready.length}</span> : null}</a>)}</nav>
      <div className="sidebar-bottom"><div className="provider-dot" /><strong>Bounded by your approval</strong><p>Local rule reader<br />Real Strands orchestration<br />Scripted model · simulated outbox</p><a href={navLink('history')}>Understand the receipt states ↗</a></div>
    </aside>
    <div className="workspace-shell"><header className="topbar"><div><span className="demo-pill">SYNTHETIC DEMO</span><span className="asof">As of {data?.as_of ?? 'Unknown'}{stale ? ' · Last known snapshot' : ''}</span></div><div className="flex gap-2"><button className="ghost" disabled={busy} onClick={() => void refresh()}>Refresh</button><button className="secondary small" disabled={busy} onClick={() => setNewSession(true)}>New workspace</button></div></header>
      <main id="main" tabIndex={-1} aria-busy={busy}>
        {storageWarning ? <p className="notice warning">{storageWarning}</p> : null}
        {newSession ? <section className="notice" role="region" aria-label="Start a new workspace"><h2>Start an empty synthetic workspace?</h2><p>Session access expires after seven days. Stored records may be retained longer. This browser will receive a new session handle.</p><div className="flex gap-3"><button className="primary" onClick={() => void refresh(true)} disabled={busy}>Start new workspace</button><button className="secondary" onClick={() => setNewSession(false)}>Keep current workspace</button></div></section> : null}
        {error ? <div className="notice error" role="alert"><strong>We couldn't complete that action</strong><p>{error}</p><button className="secondary" onClick={() => void refresh()} disabled={busy}>Refresh durable state</button><p className="field-help">Review current evidence before approving again. An uncertain send must never be retried automatically.</p></div> : null}
        <div className="status-line" role="status" aria-live="polite">{busy ? progress : notice}</div>
        {data ? <>{page === 'dashboard' ? <Dashboard data={data} stale={stale} /> : page === 'workspace' ? <Queue data={data} busy={busy} mutate={mutate} route={route} stale={stale} reviewEpoch={reviewEpoch} /> : page === 'records' ? <Documents key={session.current} data={data} busy={busy || stale} mutate={mutate} route={route} /> : page === 'history' ? <Activity key={session.current} data={data} loadEvidence={() => request<Bundle>('/evidence', session.current)} /> : <div className="empty"><h1 tabIndex={-1}>Page not found</h1><p><a href="#/dashboard">Return to Dashboard</a></p></div>}</> : !error ? <div className="loading" role="status"><div className="loading-bar" /><h1>Opening your ledger</h1><p>Creating or reading your isolated demo session.</p></div> : null}
        <footer className="footer"><span>ARCHON / Source-backed bookkeeping</span><a href="/acceptance.html">Release acceptance</a><span>EUR only · Synthetic data only · No real messages</span></footer>
      </main>
    </div>
  </div>;
}
