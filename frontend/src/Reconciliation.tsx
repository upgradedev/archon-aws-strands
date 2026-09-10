import type { MouseEvent } from 'react';
import type { Workspace } from './types';
import { intakeLink, reconciliation } from './decision';
import { money } from './ui';
import { reasonTarget, workspaceLink } from './ledger';
import { useClock } from './useClock';

function jump(event: MouseEvent<HTMLAnchorElement>, id: string) {
  event.preventDefault();
  document.getElementById(id)?.focus();
  document.getElementById(id)?.scrollIntoView({ block: 'center' });
}

export function ReconciliationStart({ data }: { data: Workspace }) {
  const invoice = data.draft?.invoice_id ?? reasonTarget(data).id ?? data.sales[0]?.doc_id;
  return <section className="reconciliation-hero" aria-label="Reconciliation journey">
    <div><p className="eyebrow">FOR THE JOINER RECONCILING AN INBOX</p><h2>Would you still chase after a payment arrives?</h2>
      <p>Prepare a collection draft. Add new payment evidence. See the old draft withdrawn, then review the supported next action.</p>
      <a className="primary" href={invoice ? workspaceLink(invoice) : intakeLink('invoice')}>{invoice ? 'Continue reconciliation' : 'Start reconciliation'} <span aria-hidden="true">→</span></a>
    </div><ol aria-label="Reconciliation steps"><li>Inspect the invoice and exact draft</li><li>Add a payment or check a duplicate</li><li>Review the changed decision and keep its evidence</li></ol>
    <p className="reconciliation-limit">Editable synthetic post · bounded rule reader · real Strands graph with scripted model · simulated mail only</p>
  </section>;
}

export function Reconciliation({ data, invoice, stale, view = 'draft' }: { data: Workspace; invoice: string; stale: boolean; view?: string }) {
  const decision = reconciliation(data, invoice, stale, useClock(data.draft?.at));
  const localReview = decision.href === '#collection-draft' || decision.href === '#prepare-current-draft';
  const href = view === 'terms' && localReview ? workspaceLink(invoice) : decision.href;
  const latest = data.sources.at(-1);
  return <section className="reconciliation-brief" aria-label="Current reconciliation decision" data-testid="reconciliation-decision">
    <p className="eyebrow">NEXT DECISION · REVISION {data.revision}</p><h2>{decision.title}</h2><p>{decision.why}</p>
    {href ? <a className="secondary" href={href} onClick={href.startsWith('#/') ? undefined : e => jump(e, href.slice(1))}>{href !== decision.href ? 'Open draft review' : decision.action} <span aria-hidden="true">→</span></a> : <p className="field-help">Use Refresh in the top bar before acting.</p>}
    {decision.before && decision.latest ? <div className="payment-change" data-testid="payment-change">
      <div><span>Before latest posted receipt · derived</span><strong>{money(decision.before)}</strong></div>
      <div><span>Now outstanding · current books</span><strong>{money(decision.balance!.outstanding)}</strong></div>
      <p><a href={workspaceLink(invoice, decision.latest.id)}>Inspect {decision.latest.id} · {decision.latest.document!.transfer_id || 'Identity unavailable'}</a> · {money(decision.latest.document!.amount)} recorded against {invoice}. A second email is not a second bank event.</p>
    </div> : null}
    {latest ? <p className="latest-evidence">Latest session evidence: <a href={`#/records?source=${encodeURIComponent(latest.id)}`}>{latest.id} · {latest.status}</a>. {latest.status === 'refused' ? latest.error : latest.resolution ? `Human resolution: ${latest.resolution.decision}. No additional payment posted.` : 'Open the retained source to inspect the reader decision.'}</p> : null}
    {decision.balance ? <details className="reconciliation-next"><summary>Try new evidence before approving</summary><p>These links only fill editable text in Records. Review and submit it to change the books.</p><div className="flex flex-wrap gap-3">
      <a href={intakeLink(invoice === 'JN-4410' && !decision.latest ? 'payment' : 'custom', invoice)}>Add payment evidence →</a>
      {decision.latest ? <a href={intakeLink('duplicate', invoice)}>Check a forwarded duplicate →</a> : null}
    </div><p>Use the original transfer reference for a duplicate. Only a genuinely distinct payment gets a distinct identity. Sample references represent invented events.</p></details> : null}
    <p className="reconciliation-limit">Source-backed means retained post, not verified bank settlement. All approvals here record simulated mail; no actual email or payment occurs.</p>
  </section>;
}
