# The first fair comparison, and it does not flatter this project

> Historical evaluation record, not current acceptance or performance evidence. Earlier
> comparisons remain withdrawn. The retained independent run made zero Archon chases;
> the evaluator has since gained exact invoice and nonempty-recipient checks. No new benchmark.

For the joiner reconciling inbox invoices: [live AWS workstation](https://d2ssmv59q16d0b.cloudfront.net/).
Try Records → invoice → payment → Workspace → Run Strands → exact review → History.
Public extraction is bounded, the model scripted and acceptance simulated; the real Strands graph
must finish all six reports before drafting. [Evidence and limits](../README.md#evidence-and-limits) ·
[Required disclosures](../README.md#pre-existing-work-disclosed).

## 2026-09-10: bounded public synthetic replacement instrument (AR2)

**Execution status at authoring: NOT_MEASURED.** The historical results below
remain historical evidence, including their corrections and withdrawals. No old
conclusion is reinstated by this instrument. The new instrument evaluates only
the current public synthetic workflow, not a real model or human benefit.

The raw email cases, exact answers and acceptance contract were committed first
in `33dbe4f534b02fb07945561264879a46e8c9793e`, before the harness. The frozen input
is [ar2-golden-v1.json](ar2-golden-v1.json), SHA256
`4e94e162f9c72224496ef41f27aa6aab00c95a9065a65ec306195a72b0af2a25`.
These are author-created golden cases informed by the public reader's supported
format. They are neither independent nor held out. They cannot establish inbox
accuracy, comparative AI quality, time saved, money collected or human benefit.

`python -m evaluation.ar2 --candidate-sha "$CANDIDATE_SHA" --output ar2-output`
runs only in GitHub Actions. Each method receives the same ordered raw intake,
draft, approval and reload tasks, with the same business and date. Expected
answers and case labels are withheld from method arguments. The public method
calls the actual ASGI API, bounded reader, ledger, Strands scripted graph, draft
gate and simulated provider using a fresh temporary SQLite session. It counts
actual new provider calls and their message contents, including across a new API
client/store connection. It does not exercise the live AWS endpoint, real SES,
concurrent sends, process death or a real model. Network/cloud clients are denied.

The simple baseline uses the same bounded reader and a separate flat reference
ledger. It checks invoice direction and due date, subtracts explicitly identified
receipts, holds unreadable/inconsistent input and duplicate transfer IDs,
rechecks the balance on approval and suppresses repeat exact approvals. It has
no Strands graph, double-entry books or claim gate. This isolates downstream
workflow on a shared reader; it is not a claim about commercial software. A tie
is an acceptable result and does not demonstrate a benefit from the graph.

The JSON reports action confusion counts, exact legitimate opportunities
captured, missed/wrong opportunities, false chases, abstentions, ledger/hold
mismatches and execution errors. Wrong invoice, recipient or amount is never an
exact capture, even when binary action counts call it a true positive. Each
approval attempt is a decision point; stale and duplicate approvals count too.
Always-abstain and deliberately unsafe controls must both fail candidate
acceptance. A crash or missing observation is NOT_MEASURED, never safe silence.
Candidate acceptance requires all fixed legitimate opportunities captured and
zero false chases or ledger/hold mismatches. No production policy is altered.

The workflow retains `result.json`, `receipt.json`, `source-sha256.json`,
`SHA256SUMS` and instrument JUnit output, including failed runs, for 90 days.
Artifacts name the exact candidate SHA, run and attempt. Two independent runs
must produce identical result bytes. Output directories are create-only, so a
retry cannot overwrite a failing receipt. The receipt records resolved SDK/API
versions; hashes attest bytes and provenance, not truth. This does not replace
the retained old transcripts. **AR2 concerns bounded synthetic evaluation only;
C1 real AI and human benefit remain NOT_MEASURED.**

## Historical comparison (retained without re-scoring)

Both earlier sets are withdrawn and stay withdrawn. The worse failure was the
second: **Archon's column was scored from books the fixture had already posted
correctly**, while the method it was measured against started from raw text.
That is a ledger agreeing with itself.

**This page was itself wrong for about an hour on 2026-09-09.** It published a
live row of 1 wrong-money in 20, read off the totals of an earlier aborted run.
The transcript said 10. The numbers below are the ones the committed transcript
and the committed code produce, and the mistake is recorded here rather than
quietly corrected, because a results page that edits itself silently is worth
nothing.

## The protocol, fixed before the run

* **Same raw inputs.** Every method gets the same list of email strings.
* **Same allowed context.** Every email in the case and today's date. Nothing is
  told the answer or the shape of the case.
* **A declared baseline.** `reference matching` — match a payment to an invoice
  by its reference, chase the remainder — is what small-business software does.
  Named as the thing to beat before the run.
* **Answers fixed first**, arriving with the fixtures.
* **Held-out cases.** Four, excluded from every published figure.

## Where the inputs came from

Twenty-four independent agents each wrote one month of a small firm's post, told
only the business situation and **nothing about how anything here reads an
email**. Each set was audited by a different agent. They came back as real post:
line items, VAT at the local rate, IBANs, a Saturday call-out charge, a note
asking someone to look at a condenser fan that is starting to rattle.

## The result

Twenty scored cases. Thirteen of them are cases where a chase was genuinely owed.

| method | wrong money | missed | correct | **sends** | **sends and is right** |
|---|---|---|---|---|---|
| reference matching (baseline) | 10 / 20 | 6 | 4 | 10 | **0** |
| naive text extraction | 11 / 20 | 5 | 4 | 11 | **0** |
| Archon, offline rule reader | **0 / 20** | 15 | 5 | **0** | **0** |
| Archon, live Bedrock reader | **0 / 20** | 15 | 5 | **0** | **0** |

Held out: baselines 3 of 4 wrong money; Archon 0 of 4, sending nothing.

Live rows: `eu.anthropic.claude-opus-5`, us-west-2, 2026-09-09, one call per
email. Transcript: [`FAIR-LIVE-2026-09-09.txt`](FAIR-LIVE-2026-09-09.txt).

## What this actually says

**Nobody collects any money correctly on this benchmark.** The baselines send ten
and eleven times and get the figure wrong **every single time**. Archon sends
nothing at all.

**Archon's zero wrong-money is achieved by not acting.** It is correct five times
and all five are cases where silence or a question was the right answer. On the
thirteen cases where a chase was genuinely owed it sent nothing. Reporting the
zero without this sentence would be the most misleading true statement in the
repository.

So the honest position is: **on independently written post this product is safe
and not yet useful.** That is a real result and it is worth more than the
flattering one, because it says exactly where the work is.

## Why it sends nothing

Every case has at least one email it could not read. Forty-one refusals across
twenty cases, and they are almost all one thing: *the email does not state an
issue date*. The reader wants `dated 2026-07-24`; a person writes "dated today,
24 July 2026". Five more are *the email does not identify a document*.

**Reading real post is the unsolved part of this product**, and until this
benchmark existed nothing said so, because the demo books were seeded and the
screen looked complete.

## Three defects this run found

**Chasing from partial books.** Before the fix, a month with one unread email
still produced a chase — from the invoice, without the payment. It demanded
2,029.50 where 1,429.50 was owed, thirteen times out of twenty-four. Partial
books are the most dangerous shape a number can have here: every figure in them
is arithmetically right and the total is wrong. **A refusal now stops the chase**,
which is what turned that 13 into a 0 and is a genuine product fix rather than a
scoring change.

**Every live read was returning empty** with `stopReason: max_tokens`, because
the budget was 400 and a reasoning model spends that before it reaches the JSON.
It read exactly like a model that could not do the job. **Every earlier live
figure in this repository was measured through that** and none is carried over.

**Nothing told the reader which side of the email the firm was on.** A purchase
invoice and a sales invoice are the same email seen from two sides, so it
guessed, and turned money owed *to* the firm into money owed *by* it.

## The baseline is weaker here than real software would be

An adversarial review found that `reference_matching` reads anglophone number formats and a hard-coded
list of reference prefixes. Several fixtures are Dutch and Irish, and on those it fails for reasons a real
reconciliation tool would not.

**So its 10-of-20 is an upper bound on its error rate rather than a measurement of it.** Fixing it can
only narrow the gap this page reports, never widen it. That is stated here rather than left for somebody
else to find, because a baseline nobody has tried to strengthen is not a baseline.

## What this still does not show

Twenty-four cases is small. The authors were agents, not the firms themselves,
and the audits were agents too. One currency, one region, one firm's worth of
shapes. Nobody has run this against a real inbox.

**No claim is made that Archon is better overall, and on this evidence it is not
better in any way a small firm could bank.** It is safer, and safety while
sending nothing is a starting point rather than a product.
