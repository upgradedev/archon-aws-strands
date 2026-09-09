import { useState } from 'react';
import type { Mutate, Workspace } from './types';
import { Badge, Empty, Heading, money } from './ui';
import { DraftEvidence } from './DraftEvidence';
import { draftState, workspaceLink } from './ledger';
import { useClock } from './useClock';

export function Approvals({ data, busy, mutate, mode = 'all', selectedInvoice, stale = false }: { data: Workspace; busy: boolean; mutate: Mutate; mode?: 'draft' | 'terms' | 'all'; selectedInvoice?: string; stale?: boolean }) {
  const [consent, setConsent] = useState('');
  const [termsConsent, setTermsConsent] = useState('');
  const [invoice, setInvoice] = useState(selectedInvoice ?? '');
  const [terms, setTerms] = useState('');
  const draft = data.draft;
  const now = useClock(mode === 'terms' ? data.proposal?.at : draft?.at);
  const status = draftState(data, now);
  const binding = JSON.stringify([data.revision, draft]);
  const checked = consent === binding;
  const termsBinding = JSON.stringify([data.revision, data.proposal, invoice, terms]);
  const termsChecked = termsConsent === termsBinding;
  const proposalMatches = !selectedInvoice || data.proposal?.invoice_id === selectedInvoice;
  const proposalTime = Date.parse(data.proposal?.at ?? '');
  const termsExpired = !!data.proposal && (!Number.isFinite(proposalTime) || proposalTime > now || now >= proposalTime + 30 * 60 * 1000);
  const receipt = data.receipts.find(r => r.fingerprint === draft?.fingerprint);
  return <>
    {mode === 'all' ? <Heading eyebrow="HUMAN DECISIONS" title="Approvals & arrangements">Your approval belongs to these exact words, this recipient, and this evidence.</Heading> : null}
    {mode !== 'terms' ? <section className="panel"><div className="panel-heading"><div><h2>Collection draft</h2><p>Every money claim is re-derived at approval. Drafts expire after 30 minutes.</p></div><Badge tone="amber">Simulated delivery</Badge></div>
      {draft ? <div className="draft-grid"><article className="email"><dl><dt>To</dt><dd>{draft.recipient}</dd><dt>Subject</dt><dd>{draft.subject}</dd><dt>Invoice</dt><dd><a href={`#/documents?source=${encodeURIComponent(draft.invoice_id)}`}>{draft.invoice_id} · Source evidence ↗</a></dd></dl><pre>{draft.body}</pre><DraftEvidence data={data} invoiceId={draft.invoice_id} /><details><summary>Exact content fingerprint</summary><code className="fingerprint">{draft.fingerprint}</code></details></article>
        <aside className="approval-box"><h3>Review before approving</h3><p>The public outbox is simulated. This records an approval and a simulated provider receipt. No message is sent to this address.</p>
          <p className="decision-binding">Ledger revision {data.revision} · Prepared {draft.at}</p>
          <label className="checkbox"><input type="checkbox" checked={checked && status === 'pending' && !stale} onChange={e => setConsent(e.target.checked ? binding : '')} disabled={busy || status !== 'pending' || stale} /><span>I reviewed this recipient, subject, body and balance.</span></label>
          <button className="primary" disabled={busy || !checked || status !== 'pending' || stale} onClick={async () => { const origin = location.hash; if (await mutate('/approve', { fingerprint: draft.fingerprint })) { setConsent(''); if (location.hash === origin) location.hash = '/history'; } }}>Approve exact draft · simulate</button>
          <p className="field-help">{receipt ? 'This exact draft already has a receipt. Read it in History.' : stale ? 'Refresh durable state and review again before approving.' : status === 'expired' ? 'This draft expired. Run the graph and review a newly prepared draft.' : status === 'unavailable' ? 'The draft time is unavailable. Refresh and prepare again.' : status === 'held' ? 'Unresolved evidence holds approval.' : busy ? 'An action is pending. Wait for durable state.' : 'Tick the review confirmation to enable approval.'}</p>
        </aside></div> : <Empty title="No draft awaiting approval">{data.holds.length ? 'Unresolved source evidence holds collections. Correct it in Records.' : <>Run the Strands graph from the <a href="#/workspace">action queue</a> to prepare a source-backed draft.</>}</Empty>}
    </section> : null}
    {mode !== 'draft' ? <section className="panel terms-panel"><div className="panel-heading"><div><h2>Agree a payment arrangement</h2><p>A promise changes when you chase. It never changes how much is owed.</p></div></div>
      <div className="terms-grid"><form onSubmit={async e => { e.preventDefault(); setTermsConsent(''); await mutate('/arrangements/propose', { invoice_id: invoice, body: terms }); }}>
        <label htmlFor="invoice-select">Outstanding invoice</label><select id="invoice-select" required disabled={busy || !!selectedInvoice} value={invoice} onChange={e => { setInvoice(e.target.value); setTermsConsent(''); }}><option value="">Choose an invoice</option>{data.sales.filter(s => s.outstanding !== '0.00').map(s => <option key={s.doc_id} value={s.doc_id}>{s.doc_id} · {s.counterparty} · {money(s.outstanding)}</option>)}</select>
        {selectedInvoice ? <p className="field-help">Bound to the selected invoice. Select another case in the queue to change it.</p> : null}
        <label htmlFor="terms">Client's proposed terms</label><textarea id="terms" disabled={busy} value={terms} required rows={4} maxLength={4000} onChange={e => { setTerms(e.target.value); setTermsConsent(''); }} placeholder="YYYY-MM-DD: 0.00 EUR" aria-describedby="terms-help" />
        <p id="terms-help" className="field-help">Bounded rule reader, no AI judgment. One YYYY-MM-DD: 0.00 EUR line per instalment. The total must equal the current balance. Disputes or ambiguous replies require a person.</p>
        <button className="secondary" disabled={busy || stale || !invoice || !terms.trim() || !!data.holds.length}>Read proposed terms</button>{data.holds.length ? <p className="disabled-reason">Correct refused sources before proposing terms.</p> : <p className="field-help">{stale ? 'Refresh durable state before reading terms.' : 'Choose an invoice and enter dated amounts to read a proposal.'}</p>}
      </form>
      <div className="terms-preview">{data.proposal && proposalMatches ? <><Badge tone={data.proposal.plan ? 'blue' : 'red'}>{data.proposal.outcome}</Badge><h3>{data.proposal.invoice_id}</h3><p>{data.proposal.why}</p>{data.proposal.plan ? <><ul>{data.proposal.plan.instalments.map(i => <li key={i.due}><time>{i.due}</time><strong>{money(i.amount)}</strong></li>)}</ul><p className="field-help">Already received before this plan: {money(data.proposal.plan.baseline)}. Earlier payments do not satisfy future instalments.</p><details><summary>Stored terms and fingerprint</summary><pre>{data.proposal.body ?? 'Original proposal text unavailable'}</pre><code className="fingerprint">{data.proposal.fingerprint}</code></details><label className="checkbox"><input type="checkbox" checked={termsChecked && !termsExpired && !stale} disabled={busy || termsExpired || stale || !!data.holds.length} onChange={e => setTermsConsent(e.target.checked ? termsBinding : '')} /><span>I approve these exact dates and amounts.</span></label><button className="primary" disabled={busy || !termsChecked || termsExpired || stale || !!data.holds.length} onClick={async () => { if (await mutate('/arrangements/approve', { fingerprint: data.proposal!.fingerprint })) setTermsConsent(''); }}>Approve arrangement</button><p className="field-help">{termsExpired ? 'These terms expired. Read a new proposal before approving.' : 'Review the stored proposal and confirm its exact dates and amounts.'}</p></> : null}</> : <><h3>No terms proposed yet</h3><p>Read the client's dated amounts, then approve the exact proposal. Nothing is agreed by merely reading it.</p>{data.proposal ? <a href={workspaceLink(data.proposal.invoice_id, null, 'terms')}>Open the stored proposal for {data.proposal.invoice_id} →</a> : null}</>}</div></div>
      {data.arrangements.length ? <div className="agreed"><h3>Agreed arrangements</h3>{data.arrangements.map(a => <div key={a.invoice_id}><strong>{a.invoice_id}</strong><Badge tone="green">Agreed {a.agreed_on}</Badge><p>{a.instalments.map(i => `${i.due}: ${money(i.amount)}`).join(' · ')}</p><small>Approved by {a.approved_by}. Stored with the books; survives reload.</small></div>)}</div> : null}
    </section> : null}
    {data.graph && mode !== 'terms' ? <section className="panel"><div className="panel-heading"><div><h2>Six domain reports</h2><p>{data.graph.mode}</p></div></div><div className="domain-reports">{Object.entries(data.graph.reports).map(([name, report]) => <details key={name}><summary>{name}</summary><pre>{report}</pre></details>)}</div></section> : null}
  </>;
}
