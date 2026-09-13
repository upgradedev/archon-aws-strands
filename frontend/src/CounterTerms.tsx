import { useState } from 'react';
import type { Mutate, Workspace } from './types';

export function CounterTerms({ data, disabled, mutate }: { data: Workspace; disabled: boolean; mutate: Mutate }) {
  const [body, setBody] = useState('');
  const [consent, setConsent] = useState('');
  const proposal = data.proposal;
  const binding = JSON.stringify([data.revision, proposal?.fingerprint, body]);
  if (!proposal?.plan) return null;
  return <details className="panel counter-terms"><summary>Offer different payment dates</summary>
    <p>Keep the client's original reply and record your counterproposal. This does not send a message, record client acceptance, change debt or create a collection hold.</p>
    <label htmlFor="counter-terms">Your counterproposal</label>
    <textarea id="counter-terms" rows={4} maxLength={4000} value={body} disabled={disabled} aria-describedby="counter-help" onChange={event => { setBody(event.target.value); setConsent(''); }} />
    <p id="counter-help" className="field-help">One YYYY-MM-DD: 0.00 EUR line per instalment. Review the exact dates and amounts below. The server checks them against the current balance before recording.</p>
    <pre className="counter-preview">{body || 'Enter your proposed dates and amounts.'}</pre>
    <label className="checkbox"><input type="checkbox" checked={consent === binding && !disabled} disabled={disabled || !body.trim()} onChange={event => setConsent(event.target.checked ? binding : '')} /><span>I reviewed my counterproposal. Record it as pending client acceptance only.</span></label>
    <button className="secondary" disabled={disabled || !body.trim() || consent !== binding} onClick={async () => {
      if (await mutate('/arrangements/counter', { fingerprint: proposal.fingerprint, body })) { setBody(''); setConsent(''); }
    }}>Record counterproposal · no send</button>
  </details>;
}

export function TermsHistory({ data, invoice }: { data: Workspace; invoice?: string }) {
  const history = (data.terms_history ?? []).filter(item => !invoice || (item.invoice_id ?? item.original?.invoice_id) === invoice);
  if (!history.length) return null;
  return <section className="panel terms-history" aria-label="Terms decision history"><h3>Terms decision history</h3>
    <p>Historical decisions, not payment or delivery receipts. An owner counterproposal needs a fresh client reply before it can become an agreed arrangement.</p>
    {history.map((item, index) => <details key={`${item.at}-${index}`}><summary>{item.decision === 'owner-counterproposal' ? 'Counterproposal recorded · client acceptance not recorded' : item.decision === 'arrangement-approved' ? 'Client terms approved by owner' : 'Client proposal read'} · {item.invoice_id ?? item.original?.invoice_id}</summary>
      <p>Recorded {item.at}</p>{item.body ? <pre>{item.body}</pre> : null}
      {item.original ? <><h4>Original client reply · retained</h4><pre>{item.original.body ?? 'Original text unavailable for this historical record.'}</pre></> : null}
      {item.fingerprint ? <code className="fingerprint">{item.fingerprint}</code> : null}
    </details>)}
  </section>;
}
