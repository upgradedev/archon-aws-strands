import { useMemo } from 'react';
import type { Workspace } from './types';
import { money } from './ui';
import { barPercent, businessPortfolio, QUARTER_START, recordLink } from './portfolio';

type Portfolio = ReturnType<typeof businessPortfolio>;

function CashFlows({ months }: { months: Portfolio['months'] }) {
  const values = months.flatMap(m => [m.cashIn, m.cashOut]);
  return <section className="panel business-widget" aria-labelledby="monthly-cash-heading">
    <div className="panel-heading"><div><h3 id="monthly-cash-heading">Monthly cash records</h3><p>Client receipts and supplier payments, including VAT. September is partial.</p></div></div>
    <svg className="cash-chart" viewBox="0 0 360 160" role="img" aria-labelledby="cash-chart-title cash-chart-description">
      <title id="cash-chart-title">Recorded cash in and cash out, July to September</title>
      <desc id="cash-chart-description">Paired bars share a zero baseline and scale. Exact values and document links are in the table below. No forecast.</desc>
      <line x1="62" x2="62" y1="10" y2="150" stroke="currentColor" />
      {months.map((month, index) => <g key={month.month}>
        <text x="4" y={28 + index * 48} fill="currentColor" fontSize="13">{['Jul', 'Aug', 'Sep'][index]}</text>
        <rect x="64" y={12 + index * 48} width={barPercent(month.cashIn, values) * 2.8} height="12" rx="2" fill="#79e1bd" />
        <rect x="64" y={27 + index * 48} width={barPercent(month.cashOut, values) * 2.8} height="12" rx="2" fill="#c1baff" />
      </g>)}
    </svg>
    <div className="table-scroll" tabIndex={0} role="region" aria-label="Monthly cash values"><table className="compact-table"><caption className="sr-only">Monthly cash records · exact EUR values</caption><thead><tr><th>Period</th><th className="numeric">Cash in</th><th className="numeric">Cash out</th></tr></thead>
      <tbody>{months.map((month, i) => <tr key={month.month}><th scope="row">{['July', 'August', 'September'][i]}<span className="subline">{month.observed ? `Through ${month.through}` : 'Not yet observed'}</span></th>
        <td className="numeric">{month.observed ? <a href={recordLink({ view: 'client-receipts', from: month.start, to: month.through })}>{money(month.cashIn)}</a> : 'Not observed'}</td>
        <td className="numeric">{month.observed ? <a href={recordLink({ view: 'supplier-payments', from: month.start, to: month.through })}>{money(month.cashOut)}</a> : 'Not observed'}</td>
      </tr>)}</tbody></table></div>
    <p className="section-note"><span className="cash-key cash-in" /> Cash in <span className="cash-key cash-out" /> Cash out · retained records, no bank connection.</p>
  </section>;
}

function TopParties({ title, rows, view }: { title: string; rows: Portfolio['clients']; view: 'sales' | 'purchases' }) {
  return <section className="panel business-widget" aria-label={title}><div className="panel-heading"><div><h3>{title}</h3><p>Up to five parties by open balance · all invoices through the ledger date.</p></div></div>
    {rows.length ? <div className="table-scroll" tabIndex={0} role="region" aria-label={`${title} values`}><table className="compact-table"><caption className="sr-only">{title}</caption><thead><tr><th>Party / invoices</th><th className="numeric">Outstanding</th></tr></thead><tbody>
      {rows.map(row => <tr key={row.party}><td><a href={recordLink({ view, party: row.party })}>{row.party || 'Unnamed party'}</a><span className="subline">{row.count} invoice(s)</span></td><td className="numeric">{money(row.outstanding)}</td></tr>)}
    </tbody></table></div> : <p className="section-note">No posted invoices.</p>}
  </section>;
}

export function BusinessWidgets({ data }: { data: Workspace }) {
  const portfolio = useMemo(() => businessPortfolio(data), [data]);
  const { totals, end } = portfolio;
  const period = { from: QUARTER_START, to: end };
  const cards = [
    { id: 'net-sales', label: 'Net sales after credits', value: totals.netSales, view: 'sales-invoices', note: `Invoices ${money(totals.sales)} · excludes VAT` },
    { id: 'net-purchases', label: 'Net purchases after credits', value: totals.netPurchases, view: 'purchase-invoices', note: `Invoices ${money(totals.purchases)} · excludes VAT` },
    { id: 'sales-credits', label: 'Sales credits · net', value: totals.salesCredits, view: 'sales-credits', note: 'Reduces client balances · not cash' },
    { id: 'purchase-credits', label: 'Purchase credits · net', value: totals.purchaseCredits, view: 'purchase-credits', note: 'Reduces supplier balances · not cash' },
    { id: 'cash-in', label: 'Recorded cash in', value: totals.cashIn, view: 'client-receipts', note: 'Posted client receipts · includes VAT' },
    { id: 'cash-out', label: 'Recorded cash out', value: totals.cashOut, view: 'supplier-payments', note: 'Posted supplier payments · includes VAT' },
  ];
  return <section className="business-overview" aria-labelledby="business-overview-heading">
    <div className="panel-heading"><div><p className="eyebrow">POSTED BOOKS / QUARTER TO DATE</p><h2 id="business-overview-heading">Business overview</h2><p>{QUARTER_START} to {data.as_of} · EUR · Credits reduce balances; settled means cash only.</p></div><a href="#/records?view=ledger">Quarter ledger →</a></div>
    <p className="section-note">Derived from posted typed documents and server-computed outstanding balances. {data.demo_seed === 'business-v1' ? 'The portfolio seed is fictional typed data, not AI extraction evidence. ' : ''}Refused sources are excluded. Aging includes open balances before this quarter.</p>
    {!portfolio.validAsOf || portfolio.undated || portfolio.unknownAmounts ? <p className="notice warning" role="status">Incomplete reporting evidence: {portfolio.undated} document(s) lack a valid financial date; {portfolio.unknownAmounts} dated document(s) lack a valid amount. Affected totals show Unknown. {!portfolio.validAsOf ? 'The ledger date is invalid.' : ''}</p> : null}
    <div className="business-stats">{cards.map(card => <a key={card.id} data-testid={`business-${card.id}`} className="stat" href={recordLink({ view: card.view, ...period })}><p>{card.label} ↗</p><strong>{money(card.value)}</strong><small>{card.note}</small></a>)}</div>
    <div className="business-grid"><CashFlows months={portfolio.months} />
      <section className="panel business-widget" aria-labelledby="aging-heading"><div className="panel-heading"><div><h3 id="aging-heading">Open balance aging</h3><p>As of {data.as_of} · includes balances held by arrangements.</p></div></div>
        <div className="table-scroll" tabIndex={0} role="region" aria-label="Aging values"><table className="compact-table"><caption className="sr-only">Open client and supplier balances by days overdue</caption><thead><tr><th>Age</th><th className="numeric">Clients</th><th className="numeric">Suppliers</th></tr></thead><tbody>
          {portfolio.aging.map(row => <tr key={row.id}><th scope="row">{row.label}</th><td className="numeric"><a href={recordLink({ view: 'sales', filter: 'outstanding', age: row.id })}>{money(row.clients)}</a></td><td className="numeric"><a href={recordLink({ view: 'purchases', filter: 'outstanding', age: row.id })}>{money(row.suppliers)}</a></td></tr>)}
        </tbody></table></div><p className="section-note">Credits are already included in outstanding. No payment is executed from these links.</p>
      </section>
      <TopParties title="Top clients" rows={portfolio.clients} view="sales" />
      <TopParties title="Top suppliers" rows={portfolio.suppliers} view="purchases" />
      <section className="panel business-widget document-mix" aria-labelledby="document-mix-heading"><div className="panel-heading"><div><h3 id="document-mix-heading">Document-type mix</h3><p>Posted documents dated in this quarter through {end}.</p></div></div>
        <table className="compact-table"><caption className="sr-only">Document-type counts and record drilldowns</caption><thead><tr><th>Document type</th><th className="numeric">Records</th></tr></thead><tbody>{portfolio.mix.map(row => <tr key={row.kind}><td><a href={recordLink({ view: row.view, ...period })}>{row.label}</a><span className="mix-track" aria-hidden="true"><span style={{ width: `${barPercent(String(row.count), portfolio.mix.map(r => String(r.count)))}%` }} /></span></td><td className="numeric">{row.count}</td></tr>)}</tbody></table>
      </section>
    </div>
  </section>;
}
