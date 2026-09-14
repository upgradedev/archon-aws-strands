import { useState, type CSSProperties } from 'react';
import type { Mutate, Workspace } from './types';
import { Heading } from './ui';
import { routeInfo, workspaceLink } from './ledger';
import { RecordViews } from './RecordViews';
import { FileIntake } from './FileIntake';
import { duplicateReceiptMail } from './portfolio';

const samples = ['invoice', 'payment', 'supplier', 'refusal'] as const;

export function Documents({ data, busy, mutate, route }: { data: Workspace; busy: boolean; mutate: Mutate; route: string }) {
  const { params } = routeInfo(route);
  const journey = params.get('journey');
  const [body, setBody] = useState(() => {
    if (journey === 'invoice' && !data.sales.length) return data.samples.invoice;
    if (journey === 'payment' && params.get('invoice') === 'JN-4410') return data.samples.payment;
    if (journey === 'duplicate') return duplicateReceiptMail(data, params.get('invoice'));
    return '';
  });
  const [submitted, setSubmitted] = useState(false);
  const [flow, setFlow] = useState('');
  const [replaceId, setReplaceId] = useState<string | null>(null);
  const [intake, setIntake] = useState(route.startsWith('/documents'));
  const showIntake = intake || params.get('intake') === 'open';
  function toggleIntake() {
    setIntake(!showIntake);
    if (showIntake && params.get('intake') === 'open') {
      const next = new URLSearchParams(params); next.delete('intake');
      location.hash = `/records?${next}`;
    }
  }
  const heldPayment = data.sources.find(s => s.status === 'refused' && s.kind === 'Receipt');
  const latest = data.sources.at(-1);
  const selectedSample = samples.findIndex(key => body.length > 0 && body === data.samples[key]);
  return <>
    <Heading eyebrow="INBOX → BOOKS" title="Records">Find the posted documents and retained evidence behind every balance.</Heading>
    <div className="scope-line"><span>All session records · As of {data.as_of} · EUR</span><button className="secondary" aria-expanded={showIntake} onClick={toggleIntake}>{showIntake ? 'Close intake' : 'Add synthetic email'}</button></div>
    {showIntake ? <div className="intake-grid">
      <section className="panel intake"><h2>{replaceId ? `Correct ${replaceId}` : 'Read an email'}</h2><p>{data.live ? 'Real Bedrock semantic extraction with source checks. Use explicit ISO dates and EUR decimals such as 1,234.56. Unsupported or ambiguous evidence is refused.' : 'The bounded reader supports explicit EUR invoices and remittances. No live model call.'}</p>
        {journey ? <div className="notice"><h3>{journey === 'invoice' ? 'First, prepare a draft from the invoice' : journey === 'duplicate' ? 'Is this the same payment arriving twice?' : 'New evidence must change the review'}</h3><p>{journey === 'invoice' ? 'Review and post this editable invoice. Then open its decision and prepare a draft before adding payment evidence.' : journey === 'duplicate' ? 'This is a forward of the selected case’s latest posted receipt, retaining its Transfer ID. Submit it to observe the hold, then link the original in the human resolution form.' : 'Review and submit the payment. The server invalidates any previous draft; return to the case for a fresh decision. For your own synthetic example, supply the matching invoice and actual invented event reference.'}</p></div> : null}
        <FileIntake disabled={busy} onUse={text => { setBody(text); setSubmitted(false); }} />
        {journey === 'duplicate' && body.includes('Fictional remittance reconstructed from typed fixture') ? <p className="notice">This editable remittance was reconstructed from a typed fictional receipt, not received from a mailbox. Its original transfer identity, amount and financial date are preserved for the duplicate check.</p> : null}
        <section className="workflow-guide" aria-label="Three editable API workflows"><h3>Try a complete decision</h3>
          <p>These controls fill the editable source below. Nothing posts until you submit it.</p>
          <div className="flex flex-wrap gap-3">
            <button type="button" className="secondary small" disabled={busy} onClick={() => { setReplaceId(null); setBody(data.samples.invoice); setFlow('Success: post the invoice, then Sample payment. Inspect the resulting balance and run Strands in Workspace.'); }}>Try success</button>
            <button type="button" className="secondary small" disabled={busy} onClick={() => { setReplaceId(null); setBody(data.samples.payment.split('\nTransfer ID:')[0]); setFlow('Refusal: post an invoice first. Submit this remittance without an identity; the API must retain it and hold collections.'); }}>Try identity refusal</button>
            <button type="button" className="secondary small" disabled={busy || !heldPayment} onClick={() => { if (heldPayment) { setReplaceId(heldPayment.id); setBody(heldPayment.body); setFlow('Correction: the original source is below. Add the actual Transfer ID for a distinct bank event, then Read corrected source. Do not invent a second identity for a duplicate.'); } }}>Correct held payment</button>
          </div>{flow ? <p>{flow}</p> : null}
          {latest ? <p data-testid="latest-source-decision">Latest server decision: {latest.id} · {latest.status}. {latest.error || latest.document?.doc_id}</p> : <p>No source decision yet.</p>}
          {submitted && latest ? <p>{latest.status === 'refused' ? 'Collection is held. Inspect the retained source below and correct or resolve its evidence.' : 'Evidence saved. Review the current decision before approving.'} <a className="secondary" href={workspaceLink(latest.document?.settles ?? (latest.kind === 'SalesInvoice' ? latest.document?.doc_id : params.get('invoice')))}>Review changed decision →</a></p> : null}
        </section>
        <div className="sample-buttons" role="group" aria-label="Load a synthetic sample" data-selected={selectedSample >= 0}
          style={{ '--selected-sample': selectedSample, '--sample-column': selectedSample % 2, '--sample-row': Math.floor(selectedSample / 2) } as CSSProperties}>
          {samples.map((key, index) => <button type="button" key={key} className="secondary small" aria-pressed={selectedSample === index}
            disabled={busy} onClick={() => setBody(data.samples[key])}>Sample {key}</button>)}
        </div>
        <form onSubmit={async e => { e.preventDefault(); if (await mutate('/intake', { body, replace_id: replaceId })) { setBody(''); setReplaceId(null); setSubmitted(true); } }}>
          <label htmlFor="raw-email">Email headers and body <span className="required">Required</span></label>
          <textarea id="raw-email" disabled={busy} value={body} onChange={e => setBody(e.target.value)} rows={7} maxLength={32000} required placeholder="From: …&#10;To: …&#10;Subject: Invoice …&#10;&#10;Paste synthetic invoice or remittance text." aria-describedby="intake-help" />
          <p className="field-help">Business: {data.business?.name ?? 'My Joinery'} · {data.business?.email ?? 'me@myjoinery.example'}. For a forward, retain the original From/To headers. Remittances require an explicit Transfer ID.</p><p id="intake-help" className="field-help">Synthetic data only: fictional business examples, even with real providers. English plain text only; no bank feed or OCR. Include dates, currency, reference, net, VAT and total. Payments must reference a posted sales invoice. Credit notes and supplier payment fixtures cannot be ingested by this raw-mail reader.</p>
          <div className="flex flex-wrap gap-3"><button className="primary" disabled={busy || !body.trim()}>{busy ? 'Reading…' : replaceId ? 'Read corrected source' : 'Read & post email'}</button>{replaceId ? <button type="button" className="secondary" onClick={() => { setReplaceId(null); setBody(''); }}>Cancel correction</button> : null}</div>
        </form>
      </section>
    </div> : null}
    <RecordViews data={data} busy={busy} mutate={mutate} route={route} correct={source => {
      setIntake(true); setReplaceId(source.id); setBody(source.body);
      requestAnimationFrame(() => document.getElementById('raw-email')?.focus());
    }} />
  </>;
}
