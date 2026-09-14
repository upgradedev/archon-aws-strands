import { useRef, useState } from 'react';
import { errorText, openWorkspace, type DemoSeed } from './api';
import type { Workspace } from './types';

export function DemoSetup({ onOpened, blocked = false, onLoadingChange }: {
  onOpened: (result: { session: string; workspace: Workspace }) => void;
  blocked?: boolean; onLoadingChange?: (loading: boolean) => void;
}) {
  const pending = useRef(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function load(seed: DemoSeed) {
    if (pending.current || blocked) return;
    pending.current = true; onLoadingChange?.(true); setBusy(true); setError('');
    try { onOpened(await openWorkspace(true, seed)); }
    catch (failure) { setError(errorText(failure)); }
    finally { pending.current = false; onLoadingChange?.(false); setBusy(false); }
  }
  return <div className="welcome-shell"><main id="main" className="demo-setup" aria-busy={busy}>
    <a href="#/welcome">← Archon home</a>
    <p className="eyebrow">EXPLORE A WORKING BUSINESS EXAMPLE</p>
    <h1 tabIndex={-1}>A ledger with a story, ready to explore.</h1>
    <section className="demo-choice" aria-label="Small joinery demo"><h2>Start small · five source emails</h2>
    <p>Alex runs a small joinery. One customer has paid in part, another has paid in full, and a supplier invoice is due next month.</p>
    <ul><li>Two customer invoices with retained source emails</li><li>Two payments: 600.00 EUR and 1,860.00 EUR</li><li>1,260.00 EUR still owed by a customer; 124.00 EUR owed to a supplier</li></ul>
    <button className="primary" disabled={busy || blocked} onClick={() => void load('joinery')}>{busy ? 'Loading validated demo…' : 'Load demo workspace'}</button></section>
    <section className="demo-choice" aria-label="Business portfolio demo"><h2>Explore a quarter · 240 records, six types</h2>
      <p>A fictional business portfolio from July through 9 September 2026, with invoices, credits and cash records to explore.</p>
      <ul className="demo-mix"><li>80 sales invoices</li><li>50 purchase invoices</li><li>20 sales credits</li><li>10 purchase credits</li><li>50 client receipts</li><li>30 supplier payments</li></ul>
      <p>These are typed demo documents posted through deterministic books checks, not AI-extracted emails. Credit notes are supported in these books; the raw-mail reader does not yet support credit notes.</p>
      <button className="secondary" disabled={busy || blocked} onClick={() => void load('business')}>{busy ? 'Loading business portfolio…' : 'Load business portfolio'}</button>
    </section>
    <p>Loading creates a separate workspace using clearly fictional templates and deterministic ledger checks. It does not call AI, prepare a reminder, or send email. Your most recent workspace stays available via “Return to previous workspace”.</p>
    {blocked && !busy ? <p role="status">Wait for the current workspace operation to finish before switching. Return to the guided check to inspect a pending or uncertain provider outcome.</p> : null}
    {error ? <p className="notice error" role="alert">{error} Your previous workspace has not been replaced.</p> : null}
    <p className="field-help">Then explore Dashboard → Records → Guided check. Run the agent explicitly when ready; review and approve any real email separately.</p>
    <a href="#/journey">Prefer to add the invoice and payment yourself? Use the guided check →</a>
  </main></div>;
}
