# Business portfolio

An opt-in fictional quarter for exploring the [Archon workstation](https://d2ssmv59q16d0b.cloudfront.net/).
Controlled-live mode uses Bedrock and restricted SES; retained simulation uses a scripted model
and simulated acceptance. Verify [release.json](https://d2ssmv59q16d0b.cloudfront.net/release.json),
[/api/health](https://d2ssmv59q16d0b.cloudfront.net/api/health) and
[acceptance](https://d2ssmv59q16d0b.cloudfront.net/acceptance.html) together.
[Evaluation](EVALUATION.md) and [disclosures](../README.md#pre-existing-work-disclosed) apply.
Choose **Explore populated demo → Load business portfolio**, the first and recommended option.
An existing small or empty Dashboard also offers **Load full dashboard · 240 records** directly.
The **Demo data** link is always available in the header; the current dataset is labelled above
the dashboard. The small five-source guided example
remains available through **Load demo workspace**. Both create a separate workspace and retain
access to the previous one; neither silently adds records to your existing books.

## What is in the bundle

| Document type | Records | Effect |
|---|---:|---|
| Sales invoices | 80 | Client debt, net sales and output VAT |
| Purchase invoices | 50 | Supplier debt, net purchases and input VAT |
| Sales credit notes | 20 | Reduce referenced client debt, sales and output VAT; no cash movement |
| Purchase credit notes | 10 | Reduce referenced supplier debt, purchases and input VAT; no cash movement |
| Client receipts | 50 | Reduce referenced client debt and record cash in |
| Supplier payments | 30 | Reduce referenced supplier debt and record cash out |
| **Total** | **240** | **240 validated balanced journal entries** |

The versioned generator is [business_demo.py](../src/archon/web/business_demo.py), version
`business-v1`. Counts, links, source hashes, replay and ledger invariants are asserted in
[CI tests](../tests/test_business_demo.py). There are 16 invented clients and 10 invented suppliers,
with activity from July through 9 September 2026. September is a partial period, not a full-month
forecast. The demo uses EUR and an explicitly fictional 24% VAT assumption, not tax advice or a
claim that any business's VAT has been verified.

Each record retains its typed source document and hash. Its origin is
`fictional-business-fixture`, explicitly **not an imported email or bank feed**. Amounts are
validated and posted through `Books.record`; they are not arbitrary widget values. Data generation
does not call Bedrock, prepare a draft, send mail or execute a bank payment.

## How to explore

- Inspect net sales/purchases, credit notes and recorded cash separately on Dashboard.
- Follow a widget to its Records view; filter by document type, dates or reference.
- Page through the register and open an invoice's retained source and linked movements.
- Compare a partially paid invoice with a fully credited invoice. Both can have a lower balance,
  but **credit notes are not money received**. A fully credited invoice is not eligible for a chase.
- Use the current priority case for agent preparation. Viewing another invoice does not retarget
  the backend's oldest-overdue selection policy. Model usage is explicit and remains bounded.

The financial relationship is `invoice gross = cash settled + credited + outstanding`.
Net-sales and purchase charts subtract their corresponding credit notes. Cash charts use only
recorded receipts and payments; issuing an invoice is never assumed to move money.
Bank balance here is the recorded movement from a zero opening balance, not a connected account.
The example contains no payroll: trading surplus is not a complete real-world net-profit claim.

## Scope and limits

The fixed bundle is separate from the existing **50 interactive source-email** allowance.
Business sessions hold at most the fixed 240 records plus 50 subsequent source records; ordinary
and small-demo sessions keep their prior 50-source boundary. There is no user-supplied bulk seed,
arbitrary corpus size, provider-limit change or unlimited ingestion endpoint. Existing request,
provider-job, financial budget and expiry limits remain.

Credit notes in the bundle use native posting and replay rules, including invoice-direction,
net/VAT and remaining-balance checks. **The public mail reader does not ingest arbitrary credit
notes or supplier-payment messages.** Those richer fixture types are not evidence that AI can
extract them. Unsupported mail must still be refused. Refunds, unallocated cash, opening balances,
stock valuation, multi-currency accounting and bank execution are outside this extension.

The larger fixture is not an independent benchmark, scale certification or demonstrated customer
benefit. See [evaluation limitations](EVALUATION.md). New source CI does not establish deployment:
compare served frontend/backend identities and exact-release acceptance before reporting it live.

### Operator recovery

`ARCHON_BUSINESS_DEMO_DISABLED=true` refuses creation of new business portfolios while preserving
existing sessions and the smaller demo. It is an operator setting, never a caller-controlled field.
After any credit-note session has been created, **do not roll the API or worker back to a binary
that cannot decode credit notes**. Retain the compatible domain/codec and pause new bundles, or
roll forward with a reviewed correction. A frontend rollback alone does not remove stored records.
No existing session is migrated, deleted or rewritten when this extension is installed.

## Dataset provenance

All bundled identities, amounts and documents are freshly authored deterministic examples under
this repository's MIT licence. No Kaggle rows, prior project data, customer records or external
generator code are included.

Public dataset discovery included Kaggle. No matching, licence-verified six-type dataset was
imported. Online Retail II's primary publisher describes sales/cancellations and GBP unit prices,
not linked purchase invoices, supplier credits and independent cash settlements. Relabeling those
amounts as EUR or inventing missing bank evidence would misrepresent the source, so it is not used.
See the [primary dataset card](https://archive.ics.uci.edu/dataset/502/online+retail+ii).

The dashboard's accounting fields and visual layout are newly implemented. Existing prior-work
and ownership disclosures remain in [PRIOR-WORK.md](PRIOR-WORK.md).
