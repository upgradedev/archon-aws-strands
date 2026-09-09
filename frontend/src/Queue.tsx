import type { Mutate, Workspace } from './types';
import { Badge, Empty, Heading, money } from './ui';

export function Queue({ data, busy, mutate }: { data: Workspace; busy: boolean; mutate: Mutate }) {
  const held = data.holds.length > 0;
  return <>
    <Heading eyebrow="YOUR DAILY WORKSPACE" title="Action queue">Know what is owed. See what can move. Approve every outgoing word.</Heading>
    <section className="stats" aria-label="Ledger balances">
      {[
        ['Owed to you', data.metrics.owed_by_clients, 'Open client invoices'],
        ['Overdue', data.metrics.overdue_amount, `${data.metrics.overdue_count} overdue invoice${data.metrics.overdue_count === 1 ? '' : 's'}`],
        ['You owe', data.metrics.owed_to_suppliers, 'Open supplier invoices'],
        ['Bank movement', data.metrics.bank, 'Recorded payments and receipts'],
      ].map(([label, amount, note]) => <div className="stat" key={label}><p>{label}</p><strong>{money(amount)}</strong><small>{note}</small></div>)}
    </section>
    {held ? <div className="notice warning"><strong>Collections held · incomplete evidence</strong><p>{data.holds.length} refused source email(s) may change these balances. Correct them before any chase can be prepared.</p><a href="#/documents">Review refused sources →</a></div> : null}
    <section className="panel">
      <div className="panel-heading"><div><h2>Ready for review <span className="count">{held ? 0 : data.queue.ready.length}</span></h2><p>Oldest overdue first, then largest balance. Ranked by the books.</p></div><Badge tone="blue">EUR ledger</Badge></div>
      {!data.queue.ready.length ? <Empty title="Nothing to chase yet">Add a sales invoice and its payments in <a href="#/documents">Documents & payments</a>. Settled invoices and agreed arrangements stay out of this queue.</Empty> :
        <div className="table-scroll"><table><caption className="sr-only">Outstanding sales invoices</caption><thead><tr><th>Client / invoice</th><th>Age</th><th className="numeric">Outstanding</th><th>Status</th></tr></thead><tbody>{data.queue.ready.map(item => <tr key={item.invoice_id}>
          <td><strong>{item.client}</strong><a className="subline" href={`#/documents?source=${encodeURIComponent(item.invoice_id)}`}>{item.invoice_id} · View evidence ↗</a></td>
          <td>{item.days_overdue} days overdue</td><td className="numeric money">{money(item.outstanding)}</td><td><Badge tone={held ? 'red' : 'amber'}>{held ? 'Evidence held' : 'Approval required'}</Badge></td>
        </tr>)}</tbody></table></div>}
      <div className="panel-footer"><p>Six ledger readers must report before the composer runs.</p><button className="primary" disabled={busy || held || !data.queue.ready.length} onClick={async () => { if (await mutate('/reason')) location.hash = '/approvals'; }}>{busy ? 'Working…' : 'Run Strands & prepare draft'} <span aria-hidden="true">→</span></button></div>
      {held || !data.queue.ready.length ? <p className="disabled-reason">{held ? 'Disabled until every refused source is corrected.' : 'Available when an invoice is overdue and chaseable.'}</p> : null}
    </section>
    <section className="panel"><div className="panel-heading"><div><h2>On hold & not yet due <span className="count">{data.queue.blocked.length}</span></h2><p>Every balance stays visible, with the reason it cannot be chased.</p></div></div>
      {data.queue.blocked.length ? <ul className="hold-list">{data.queue.blocked.map(item => <li key={item.invoice_id}><div><strong>{item.client} · {item.invoice_id}</strong><p>{item.reason}</p></div><span className="money">{money(item.outstanding)}</span></li>)}</ul> : <p className="section-note">No held or future-due invoices in this workspace.</p>}
    </section>
    <div className="note-grid"><div><h3>Real books. Synthetic business.</h3><p>Every number comes from posted source documents and decimal arithmetic. No bank or mailbox is connected.</p></div><div><h3>The honest limit</h3><p>The independent benchmark produced zero chases. Unreadable post remains a blocker; a clean error column does not prove useful collections.</p></div></div>
  </>;
}
