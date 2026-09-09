import { useState } from 'react';
import type { Mutate, Workspace } from './types';
import { Badge, Empty, Heading, money } from './ui';

export function Approvals({ data, busy, mutate }: { data: Workspace; busy: boolean; mutate: Mutate }) {
  const [checked, setChecked] = useState(false);
  const [termsChecked, setTermsChecked] = useState(false);
  const [invoice, setInvoice] = useState('');
  const [terms, setTerms] = useState('');
  const draft = data.draft;
  const receipt = data.receipts.find(r => r.fingerprint === draft?.fingerprint);
  return <>
    <Heading eyebrow="HUMAN DECISIONS" title="Approvals & arrangements">Your approval belongs to these exact words, this recipient, and this evidence.</Heading>
    <section className="panel"><div className="panel-heading"><div><h2>Collection draft</h2><p>Every money claim is re-derived at approval. Drafts expire after 30 minutes.</p></div><Badge tone="amber">Simulated delivery</Badge></div>
      {draft ? <div className="draft-grid"><article className="email"><dl><dt>To</dt><dd>{draft.recipient}</dd><dt>Subject</dt><dd>{draft.subject}</dd><dt>Invoice</dt><dd><a href={`#/documents?source=${encodeURIComponent(draft.invoice_id)}`}>{draft.invoice_id} · Source evidence ↗</a></dd></dl><pre>{draft.body}</pre><details><summary>Exact content fingerprint</summary><code className="fingerprint">{draft.fingerprint}</code></details></article>
        <aside className="approval-box"><h3>Review before approving</h3><p>The public outbox is simulated. This records an approval and a simulated provider receipt. No message is sent to this address.</p>
          <label className="checkbox"><input type="checkbox" checked={checked} onChange={e => setChecked(e.target.checked)} disabled={!!receipt} /><span>I reviewed this recipient, subject, body and balance.</span></label>
          <button className="primary" disabled={busy || !checked || !!receipt} onClick={async () => { if (await mutate('/approve', { fingerprint: draft.fingerprint })) { setChecked(false); location.hash = '/activity'; } }}>Approve exact draft · simulate</button>
          <p className="field-help">{receipt ? 'This exact draft already has a receipt. Read it in Activity.' : 'Tick the review confirmation to enable approval.'}</p>
        </aside></div> : <Empty title="No draft awaiting approval">{data.holds.length ? 'Unresolved source evidence holds collections. Correct it in Documents & payments.' : <>Run the Strands graph from the <a href="#/queue">action queue</a> to prepare a source-backed draft.</>}</Empty>}
    </section>
    <section className="panel terms-panel"><div className="panel-heading"><div><h2>Agree a payment arrangement</h2><p>A promise changes when you chase. It never changes how much is owed.</p></div></div>
      <div className="terms-grid"><form onSubmit={async e => { e.preventDefault(); setTermsChecked(false); await mutate('/arrangements/propose', { invoice_id: invoice, body: terms }); }}>
        <label htmlFor="invoice-select">Outstanding invoice</label><select id="invoice-select" required value={invoice} onChange={e => setInvoice(e.target.value)}><option value="">Choose an invoice</option>{data.sales.filter(s => s.outstanding !== '0.00').map(s => <option key={s.doc_id} value={s.doc_id}>{s.doc_id} · {s.counterparty} · {money(s.outstanding)}</option>)}</select>
        <label htmlFor="terms">Client's proposed terms</label><textarea id="terms" value={terms} required rows={4} maxLength={4000} onChange={e => setTerms(e.target.value)} placeholder="2026-09-20: 600.00 EUR&#10;2026-10-05: 660.00 EUR" aria-describedby="terms-help" />
        <p id="terms-help" className="field-help">Bounded rule reader, no AI judgment. One YYYY-MM-DD: 0.00 EUR line per instalment. The total must equal the current balance. Disputes or ambiguous replies require a person.</p>
        <button className="secondary" disabled={busy || !invoice || !terms.trim() || !!data.holds.length}>Read proposed terms</button>{data.holds.length ? <p className="disabled-reason">Correct refused sources before proposing terms.</p> : null}
      </form>
      <div className="terms-preview">{data.proposal ? <><Badge tone={data.proposal.plan ? 'blue' : 'red'}>{data.proposal.outcome}</Badge><h3>{data.proposal.invoice_id}</h3><p>{data.proposal.why}</p>{data.proposal.plan ? <><ul>{data.proposal.plan.instalments.map(i => <li key={i.due}><time>{i.due}</time><strong>{money(i.amount)}</strong></li>)}</ul><p className="field-help">Already received before this plan: {money(data.proposal.plan.baseline)}. Earlier payments do not satisfy future instalments.</p><label className="checkbox"><input type="checkbox" checked={termsChecked} onChange={e => setTermsChecked(e.target.checked)} /><span>I approve these exact dates and amounts.</span></label><button className="primary" disabled={busy || !termsChecked} onClick={async () => { if (await mutate('/arrangements/approve', { fingerprint: data.proposal!.fingerprint })) setTermsChecked(false); }}>Approve arrangement</button></> : null}</> : <><h3>No terms proposed yet</h3><p>Read the client's dated amounts, then approve the exact proposal. Nothing is agreed by merely reading it.</p></>}</div></div>
      {data.arrangements.length ? <div className="agreed"><h3>Agreed arrangements</h3>{data.arrangements.map(a => <div key={a.invoice_id}><strong>{a.invoice_id}</strong><Badge tone="green">Agreed {a.agreed_on}</Badge><p>{a.instalments.map(i => `${i.due}: ${money(i.amount)}`).join(' · ')}</p><small>Approved by {a.approved_by}. Stored with the books; survives reload.</small></div>)}</div> : null}
    </section>
    {data.graph ? <section className="panel"><div className="panel-heading"><div><h2>Six domain reports</h2><p>{data.graph.mode}</p></div></div><div className="domain-reports">{Object.entries(data.graph.reports).map(([name, report]) => <details key={name}><summary>{name}</summary><pre>{report}</pre></details>)}</div></section> : null}
  </>;
}
