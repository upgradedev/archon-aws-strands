import { useEffect, useState } from 'react';

// Re-evaluate exactly when a stored decision expires, including background tabs.
export function useClock(at?: string) {
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    const update = () => setNow(Date.now());
    update();
    const remaining = Date.parse(at ?? '') + 30 * 60 * 1000 - Date.now();
    const timer = Number.isFinite(remaining) && remaining > 0 ? window.setTimeout(update, remaining + 1) : undefined;
    window.addEventListener('focus', update);
    document.addEventListener('visibilitychange', update);
    return () => { clearTimeout(timer); window.removeEventListener('focus', update); document.removeEventListener('visibilitychange', update); };
  }, [at]);
  return now;
}
