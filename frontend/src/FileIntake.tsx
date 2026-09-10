import { useEffect, useRef, useState } from 'react';

export function validateFileText(body: string): string {
  if (!body.trim()) return 'The file is empty. Choose a text email containing invoice or remittance evidence.';
  if (body.length > 32000 || new TextEncoder().encode(JSON.stringify({ body })).length > 39000)
    return 'The text exceeds the intake limit. Use a smaller plain-text email without attachments.';
  if (/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/.test(body)) return 'Binary content is not supported. Export the email as UTF-8 plain text.';
  if (/^Content-Type:\s*(?:multipart\/|text\/html)|^Content-Transfer-Encoding:\s*(?:base64|quoted-printable)|^Content-Disposition:\s*attachment/im.test(body))
    return 'Encoded, HTML or multipart email is not supported here. Export the readable email as UTF-8 plain text, preserving its original headers.';
  return '';
}

export function FileIntake({ disabled, onUse }: { disabled: boolean; onUse: (body: string) => void }) {
  const generation = useRef(0);
  useEffect(() => () => { generation.current += 1; }, []);
  const [preview, setPreview] = useState<{ name: string; body: string } | null>(null);
  const [error, setError] = useState('');
  const [reading, setReading] = useState(false);
  async function select(file?: File) {
    const current = ++generation.current;
    setPreview(null); setError(''); setReading(false);
    if (!file) return;
    if (!/\.(txt|eml)$/i.test(file.name)) { setError('Choose a .txt or plain-text .eml file. PDF, images and attachments are not supported by this intake.'); return; }
    if (file.size > 32000) { setError('The file exceeds 32 KB. Choose a smaller plain-text email.'); return; }
    setReading(true);
    try {
      const bytes = await new Promise<ArrayBuffer>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result as ArrayBuffer);
        reader.onerror = reader.onabort = () => reject(new Error('Could not read this file. Select it again or paste its readable text.'));
        reader.readAsArrayBuffer(file);
      });
      let body: string;
      try { body = new TextDecoder('utf-8', { fatal: true }).decode(bytes); }
      catch { throw new Error('The file is not UTF-8 text. Export it as UTF-8 or paste the readable email.'); }
      const invalid = validateFileText(body);
      if (invalid) throw new Error(invalid);
      if (current === generation.current) setPreview({ name: file.name, body });
    } catch (failure) { if (current === generation.current) setError((failure as Error).message); }
    finally { if (current === generation.current) setReading(false); }
  }
  return <details className="file-intake"><summary>Open a text email file</summary>
    <p>UTF-8 .txt or plain-text .eml, up to 32 KB. Synthetic data only. Reading a file stays in this browser until you submit the email.</p>
    <label>Choose text email<input type="file" accept=".txt,.eml" disabled={disabled} onChange={e => { void select(e.target.files?.[0]); e.target.value = ''; }} /></label>
    {reading ? <p role="status">Reading file for preview…</p> : null}
    {error ? <p role="alert">{error} The editor and posted evidence are unchanged.</p> : null}
    {preview ? <section aria-label="File preview"><h3>{preview.name}</h3><pre>{preview.body}</pre><button type="button" className="secondary" disabled={disabled || reading} onClick={() => { onUse(preview.body); setPreview(null); }}>Use file text in editor</button><p>Review the editable text, then Read &amp; post email. The server decides whether it can be posted or must be held.</p></section> : null}
  </details>;
}
