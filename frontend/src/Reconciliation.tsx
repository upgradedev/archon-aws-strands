import type { MouseEvent } from 'react';
import type { Workspace } from './types';
import { intakeLink, reconciliation, reviewReset } from './decision';
import { money } from './ui';
import { reasonTarget, workspaceLink } from './ledger';
import { useClock } from './useClock';

function jump(event: MouseEvent<HTMLAnchorElement>, id: string) {
  event.preventDefault();
  document.getElementById(id)?.focus();
  document.getElementById(id)?.scrollIntoView({ block: 'center' });
}

export function ReconciliationStart({ data, stale = false }: { data: Workspace; stale?: boolean }) {
  const invoice = data.draft?.invoice_id ?? reasonTarget(data).id ?? data.sales[0]?.doc_id;
  const decision = reconciliation(data, invoice ?? '', stale, useClock(data.draft?.at));
  const returning = data.sources.length > 0 || data.activity.length > 0;
  const href = decision.href?.startsWith('#/') ? decision.href : invoice ? workspaceLink(invoice) : intakeLink('invoice');
  return <section className="reconciliation-hero" aria-label="Reconciliation journey">
    <div><p className="eyebrow">ALEX'S COLLECTIONS DESK</p>
      <h2>{returning ? decision.title : 'Would you still chase after a payment arrives?'}</h2>
      <p>{returning ? decision.why : 'Alex, a self-employed joiner, checks client payments. Get the current balance, its source evidence and one safe next action.'}</p>
      {stale ? <a className="primary" href="#refresh-workspace" onClick={e => jump(e, 'refresh-workspace')}>Refresh before continuing <span aria-hidden="true">→</span></a>
        : <a className="primary" href={href}>{invoice || returning ? 'Continue reconciliation' : 'Start reconciliation'} <span aria-hidden="true">→</span></a>}
      <p className="desk-next">{returning ? `Next: ${decision.action}.` : 'First: review and post an editable sample invoice. No account needed.'}</p>
    </div><div className="desk-context">
      {decision.balance ? <><p className="eyebrow">{stale ? 'LAST KNOWN BALANCE' : 'CURRENT LEDGER BALANCE'}</p><h3>{decision.balance.counterparty} · {invoice}</h3><strong className="desk-balance">{money(decision.balance.outstanding)}</strong><p>{money(decision.balance.gross)} invoiced − {money(decision.balance.settled)} recorded receipts</p><a href={workspaceLink(invoice)}>Inspect invoice and receipt sources →</a></>
        : <><p className="eyebrow">{returning ? 'YOUR SAVED WORKSPACE' : 'YOUR FIRST DECISION'}</p><p>{returning ? 'Your sources and decisions are retained in this browser’s session. Resolve incomplete evidence before collecting.' : 'Your books start empty. Alex and every example are invented; nothing is posted until you submit it.'}</p><ol aria-label="Reconciliation steps"><li>Inspect the invoice and exact draft</li><li>Add a payment or check a duplicate</li><li>Review the changed decision and keep its evidence</li></ol></>}
    </div>
    <p className="reconciliation-limit">{data.live ? 'Fictional examples · real Bedrock and Strands · controlled real SES mail after approval. No bank connection or payment execution.' : 'Synthetic examples · real Strands graph with scripted model · simulated mail only. Retained post, no bank connection. No real email or payment.'}</p>
    <details className="desk-details"><summary>How this demo works</summary><p>{data.live ? 'Bedrock reads editable fictional examples; source and ledger checks can refuse them.' : 'The bounded rule reader handles editable synthetic post.'} Alex is an invented persona. This session handle lasts seven days; records may be retained longer. No measured time or money savings are claimed.</p></details>
  </section>;
}

export function Reconciliation({ data, invoice, stale, view = 'draft' }: { data: Workspace; invoice: string; stale: boolean; view?: string }) {
  const decision = reconciliation(data, invoice, stale, useClock(data.draft?.at));
  const localReview = decision.href === '#collection-draft' || decision.href === '#prepare-current-draft';
  const href = view === 'terms' && localReview ? workspaceLink(invoice) : decision.href;
  const latest = data.sources.at(-1);
  const reset = reviewReset(data);
  return <section className="reconciliation-brief" aria-label="Current reconciliation decision" data-testid="reconciliation-decision">
    <p className="eyebrow">NEXT DECISION · REVISION {data.revision}</p><h2>{decision.title}</h2><p>{decision.why}</p>
    {decision.balance ? <div className="desk-case-balance"><div><span>{stale ? 'Last known outstanding' : 'Current outstanding'}</span><strong>{money(decision.balance.outstanding)}</strong></div><p>{invoice} · {decision.balance.counterparty}<br />{money(decision.balance.gross)} invoiced − {money(decision.balance.settled)} recorded receipts</p><a href={workspaceLink(invoice, decision.latest?.id)}>Follow the ledger sources →</a></div> : null}
    {reset ? <aside className="review-reset" aria-label="Previous review invalidated"><h3>Previous draft cannot be approved</h3><p>Evidence changed after the last graph run. Any previous draft and review confirmation are no longer usable. Review the current books before a new decision.</p><p>{reset.title} · {reset.detail}</p><a href="#/history">Inspect recorded change →</a></aside> : null}
    {href ? <a className="secondary" href={href} onClick={href.startsWith('#/') ? undefined : e => jump(e, href.slice(1))}>{href !== decision.href ? 'Open draft review' : decision.action} <span aria-hidden="true">→</span></a> : <p className="field-help">Use Refresh in the top bar before acting.</p>}
    {decision.before && decision.latest ? <div className="payment-change" data-testid="payment-change">
      <div><span>Before latest posted receipt · derived</span><strong>{money(decision.before)}</strong></div>
      <div><span>Now outstanding · current books</span><strong>{money(decision.balance!.outstanding)}</strong></div>
      <p><a href={workspaceLink(invoice, decision.latest.id)}>Inspect {decision.latest.id} · {decision.latest.document!.transfer_id || 'Identity unavailable'}</a> · {money(decision.latest.document!.amount)} recorded against {invoice}. A second email is not a second bank event.</p>
    </div> : null}
    {latest ? <p className="latest-evidence">Latest session evidence: <a href={`#/records?source=${encodeURIComponent(latest.id)}`}>{latest.id} · {latest.status}</a>. {latest.status === 'refused' ? latest.error : latest.resolution ? `Human resolution: ${latest.resolution.decision}. No additional payment posted.` : 'Open the retained source to inspect the reader decision.'}</p> : null}
    {decision.balance ? <details className="reconciliation-next"><summary>Try new evidence before approving</summary><p>Would you still chase if the client just paid? Add their remittance here before approving. These links only fill editable text in Records. Review and submit it to change the books.</p><div className="flex flex-wrap gap-3">
      <a href={intakeLink(invoice === 'JN-4410' && !decision.latest ? 'payment' : 'custom', invoice)}>Add payment evidence →</a>
      {decision.latest ? <a href={intakeLink('duplicate', invoice)}>Check a forwarded duplicate →</a> : null}
    </div><p>Use the original transfer reference for a duplicate. Only a genuinely distinct payment gets a distinct identity. Sample references represent invented events.</p></details> : null}
    <p className="reconciliation-limit">Source-backed means retained post, not verified bank settlement. {data.live ? 'Email approval can send real SES mail to the verified test recipient. No payment is executed.' : 'All approvals here record simulated mail; no actual email or payment occurs.'}</p>
  </section>;
}
