# The comparison was not a comparison, and here is what it says now

> Historical evaluation record, not current acceptance or performance evidence. Earlier
> comparisons remain withdrawn. The retained independent run made zero Archon chases;
> the evaluator has since gained exact invoice and nonempty-recipient checks. No new benchmark.

For the joiner reconciling inbox invoices: [live AWS workstation](https://d2ssmv59q16d0b.cloudfront.net/).
Try Records → invoice → payment → Workspace → Run Strands → exact review → History.
Public extraction is bounded, the model scripted and acceptance simulated; the real Strands graph
must finish all six reports before drafting. [Evidence and limits](../README.md#evidence-and-limits) ·
[Required disclosures](../README.md#pre-existing-work-disclosed).

**This supersedes the Archon column in `RESULTS-2026-09-04.md` and
`RESULTS-HARD-2026-09-08.md`. Those numbers should not be quoted.**

## What was wrong

`archon()` in `evidence/methods.py` read `scenario.books` — a set of books the
fixture had **already posted correctly** — while `one_pass_reading()` read
`scenario.post`, the raw text. Archon was never asked to build the books it then
reasoned over. It was handed them.

The published result, Archon correct on 20 of 20 and 15 of 15, was therefore not
a measurement of the product. It was a measurement of what a ledger says when a
ledger is already right.

Codex called this on 2026-09-08. It is correct, and the fix changes the answer
completely.

## What it says when every method starts from the same raw post

Archon now reads `scenario.post` through the same inbound pipeline the screen
uses, builds its own books, and decides from those.

| method | wrong money | missed | correct | |
|---|---|---|---|---|
| reference matching | 0 / 20 | 13 | 7 | unchanged |
| naive text extraction | 19 / 20 | 0 | 1 | unchanged |
| **Archon, offline rule reader** | **0 / 20** | **14** | **6** | was 0 / 20 · 0 · 20 |
| **Archon, live Bedrock reader** | **0 / 20** | **14** | **6** | new |

| the awkward month | wrong money | missed | correct | |
|---|---|---|---|---|
| reference matching | 0 / 15 | 6 | 9 | unchanged |
| naive text extraction | 15 / 15 | 0 | 0 | unchanged |
| **Archon, offline rule reader** | **0 / 15** | **15** | **0** | was 0 / 15 · 0 · 15 |
| **Archon, live Bedrock reader** | **0 / 15** | **15** | **0** | new |

Live rows: `global.anthropic.claude-opus-5`, us-west-2, 2026-09-08, one call per
email. Transcript: [`ARCHON-LIVE-READER-2026-09-08.txt`](ARCHON-LIVE-READER-2026-09-08.txt).

## The two things this actually shows

**The reader is not the bottleneck.** The live model scores exactly what the
offline rule reader scores, to the case. Paying for a frontier model to read
these emails changes nothing, which is worth knowing and is the opposite of what
this project would have guessed.

**The fixtures were never emails.** Every refusal in the transcript is one of two
lines:

```
a sales invoice with no client address cannot be chased
the email does not identify a document
```

The scenario post is a one-line summary written to exercise a naive extractor. A
real invoice email carries a recipient; these do not carry one the domain can
use. **Archon refuses to chase a debt when it does not know who to send it to,
and that refusal is correct** — but it means these fixtures cannot measure it.

## What survives, and what does not

**Survives:** Archon demands wrong money in 0 of 35 cases across both sets and
both readers. It goes silent rather than inventing a figure or a recipient. That
was the property being claimed, and it is the only one these fixtures can test.

**Does not survive:** any claim that Archon collects more than the alternatives.
On this evidence it collects less, because it refuses more. **A method that
refuses everything is not better than one that chases six months correctly**, and
`reference matching` beats Archon on both sets once Archon has to read.

## What would make this a real measurement

The fixtures have to become emails a person would actually receive: a From line
that identifies the counterparty, a recipient, and the invoice detail in prose
rather than in a summary line written for a parser. That is a rewrite of
`scenarios.py` and `hard.py`, not a tweak, and it must not be done by the same
hand that writes the reader's expectations, or the circularity comes back one
layer down.

**Until that is done, this project has no published claim that Archon is more
accurate than the alternatives, and the README says so.**
