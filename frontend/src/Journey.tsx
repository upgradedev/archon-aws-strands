import { useEffect, useRef, useState } from 'react';
import type { Mutate, Workspace } from './types';
import { Approvals } from './Approvals';
import { EvidenceBundle, type Bundle } from './EvidenceBundle';
import { FileIntake, validateFileText } from './FileIntake';
import { draftState, linkedSources, reasonTarget, routeInfo, workspaceLink } from './ledger';
import { reconciliation, reviewReset } from './decision';
import { useClock } from './useClock';
import { Badge, Heading, money } from './ui';

export function journeyState(data: Workspace, route: string) {
  const params = routeInfo(route).params;
  const requested = params.get('invoice');
  const invoice = requested ?? data.draft?.invoice_id ?? reasonTarget(data).id ?? data.sales[0]?.doc_id;
  const balance = data.sales.find(item => item.doc_id === invoice);
  const sources = linkedSources(data, invoice ?? '');
  const payments = sources.filter(source => source.kind === 'Receipt');
  const draft = data.draft?.invoice_id === invoice ? data.draft : null;
  const receipt = draft ? data.receipts.find(item => item.fingerprint === draft.fingerprint) : undefined;
  const step = !balance ? 0 : params.get('step') === 'payment' ? 1 : receipt ? 3 : draft || payments.length || params.get('step') === 'review' ? 2 : 1;
  return { invoice, balance, sources, payments, draft, receipt, step, missing: !!requested && !balance };
}

function SourceStep({ data, payment, invoice, disabled, mutate, finish, hasPayment }: {
  data: Workspace; payment: boolean; invoice?: string; disabled: boolean; mutate: Mutate; finish: () => void; hasPayment: boolean;
}) {
  const example = payment ? (invoice === 'JN-4410' && !hasPayment ? data.samples.payment : '') : data.samples.invoice;
  const [body, setBody] = useState(example);
  const [validation, setValidation] = useState('');
  return <form className="journey-editor" onSubmit={async event => {
    event.preventDefault();
    const problem = validateFileText(body);
    setValidation(problem);
    if (problem) return;
    const origin = location.hash;
    if (await mutate('/intake', { body, replace_id: null })) {
      setBody('');
      if (location.hash === origin) finish();
    }
  }}>
    <div className="panel-heading"><div><p className="eyebrow">{payment ? 'STEP 2 / PAYMENT EVIDENCE' : 'STEP 1 / YOUR INVOICE'}</p><h2 id="guided-source-heading" tabIndex={-1}>{payment ? 'Did the customer pay anything?' : 'Start with an invoice email'}</h2><p>{payment ? 'Add the remittance, not a guess. Reuse the original transfer reference when an email is forwarded.' : 'Alex has invoiced a customer. Inspect or edit this invented email before adding it to the books.'}</p></div></div>
    <div className="journey-editor-body"><label htmlFor="journey-source">Email headers and plain-text body</label><textarea id="journey-source" rows={11} value={body} disabled={disabled} maxLength={32000} onChange={event => { setBody(event.target.value); setValidation(''); }} aria-describedby="journey-format" />
      <p id="journey-format" className="field-help">Supported: plain-text English email with explicit sender, recipient, invoice reference, ISO dates and EUR amounts. Payments also need the original transfer ID. This is a bounded rule reader, not general document AI. No PDFs, scans or attachments.</p>
      <FileIntake disabled={disabled} onUse={text => { setBody(text); setValidation(''); }} />
      {validation ? <p role="alert" className="notice error">{validation}</p> : null}
      <div className="journey-actions"><button className="primary" disabled={disabled || !body.trim()}>{payment ? 'Record payment & check balance' : 'Read & add invoice'}</button>{payment ? <a className="journey-link" href={`#/journey?step=review&invoice=${encodeURIComponent(invoice!)}`}>No payment to add · review invoice →</a> : null}</div>
      <p className="field-help">Your click posts only this source. It does not approve a reminder or send an email. Refused evidence remains visible for correction.</p>
    </div>
  </form>;
}

export function Journey({ data, busy, stale, mutate, route, reviewEpoch, loadEvidence }: {
  data: Workspace; busy: boolean; stale: boolean; mutate: Mutate; route: string; reviewEpoch: number; loadEvidence: () => Promise<Bundle>;
}) {
  const state = journeyState(data, route);
  const { balance, invoice, sources, payments, draft, receipt, step } = state;
  const target = reasonTarget(data);
  const now = useClock(draft?.at);
  const status = draftState(data, now);
  const decision = reconciliation(data, invoice ?? '', stale, now);
  const reset = reviewReset(data);
  const needsDraft = !draft || status === 'expired' || status === 'unavailable';
  const blocked = stale || !!data.holds.length || state.missing;
  const focusTarget = blocked ? 'guided-pause-heading' : step < 2 ? 'guided-source-heading' : step === 3 ? 'guided-outcome-heading' : draft && !needsDraft ? 'collection-draft' : 'guided-review-heading';
  const transition = `${step}:${draft?.fingerprint ?? ''}:${blocked}`;
  const previousTransition = useRef(transition);
  useEffect(() => {
    if (previousTransition.current !== transition) {
      const heading = document.getElementById(focusTarget);
      heading?.focus();
      heading?.scrollIntoView({ block: 'start' });
    }
    previousTransition.current = transition;
  }, [transition, focusTarget]);
  const href = (part: string) => `#/journey?step=${part}${invoice ? `&invoice=${encodeURIComponent(invoice)}` : ''}`;
  return <>
    <Heading eyebrow="YOUR GUIDED COLLECTION CHECK" title="From invoice to a safe decision">Add the evidence. Check the balance. You approve the next action.</Heading>
    <p className="journey-session">This is your current saved workspace, not a separate sandbox. Returning here keeps its records. Use <strong>New workspace</strong> for an empty example; you will be asked first.</p>
    <ol className="journey-progress" aria-label="Collection check progress">{['Invoice', 'Payment', 'Review', 'Outcome'].map((label, index) => <li key={label} aria-current={step === index ? 'step' : undefined}><span aria-hidden="true">{index + 1}</span>{label}</li>)}</ol>
    {blocked ? <section className="notice warning" aria-label="Guided check paused"><h2 id="guided-pause-heading" tabIndex={-1}>{stale ? 'Reconnect and refresh before continuing' : state.missing ? 'That invoice is not in this workspace' : 'We need you to check the evidence'}</h2><p>{stale ? 'These are last known records. No new source or approval is safe until the workspace is refreshed.' : state.missing ? 'No different invoice has been selected silently.' : `${data.holds.length} source email(s) could not be posted. The books may be incomplete; no reminder can be approved.`}</p><a href={state.missing ? '#/journey' : '#/records?filter=refused'}>{state.missing ? 'Return to current check →' : 'Review sources and corrections →'}</a></section> : null}
    <div className="guided-desk"><div className="guided-task">
      {!data.holds.length && !state.missing && step < 2 ? <SourceStep key={`${step}-${invoice ?? 'new'}`} data={data} payment={step === 1} invoice={invoice} disabled={busy || stale} mutate={mutate} hasPayment={payments.length > 0} finish={() => { location.hash = invoice ? `/journey?invoice=${encodeURIComponent(invoice)}` : '/journey'; }} /> : null}
      {!blocked && step === 2 ? <>
        <section className="journey-review"><p className="eyebrow">STEP 3 / REVIEW THE NEXT ACTION</p><h2 id="guided-review-heading" tabIndex={-1}>{needsDraft ? decision.title : 'Read the exact reminder before deciding'}</h2><p>{needsDraft ? decision.why : 'A recorded payment is deducted once. The graph reads the books; it does not verify your bank or decide for you.'}</p>
          {reset ? <aside className="review-reset" aria-label="Previous review invalidated"><h3>Previous draft cannot be approved</h3><p>New evidence changed the books. Review the current balance and prepare a fresh draft; the previous confirmation does not carry over.</p><a href="#/history">Inspect recorded change →</a></aside> : null}
          {needsDraft ? <><button className="primary" disabled={busy || !target.id || target.id !== invoice || !!target.issue} onClick={() => void mutate('/reason')}>Run Strands & prepare draft</button><p className="field-help">{target.id !== invoice ? 'This invoice is not currently the collection priority. Open the collection desk to inspect holds or another case.' : target.issue || 'Runs the real Strands graph using a scripted model. No email is sent.'}</p></> : null}
          <div className="journey-actions"><a href={href('payment')}>← Add or review payment evidence</a><a href={workspaceLink(invoice, null, 'terms')}>Discuss a payment arrangement →</a></div>
        </section>
        {draft ? <Approvals key={`${invoice}-${data.revision}-${reviewEpoch}`} data={data} busy={busy} stale={stale} mutate={mutate} mode="draft" selectedInvoice={invoice} onApproved={() => { location.hash = href('result').slice(1); }} /> : null}
        {!draft && target.id !== invoice ? <a className="journey-link" href={workspaceLink(invoice)}>Open the collection desk →</a> : null}
      </> : null}
      {!blocked && step === 3 && receipt ? <section className="journey-result" aria-label="Guided check outcome"><Badge tone={receipt.state === 'provider-accepted' ? 'green' : 'amber'}>Simulated · {receipt.state}</Badge><h2 id="guided-outcome-heading" tabIndex={-1}>{receipt.state === 'provider-accepted' ? 'Your decision is recorded.' : 'Read this outcome before acting again.'}</h2><p>{data.receipt_states[receipt.state] ?? 'This state has no known explanation. Inspect the receipt before taking any further action.'}</p><p>No real email was sent. Approval did not collect money or reduce the debt. The current outstanding balance remains <strong>{money(balance?.outstanding)}</strong>.</p><a className="primary" href="#/dashboard">Return to overview →</a><div className="journey-actions"><a href="#/history">Inspect the saved receipt →</a><a href={href('payment')}>Add new payment evidence →</a></div><EvidenceBundle revision={data.revision} load={loadEvidence} /></section> : null}
    </div><aside className="journey-ledger" aria-label="Current case evidence"><p className="eyebrow">{stale ? 'LAST KNOWN BOOKS' : 'YOUR CASE, AT A GLANCE'}</p>
      {balance ? <><h2>{balance.counterparty}</h2><p>{invoice} · Due {balance.due}</p><dl><div><dt>Invoiced</dt><dd>{money(balance.gross)}</dd></div><div><dt>Recorded receipts</dt><dd>{money(balance.settled)}</dd></div><div className="journey-total"><dt>Still owed</dt><dd>{money(balance.outstanding)}</dd></div></dl><p>Retained email evidence, not verified bank settlement.</p><details><summary>Inspect original sources ({sources.length})</summary>{sources.map(source => <div className="journey-source" key={source.id}><a href={`#/records?source=${encodeURIComponent(source.id)}`}>{source.id} · {source.kind}</a><pre>{source.body}</pre></div>)}</details></> : <><h2>No invoice posted yet</h2><p>Your real session balance appears here after you submit an invoice. We do not insert illustrative totals into your books.</p></>}
      <div className="journey-boundary"><strong>You stay in control</strong><p>Synthetic examples · scripted model · simulated outbox. A new payment invalidates an old draft and its review confirmation.</p></div><a href="#/dashboard">Back to overview →</a>
    </aside></div>
  </>;
}
