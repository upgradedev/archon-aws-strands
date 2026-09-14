import { useState } from 'react';
import type { Mutate, Settlement, Source, Workspace } from './types';
import { Badge, Empty, money } from './ui';
import { cents, routeInfo, unique, validDay, workspaceLink } from './ledger';
import { ageBucket, documentDay, documentParty, documentViews, pageOf, partyIndex, postedDocuments, recordDay, recordLink, sourceLink, sourceOrigin } from './portfolio';
import { Resolution } from './Resolution';

function Pagination({ page, pages, total, start, change }: ReturnType<typeof pageOf> & { change: (key: string, value: string) => void }) {
  return <nav className="record-pagination" aria-label="Record pages"><p role="status">{total ? `${start + 1}–${Math.min(start + 25, total)} of ${total}` : '0 matching records'} · Page {page} of {pages} · 25 per page</p><div>
    <button className="secondary small" disabled={page <= 1} onClick={() => change('page', String(page - 1))}>Previous page</button>
    <button className="secondary small" disabled={page >= pages} onClick={() => change('page', String(page + 1))}>Next page</button>
  </div></nav>;
}

function Balances({ title, rows }: { title: string; rows: Settlement[] }) {
  const showCredits = rows.some(row => row.credited !== undefined && cents(row.credited) !== 0n);
  return <section className="panel"><div className="panel-heading"><h2>{title}</h2></div>{rows.length ?
    <div className="table-scroll" tabIndex={0} role="region" aria-label={title}><table><caption className="sr-only">{title}</caption><thead><tr><th>Invoice / party</th><th>Due</th><th className="numeric">Invoice total</th><th className="numeric">Settled · cash</th>{showCredits ? <th className="numeric">Credited</th> : null}<th className="numeric">Outstanding</th></tr></thead><tbody>{rows.map(row => <tr key={row.doc_id}><td><a href={`#/documents?source=${encodeURIComponent(row.doc_id)}`}>{row.doc_id}</a><span className="subline">{row.counterparty}</span></td><td>{row.due}</td><td className="numeric">{money(row.gross)}</td><td className="numeric">{money(row.settled)}</td>{showCredits ? <td className="numeric">{money(row.credited ?? '0.00')}</td> : null}<td className="numeric money">{money(row.outstanding)}{(cents(row.credited) ?? 0n) > 0n ? <span className="subline">{cents(row.outstanding) === 0n ? 'Closed with credit' : 'Credit applied'}</span> : null}</td></tr>)}</tbody></table></div> : <p className="section-note">No invoices posted.</p>}</section>;
}

function TypedDocuments({ title, rows, data }: { title: string; rows: Source[]; data: Workspace }) {
  const parties = partyIndex(data);
  return <section className="panel"><div className="panel-heading"><div><h2>{title}</h2><p>Posted documents · click a reference to inspect the retained source.</p></div></div>
    {rows.length ? <div className="table-scroll" tabIndex={0} role="region" aria-label={`${title} records`}><table className="typed-records"><caption className="sr-only">{title}</caption><thead><tr><th>Document / party</th><th>Financial date / due</th><th className="numeric">Net</th><th className="numeric">VAT</th><th className="numeric">Gross / cash</th><th>Linked evidence</th></tr></thead><tbody>{rows.map(source => {
      const doc = source.document!;
      const cash = source.kind === 'Receipt' || source.kind === 'Payment';
      return <tr key={source.id} data-record-id={doc.doc_id}><td><a href={sourceLink(source.id)}>{doc.doc_id}</a><span className="subline">{documentParty(source, parties) || 'Party not recorded'}</span></td><td>{documentDay(source) ?? 'Unknown'}{doc.due ? <span className="subline">Due {doc.due}</span> : null}</td><td className="numeric">{cash ? '—' : money(doc.net)}</td><td className="numeric">{cash ? '—' : money(doc.vat)}</td><td className="numeric">{money(cash ? doc.amount : doc.gross)}<span className="subline">{cash ? 'Recorded cash' : source.kind.endsWith('CreditNote') ? 'Credit · not cash' : 'Invoice total'}</span></td><td>{doc.settles ? <a href={sourceLink(doc.settles)}>Linked invoice {doc.settles} →</a> : <a href={recordLink({ q: doc.doc_id })}>Related sources →</a>}</td></tr>;
    })}</tbody></table></div> : <Empty title="No matching documents">Change the search or date range to see posted records.</Empty>}
    <p className="section-note">Fictional records only. Supplier payments are retained cash records; these views cannot execute a bank payment. Credits are supported in typed demo books, not yet by the raw-mail reader.</p>
  </section>;
}

function SourceRegister({ rows, selected, data, busy, mutate, correct }: {
  rows: Source[]; selected: string | null; data: Workspace; busy: boolean; mutate: Mutate; correct: (source: Source) => void;
}) {
  return rows.length ? <div className="source-list">{rows.map(source => <details key={source.id} data-source-id={source.id} open={selected === source.id || selected === source.document?.doc_id || source.status === 'refused'}><summary><span><strong>{source.document?.doc_id ?? source.id}</strong><span className="subline">{source.id} · {source.kind || 'Unrecognized post'}</span></span><Badge tone={source.status === 'refused' ? 'red' : source.status === 'posted' ? 'green' : 'neutral'}>{source.status}</Badge></summary>
    <div className="source-content"><p className="source-origin">{sourceOrigin(source)}</p><p>{source.status === 'refused' ? source.error : source.origin === 'fictional-business-fixture' ? 'Typed JSON fixture retained as source; not an email or AI extraction.' : `${source.redactions} sensitive field(s) redacted for interpretation.`}</p><p className="field-help">{documentDay(source) ? 'Financial date' : 'Recorded at (financial date unavailable)'}: {recordDay(source) ?? 'Unknown'}</p><pre>{source.body}</pre>
      {source.document?.settles ? <p><a href={sourceLink(source.document.settles)}>Inspect linked invoice {source.document.settles} →</a></p> : null}
      {source.document && ['SalesInvoice', 'Receipt', 'SalesCreditNote'].includes(source.kind) ? <p><a href={workspaceLink(source.document.settles ?? source.document.doc_id, source.id)}>Review this case in Workspace →</a></p> : null}
      {source.kind.endsWith('CreditNote') ? <p>Credit reduces the linked invoice balance. It is not a cash receipt or bank payment.</p> : null}
      {source.corrected_by ? <p>Corrected by {source.corrected_by}; original evidence retained.</p> : null}
      {source.status === 'refused' ? ['ClientReply', 'LegacyPaymentReview'].includes(source.kind) ? <Resolution key={`${source.id}:${data.revision}`} source={source} data={data} busy={busy} mutate={mutate} /> : <button className="secondary" disabled={busy} onClick={() => correct(source)}>Correct source</button> : null}
      {source.status === 'refused' && source.kind === 'Receipt' ? <Resolution key={`${source.id}:${data.revision}`} source={source} data={data} busy={busy} mutate={mutate} /> : null}
      {source.resolution ? <p>Human resolution: {source.resolution.decision} · {source.resolution.note}. Original evidence retained.</p> : null}
    </div>
  </details>)}</div> : <Empty title="No matching sources">Post an email above, or change the source filter.</Empty>;
}

export function RecordViews({ data, busy, mutate, route, correct }: { data: Workspace; busy: boolean; mutate: Mutate; route: string; correct: (source: Source) => void }) {
  // Event-local values keep standalone controls responsive; new URL props always win.
  // No effect is needed to copy route filters into component state.
  const [edited, setEdited] = useState<{ route: string; query: string } | null>(null);
  const params = edited?.route === route ? new URLSearchParams(edited.query) : routeInfo(route).params;
  if (edited && edited.route !== route) setEdited(null);
  const view = params.get('view') ?? 'sources', filter = params.get('filter') ?? 'all';
  const query = params.get('q') ?? '', from = params.get('from') ?? '', to = params.get('to') ?? '';
  const party = params.get('party'), age = params.get('age'), selected = params.get('source');
  const typed = documentViews.find(v => v.view === view);
  const balances = view === 'sales' || view === 'purchases';
  const sourceView = !typed && !balances && view !== 'payments' && view !== 'ledger';
  const invalidRange = !!((from && !validDay(from)) || (to && !validDay(to)) || (from && to && from > to));
  const matches = (text: string) => text.toLowerCase().includes(query.trim().toLowerCase());
  const inRange = (day?: string) => !invalidRange && ((!from && !to) || !!day && validDay(day) && (!from || day >= from) && (!to || day <= to));
  const parties = partyIndex(data);
  const byId = new Map(data.sources.filter(s => s.status === 'posted' && s.document).map(s => [s.document!.doc_id, s]));
  const matchSource = (s: Source) => matches(`${s.id} ${s.document?.doc_id ?? ''} ${s.document?.settles ?? ''} ${documentParty(s, parties)} ${s.body}`)
    && (!party || documentParty(s, parties) === party) && inRange(sourceView ? recordDay(s) : documentDay(s));
  const sources = sourceView ? unique([...data.holds.filter(s => s.kind === 'LegacyPaymentReview'), ...data.sources], s => s.id).filter(s => (filter === 'all' || s.status === filter) && matchSource(s))
    : postedDocuments(data.sources).filter(s => s.kind === (typed?.kind ?? 'Receipt') && matchSource(s));
  const rows = (view === 'purchases' ? data.purchases : data.sales).filter(s => matches(`${s.doc_id} ${s.counterparty}`) && (!party || s.counterparty === party)
    && (filter === 'outstanding' ? (cents(s.outstanding) ?? -1n) > 0n : filter === 'overdue' ? (cents(s.outstanding) ?? -1n) > 0n && s.due < data.as_of : filter === 'closed' ? cents(s.outstanding) === 0n : true)
    && (!age || ageBucket(s, data.as_of) === age) && inRange(byId.get(s.doc_id)?.document?.issued));
  const sourcePage = pageOf(sources, params.get('page'), sources.findIndex(s => s.id === selected || s.document?.doc_id === selected));
  const balancePage = pageOf(rows, params.get('page'));
  function change(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value); else next.delete(key);
    if (key !== 'page') next.delete('page');
    setEdited({ route, query: next.toString() });
    if (key === 'q' || key === 'from' || key === 'to') {
      history.replaceState(null, '', `#/records?${next}`);
      window.dispatchEvent(new HashChangeEvent('hashchange'));
    } else location.hash = `/records?${next}`;
  }
  return <>
    <div className="workspace-tabs" role="group" aria-label="Document views">{documentViews.map(item => <a key={item.view} href={recordLink({ view: item.view })} aria-current={view === item.view ? 'page' : undefined}>{item.label}</a>)}</div>
    <div className="workspace-tabs record-aliases" role="group" aria-label="Record type">{[['sources', 'Sources'], ['sales', 'Client balances'], ['purchases', 'Supplier balances'], ['payments', 'Recorded receipts'], ['ledger', 'Quarter ledger']].map(([key, label]) => <a key={key} href={recordLink({ view: key })} aria-current={view === key ? 'page' : undefined}>{label}</a>)}</div>
    {view !== 'ledger' ? <>
      <div className="record-filters"><label className="records-search">Search records<input type="search" value={query} onChange={e => change('q', e.target.value)} placeholder="Invoice, party or source reference" /></label><label>From date<input type="date" value={from} onChange={e => change('from', e.target.value)} /></label><label>To date<input type="date" value={to} onChange={e => change('to', e.target.value)} /></label></div>
      <p className="field-help">Inclusive date range · {sourceView ? 'financial date where recorded; otherwise retained source date' : balances ? 'invoice issue date' : 'issued / received-on / paid-on date'} · All dates unless selected. {party ? `Party: ${party}. ` : ''}{age ? `Aging: ${age}. ` : ''}<a href={recordLink({ view })}>Clear filter</a></p>
      {invalidRange ? <p className="notice warning" role="alert">Choose valid dates with From date on or before To date. No records match an invalid range.</p> : null}
      {balances ? <div className="workspace-tabs" role="group" aria-label="Balance filter">{[['all', 'All balances'], ['outstanding', 'Open balances'], ['overdue', 'Overdue balances'], ['closed', 'Closed balances']].map(([key, label]) => <button className="secondary small" key={key} aria-pressed={filter === key} onClick={() => change('filter', key)}>{label}</button>)}</div> : null}
      {sourceView ? <section className="panel"><div className="panel-heading"><div><h2>Source register <span className="count">{sources.length}</span></h2><p>Original post, document reference, and the reader's decision.</p></div><label className="inline-label">Show <select value={filter} onChange={e => change('filter', e.target.value)}><option value="all">All sources</option><option value="posted">Posted</option><option value="refused">Refused</option><option value="corrected">Corrected</option><option value="resolved">Resolved</option></select></label></div>
        {selected && !sources.some(s => s.id === selected || s.document?.doc_id === selected) ? <p className="notice warning">Selected source is unavailable in this view. Clear the filter or choose a current source.</p> : null}
        <SourceRegister rows={sourcePage.rows} selected={selected} data={data} busy={busy} mutate={mutate} correct={correct} />
      </section> : balances ? <><p className="section-note">{filter === 'all' ? 'All balances' : `Filter: ${filter}`} · {rows.length} matching record(s).</p><Balances title={view === 'sales' ? 'Client balances' : 'Supplier balances'} rows={balancePage.rows} /></>
        : view === 'payments' ? <section className="panel"><div className="panel-heading"><h2>Recorded client receipts</h2></div>{sources.length ? <ul className="hold-list">{sourcePage.rows.map(s => <li key={s.id}><div><a href={sourceLink(s.id)}>{s.document?.doc_id} · {s.id}</a><p>Settles {s.document?.settles ?? 'Unknown invoice'}</p>{s.document?.settles ? <a href={workspaceLink(s.document.settles, s.id)}>Inspect linked case →</a> : null}</div><strong>{money(s.document?.amount)}</strong></li>)}</ul> : <Empty title="No matching receipts">Only posted client remittances appear here. No bank feed is connected.</Empty>}</section>
        : <TypedDocuments title={typed!.label} rows={sourcePage.rows} data={data} />}
      <Pagination {...(balances ? balancePage : sourcePage)} change={change} />
    </> : <section className="panel"><div className="panel-heading"><h2>Quarter ledger · 2026-07-01 to {data.as_of}</h2><Badge tone="blue">Trial balance {money(data.trial_balance)}</Badge></div><dl className="report-grid">{[['Sales', data.pnl.sales], ['Purchases', data.pnl.purchases], ['Wages recorded', data.pnl.wages], [data.demo_seed === 'business-v1' ? 'Trading surplus' : 'Profit', data.pnl.profit], ['Cash received', data.cashflow.inflow], ['Cash paid', data.cashflow.outflow]].map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{money(value)}</dd></div>)}</dl><p className="section-note">{data.demo_seed === 'business-v1' ? 'No payroll is included in this seed. Trading surplus is not complete net profit. ' : ''}Payroll is ledger state only. The public reader supports invoices and client receipts; it cannot ingest credit notes, run payroll or execute payments.</p></section>}
  </>;
}
