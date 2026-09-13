export function WorkspaceMode({ live, available }: { live: boolean; available?: boolean }) {
  if (live || available !== true) return null;
  return <section className="notice warning" aria-label="Older simulation workspace">
    <h2>This saved workspace still uses the simulator.</h2>
    <p>Real AI is now available. Your saved records and simulated receipts have not been converted into live activity.</p>
    <a className="secondary" href="#/demo">Open a separate demo with current providers →</a>
    <p className="field-help">Your previous workspace remains accessible. No AI call or email is triggered by switching.</p>
  </section>;
}
