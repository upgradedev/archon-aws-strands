import type { Workspace } from './types';
import { Badge, Empty, Heading, money } from './ui';
import { dashboardMetrics, reasonTarget, workspaceLink } from './ledger';
import { useClock } from './useClock';
import { ReconciliationStart } from './Reconciliation';

export function Dashboard({ data, stale }: { data: Workspace; stale: boolean }) {
  const metrics = dashboardMetrics(data, useClock(data.draft?.at));
  const target = reasonTarget(data);
  return <>
    <Heading eyebrow="COLLECTIONS / MY JOINERY" title="Dashboard">Check what is still owed before chasing.</Heading>
    <ReconciliationStart data={data} stale={stale} />
    <div className="dashboard-help"><span>Want a step-by-step view of your next decision?</span><a href="#/journey">Open guided check →</a></div>
    <div className="scope-line"><span>All records in this synthetic session · As of {data.as_of}</span><Badge tone={stale || data.holds.length ? 'amber' : 'blue'}>{stale ? 'Last known snapshot' : `Ledger revision ${data.revision}`}</Badge></div>
    <section className="stats dashboard-stats" aria-label="Ledger balances">{metrics.map(metric => <a key={metric.id} className="stat" data-testid={`metric-${metric.id}`} href={metric.href}>
      <p>{metric.label}<span aria-hidden="true"> ↗</span></p><strong>{'amount' in metric ? money(metric.amount) : metric.count === null ? 'Unknown' : metric.count}</strong><small>{metric.note}</small>
    </a>)}</section>
    {data.holds.length ? <div className="notice warning"><strong>Partial books · collections held</strong><p>The displayed amounts cover posted records only. Refused evidence can change them.</p><a href="#/records?filter=refused">Resolve source holds →</a></div> : null}
    <div className="dashboard-grid"><section className="panel"><div className="panel-heading"><div><h2>Priority work</h2><p>Oldest overdue first, then largest balance.</p></div><a href="#/workspace">Open workspace →</a></div>
      {target.id ? <a className="priority-callout" href={workspaceLink(target.id)}><span className="eyebrow">BACKEND PRIORITY</span><h3>{target.id}</h3><p>{data.sales.find(s => s.doc_id === target.id)?.counterparty}</p><strong>{money(data.sales.find(s => s.doc_id === target.id)?.outstanding)}</strong><p>{data.holds.length ? 'Correct source holds before preparing a chase.' : target.issue || 'Inspect the sources and prepare the exact draft.'}</p></a> : <Empty title="Nothing to chase yet">{target.issue} <a href="#/records?intake=open">Add synthetic post</a> to begin.</Empty>}
      <ul className="hold-list">{data.holds.slice(0, 3).map(s => <li key={s.id}><a href={`#/records?filter=refused&source=${encodeURIComponent(s.id)}`}><strong>{s.id}</strong><p>{s.error}</p></a></li>)}</ul>
    </section><section className="panel"><div className="panel-heading"><div><h2>Recent activity</h2><p>Recorded events · latest first</p></div><a href="#/history">All history →</a></div>
      {data.activity.length ? <ol className="timeline">{data.activity.slice(-5).reverse().map(event => <li key={event.id}><span className="timeline-dot" aria-hidden="true" /><div><h3>{event.title}</h3><p>{event.detail}</p><time>{event.at}</time></div></li>)}</ol> : <Empty title="No recorded activity">Post your first synthetic email from Records. Reading a page creates no financial event.</Empty>}
    </section></div>
    <section className="panel" aria-label="Observed session outcomes"><div className="panel-heading"><h2>Observed session outcomes</h2></div><dl className="report-grid"><div><dt>Posted sources</dt><dd>{data.sources.filter(s => s.status === 'posted').length}</dd></div><div><dt>Unresolved sources</dt><dd>{data.holds.length}</dd></div><div><dt>Corrections retained</dt><dd>{data.sources.filter(s => s.status === 'corrected').length}</dd></div><div><dt>Human resolutions</dt><dd>{data.sources.filter(s => s.status === 'resolved').length + (data.resolutions?.length ?? 0)}</dd></div><div><dt>Recorded approval outcomes</dt><dd>{data.receipts.length}</dd></div></dl><p className="section-note">Human active time, time saved and money recovered: Unknown. These are counts of this session's recorded outcomes, not measured benefits.</p><a href="#/history">Inspect decisions and evidence →</a></section>
    <p className="section-note">Recorded receipts are retained remittances, not independent proof of bank settlement. {data.live?.mail ? 'Email can be sent through controlled SES after approval.' : 'Email delivery is simulated.'} No estimated savings or trends.</p>
  </>;
}
