import { useEffect, useRef, useState } from 'react';
import { ApiError, openWorkspace, request, errorText, storageWarning, hasPreviousWorkspace, restorePreviousWorkspace } from './api';
import type { Workspace } from './types';
import { Queue } from './Queue';
import { Documents } from './Documents';
import { Activity } from './Activity';
import { Icon } from './ui';
import { Dashboard } from './Dashboard';
import { reasonTarget, routeInfo, workspaceLink } from './ledger';
import type { Bundle } from './EvidenceBundle';
import { Welcome } from './Welcome';
import { Journey } from './Journey';
import { ProviderStatus } from './ProviderStatus';
import { DemoSetup } from './DemoSetup';
import { WorkspaceMode } from './WorkspaceMode';
import { Incoming } from './Incoming';

const navigation = [
  ['dashboard', 'Dashboard', 'See what is owed'], ['workspace', 'Workspace', 'Review & approve'], ['records', 'Records', 'Invoices & payments'], ['incoming', 'Incoming', 'Automated document intake'], ['history', 'History', 'Decisions & receipts'],
] as const;

export function App() {
  const [data, setData] = useState<Workspace | null>(null);
  const session = useRef<string | null>(null);
  const inFlight = useRef(false);
  const intent = useRef<{ key: string; id: string; needsRefresh: boolean } | null>(null);
  const [route, setRoute] = useState(() => location.hash.slice(1) || '/welcome');
  const opened = useRef(false);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState('Reading durable workspace…');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [newSession, setNewSession] = useState(false);
  const [stale, setStale] = useState(false);
  const [reviewEpoch, setReviewEpoch] = useState(0);
  function adoptWorkspace(result: { session: string; workspace: Workspace }) {
    session.current = result.session; setData(result.workspace); opened.current = true;
    intent.current = null; setStale(false); setError(''); setNewSession(false);
    setReviewEpoch(e => e + 1); location.hash = '/dashboard';
  }
  async function restore() {
    if (inFlight.current) return;
    inFlight.current = true; setBusy(true);
    try { adoptWorkspace(await restorePreviousWorkspace()); }
    catch (failure) { setError(errorText(failure)); }
    finally { inFlight.current = false; setBusy(false); }
  }
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
    const navigate = () => setRoute(location.hash.slice(1) || '/welcome');
    const offline = () => { setStale(true); setReviewEpoch(e => e + 1); setError('You are offline. These are last known records. Reconnect and refresh durable state.'); };
    window.addEventListener('hashchange', navigate);
    window.addEventListener('offline', offline);
    return () => { window.removeEventListener('hashchange', navigate); window.removeEventListener('offline', offline); };
  }, []);
  useEffect(() => {
    if (page !== 'welcome' && page !== 'demo' && !opened.current) { opened.current = true; void refresh(); }
  }, [page]);
  const hasData = data !== null;
  const providerPending = !!data?.live?.job && ['queued', 'running', 'unknown'].includes(data.live.job.status);
  useEffect(() => {
    const pending = data?.live?.job && ['queued', 'running'].includes(data.live.job.status);
    const incoming = page === 'incoming' && data?.live;
    if (busy || (!pending && !incoming)) return;
    const timer = window.setInterval(() => { if (!document.hidden) void refresh(); }, pending ? 2000 : 5000);
    return () => window.clearInterval(timer);
  }, [data, busy, page]);
  useEffect(() => { document.querySelector<HTMLHeadingElement>('h1')?.focus(); }, [page, hasData]);

  async function mutate(path: string, payload: Record<string, unknown> = {}) {
    if (inFlight.current || providerPending || !data || !session.current) return false;
    if (intent.current?.needsRefresh) {
      setError('Refresh durable state before retrying an uncertain action.'); return false;
    }
    const key = JSON.stringify({ path, payload });
    setProgress(path === '/reason' ? 'Running Strands and waiting for all six reports…' : path === '/intake' ? 'Reading source and checking ledger rules…' : path === '/resolve' ? 'Recording human resolution and invalidating old drafts…' : 'Saving the reviewed decision…');
    if (intent.current?.key !== key) intent.current = { key, id: crypto.randomUUID(), needsRefresh: false };
    inFlight.current = true; setBusy(true); setError(''); setNotice('');
    try {
      let updated = await request<Workspace>(path, session.current, {
        ...payload, revision: data.revision, request_id: intent.current.id,
      });
      for (let poll = 0; updated.live?.job && ['queued', 'running'].includes(updated.live.job.status); poll++) {
        setData(updated); setProgress(`Real provider: ${updated.live.job.operation} · ${updated.live.job.status}. Your job is saved; reloading will not run it twice.`);
        if (poll >= 120) throw new ApiError('The saved job is still pending. Refresh to follow it; do not submit again.', 408);
        await new Promise(resolve => window.setTimeout(resolve, 2000));
        updated = await request<Workspace>('/workspace', session.current);
      }
      setData(updated);
      if (updated.live?.job?.status === 'failed') throw new ApiError(updated.live.job.error ?? 'Provider execution failed. No scripted fallback was used.', 422);
      if (updated.live?.job?.status === 'unknown') throw new ApiError('The provider outcome is uncertain. Operator reconciliation is required.', 409);
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

  if (page === 'welcome') return <Welcome />;
  if (page === 'demo') return <DemoSetup onOpened={adoptWorkspace} blocked={busy || providerPending}
    onLoadingChange={loading => { inFlight.current = loading; setBusy(loading); }} />;

  return <div className="app-shell">
    <a className="skip-link" href="#main" onClick={e => { e.preventDefault(); document.getElementById('main')?.focus(); }}>Skip to workspace</a>
    <aside className="sidebar"><a href="#/welcome" className="brand"><span className="brand-mark" aria-hidden="true">A</span><span>ARCHON<small>THE INBOX LEDGER</small></span></a>
      <div className="workspace-name"><span className="avatar">MJ</span><div><strong>My Joinery</strong><small>Fictional business workspace</small></div></div>
      <p className="nav-label">YOUR BUSINESS</p><nav aria-label="Workspace"><a href="#/journey" aria-current={page === 'journey' ? 'page' : undefined}><Icon name="approvals" /><span>Guided check</span></a>{navigation.map(([key, label, task]) => <a key={key} href={navLink(key)} aria-label={label} aria-current={page === key ? 'page' : undefined}><Icon name={key} /><span>{label}<small className="nav-task">{task}</small></span>{key === 'workspace' && data && data.queue.ready.length ? <span className="nav-count" aria-hidden="true">{data.queue.ready.length}</span> : null}</a>)}</nav>
      <div className="sidebar-bottom"><div className="provider-dot" /><strong>Bounded by your approval</strong><p>{data?.live ? 'Real Bedrock · real Strands · controlled SES' : 'Local rule reader · real Strands · scripted model · simulated outbox'}</p><a href={navLink('history')}>Understand the receipt states ↗</a></div>
    </aside>
    <div className="workspace-shell"><header className="topbar"><div><span className="demo-pill">{data?.live ? 'LIVE AI · TEST DATA' : 'SYNTHETIC DEMO'}</span><span className="asof">As of {data?.as_of ?? 'Unknown'}{stale ? ' · Last known snapshot' : ''}</span></div><div className="flex gap-2"><button id="refresh-workspace" className="ghost" disabled={busy} onClick={() => void refresh()}>Refresh</button><button className="secondary small" disabled={busy} onClick={() => setNewSession(true)}>New workspace</button></div></header>
      <main id="main" tabIndex={-1} aria-busy={busy || providerPending}>
        {storageWarning ? <p className="notice warning">{storageWarning}</p> : null}
        {data ? <WorkspaceMode live={!!data.live} available={data.live_available} /> : null}
        {hasPreviousWorkspace() ? <button className="secondary small" disabled={busy || providerPending} onClick={() => void restore()}>Return to previous workspace</button> : null}
        {data?.live ? <ProviderStatus live={data.live} /> : null}
        {newSession ? <section className="notice" role="region" aria-label="Start a new workspace"><h2>Start an empty workspace?</h2><p>This opens separate empty books using the currently available providers. Switching does not delete its stored records. Your previous workspace stays accessible through Return to previous workspace. Session access expires after seven days. Nothing calls AI or sends email on creation.</p><div className="flex gap-3"><button className="primary" onClick={() => void refresh(true)} disabled={busy}>Start new workspace</button><button className="secondary" onClick={() => setNewSession(false)}>Keep current workspace</button><a href="#/demo">Prefer populated demo books?</a></div></section> : null}
        {error ? <div className="notice error" role="alert"><strong>{!data ? 'Your workspace could not be opened' : stale ? 'Decision paused until the books are refreshed' : 'We could not save that input'}</strong><p>{error}</p><button className="secondary" onClick={() => void refresh()} disabled={busy}>Refresh durable state</button><p className="field-help">{!data ? 'No balance is available. Try Refresh; if the session has expired, use New workspace above to start empty books.' : stale ? 'Review current evidence before approving again. An uncertain send must never be retried automatically.' : 'Your input is still available to correct. No new approval was recorded by this refused request.'}</p></div> : null}
        <div className="status-line" role="status" aria-live="polite">{busy ? progress : notice}</div>
        {data ? <>{page === 'journey' ? <Journey key={session.current} data={data} busy={busy || providerPending} stale={stale} mutate={mutate} route={route} reviewEpoch={reviewEpoch} loadEvidence={() => request<Bundle>('/evidence', session.current)} />
          : page === 'dashboard' ? <Dashboard data={data} stale={stale} />
          : page === 'workspace' ? <Queue key={session.current} data={data} busy={busy || providerPending} mutate={mutate} route={route} stale={stale} reviewEpoch={reviewEpoch} loadEvidence={() => request<Bundle>('/evidence', session.current)} />
          : page === 'records' ? <Documents key={session.current} data={data} busy={busy || providerPending || stale} mutate={mutate} route={route} />
          : page === 'incoming' ? <Incoming key={session.current} session={session.current!} live={!!data.live} revision={data.revision} refreshKey={reviewEpoch} />
          : page === 'history' ? <Activity key={session.current} data={data} loadEvidence={() => request<Bundle>('/evidence', session.current)} />
          : <div className="empty"><h1 tabIndex={-1}>Page not found</h1><p><a href="#/dashboard">Return to Dashboard</a></p></div>}</>
          : !error ? <div className="loading" role="status"><div className="loading-bar" /><h1>Opening your ledger</h1><p>Creating or reading your isolated demo session.</p></div> : null}
        {data?.demo_seed ? <section className="notice" aria-label="Populated fictional demo"><strong>Your demo is ready to explore.</strong><p>{data.demo_seed === 'joinery-v1' ? 'Five fictional source emails, parsed with local rules.' : data.demo_seed === 'business-v1' ? 'Business portfolio: 240 fictional typed source documents across six types, posted with deterministic books checks. These seed documents were not AI-extracted; the raw-mail reader does not yet support credit notes.' : 'Fictional demo records; inspect each retained source for its origin.'} Metrics come from the ledger, not AI-generated totals. No AI report or email was generated by loading.</p><a href="#/journey">Next: review the remaining balance and run the agent →</a></section> : data && data.sources.length === 0 ? <section className="notice" aria-label="Empty workspace help"><strong>Start with a working example.</strong><p>This workspace is empty. Explore populated books, or add your first invoice below.</p><a className="secondary" href="#/demo">Explore populated demo →</a></section> : null}
        <footer className="footer"><span>ARCHON / Source-backed bookkeeping</span><a href="/acceptance.html">Release acceptance</a><span>{data?.live ? 'EUR only · Fictional examples · Controlled real email' : 'EUR only · Synthetic data only · No real messages'}</span></footer>
      </main>
    </div>
  </div>;
}
