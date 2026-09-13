import type { Workspace } from './types';

export function ProviderStatus({ live }: { live: NonNullable<Workspace['live']> }) {
  const job = live.job;
  return <section className="notice" aria-label="Real provider execution" data-testid="provider-status">
    <strong>Real Bedrock AI · real SES to a verified test recipient</strong>
    <p>Business examples are fictional. Ledger arithmetic is deterministic. A model call never authorizes an email.</p>
    {job ? <>
      <p role="status">Saved job: {job.operation} · {job.status}</p>
      <code>{job.id}</code>
      {job.error ? <p role="alert">{job.error}</p> : null}
      {job.status === 'queued' || job.status === 'running' ? <p>You can reload and return. The saved job continues; do not start it again.</p> : null}
      {job.status === 'unknown' ? <p>Do not resend. An operator must reconcile the durable record and provider evidence.</p> : null}
      {job.calls?.length ? <details><summary>Model usage and reserved budget</summary><ul>{job.calls.map(call => <li key={call.call_id}>{call.model_id} · {call.status} · {call.usage ? `${call.usage.inputTokens} input / ${call.usage.outputTokens} output tokens` : 'Usage unconfirmed'} · reserved USD {call.reserved_usd}</li>)}</ul><p>Reservations are conservative price-based limits, not an AWS invoice. Unknown attempts are not refunded automatically.</p></details> : null}
    </> : <p>No model call or send has been performed in this workspace yet.</p>}
  </section>;
}
