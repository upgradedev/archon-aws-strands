import { useEffect, useRef, useState } from 'react';
import { errorText } from './api';

export interface Bundle { revision: number; commit: string; text: string }
export function EvidenceBundle({ load, revision }: { load?: () => Promise<Bundle>; revision: number }) {
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const [bundle, setBundle] = useState<Bundle | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [copyStatus, setCopyStatus] = useState('');
  return <section className="panel"><div className="panel-heading"><h2>Evidence bundle</h2></div>
    <p className="section-note">Redacted sources, decisions, corrections, runtime identity and limits. A hash identifies bytes, not truth. Exporting preserves recorded provider outcomes; it does not prove bank settlement or email arrival. Review before sharing.</p>
    <button className="secondary" disabled={!load || busy} onClick={async () => { setBusy(true); setError(''); setCopyStatus(''); try { const result = await load!(); if (mounted.current) setBundle(result); } catch (failure) { if (mounted.current) setError(errorText(failure)); } finally { if (mounted.current) setBusy(false); } }}>{busy ? 'Reading durable evidence…' : 'Prepare evidence bundle'}</button>
    {!load ? <p>Evidence export is unavailable in this embedded view. Open History in the connected workstation.</p> : null}
    {error ? <p role="alert">{error} Retry this read when the workspace is available.</p> : null}
    {bundle ? <><p>Ledger revision {bundle.revision} · Backend {bundle.commit}{bundle.revision !== revision ? ' · Historical snapshot; prepare again for current evidence.' : ''}</p><div className="flex flex-wrap gap-3"><a download={`archon-evidence-r${bundle.revision}.txt`} href={`data:text/plain;charset=utf-8,${encodeURIComponent(bundle.text)}`}>Download readable evidence</a><button className="secondary small" onClick={async () => {
      try { await navigator.clipboard.writeText(bundle.text); if (mounted.current) setCopyStatus(`Copied evidence from revision ${bundle.revision}. Review before sharing.`); }
      catch { if (mounted.current) setCopyStatus('Clipboard unavailable. Download the readable evidence or select the text under Inspect evidence and limits.'); }
    }}>Copy readable evidence</button></div><p role="status">{copyStatus}</p><details><summary>Inspect evidence and limits</summary><pre className="evidence-text">{bundle.text}</pre></details></> : null}
  </section>;
}
