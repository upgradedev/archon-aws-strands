# Graphics: concept art only

**CONCEPT ART — NOT PRODUCT SCREENSHOTS. These images do not describe current infrastructure.**

For the joiner reviewing inbox records in the [AWS workstation](https://d2ssmv59q16d0b.cloudfront.net/),
controlled-live mode uses Bedrock and restricted SES; retained simulation uses a scripted
Strands model and simulated acceptance. Read [release.json](https://d2ssmv59q16d0b.cloudfront.net/release.json),
[/api/health](https://d2ssmv59q16d0b.cloudfront.net/api/health), and
[exact-pair acceptance](https://d2ssmv59q16d0b.cloudfront.net/acceptance.html).
[Evidence](EVALUATION.md) and [disclosures](../README.md#pre-existing-work-disclosed) apply to both modes.

## Supplied files

These owner-supplied JPGs are preserved unchanged under `graphics/`. They were inspected visually
for this disclosure. Their filenames indicate possible uses, not a completed video, a submission,
or approval to present their contents as shipped features.

| File | Visible concept claims that are incorrect for the current product |
|---|---|
| [archon_devpost_thumb.jpg](../graphics/archon_devpost_thumb.jpg) | A mock phone says “BANK MATCHED”, shows GBP £2,150.00 and an invoice approval screen; “Autonomous Financial Core” and “1-TAP APPROVALS” imply a broader product than the bounded email workflow. |
| [archon_financial_core_clean.jpg](../graphics/archon_financial_core_clean.jpg) | Labels AWS Aurora DSQL, incoming bank data, detection of deposits, outgoing-bank matching, receipt/fuel-ticket intake, invoice issuing, live cash flow and one-tap mobile approvals as if connected. |
| [archon_multi_trade_guild.jpg](../graphics/archon_multi_trade_guild.jpg) | Labels Aurora DSQL and bank matching, with automated flows for several trades, design purchases, project data/revenue streams and phone approvals that are not implemented integrations. |
| [archon_youtube_thumb.jpg](../graphics/archon_youtube_thumb.jpg) | A mock phone and receipt show GBP £2,450.00 and £38.40, “BANK MATCHED”, a named fictional client and one-tap invoice approval; these are not captured product screens or supported GBP intake. |

## What is true instead

Current AWS storage is private S3 session documents with conditional writes; Aurora DSQL is not
deployed. CloudFront/private S3, API Gateway, Lambda, a separate durable worker, Strands/Bedrock
and controlled-recipient SES are the described runtime. Use
[the architecture documentation](ARCHITECTURE.md) and served identity/acceptance links above.

Invoices and payment references come from supplied fictional text. No bank connection verifies
a deposit or matches a transaction. Public intake uses bounded EUR amounts; it does not establish
GBP support. Photographed receipts, fuel tickets, PDFs and OCR are not public input capabilities.
The real action is exact human review of a collection email, with controlled SES sending only
after explicit consent. It is not bank execution or general one-tap invoice approval.

The opt-in incoming HTTP webhook in this source revision starts with a disabled per-workspace key
and requires producer setup plus served-identity/acceptance checks before use. Its
[contract](incoming-webhook.md) allows intake only; it does not turn these bank/mailbox claims true.
There is no Gmail/Outlook login or automatic outbound email.

## Presentation boundary

Do not use these files as the README hero, product screenshots, current architecture evidence,
or proof of a recorded walkthrough. If displayed elsewhere, keep the CONCEPT ART / NOT PRODUCT
SCREENSHOTS label and these limitations next to them. Brand artwork and plausible accounting
arithmetic are not evidence that any illustrated connector or screen exists.
