import type { Source, Workspace } from './types';
import { money } from './ui';

function SourceBadge({ source, label }: { source: Source; label: string }) {
  return <a className="source-badge" href={`#/documents?source=${encodeURIComponent(source.id)}`}>
    <span className="source-badge-label">{label}<span aria-hidden="true"> ↗</span></span>
    <span>{source.document!.doc_id}</span>
    <small>{source.id}</small>
  </a>;
}

/** Relationships come from posted document fields, never the draft's prose. */
export function DraftEvidence({ data, invoiceId }: { data: Workspace; invoiceId: string }) {
  const balance = data.sales.find(row => row.doc_id === invoiceId);
  const invoices = data.sources.filter(source => source.status === 'posted'
    && source.kind === 'SalesInvoice' && source.document?.doc_id === invoiceId);
  const receipts = data.sources.filter(source => source.status === 'posted'
    && source.kind === 'Receipt' && source.document?.settles === invoiceId);

  return <section className="draft-evidence" aria-label="Draft ledger evidence">
    <div className="evidence-heading"><h3>Follow this balance</h3><span className="evidence-kicker">CURRENT LEDGER · EUR</span></div>
    <p>Ledger values for {invoiceId}. The exact email above is unchanged; approval rechecks its evidence.</p>
    {balance ? <dl className="evidence-figures">
      <div><dt>Invoice total</dt><dd>{money(balance.gross)}</dd></div>
      <div><dt>Recorded receipts</dt><dd>{money(balance.settled)}</dd></div>
      <div><dt>Outstanding</dt><dd>{money(balance.outstanding)}</dd></div>
    </dl> : <p className="evidence-unavailable">No current sales balance is available for this draft.</p>}
    <div className="evidence-sources">
      <div><h4>Sourced · posted invoice</h4>
        {invoices.length ? <div className="source-badges">{invoices.map(source => <SourceBadge key={source.id} source={source} label="Invoice source" />)}</div>
          : <p className="evidence-unavailable">No linked posted invoice source is available.</p>}
      </div>
      <div><h4>{receipts.length ? 'Reconciled in ledger · linked receipts' : 'Receipt evidence'}</h4>
        {receipts.length ? <div className="source-badges">{receipts.map(source => <SourceBadge key={source.id} source={source}
          label={source.document!.amount ? `Receipt source · ${money(source.document!.amount)}` : 'Receipt source'} />)}</div>
          : <p className="evidence-unavailable">No linked posted receipt sources are available.</p>}
      </div>
    </div>
    <p className="evidence-limit">Sourced means retained post. Reconciled means receipts linked by invoice reference in these books, not independent bank verification. Delivery remains simulated.</p>
  </section>;
}
