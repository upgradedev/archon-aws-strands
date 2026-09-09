import type { Workspace } from './types';
import { Badge, Empty, Heading, money } from './ui';

export function Activity({ data }: { data: Workspace }) {
  return <>
    <Heading eyebrow="THE DURABLE RECORD" title="History">Read back what was approved, what the provider confirmed, and what remains unknown.</Heading>
    <div className="notice"><strong>Public provider: simulated outbox</strong><p>Provider acceptance is not delivery. Real sending requires a separate operator configuration, a durable ledger, explicit authorization and a controlled verified recipient.</p></div>
    <section className="panel"><div className="panel-heading"><h2>Delivery receipts <span className="count">{data.receipts.length}</span></h2></div>{data.receipts.length ? <div className="receipt-list">{data.receipts.map(receipt => <article key={receipt.fingerprint}><div className="flex flex-wrap items-center justify-between gap-3"><h3>{receipt.invoice_id} · {money(receipt.amount)}</h3><Badge tone="blue">Simulated · {receipt.state}</Badge></div><p>{receipt.to_address}</p><dl><dt>Receipt ID</dt><dd>{receipt.message_id ?? 'No provider identifier'}</dd><dt>Recorded</dt><dd>{receipt.at}</dd><dt>Arrival</dt><dd>Unproven · no real email sent</dd></dl>{receipt.error ? <p role="alert">{receipt.error}</p> : null}<details><summary>Approved content fingerprint</summary><code className="fingerprint">{receipt.fingerprint}</code></details></article>)}</div> : <Empty title="No delivery attempts">Approving an exact draft creates a simulated receipt here. Reading or drafting alone never sends.</Empty>}</section>
    <section className="panel"><div className="panel-heading"><h2>What each receipt state means</h2></div><dl className="state-key">{Object.entries(data.receipt_states).map(([state, explanation]) => <div key={state}><dt><Badge>{state}</Badge></dt><dd>{explanation}</dd></div>)}</dl></section>
    <section className="panel"><div className="panel-heading"><h2>Workspace history</h2><span className="muted">Latest first</span></div>{data.activity.length ? <ol className="timeline">{[...data.activity].reverse().map(event => <li key={event.id}><span className="timeline-dot" aria-hidden="true" /><div><h3>{event.title}</h3><p>{event.detail}</p><time>{event.at}</time></div></li>)}</ol> : <p className="section-note">Your first posted source will start the history.</p>}</section>
  </>;
}
