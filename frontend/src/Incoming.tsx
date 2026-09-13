import { useEffect, useRef, useState } from 'react';
import { ApiError, errorText, request } from './api';
import { Badge, Heading } from './ui';
import type { IncomingConnection } from './types';

export function Incoming({ session, live, revision, refreshKey = 0 }: { session: string; live: boolean; revision: number; refreshKey?: number }) {
  const [connection, setConnection] = useState<IncomingConnection | null>(null);
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [token, setToken] = useState('');
  const [retry, setRetry] = useState(0);
  const inFlight = useRef(false);
  const intent = useRef<{ action: string; id: string } | null>(null);
  const generation = useRef(0);
  useEffect(() => {
    if (!live || inFlight.current) return;
    const current = ++generation.current;
    let disposed = false;
    request<IncomingConnection>('/incoming/connection', session).then(value => {
      if (!disposed && generation.current === current) setConnection(value);
    }).catch(failure => { if (!disposed) setError(errorText(failure)); });
    return () => { disposed = true; };
  }, [session, live, revision, refreshKey, retry]);

  async function change(action: 'enable' | 'disable') {
    if (inFlight.current || (action === 'enable' && !consent)) return;
    inFlight.current = true; generation.current++; setBusy(true); setError(''); setMessage(''); setToken('');
    if (intent.current?.action !== action) intent.current = { action, id: crypto.randomUUID() };
    try {
      const result = await request<IncomingConnection>('/incoming/connection', session, {
        action, request_id: intent.current.id, ...(action === 'enable' ? { consent: 'fictional-intake' } : {}),
      });
      setToken(result.token ?? '');
      const { token: _secret, ...safe } = result;
      setConnection(safe); setConsent(false); intent.current = null;
      setMessage(action === 'enable' ? 'Intake key ready. Configure your external sender; no mailbox is connected yet.' : 'Intake key revoked. Previously accepted jobs may still finish.');
    } catch (failure) {
      const definitive = failure instanceof ApiError && [400, 401, 409, 422].includes(failure.status);
      if (definitive) { intent.current = null; setConsent(false); }
      setError(`${errorText(failure)} ${definitive ? 'Refresh connection, review its status and authorize a new action.' : 'Retry the same action to recover its saved result.'}`);
    }
    finally { inFlight.current = false; setBusy(false); }
  }
  async function copyKey() {
    try { await navigator.clipboard.writeText(token); setMessage('Intake key copied. Store it only in your automation’s secret settings.'); }
    catch { setMessage('Clipboard unavailable. Select and copy the key field manually.'); }
  }
  const endpoint = new URL('/api/incoming', import.meta.env.VITE_API_BASE_URL || location.origin).href;
  return <>
    <Heading eyebrow="RECEIVE → CHECK → REVIEW" title="Incoming">Let an external system deliver new documents. Archon reads each accepted event with Bedrock; you still decide what leaves the business.</Heading>
    {!live ? <section className="notice warning"><h2>Live intake is unavailable in this workspace</h2><p>This retained session uses local rules. Open a controlled-live workspace to configure metered incoming processing.</p><a href="#/demo">Choose a new workspace →</a></section> : <>
      <section className="panel p-5" aria-label="Incoming connection">
        <div className="flex flex-wrap items-center gap-3"><h2>Connect a document sender</h2><Badge tone={connection?.enabled ? 'good' : 'neutral'}>{connection ? connection.enabled ? 'Key active · sender setup required' : 'Not connected' : 'Reading connection…'}</Badge></div>
        <p>An email automation, export job or webhook service can submit plain-text invoices and receipts here. This is not a Gmail, Outlook or bank connection. Only fictional test data is authorized.</p>
        <ol className="space-y-2 my-4"><li>1. Enable an intake-only key below.</li><li>2. Configure your external sender with this endpoint and the key in its secret settings.</li><li>3. Watch arrivals here, then review source checks in <a href="#/records">Records</a>.</li></ol>
        <label className="block">Webhook endpoint<input className="w-full" aria-label="Webhook endpoint" value={endpoint} readOnly /></label>
        <p className="field-help">POST JSON with an Authorization: Bearer header. The key cannot read your ledger or approve email. Keep it out of URLs, screenshots and shared logs.</p>
        <label className="consent"><input type="checkbox" checked={consent} disabled={busy} onChange={event => setConsent(event.target.checked)} />I authorize automatic, metered AI intake of fictional test documents for up to 24 hours, within the existing operator budget. No automatic email approval.</label>
        <div className="flex flex-wrap gap-3 my-4"><button className="primary" disabled={busy || !consent || !connection} onClick={() => void change('enable')}>{connection?.enabled ? 'Rotate intake key' : 'Enable incoming documents'}</button><button className="secondary" disabled={busy || !connection?.enabled} onClick={() => void change('disable')}>Revoke intake key</button></div>
        {connection?.expires_at ? <p className="field-help">Key expires: <time dateTime={connection.expires_at}>{new Date(connection.expires_at).toLocaleString()}</time>. Rotation invalidates the previous key. Revoking does not cancel an already accepted job.</p> : null}
        {token ? <section className="notice" aria-label="Private intake key"><label>Intake-only key<input aria-label="Intake-only key" className="w-full" readOnly type="password" value={token} onFocus={event => event.target.select()} /></label><div className="flex flex-wrap gap-3 mt-3"><button className="secondary" onClick={() => void copyKey()}>Copy intake key</button><button className="ghost" onClick={() => setToken('')}>Hide key</button></div><p>The key is shown only after enabling. It is not saved in browser storage. If you lose it, explicitly rotate it here.</p></section> : null}
        {error ? <div role="alert" className="notice error"><p>{error}</p><button className="secondary" disabled={busy} onClick={() => { setError(''); setRetry(value => value + 1); }}>Refresh connection</button></div> : null}<p role="status">{busy ? 'Saving connection…' : message}</p>
      </section>
      <section className="panel p-5 mt-5" aria-label="Incoming events"><h2>Recent arrivals</h2><p>Refreshes while this page is visible. Completed means processing finished, not that the source passed validation. Check Records for posted or refused evidence.</p>
        {connection?.events.length ? <ul className="space-y-3">{connection.events.map(event => <li className="notice" key={event.job_id}><div className="flex flex-wrap gap-3"><strong className="break-all">{event.event_id}</strong><Badge>{event.status}</Badge></div><small><time dateTime={event.created_at}>{new Date(event.created_at).toLocaleString()}</time></small><p><a href="#/records">Inspect source decisions →</a></p></li>)}</ul> : <p className="empty">No incoming documents recorded. Enabling a key does not connect an inbox or generate sample arrivals.</p>}
      </section>
      <details className="panel p-5 mt-5"><summary>Sender setup & retry contract</summary><p>Use a unique event_id (8–100 letters, digits, hyphens or underscores) and a plain-text body (up to 32,000 characters). Example payload:</p><pre className="overflow-x-auto"><code>{JSON.stringify({ event_id: 'invoice-export-0001', body: 'The complete fictional document, including its headers and dates.' }, null, 2)}</code></pre><p>A 202 response returns event_id, job_id and status. It is acceptance, not proof of successful extraction. Repeat an uncertain request using the identical event_id and body; Archon reuses its saved job. Changed content under an old event_id is refused.</p><p>If another job is running, wait and retry the same event after HTTP 409. After a network error or 503, retry the same event. Stop and review other refusals. Your sender must retain unsent events; Archon does not provide a mailbox backlog. At most 20 provider jobs per workspace, with the existing shared budget and expiry still enforced.</p><p>New arrivals can invalidate a reviewed draft. Nothing drafts or sends a collection email automatically. No attachments, OAuth connection or bank polling is implemented.</p></details>
    </>}
  </>;
}
