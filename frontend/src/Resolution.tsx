import { useState } from 'react';
import type { Mutate, Source, Workspace } from './types';

export function Resolution({ source, data, busy, mutate }: { source: Source; data: Workspace; busy: boolean; mutate: Mutate }) {
  const [note, setNote] = useState('');
  const [duplicate, setDuplicate] = useState('');
  const [consent, setConsent] = useState(false);
  const payment = source.kind === 'Receipt';
  const receipts = data.sources.filter(s => s.status === 'posted' && s.kind === 'Receipt');
  return <form className="resolution-form" aria-label={`Human resolution for ${source.id}`} onSubmit={async e => {
    e.preventDefault();
    if (await mutate('/resolve', { source_id: source.id, decision: payment ? 'duplicate-payment' : 'resume-collection', note, duplicate_of: payment ? duplicate : null })) { setConsent(false); setNote(''); }
  }}>
    <h3>Human resolution</h3><p>{payment ? 'For a distinct payment, correct the source with its actual bank transfer ID. For a duplicate, link the original receipt below. No additional credit is posted.' : 'Resolve the dispute with the client outside this application first. Record why collections may resume; this does not arbitrate the dispute or change the debt.'}</p>
    {payment ? <label>Original posted receipt<select required value={duplicate} disabled={busy} onChange={e => { setDuplicate(e.target.value); setConsent(false); }}><option value="">Select the matching bank event</option>{receipts.map(s => <option key={s.id} value={s.id}>{s.id} · {s.document?.doc_id} · {s.document?.amount} EUR</option>)}</select></label> : null}
    <label>Resolution evidence and reason<textarea rows={3} maxLength={2000} minLength={20} required value={note} disabled={busy} onChange={e => { setNote(e.target.value); setConsent(false); }} /></label>
    <label className="check-line"><input type="checkbox" checked={consent} disabled={busy} onChange={e => setConsent(e.target.checked)} />I reviewed this source and take responsibility for this resolution.</label>
    <button className="secondary" disabled={busy || !consent || note.trim().length < 20 || (payment && !duplicate)}>Record human resolution</button>
    <p className="field-help">Original evidence remains retained. Any existing draft is invalidated; run Strands and review again.</p>
  </form>;
}
