# Using Archon

For the joiner reviewing inbox records in the [AWS workstation](https://d2ssmv59q16d0b.cloudfront.net/),
controlled-live mode uses Bedrock and restricted SES; retained simulation uses a scripted
Strands model and simulated acceptance. Read [release.json](https://d2ssmv59q16d0b.cloudfront.net/release.json),
[/api/health](https://d2ssmv59q16d0b.cloudfront.net/api/health), and
[exact-pair acceptance](https://d2ssmv59q16d0b.cloudfront.net/acceptance.html).
[Evidence](EVALUATION.md) and [disclosures](../README.md#pre-existing-work-disclosed) apply to both modes.

## Start with fictional records

The application shows its introduction before accessing the session API.

1. Choose **Explore populated demo → Load business portfolio**, the recommended first option.
   It opens a separate fictional quarter with 240 typed records across six document types.
2. Inspect Dashboard's net sales, net purchases, credits and cash movements. Follow a widget to
   Records, then open a document's retained source and linked invoice. Credits reduce debt;
   they do not record cash received or paid.
3. Use the six document views, search and date filters to explore the books. Check the dataset
   label above the dashboard: it distinguishes the full portfolio from a small or empty workspace.
4. Open Workspace or Guided check to inspect the collection priority. **Run Strands & prepare
   draft** is a separate, explicit action. In controlled-live mode it uses Bedrock; sending needs
   another exact review and real-email consent.

Loading the portfolio posts typed fixtures through deterministic ledger checks. It creates no AI
report, draft, approval or email. Zero activity counters mean those actions have not happened.
See [Business portfolio](BUSINESS-DEMO.md) for the record mix, financial dates and limits.
An existing small or empty Dashboard also offers **Load full dashboard · 240 records**.

### Optional product tour

The **Take a tour** header button becomes available once a workspace is loaded. Its six stops explain
Dashboard → Records → Incoming → Workspace → Guided check → History. **Next stop** and
**Previous stop** change the explanation only. **Open [page]** is an optional navigation link;
finish any unsaved input first. Page navigation is paused while an operation is busy, a provider
outcome is pending or uncertain, or the workspace snapshot is stale.

Use **Close tour**, **Finish tour** or Escape to close it. The tour never loads demo data, changes
sessions, enables Incoming, runs a model or approves/sends email. It is separate from the Guided
check, where explicit actions can post evidence and prepare a draft. The tour accompanies this
documentation update; the recorded `3e89590` acceptance snapshot predates it, so its release needs
its own CI and acceptance. Reopening starts at the first stop; tour progress is not saved.

### The smaller example and your saved workspace

**Demo data → Load demo workspace** is the optional five-source tutorial: two customer invoices,
their client receipts, and a supplier invoice. Its sources are fictional email templates parsed
with local rules. It has no credits or supplier payments, so their widgets show zero.
Neither demo load calls Bedrock or sends mail, even when the workspace mode says live.

**Return to previous workspace** restores the immediately previous session without rewriting its
books. The browser retains the current and one previous handle, not a list of every workspace;
session access still expires after seven days. If browser storage is blocked, handles last only
until the page closes. A retained simulation warns when live providers are available and offers
a separate demo with current providers. Its simulated receipts never become real sends.

Choose **Try the example step by step** for invoice → payment → review → outcome, or
**Continue my workspace** for the current dashboard. The guided check uses the current session;
it is not an empty sandbox after loading a portfolio. Use **New workspace** and its explicit
confirmation to start empty books. You inspect sources and approve the exact draft yourself.

### Check how an invoice changes

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

## Supported input and execution mode

The Records editor, file-text preview and opt-in Incoming webhook share the public reader's
three document types. The button **Sample payment** supplies a client receipt, not a supplier payment.

| Input | Public raw-mail reader | Full portfolio |
|---|---|---|
| Sales invoice (`SalesInvoice`) | Supported within the format limits below | Typed fixture |
| Purchase invoice (`PurchaseInvoice`) | Supported within the format limits below | Typed fixture |
| Client remittance (`Receipt`) | Must settle a posted sales invoice and carry a Transfer ID | Typed fixture |
| Supplier payment (`Payment`) | Unsupported | Typed fixture only |
| Sales or purchase credit note | Unsupported | Typed fixture only |

This boundary comes from [Documents.tsx](../frontend/src/Documents.tsx) and the
[reader's document constructors](../src/archon/adapters/inbound.py); richer ledger support does
not extend extraction. Use invented English plain text. PDFs, scans, images and OCR are unsupported
in the public workstation.

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

## Review, arrangements and evidence

In Payment arrangement, read the client's dated terms and either approve that exact plan or
choose **Offer different payment dates**. Review your counterproposal and explicitly record it.
The original reply and counterproposal survive reload and appear in the readable evidence bundle.
A counterproposal is pending client acceptance: it sends no message, changes no debt and creates
no collection hold. Record a fresh client reply before approving an arrangement. New evidence,
holds, expired proposals or stale revisions require review again. An arrangement changes chase
timing, not the balance. The original reply is also retained when a client plan is approved.

Navigation includes Guided check, Dashboard, Workspace, Records, Incoming and History.
These cover step-by-step review, balances, exact approval, documents, opt-in intake and retained
outcomes. Legacy bookmarks still resolve.
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

The incoming HTTP webhook is opt-in. The per-workspace key starts disabled;
the owner enables it and configures the external producer. Check served identities and matching
acceptance before using it. It accepts intake only, not mailbox login or automatic collection.
See [incoming-webhook.md](incoming-webhook.md) for setup, scope, expiry and retry behavior.
