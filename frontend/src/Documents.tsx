import { useEffect, useState, type CSSProperties } from 'react';
import type { Mutate, Settlement, Workspace } from './types';
import { Badge, Empty, Heading, money } from './ui';
import { cents, routeInfo, unique, workspaceLink } from './ledger';

const samples = ['invoice', 'payment', 'supplier', 'refusal'] as const;

function Balances({ title, rows }: { title: string; rows: Settlement[] }) {
  return <section className="panel"><div className="panel-heading"><h2>{title}</h2></div>{rows.length ?
    <div className="table-scroll"><table><caption className="sr-only">{title}</caption><thead><tr><th>Invoice / party</th><th className="numeric">Invoice total</th><th className="numeric">Settled</th><th className="numeric">Outstanding</th></tr></thead><tbody>{rows.map(row => <tr key={row.doc_id}><td><a href={`#/documents?source=${encodeURIComponent(row.doc_id)}`}>{row.doc_id}</a><span className="subline">{row.counterparty}</span></td><td className="numeric">{money(row.gross)}</td><td className="numeric">{money(row.settled)}</td><td className="numeric money">{money(row.outstanding)}</td></tr>)}</tbody></table></div> : <p className="section-note">No invoices posted.</p>}</section>;
}

export function Documents({ data, busy, mutate, route }: { data: Workspace; busy: boolean; mutate: Mutate; route: string }) {
  const { params } = routeInfo(route);
  const view = params.get('view') ?? 'sources';
  const urlFilter = params.get('filter') ?? 'all';
  const query = params.get('q') ?? '';
  const [body, setBody] = useState('');
  const [replaceId, setReplaceId] = useState<string | null>(null);
  const [filter, setFilter] = useState(urlFilter);
  const [intake, setIntake] = useState(route.startsWith('/documents') || params.get('intake') === 'open');
  useEffect(() => { setFilter(urlFilter); }, [urlFilter]);
  const openIntake = params.get('intake') === 'open';
  useEffect(() => { if (openIntake) setIntake(true); }, [openIntake]);
  const selected = params.get('source');
  const matches = (text: string) => text.toLowerCase().includes(query.trim().toLowerCase());
  const sources = unique(data.sources, s => s.id).filter(s => (filter === 'all' || s.status === filter) && matches(`${s.id} ${s.document?.doc_id ?? ''} ${s.body}`));
  const rows = (view === 'purchases' ? data.purchases : data.sales).filter(s => matches(`${s.doc_id} ${s.counterparty}`) && (urlFilter === 'outstanding' ? (cents(s.outstanding) ?? -1n) > 0n : urlFilter === 'overdue' ? (cents(s.outstanding) ?? -1n) > 0n && s.due < data.as_of : true));
  const payments = unique(data.sources.filter(s => s.status === 'posted' && s.kind === 'Receipt' && matches(`${s.document?.doc_id ?? ''} ${s.document?.settles ?? ''} ${s.id}`)), s => s.document?.doc_id ?? s.id);
  function changeParam(key: string, value: string) { const next = new URLSearchParams(params); if (value) next.set(key, value); else next.delete(key); location.hash = `/records?${next}`; }
  const selectedSample = samples.findIndex(key => body.length > 0 && body === data.samples[key]);
  return <>
    <Heading eyebrow="INBOX → BOOKS" title="Records">Find the posted documents and retained evidence behind every balance.</Heading>
    <div className="scope-line"><span>All session records · As of {data.as_of} · EUR</span><button className="secondary" aria-expanded={intake} onClick={() => setIntake(!intake)}>{intake ? 'Close intake' : 'Add synthetic email'}</button></div>
    <div className="workspace-tabs" role="group" aria-label="Record type">{[['sources', 'Sources'], ['sales', 'Client balances'], ['purchases', 'Supplier balances'], ['payments', 'Recorded receipts'], ['ledger', 'Quarter ledger']].map(([key, label]) => <a key={key} href={`#/records?view=${key}`} aria-current={view === key ? 'page' : undefined}>{label}</a>)}</div>
    <label className="records-search">Search records<input type="search" value={query} onChange={e => changeParam('q', e.target.value)} placeholder="Invoice, party or source reference" /></label>
    {intake ? <div className="intake-grid">
      <section className="panel intake"><h2>{replaceId ? `Correct ${replaceId}` : 'Read an email'}</h2><p>The bounded reader supports explicit EUR invoices and remittances. No live model call.</p>
        <div className="sample-buttons" role="group" aria-label="Load a synthetic sample" data-selected={selectedSample >= 0}
          style={{ '--selected-sample': selectedSample, '--sample-column': selectedSample % 2, '--sample-row': Math.floor(selectedSample / 2) } as CSSProperties}>
          {samples.map((key, index) => <button type="button" key={key} className="secondary small" aria-pressed={selectedSample === index}
            disabled={busy} onClick={() => setBody(data.samples[key])}>Sample {key}</button>)}
        </div>
        <form onSubmit={async e => { e.preventDefault(); if (await mutate('/intake', { body, replace_id: replaceId })) { setBody(''); setReplaceId(null); } }}>
          <label htmlFor="raw-email">Email headers and body <span className="required">Required</span></label>
          <textarea id="raw-email" disabled={busy} value={body} onChange={e => setBody(e.target.value)} rows={7} maxLength={32000} required placeholder="From: …&#10;To: …&#10;Subject: Invoice …&#10;&#10;Paste synthetic invoice or remittance text." aria-describedby="intake-help" />
          <p id="intake-help" className="field-help">Synthetic data only. Include dates, currency, reference, net, VAT and total. Payments must reference a posted sales invoice.</p>
          <div className="flex flex-wrap gap-3"><button className="primary" disabled={busy || !body.trim()}>{busy ? 'Reading…' : replaceId ? 'Read corrected source' : 'Read & post email'}</button>{replaceId ? <button type="button" className="secondary" onClick={() => { setReplaceId(null); setBody(''); }}>Cancel correction</button> : null}</div>
        </form>
      </section>
    </div> : null}
    {view === 'sales' || view === 'purchases' ? <><p className="section-note">{urlFilter === 'all' ? 'All balances' : `Filter: ${urlFilter}`} · {rows.length} matching record(s). <a href={`#/records?view=${view}`}>Clear filter</a></p><Balances title={view === 'sales' ? 'Client balances' : 'Supplier balances'} rows={rows} /></> : view === 'payments' ? <section className="panel"><div className="panel-heading"><h2>Recorded client receipts</h2></div>{payments.length ? <ul className="hold-list">{payments.map(s => <li key={s.id}><div><a href={`#/records?source=${encodeURIComponent(s.id)}`}>{s.document?.doc_id} · {s.id}</a><p>Settles {s.document?.settles ?? 'Unknown invoice'}</p>{s.document?.settles ? <a href={workspaceLink(s.document.settles, s.id)}>Inspect linked case →</a> : null}</div><strong>{money(s.document?.amount)}</strong></li>)}</ul> : <Empty title="No matching receipts">Only posted client remittances appear here. No bank feed is connected.</Empty>}</section> : view !== 'ledger' ? <section className="panel"><div className="panel-heading"><div><h2>Source register <span className="count">{sources.length}</span></h2><p>Original post, document reference, and the reader's decision.</p></div><label className="inline-label">Show <select value={filter} onChange={e => { setFilter(e.target.value); changeParam('filter', e.target.value); }}><option value="all">All sources</option><option value="posted">Posted</option><option value="refused">Refused</option><option value="corrected">Corrected</option></select></label></div>
      {selected && !sources.some(s => s.id === selected || s.document?.doc_id === selected) ? <p className="notice warning">Selected source is unavailable in this view. Clear the filter or choose a current source.</p> : null}
      {sources.length ? <div className="source-list">{sources.map(source => <details key={source.id} data-source-id={source.id} open={selected === source.id || selected === source.document?.doc_id || source.status === 'refused'}><summary><span><strong>{source.document?.doc_id ?? source.id}</strong><span className="subline">{source.id} · {source.kind || 'Unrecognized post'}</span></span><Badge tone={source.status === 'refused' ? 'red' : source.status === 'posted' ? 'green' : 'neutral'}>{source.status}</Badge></summary>
        <div className="source-content"><p>{source.status === 'refused' ? source.error : `${source.redactions} sensitive field(s) redacted for interpretation.`}</p><pre>{source.body}</pre>{source.document && (source.kind === 'SalesInvoice' || source.kind === 'Receipt') ? <p><a href={workspaceLink(source.document.settles ?? source.document.doc_id, source.id)}>Review this case in Workspace →</a></p> : null}{source.corrected_by ? <p>Corrected by {source.corrected_by}; original evidence retained.</p> : null}{source.status === 'refused' ? source.kind === 'ClientReply' ? <p>Client reply requires human resolution outside this demo. Collections remain held; replacing it with an invoice cannot resolve the dispute.</p> : <button className="secondary" disabled={busy} onClick={() => { setIntake(true); setReplaceId(source.id); setBody(source.body); requestAnimationFrame(() => document.getElementById('raw-email')?.focus()); }}>Correct source</button> : null}</div>
      </details>)}</div> : <Empty title="No matching sources">Post an email above, or change the source filter.</Empty>}
    </section> : <section className="panel"><div className="panel-heading"><h2>Quarter ledger · 2026-07-01 to {data.as_of}</h2><Badge tone="blue">Trial balance {money(data.trial_balance)}</Badge></div><dl className="report-grid">{[['Sales', data.pnl.sales], ['Purchases', data.pnl.purchases], ['Wages recorded', data.pnl.wages], ['Profit', data.pnl.profit], ['Cash received', data.cashflow.inflow], ['Cash paid', data.cashflow.outflow]].map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{money(value)}</dd></div>)}</dl><p className="section-note">Payroll is ledger state only. The public reader supports invoices and receipts; it cannot run payroll or execute payments.</p></section>}
  </>;
}
