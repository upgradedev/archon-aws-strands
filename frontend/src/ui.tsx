import type { ReactNode } from 'react';

export function money(value: string): string {
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
    queue: 'M4 5h16M4 12h10M4 19h7M17 16l3 3-3 3',
    documents: 'M7 3h7l4 4v14H7zM14 3v5h5M10 12h5M10 16h5',
    approvals: 'M12 3l8 4v6c0 4-8 8-8 8S4 17 4 13V7zM8 12l3 3 5-6',
    activity: 'M4 12h3l3-7 4 14 3-7h3',
  };
  return <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name]} /></svg>;
}
