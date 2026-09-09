import { useState } from 'react';
import type { Mutate, Settlement, Workspace } from './types';
import { Badge, Empty, Heading, money } from './ui';

function Balances({ title, rows }: { title: string; rows: Settlement[] }) {
  return <section className="panel"><div className="panel-heading"><h2>{title}</h2></div>{rows.length ?
    <div className="table-scroll"><table><caption className="sr-only">{title}</caption><thead><tr><th>Invoice / party</th><th className="numeric">Invoice total</th><th className="numeric">Settled</th><th className="numeric">Outstanding</th></tr></thead><tbody>{rows.map(row => <tr key={row.doc_id}><td><a href={`#/documents?source=${encodeURIComponent(row.doc_id)}`}>{row.doc_id}</a><span className="subline">{row.counterparty}</span></td><td className="numeric">{money(row.gross)}</td><td className="numeric">{money(row.settled)}</td><td className="numeric money">{money(row.outstanding)}</td></tr>)}</tbody></table></div> : <p className="section-note">No invoices posted.</p>}</section>;
}

export function Documents({ data, busy, mutate, route }: { data: Workspace; busy: boolean; mutate: Mutate; route: string }) {
  const [body, setBody] = useState('');
  const [replaceId, setReplaceId] = useState<string | null>(null);
  const [filter, setFilter] = useState('all');
  const selected = new URLSearchParams(route.split('?')[1]).get('source');
  const sources = data.sources.filter(s => filter === 'all' || s.status === filter);
  return <>
    <Heading eyebrow="INBOX → BOOKS" title="Documents & payments">Paste synthetic post. Inspect the evidence behind every balance.</Heading>
    <div className="intake-grid">
      <section className="panel intake"><h2>{replaceId ? `Correct ${replaceId}` : 'Read an email'}</h2><p>The bounded reader supports explicit EUR invoices and remittances. No live model call.</p>
        <div className="sample-buttons" aria-label="Load a synthetic sample">{(['invoice', 'payment', 'supplier', 'refusal'] as const).map(key => <button key={key} className="secondary small" onClick={() => setBody(data.samples[key])}>Sample {key}</button>)}</div>
        <form onSubmit={async e => { e.preventDefault(); if (await mutate('/intake', { body, replace_id: replaceId })) { setBody(''); setReplaceId(null); } }}>
          <label htmlFor="raw-email">Email headers and body <span className="required">Required</span></label>
          <textarea id="raw-email" value={body} onChange={e => setBody(e.target.value)} rows={9} maxLength={32000} required placeholder="From: …&#10;To: …&#10;Subject: Invoice …&#10;&#10;Paste synthetic invoice or remittance text." aria-describedby="intake-help" />
          <p id="intake-help" className="field-help">Synthetic data only. Include dates, currency, reference, net, VAT and total. Payments must reference a posted sales invoice.</p>
          <div className="flex flex-wrap gap-3"><button className="primary" disabled={busy || !body.trim()}>{busy ? 'Reading…' : replaceId ? 'Read corrected source' : 'Read & post email'}</button>{replaceId ? <button type="button" className="secondary" onClick={() => { setReplaceId(null); setBody(''); }}>Cancel correction</button> : null}</div>
        </form>
      </section>
      <aside className="workflow-note"><p className="eyebrow">FOLLOW THE MONEY</p><h2>One invoice.<br />One partial payment.<br />The amount that remains.</h2><ol><li>Load and post the sample invoice.</li><li>Load and post the sample payment.</li><li>Review the actual balance below.</li><li>Prepare a draft in the action queue.</li></ol><p className="fine-print">Addresses are read locally. Redaction happens before interpretation. Unsupported or contradictory evidence holds collections.</p></aside>
    </div>
    <Balances title="Client balances" rows={data.sales} /><Balances title="Supplier balances" rows={data.purchases} />
    <section className="panel"><div className="panel-heading"><div><h2>Source register <span className="count">{data.sources.length}</span></h2><p>Original post, document reference, and the reader's decision.</p></div><label className="inline-label">Show <select value={filter} onChange={e => setFilter(e.target.value)}><option value="all">All sources</option><option value="posted">Posted</option><option value="refused">Refused</option><option value="corrected">Corrected</option></select></label></div>
      {sources.length ? <div className="source-list">{sources.map(source => <details key={source.id} open={selected === source.document?.doc_id || source.status === 'refused'}><summary><span><strong>{source.document?.doc_id ?? source.id}</strong><span className="subline">{source.id} · {source.kind || 'Unrecognized post'}</span></span><Badge tone={source.status === 'refused' ? 'red' : source.status === 'posted' ? 'green' : 'neutral'}>{source.status}</Badge></summary>
        <div className="source-content"><p>{source.status === 'refused' ? source.error : `${source.redactions} sensitive field(s) redacted for interpretation.`}</p><pre>{source.body}</pre>{source.corrected_by ? <p>Corrected by {source.corrected_by}; original evidence retained.</p> : null}{source.status === 'refused' ? <button className="secondary" onClick={() => { setReplaceId(source.id); setBody(source.body); document.getElementById('raw-email')?.focus(); }}>Correct source</button> : null}</div>
      </details>)}</div> : <Empty title="No matching sources">Post an email above, or change the source filter.</Empty>}
    </section>
    <section className="panel"><div className="panel-heading"><h2>Quarter ledger · July–September</h2><Badge tone="green">Trial balance {money(data.trial_balance)}</Badge></div><dl className="report-grid">{[['Sales', data.pnl.sales], ['Purchases', data.pnl.purchases], ['Wages recorded', data.pnl.wages], ['Profit', data.pnl.profit], ['Cash received', data.cashflow.inflow], ['Cash paid', data.cashflow.outflow]].map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{money(value)}</dd></div>)}</dl><p className="section-note">Payroll is ledger state only. The public reader supports invoices and receipts; it cannot run payroll or execute payments.</p></section>
  </>;
}
