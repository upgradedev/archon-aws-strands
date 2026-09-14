# Using Archon

For the joiner reviewing inbox records in the [AWS workstation](https://d2ssmv59q16d0b.cloudfront.net/),
controlled-live mode uses Bedrock and restricted SES; retained simulation uses a scripted
Strands model and simulated acceptance. Read [release.json](https://d2ssmv59q16d0b.cloudfront.net/release.json),
[/api/health](https://d2ssmv59q16d0b.cloudfront.net/api/health), and
[exact-pair acceptance](https://d2ssmv59q16d0b.cloudfront.net/acceptance.html).
[Evidence](EVALUATION.md) and [disclosures](../README.md#pre-existing-work-disclosed) apply to both modes.

## Start with fictional records

The application shows its introduction before accessing the session API.
Choose **Explore populated demo**, then **Load demo workspace**, for five fictional
source emails: a partially paid customer invoice, a fully paid one, their payments,
and a supplier invoice. Loading uses deterministic parsing and ledger checks, not
Bedrock, and creates no AI report, draft or email. Metrics are computed from those
records. **Return to previous workspace** restores the most recently used session
without overwriting its books; access still expires after seven days. A retained
simulation displays a warning when live providers are available and offers a separate
current-provider demo. Simulated receipts are never converted into real sends.
For more volume choose **Load business portfolio**: a separate 240-record, six-type fictional
quarter with invoices, both credit-note directions, receipts and supplier payments. See
[Business portfolio](BUSINESS-DEMO.md) for counts, navigation and limits. These are typed fixtures
validated by the ledger, not AI-extracted mail. Cash and credits remain separate.
Choose **Try the example** for a step-by-step invoice → payment → review → outcome check,
or **Continue my workspace** for the existing dashboard. Neither silently clears the books.
You inspect editable plain-text sources and approve the exact draft yourself;
the example never auto-approves. Existing records resume in the same session. Use **New workspace**
and its explicit confirmation only when you want empty books. No PDFs or OCR are
supported. Semantic extraction in controlled mode still needs explicit ISO dates,
two-decimal EUR amounts and source-backed references. Use the deployment links above to check mode.

To reproduce the deeper reconciliation path from scratch, use a separate empty workspace:
From Dashboard, choose Start reconciliation and review the editable invoice. Post it, open
Review changed decision and run Strands. Before approving that draft, open Try new evidence before
approving and add the sample payment. The original draft disappears. The decision shows why the
recorded 600.00 EUR payment changes the proposed chase from 1,860.00 EUR to 1,260.00 EUR, linked to
the retained source and transfer reference. Run the graph again and review the new exact draft.

Then try Check a forwarded duplicate. It retains the posted receipt's transfer reference;
submitting it holds collection without crediting another payment. Review the original evidence
and record the duplicate resolution in Records before preparing a fresh draft. A missing Transfer ID
requires correction with actual evidence. Original sources and earlier provider receipts stay retained.
The changed decision is a supported workflow demonstration, not comparative AI or human superiority.

## What changes the decision

- A payment carries an explicit bank transfer reference. Email hashes identify evidence bytes,
  not payments. The same reference cannot credit again, even in a forward or a different subject.
  Distinct references can identify equal instalments on the same invoice/date/amount.
  A supplied reference is evidence, not independently verified bank settlement.
- The configured business is My Joinery, me@myjoinery.example in the public synthetic workspace.
  Original issuer and customer evidence determines payable versus receivable. “Billed to” alone
  does not make a sale. Conflicting directions stop intake. A forwarded message uses its original
  headers; the full source is retained.
- Missing identity asks for human correction. A duplicate can be linked to its original posted
  receipt without another credit. A disputed or ambiguous client reply holds collection until a
  person records an invoice-linked resolution. Resolution does not arbitrate a dispute.
- Corrections, new evidence, human resolution, ledger revision changes and expired drafts
  require fresh review. A SHA-256 fingerprint binds the exact text; the release gate rechecks facts.
  A hash is not proof that an invoice is true.
- Existing sessions retain posted sources. Historical equal payments without transfer identities
  remain readable with collections held for human reconciliation. No historical financial row is
  rewritten to assign it an invented bank identity. Records exposes each hold with a bounded
  identity-attestation form for distinct historical events. The additive attestation retains human
  notes and supplied references; it does not rewrite posted sources. Conflicting duplicate events
  require an operator accounting correction, not a fabricated second reference. The legacy
  one-firm SQLite surface has no attestation UI; hand its evidence to an operator.

## React workstation usage

Synthetic mode selects `PublicPostReader` (`bounded-post-v2`): explicit ISO dates or
full English month names, and two-decimal EUR amounts such as `2,400.00` or `2.400,00`.
Net, VAT and gross must be stated and reconcile. Conflicting dates, totals or invoice references
are refused, not resolved by taking the first match. Relative dates, OCR and general prose remain
unsupported. Original text, invoice direction and transfer-identity guards remain authoritative.
Controlled mode uses semantic Bedrock extraction followed by exact-source checks for
ISO dates, decimal EUR values and invoice references. Its receipt-date instructions
are separate from the historical reader; absent fields are not guessed. The live
composer returns only JSON opening/closing fields, with the unchanged no-digit gate
before the ledger adds verified figures. A malformed response releases no draft.
The legacy `LocalReader` and the frozen AR3 baseline are unchanged. The new development regressions
are not independent held-out evidence, a model result or a rerun of the historical comparison.

In Payment arrangement, read the client's dated terms and either approve that exact plan or
choose **Offer different payment dates**. Review your counterproposal and explicitly record it.
The original reply and counterproposal survive reload and appear in the readable evidence bundle.
A counterproposal is pending client acceptance: it sends no message, changes no debt and creates
no collection hold. Record a fresh client reply before approving an arrangement. New evidence,
holds, expired proposals or stale revisions require review again. An arrangement changes chase
timing, not the balance. The original reply is also retained when a client plan is approved.

Navigation: Introduction → Guided check, or Dashboard → Workspace → Records → History.
The persistent navigation explains each task: balances, review/approval, invoices/payments and
decisions/receipts. Legacy bookmarks still resolve.
Invoice and source selection survives navigation and reload. Only the backend's oldest overdue
invoice, largest on a tie, can be prepared; inspecting another invoice does not retarget it.

Dashboard balances derive from retained posted documents using exact cents. Observed session
outcomes count posts, refusals, corrections, resolutions and approval records. Human active time,
time saved, revenue and recovery benefits remain Unknown. Quarter reports are labelled separately.
The richer dashboard shows recorded trading activity, not a claim of revenue recovered by Archon.
Credit-note and supplier-payment fixture support does not extend the public mail reader's formats.

Records also previews UTF-8 `.txt` and plain-text `.eml` files up to 32 KB. Choose a file, inspect
its literal text, then Use file text in editor. Only Read & post email submits it to the reader.
Empty, binary, oversized, encoded, HTML and multipart files are rejected with recovery guidance;
PDFs, images and attachments are not supported in this intake. Paste preserves the existing API path.

In Workspace or History, Prepare evidence bundle reads durable state. Download or Copy readable
evidence keeps that exact snapshot; clipboard failure leaves the download and selectable text available.
The readable export includes redacted
source excerpts, source hashes, decisions, corrections, backend and ledger revisions, runtime mode,
failure/recovery guidance and limits. Redaction is best effort; review before sharing.
The bundle does not attest authenticity, bank settlement, compliance or email arrival.

Public sessions use private S3 through API Gateway and Lambda, behind CloudFront and private S3
frontend hosting. Same-origin /api/* requests carry an opaque session handle. Session access expires
after seven days; physical storage retention is separately configured. The browser keeps only the
handle. Refresh durable state after an uncertain action; do not retry unknown sends automatically.
New workspace creates an empty session and does not delete the old records.

Local API storage is SQLite through ARCHON_SESSION_DB. Lambda uses ARCHON_STATE_BUCKET and a
private ARCHON_STATE_PREFIX. S3 errors never silently switch to temporary storage.
An anonymous request cannot enable SES or Bedrock or change the operating grant.
The API role cannot call these providers directly; only the configured separate
worker can, with budget, expiry, exact recipient and explicit approval checks.


## Input automation

This source revision includes an opt-in incoming HTTP webhook. The per-workspace key starts disabled;
the owner enables it and configures the external producer. Check served identities and matching
acceptance before using it. It accepts intake only, not mailbox login or automatic collection.
See [incoming-webhook.md](incoming-webhook.md) for setup, scope, expiry and retry behavior.
