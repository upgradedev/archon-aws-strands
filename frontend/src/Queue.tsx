import type { Mutate, Workspace } from './types';
import { Badge, Empty, Heading, money } from './ui';
import { Approvals } from './Approvals';
import { DraftEvidence } from './DraftEvidence';
import { cents, linkedSources, reasonTarget, routeInfo, unique, workspaceLink } from './ledger';
import { pageOf, sourceOrigin } from './portfolio';
import { Reconciliation } from './Reconciliation';
import { EvidenceBundle, type Bundle } from './EvidenceBundle';

export function Queue({ data, busy, mutate, route = '/workspace', stale = false, reviewEpoch = 0, loadEvidence }: {
  data: Workspace; busy: boolean; mutate: Mutate; route?: string; stale?: boolean; reviewEpoch?: number; loadEvidence?: () => Promise<Bundle>;
}) {
  const { params } = routeInfo(route);
  const target = reasonTarget(data);
  const invoice = params.get('invoice') ?? data.draft?.invoice_id ?? target.id ?? data.sales[0]?.doc_id ?? '';
  const balance = data.sales.find(s => s.doc_id === invoice);
  const sources = linkedSources(data, invoice);
  const selectedSource = params.get('source');
  const source = selectedSource ? sources.find(s => s.id === selectedSource || s.document?.doc_id === selectedSource) : sources[0];
  const view = params.get('view') === 'terms' ? 'terms' : 'draft';
  const held = data.holds.length > 0;
  const canPrepare = !!target.id && target.id === invoice && !target.issue && !held && !stale && !busy && (!selectedSource || !!source);
  const items = unique([...data.queue.ready, ...data.queue.blocked], item => item.invoice_id);
  const queuePage = pageOf(items, params.get('queuePage'), items.findIndex(item => item.invoice_id === invoice));
  function queuePageLink(page: number) {
    const next = new URLSearchParams(params); next.set('queuePage', String(page));
    return `#/workspace?${next}`;
  }
  return <>
    <Heading eyebrow="FINOPS / COLLECTIONS DESK" title="Workspace">Inspect one case. Follow its sources. Review one exact decision.</Heading>
    <div className="scope-line"><span>My Joinery · EUR · As of {data.as_of} · Revision {data.revision}</span><a href="#/records?intake=open">Add invoice or payment →</a></div>
    <Reconciliation data={data} invoice={invoice} stale={stale || !!selectedSource && !source} view={view} />
    {held ? <div className="notice warning"><strong>Collections held · incomplete evidence</strong><p>{data.holds.length} refused source email(s) may change these balances.</p><a href="#/records?filter=refused">Review refused sources →</a></div> : null}
    <div className="collections-desk" data-testid="selected-workspace">
      <aside className="panel case-context" aria-label="Queue and case sources">
        <div className="panel-heading"><div><h2>Priority queue <span className="count">{items.length}</span></h2><p>Overdue invoices and recorded holds.</p></div></div>
        {items.length ? <ul className="case-list hold-list">{queuePage.rows.map(item => <li key={item.invoice_id}><a className="case-row" href={workspaceLink(item.invoice_id)} aria-current={item.invoice_id === invoice ? 'true' : undefined}>
          <div><strong>{item.client}</strong><span className="subline">{item.invoice_id}</span></div><strong className="case-amount">{money(item.outstanding)}</strong>
          <span className="case-status">{item.reason || (held ? 'Evidence held' : `${item.days_overdue} days overdue`)}{target.id === item.invoice_id ? ' · Backend priority' : ''}</span>
        </a></li>)}</ul> : <Empty title="Nothing to chase yet">Add a sales invoice and its payments in <a href="#/records?intake=open">Records</a>. Settled invoices and agreed arrangements stay out of the ready queue.</Empty>}
        {queuePage.pages > 1 ? <div className="queue-pagination"><span>Queue page {queuePage.page} of {queuePage.pages}</span>{queuePage.page > 1 ? <a href={queuePageLink(queuePage.page - 1)}>Previous cases</a> : null}{queuePage.page < queuePage.pages ? <a href={queuePageLink(queuePage.page + 1)}>Next cases</a> : null}</div> : null}
        <div className="panel-heading"><div><h2>Case sources</h2><p>{balance ? `${invoice} · retained post` : 'Select an invoice to inspect its evidence.'}</p></div></div>
        <div className="case-sources">{sources.length ? sources.map(item => <a className="source-choice" key={item.id} href={workspaceLink(invoice, item.id, view)} aria-current={source?.id === item.id ? 'true' : undefined}>
          <strong>{item.kind === 'Receipt' ? 'Recorded receipt' : item.kind === 'SalesCreditNote' ? 'Sales credit · not cash' : 'Invoice'} · {item.document?.doc_id}</strong><span>{item.id} · {item.status}</span>{item.document?.amount ? <span>{money(item.document.amount)}</span> : null}
        </a>) : <p className="section-note">No linked posted source is available for this selection.</p>}</div>
        {data.holds.length ? <div className="case-sources"><h3>Source holds</h3>{data.holds.map(item => <a key={item.id} className="source-choice" href={`#/records?filter=refused&source=${encodeURIComponent(item.id)}`}><strong>{item.id}</strong><span>{item.error}</span></a>)}</div> : null}
        <details className="case-guidance"><summary>How priority and holds work</summary><p>The backend prepares only its oldest overdue invoice, then the largest on a tie. Selecting evidence does not retarget that operation.</p><p>Six ledger readers must report before the composer runs.</p></details>
      </aside>
      <section className="case-review" aria-label="Document and signoff">
        {!balance ? <div className="panel"><Empty title={invoice ? 'Selected invoice unavailable' : 'No invoice selected'}>{invoice ? <>The invoice {invoice} is not in this session. <a href="#/workspace">Return to current cases</a>.</> : <>Post a synthetic invoice in <a href="#/records?intake=open">Records</a> to start.</>}</Empty></div> : <>
          <section className="panel document-preview"><div className="panel-heading"><div><p className="eyebrow">SELECTED CASE</p><h2>{invoice} · {balance.counterparty}</h2></div><Badge tone="blue">{money(balance.outstanding)} outstanding</Badge></div>
            <div className="source-preview">{source ? <details open key={source.id} data-source-id={source.id}><summary>{source.document?.doc_id} · {source.id} · Original source</summary><p className="source-origin">{sourceOrigin(source)}</p><pre>{source.body}</pre><a href={`#/records?source=${encodeURIComponent(source.id)}`}>Open in source register ↗</a></details> : <p>{selectedSource ? 'Selected source does not belong to this invoice. Choose a case source.' : 'Original invoice source unavailable. The ledger balance alone is not a source document.'}</p>}</div>
            <dl className="arithmetic-trace" aria-label="Invoice arithmetic"><div><dt>Invoice total</dt><dd>{money(balance.gross)}</dd></div><span aria-hidden="true">−</span><div><dt>Recorded receipts</dt><dd>{money(balance.settled)}</dd></div>{(cents(balance.credited) ?? 0n) > 0n ? <><span aria-hidden="true">−</span><div><dt>Credited · not cash</dt><dd>{money(balance.credited)}</dd></div></> : null}<span aria-hidden="true">=</span><div><dt>Outstanding</dt><dd>{money(balance.outstanding)}</dd></div></dl>
          </section>
          <div className="workspace-tabs" role="group" aria-label="Case review"><a href={workspaceLink(invoice, source?.id, 'draft')} aria-current={view === 'draft' ? 'page' : undefined}>Draft & signoff</a><a href={workspaceLink(invoice, source?.id, 'terms')} aria-current={view === 'terms' ? 'page' : undefined}>Payment arrangement</a></div>
          {view === 'draft' ? <section className="prepare-panel" id="prepare-current-draft" tabIndex={-1}><button className="primary" disabled={!canPrepare} onClick={async () => { const origin = location.hash; if (await mutate('/reason')) { if (location.hash === origin) location.hash = workspaceLink(invoice, source?.id).slice(1); } }}>{busy ? 'Working…' : 'Run Strands & prepare draft'}</button><p className="field-help">{stale ? 'Refresh durable state before preparing or approving.' : held ? 'Disabled until every refused source is corrected.' : target.id !== invoice && target.id ? <>This case is evidence only for collection drafting. <a href={workspaceLink(target.id)}>Open backend priority {target.id} →</a></> : target.issue || `Prepares the backend priority ${target.id}. No email is sent.`}</p></section> : null}
          {view === 'terms' || !data.draft || data.draft.invoice_id === invoice ? <Approvals key={`${invoice}-${source?.id}-${view}-${reviewEpoch}-${data.revision}`} data={data} busy={busy} mutate={mutate} mode={view} selectedInvoice={invoice} stale={stale || !!selectedSource && !source} /> : <section className="panel"><Empty title="Draft belongs to another invoice">The stored draft is for {data.draft.invoice_id}. <a href={workspaceLink(data.draft.invoice_id)}>Review that exact draft →</a></Empty><DraftEvidence data={data} invoiceId={invoice} /></section>}
        </>}
        {!balance ? <section className="prepare-panel"><button className="primary" disabled>Run Strands & prepare draft</button><p className="field-help">{target.issue || 'Select the backend priority invoice before preparing a draft.'}</p></section> : null}
      </section>
    </div>
    {loadEvidence ? <EvidenceBundle load={loadEvidence} revision={data.revision} /> : null}
  </>;
}
