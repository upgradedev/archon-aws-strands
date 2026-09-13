import { useRef, useState } from 'react';
import { errorText, openWorkspace } from './api';
import type { Workspace } from './types';

export function DemoSetup({ onOpened }: { onOpened: (result: { session: string; workspace: Workspace }) => void }) {
  const pending = useRef(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function load() {
    if (pending.current) return;
    pending.current = true; setBusy(true); setError('');
    try { onOpened(await openWorkspace(true, 'joinery')); }
    catch (failure) { setError(errorText(failure)); }
    finally { pending.current = false; setBusy(false); }
  }
  return <div className="welcome-shell"><main id="main" className="demo-setup" aria-busy={busy}>
    <a href="#/welcome">← Archon home</a>
    <p className="eyebrow">EXPLORE A WORKING BUSINESS EXAMPLE</p>
    <h1 tabIndex={-1}>A ledger with a story, ready to explore.</h1>
    <p>Alex runs a small joinery. One customer has paid in part, another has paid in full, and a supplier invoice is due next month.</p>
    <ul><li>Two customer invoices with retained source emails</li><li>Two payments: 600.00 EUR and 1,860.00 EUR</li><li>1,260.00 EUR still owed by a customer; 124.00 EUR owed to a supplier</li></ul>
    <p>Loading creates a separate workspace using clearly fictional templates and deterministic ledger checks. It does not call AI, prepare a reminder, or send email. Your most recent workspace stays available via “Return to previous workspace”.</p>
    <button className="primary" disabled={busy} onClick={() => void load()}>{busy ? 'Loading validated demo…' : 'Load demo workspace'}</button>
    {error ? <p className="notice error" role="alert">{error} Your previous workspace has not been replaced.</p> : null}
    <p className="field-help">Then explore Dashboard → Records → Guided check. Run the agent explicitly when ready; review and approve any real email separately.</p>
    <a href="#/journey">Prefer to add the invoice and payment yourself? Use the guided check →</a>
  </main></div>;
}
