# The workflow and its limits

For the joiner reviewing inbox records in the [AWS workstation](https://d2ssmv59q16d0b.cloudfront.net/),
controlled-live mode uses Bedrock and restricted SES; retained simulation uses a scripted
Strands model and simulated acceptance. Read [release.json](https://d2ssmv59q16d0b.cloudfront.net/release.json),
[/api/health](https://d2ssmv59q16d0b.cloudfront.net/api/health), and
[exact-pair acceptance](https://d2ssmv59q16d0b.cloudfront.net/acceptance.html).
[Evidence](EVALUATION.md) and [disclosures](../README.md#pre-existing-work-disclosed) apply to both modes.

## One repeated job

A joiner doing client collections alone compares invoice and remittance emails before asking a
client for money. Archon brings the retained records, remaining balance and proposed collection
email into one review. The product currently works from supplied fictional text, not a connected
mailbox. It replaces a manual comparison within this demonstration; time savings have not been measured.

Start with **Explore populated demo → Load business portfolio**. Its 240 typed fictional records
populate six document views and the financial dashboard. They are posted through ledger checks,
not AI-extracted emails; loading creates no model call, report, draft or email.
The optional **Load demo workspace** provides five locally parsed email templates for a smaller
case. That walkthrough shows an invoice of 1,860.00 EUR, a client receipt of 600.00 EUR and
1,260.00 EUR remaining. These are source figures, not bank-verified settlement.

## What Strands contributes

The real Strands SDK graph runs six ledger readers before a composer with no tools.
The edge condition enforces all six reports; removing Strands prevents draft preparation.
It checks that reports are present, not that six agents agree or have independently verified them.
In controlled-live mode, Bedrock interprets the domain reports and supplies bounded opening/closing
text. Ledger code selects the invoice and adds the verified figures.
In retained simulation, a scripted model traverses the graph; it does not perform live inference.

Approval binds the exact rendered bytes. The gate re-derives invoice, amount, recipient and other
claims, checks expiry, and refuses stale or held evidence. Controlled-live sends use the separate
durable SES outbox and the verified test recipient. Synthetic acceptance is simulated.
Neither a provider ID nor a matching document hash proves source authenticity or mailbox arrival.

## Why the source details matter

Accounting direction follows the configured business and the original issuer/customer evidence.
A payment needs an explicit supplied transfer reference, not just an email hash.
Equal instalments may be distinct events, but forwarding a receipt cannot credit its reference twice.
An ambiguous source or missing identity stops collection for human correction.

Human resolution can link a duplicate, record an externally resolved dispute, or attest distinct
historical payment identities without rewriting old sources or journals. Conflicting legacy
duplicates need an operator accounting correction. Fresh review follows a resolution.

Synthetic `PublicPostReader` supports explicit full English month names and US/EU decimal EUR
notation; controlled extraction requires ISO dates and literal source-backed values.
Both readers construct only sales invoices, purchase invoices and client receipts. Supplier
payments and credits are supported as typed portfolio fixtures, not raw-mail extraction.
That bounded support does not establish general invoice extraction or OCR.
A recorded counterproposal preserves the client's original reply. It is pending client acceptance,
sends no message, changes no debt and creates no collection hold. An agreed plan changes collection
timing, not the outstanding balance.

## Opt-in automated input

The [incoming HTTP webhook](incoming-webhook.md) is available for opt-in intake.
Its per-workspace key starts disabled and the owner must configure an external producer.
Check served identities and matching acceptance before use. The intake path uses a separate scoped
token, maximum 24-hour lifetime within workspace expiry and durable event-ID deduplication.
It uses live Bedrock intake under existing limits and cannot send or approve email.
It is not direct Gmail/Outlook login, a bank connection, or automatic collection.

## What is established

The [dated product acceptance record](EVALUATION.md) binds actual Bedrock calls and controlled SES
acceptances to frontend/backend `b446e36` in
[run 34863683977, attempt 2](https://github.com/upgradedev/archon-aws-strands/actions/runs/34863683977/attempts/2).
Three provider journeys and six separate portfolio journeys passed. The latter used no model
or mail operations. These checks do not measure model quality or accept future changes.
The owner's six received messages are HUMAN-ATTESTED arrival; per-run correlation and the full
approved-body comparison remain unknown. Full human UAT is NOT_RUN.

Both earlier comparisons remain withdrawn. The retained evaluation produced zero Archon chases,
achieved by not acting. Fresh synthetic evaluator contracts check exact invoice, nonempty correct
recipient and amount; these are not new performance measurements.
Human active time, customer benefit, general model quality and production recovery outcomes
have not been measured. The evidence does not establish superiority, novelty or eligibility.

[Prior work](PRIOR-WORK.md) names ten earlier Archon repositories and the package/CI/visual influences.
No code from those repositories is in this repository, as disclosed by the author.
