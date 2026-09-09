# Video script: public synthetic workflow

[Evidence and limits](../README.md#evidence-and-limits) · [Required disclosures](../README.md#pre-existing-work-disclosed)

For a joiner reconciling invoice and remittance emails alone.
Open [the AWS workstation](https://d2ssmv59q16d0b.cloudfront.net/).
Short try flow: Records → invoice → payment → Workspace → Run Strands → exact draft → History.
The public reader is rules-based, the Strands graph is real, the model is scripted and all email
acceptance is simulated. No mailbox is connected and no real email leaves.

Before recording, inspect /release.json and /api/health and retain their SHA values with the
recording. This is a script, not a completed video or human UAT. CI and live acceptance must match
the recorded revision. The seven timing targets total 295 seconds; actual duration is unmeasured.

## 1. The joiner — 40 seconds

Show the empty Dashboard. Explain the repeated job: compare the client invoice with the
remittance before asking for money. Explain that the firm and all emails are synthetic.
No customer time saving or recovered-money figure has been measured.

## 2. Editable evidence — 45 seconds

Open Records, select Sample invoice and inspect its original From/To headers.
Post it. Select Sample payment and point to Transfer ID, then post it.
Show 1,860.00 EUR minus 600.00 EUR equals 1,260.00 EUR outstanding.
These are posted source figures, not independently verified bank transactions.

## 3. Refusal and correction — 55 seconds

Paste a payment with its Transfer ID removed. Submit and show the actual refusal.
Collections are held. Choose Correct source and enter the correct synthetic reference and facts
for a distinct payment. Post it and show that the original refusal remains retained.
Do not invent a new reference to relabel the same payment.

## 4. Strands is load-bearing — 35 seconds

Run Strands from Workspace. Show the actual pending status and completed six domain reports.
The composer holds no tools and waits for all six readers. Removing the SDK prevents this step.
The model here is scripted; it does not reason. Operator Bedrock configuration is a separate mode.

## 5. Exact review and changed evidence — 65 seconds

Inspect the draft, recipient, source invoice, remittance and remaining balance together.
Read every figure from the screen. Explain that changed sources, ledger revision or expiry
require a fresh draft and review. Show an actual refusal/correction decision in History.
Human resolution records an external dispute decision or duplicate-payment link; it is not
automated arbitration and it never changes money.

## 6. Simulated acceptance and recovery — 35 seconds

Approve the exact current draft, show its simulated receipt and reload History.
It remains the same recorded acceptance. No real email has been sent.
If the API is unavailable, show the error and refresh durable state before any retry.
There is no SES fallback shot and no claim that a message went to an owned inbox.
Provider acceptance does not prove arrival.

## 7. Evidence and limits — 20 seconds

Prepare the readable evidence bundle, inspect revision, source decisions and limits.
A hash identifies bytes, not truth. End on the AWS URL and repository.
The earlier comparisons are withdrawn; the retained benchmark had zero Archon chases.
That was silence, not measured accuracy. Human UAT and benefit measurement remain NOT_RUN.

## What must not be said

- Do not call the offline run agentic reasoning; the scripted model walks the graph.
- Do not claim a live mailbox, real email delivery, bank verification or OCR.
- Do not present a withdrawn or circular benchmark as current evidence.
- Do not claim compliance, competitive superiority, measured time savings or collected money.
- Do not narrate a scripted decision as a live model result.
