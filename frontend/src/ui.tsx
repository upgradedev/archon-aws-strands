import type { ReactNode } from 'react';

export function money(value: string | null | undefined): string {
  if (typeof value !== 'string' || !/^-?\d+(\.\d{1,2})?$/.test(value)) return 'Unknown';
  const [whole, cents = '00'] = value.split('.');
  return `${whole.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}.${cents.padEnd(2, '0')} EUR`;
}
export function Badge({ children, tone = 'neutral' }: { children: ReactNode; tone?: string }) {
  return <span className={`badge ${tone}`}>{children}</span>;
}
export function Empty({ title, children }: { title: string; children: ReactNode }) {
  return <div className="empty"><span className="empty-mark" aria-hidden="true">↗</span>
    <h3>{title}</h3><p>{children}</p></div>;
}
export function Heading({ eyebrow, title, children }: { eyebrow: string; title: string; children: ReactNode }) {
  return <header className="page-heading"><p className="eyebrow">{eyebrow}</p><h1 tabIndex={-1}>{title}</h1><p>{children}</p></header>;
}
export function Icon({ name }: { name: string }) {
  const paths: Record<string, string> = {
    dashboard: 'M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z',
    workspace: 'M3 4h18v16H3zM12 4v16M3 9h9',
    records: 'M7 3h7l4 4v14H7zM14 3v5h5M10 12h5M10 16h5',
    history: 'M4 12h3l3-7 4 14 3-7h3',
    incoming: 'M3 6h18v14H3zM3 6l9 7 9-7M12 2v7M9 6l3 3 3-3',
    queue: 'M4 5h16M4 12h10M4 19h7M17 16l3 3-3 3',
    documents: 'M7 3h7l4 4v14H7zM14 3v5h5M10 12h5M10 16h5',
    approvals: 'M12 3l8 4v6c0 4-8 8-8 8S4 17 4 13V7zM8 12l3 3 5-6',
    activity: 'M4 12h3l3-7 4 14 3-7h3',
  };
  return <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name]} /></svg>;
}
