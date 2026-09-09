# The first fair comparison, and it does not flatter this project

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
