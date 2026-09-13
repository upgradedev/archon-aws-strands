export function Welcome() {
  return <div className="welcome-shell">
    <a className="skip-link" href="#welcome-main" onClick={event => { event.preventDefault(); document.getElementById('welcome-main')?.focus(); }}>Skip to introduction</a>
    <header className="welcome-header"><a className="brand" href="#/welcome"><span className="brand-mark" aria-hidden="true">A</span>ARCHON</a><a className="welcome-resume" href="#/dashboard">Continue my workspace <span aria-hidden="true">↗</span></a></header>
    <main id="welcome-main" tabIndex={-1}>
      <section className="welcome-hero" aria-labelledby="welcome-title">
        <div className="welcome-message"><p className="eyebrow">FOR SELF-EMPLOYED PEOPLE & SMALL BUSINESSES</p>
          <h1 id="welcome-title" tabIndex={-1}>Chase the balance.<br /><em>Not the customer who paid.</em></h1>
          <p className="welcome-lead">Turn invoice and payment emails into a clear answer: what is still owed, why, and what you can safely do next.</p>
          <a className="primary welcome-cta" href="#/journey" data-testid="start-guided-example">Try the example <span aria-hidden="true">→</span></a>
          <p className="welcome-small">An editable example, one step at a time. No account needed. Nothing is approved automatically.</p>
          <a className="welcome-text-link" href="#/records?intake=open">Have a different example? Add supported text →</a>
        </div>
        <aside className="welcome-preview" aria-label="Illustrative example, not your saved balances">
          <div className="preview-label"><span>THE DECISION, MADE CLEAR</span><span className="preview-dot" aria-hidden="true" /></div>
          <p>Alex's joinery · illustrative example</p><h2>A payment just arrived.</h2>
          <dl><div><dt>Invoice</dt><dd>1,860.00 EUR</dd></div><div><dt>Recorded payment</dt><dd>− 600.00 EUR</dd></div><div className="preview-total"><dt>Still owed</dt><dd>1,260.00 EUR</dd></div></dl>
          <div className="preview-decision"><span aria-hidden="true">↳</span><p>Review a reminder for the remaining balance.<strong>You decide whether to approve.</strong></p></div>
          <small>Illustration only. Your workspace starts empty; the example is posted only when you submit it.</small>
        </aside>
      </section>
      <div className="welcome-boundary"><strong>Safe to explore.</strong><p>Synthetic data only · real Strands orchestration with a scripted model · simulated mail. No real AI judgment, bank connection, email or payment.</p></div>
      <section className="welcome-steps" aria-label="How Archon works"><article><span>01 / ADD</span><h2>Bring the source</h2><p>Review an editable invoice and payment email. Unsupported or incomplete evidence is held for correction.</p></article><article><span>02 / UNDERSTAND</span><h2>See what changed</h2><p>Follow the recorded payment to the invoice balance. New evidence withdraws an old draft.</p></article><article><span>03 / DECIDE</span><h2>Stay in control</h2><p>Approve the exact reminder, discuss a payment arrangement, or leave the case on hold. Keep the outcome.</p></article></section>
      <footer className="footer"><span>ARCHON / Source-backed bookkeeping</span><a href="#/dashboard">Open my workspace</a><span>EUR only · Use invented examples, not personal data</span></footer>
    </main>
  </div>;
}
