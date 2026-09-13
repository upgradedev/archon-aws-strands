# Description draft: controlled-live workflow

Draft only: refreshed against the supplied release record, not submitted.
[Evidence and limits](EVALUATION.md) · [Required disclosures](../README.md#pre-existing-work-disclosed)

Archon helps a joiner reconcile inbox invoices and approve an exact collection draft with the
source evidence beside it.

[Try the AWS workstation](https://d2ssmv59q16d0b.cloudfront.net/).
Choose Explore populated demo → Load demo workspace, inspect Records, then follow the example
or run Strands and review its exact draft. Loading the five fictional sources is deterministic:
no model call, AI report, draft or email is created by the seed.

The joiner works alone, comparing invoice and remittance emails before chasing a client.
Archon brings those records together with the amount still outstanding and the reason collection
is ready or held. Text is supplied in this demonstration; no mailbox is connected.
The example invoice is 1,860.00 EUR and its remittance is 600.00 EUR: 1,260.00 EUR remains.

In controlled-live mode, semantic intake and reasoning use real Amazon Bedrock through a separate
durable worker. The Strands Agents SDK graph requires six ledger readers to finish before a
composer with no tools prepares wording. Ledger code selects the invoice and verifies amounts;
model advice does not replace deterministic checks. Removing Strands prevents draft preparation.
The configured model is eu.anthropic.claude-opus-5 in eu-west-1; that is not the public scripted mode.

Retained simulation uses the same interface and real graph with a scripted model and simulated
outbox: no real email leaves that mode. A simulation receipt never becomes a real send.
Controlled-live mode instead requires explicit real-email consent for the exact fingerprinted
draft and sends only to the configured verified test recipient through SES.
It cannot send arbitrary collections to real customers.

Change the fictional text before posting. An unreadable amount, missing transfer identity or
conflicting invoice direction holds collection. Corrected source retains the original.
Distinct equal instalments need distinct supplied bank references; a changed subject cannot
credit the same reference twice. A supplied reference is not external bank verification.

Human decisions can link a duplicate to its original receipt or record an invoice-linked dispute
already resolved by a person. They invalidate the draft so the evidence and exact bytes require
fresh review. A payment-plan counterproposal preserves the original reply and is pending client
acceptance: it sends no message, changes no debt and creates no collection hold.

History exports readable evidence with redacted source excerpts, decisions, corrections, backend
and ledger revisions, runtime mode and recovery limits. A hash identifies bytes, not truth,
bank settlement or compliance. Dashboard outcomes count recorded actions in the session;
human active time, money recovered and time saved are unknown.

The supplied [AWS run 34778777702](https://github.com/upgradedev/archon-aws-strands/actions/runs/34778777702)
records three actual browser cases, 45 model calls and three SES acceptances for frontend
40c7ade / backend 2bb3db3. These are that release's observations, not a new model-quality benchmark.
The owner later reported six received messages and supplied a screenshot: HUMAN-ATTESTED arrival.
Exact per-run Message-ID correlation and full approved-body comparison remain unknown.
The machine delivery flag stays false, and full human UAT is NOT_RUN.

Two earlier comparisons remain withdrawn. The retained evaluation reported zero Archon chases,
earned by not acting; that is not useful accuracy. Its evaluator omitted exact invoice and
nonempty recipient checks; fresh synthetic contracts cover those fields. No new benchmark result
or held-out reuse is claimed. The withdrawn injection result establishes no current advantage.

The firm and records are invented. Public input is bounded English plain text, ISO dates and EUR;
there is no bank feed, payment execution, OCR, payroll provider, deployed AgentCore or Aurora.
A session-scoped incoming HTTP webhook is being implemented but is **not yet deployed**.
Its provisional contract allows owner-enabled external mail/export intake with a separate token,
maximum 24-hour expiry within the seven-day workspace, durable deduplication and no automatic send.
It is not a Gmail/Outlook login; producer setup remains with the owner.

[Frontend identity](https://d2ssmv59q16d0b.cloudfront.net/release.json),
[backend identity and mode](https://d2ssmv59q16d0b.cloudfront.net/api/health), and
[acceptance](https://d2ssmv59q16d0b.cloudfront.net/acceptance.html) identify the served pair.
[CI evidence](https://github.com/upgradedev/archon-aws-strands/actions) is scoped to its exact SHA.
CloudFront/private S3 serve React; API Gateway and Lambda save conditional S3 session state and
dispatch the separate Bedrock/SES worker. This draft has no new CI or deployed acceptance claim.

## Disclosure

Ten earlier Archon repositories are named in [PRIOR-WORK.md](PRIOR-WORK.md).
No code from any of them is in this repository. Pre-existing package/CI patterns and visual design
direction are disclosed there; [THIRD-PARTY.md](THIRD-PARTY.md) retains dependency notices.
This build is [MIT-licensed](../LICENSE). Eligibility remains the organizer's decision.
The supplied graphics are [concept art](GRAPHICS.md), not product screenshots or current topology.
