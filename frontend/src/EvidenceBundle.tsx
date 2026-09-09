import { useState } from 'react';
import { errorText } from './api';

export interface Bundle { revision: number; commit: string; text: string }
export function EvidenceBundle({ load, revision }: { load?: () => Promise<Bundle>; revision: number }) {
  const [bundle, setBundle] = useState<Bundle | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  return <section className="panel"><div className="panel-heading"><h2>Evidence bundle</h2></div>
    <p className="section-note">Redacted sources, decisions, corrections, runtime identity and limits. A hash identifies bytes, not truth. Review before sharing.</p>
    <button className="secondary" disabled={!load || busy} onClick={async () => { setBusy(true); setError(''); try { setBundle(await load!()); } catch (failure) { setError(errorText(failure)); } finally { setBusy(false); } }}>{busy ? 'Reading durable evidence…' : 'Prepare evidence bundle'}</button>
    {error ? <p role="alert">{error} Retry this read when the workspace is available.</p> : null}
    {bundle ? <><p>Ledger revision {bundle.revision} · Backend {bundle.commit}{bundle.revision !== revision ? ' · Historical snapshot; prepare again for current evidence.' : ''}</p><a download={`archon-evidence-r${bundle.revision}.txt`} href={`data:text/plain;charset=utf-8,${encodeURIComponent(bundle.text)}`}>Download readable evidence</a><details><summary>Inspect evidence and limits</summary><pre className="evidence-text">{bundle.text}</pre></details></> : null}
  </section>;
}
