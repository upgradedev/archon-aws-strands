import { useEffect, useRef, useState } from 'react';

const stops = [
  { page: 'dashboard', label: 'Dashboard', title: 'See the business before chasing a payment',
    text: 'Follow sales, purchases, credits and cash records in one overview. The full business demo has 240 fictional documents. Every financial widget comes from posted books, not a model-generated total.' },
  { page: 'records', label: 'Records', title: 'Follow a number back to its source',
    text: 'Filter the six document types, inspect an invoice and open its linked receipt or credit. Fixture documents are labelled. Adding a new email is a separate action; reading these records does not run AI.' },
  { page: 'incoming', label: 'Incoming', title: 'Know how new documents reach the books',
    text: 'An optional intake-only webhook accepts documents from a sender you configure. It starts disconnected. This is not a Gmail login or bank feed. The tour never enables a key or imports a document.' },
  { page: 'workspace', label: 'Workspace', title: 'Let Strands review, not decide for you',
    text: 'Six Strands Agents readers report from the ledger before a tool-less composer prepares wording. Deterministic checks govern the balance and eligibility. Run Strands & prepare draft is a separate, metered action; it does not send email.' },
  { page: 'journey', label: 'Guided check', title: 'Approve only the exact content you reviewed',
    text: 'The guided check follows invoice, payment, review and outcome. Inspect the recipient, figures and exact draft before consenting. New evidence invalidates old review. This tour never checks consent or clicks approval.' },
  { page: 'history', label: 'History', title: 'Read the recorded outcome and its limits',
    text: 'History keeps source changes and recorded attempts. SES acceptance is not proof of mailbox arrival, and an approval never reduces the debt. Zero approvals or emails mean no such action has happened.' },
] as const;

export function ProductTour({ page, live, blocked, links, onClose }: {
  page: string; live: boolean; blocked: boolean; links: Record<string, string>; onClose: () => void;
}) {
  const [index, setIndex] = useState(0);
  const heading = useRef<HTMLHeadingElement>(null);
  const stop = stops[index];
  useEffect(() => { heading.current?.focus(); }, [index]);
  useEffect(() => {
    const escape = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose(); };
    window.addEventListener('keydown', escape);
    return () => window.removeEventListener('keydown', escape);
  }, [onClose]);
  return <section id="product-tour" className="product-tour" aria-label="Product tour">
    <div className="tour-copy">
      <p className="eyebrow">PRODUCT TOUR · STEP {index + 1} OF {stops.length} · {stop.label}</p>
      <h2 ref={heading} tabIndex={-1}>{stop.title}</h2>
      <p>{stop.text}</p>
      <p className="field-help">{live ? 'This workspace can use real Bedrock and controlled SES.' : 'This workspace is a retained simulation: scripted model and simulated outbox.'} The tour itself only explains and navigates.</p>
    </div>
    <div className="tour-controls">
      <div className="flex flex-wrap gap-2">
        <button className="secondary small" disabled={index === 0} onClick={() => setIndex(current => Math.max(0, current - 1))}>Previous stop</button>
        {index < stops.length - 1 ? <button className="primary small" onClick={() => setIndex(current => Math.min(stops.length - 1, current + 1)))}>Next stop</button> : <button className="primary small" onClick={onClose}>Finish tour</button>}
        <button className="ghost small" onClick={onClose}>Close tour</button>
      </div>
      {page === stop.page ? <p className="tour-location">You are on {stop.label}. Explore the page below.</p>
        : blocked ? <p className="field-help">Page navigation is paused. Finish the current operation and refresh uncertain state.</p>
          : <a className="secondary small" href={links[stop.page]}>Open {stop.label}</a>}
      <p className="field-help">Next and Previous change this guide only. Opening another page is optional; finish any unsaved input first. Escape closes the tour.</p>
    </div>
  </section>;
}
