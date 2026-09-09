# The first comparison this project is allowed to quote

Both earlier sets are withdrawn and stay withdrawn. They failed in two different
ways, and the second was worse than the first:

* the emails were written by the same hand as the parser, so they were one-line
  summaries shaped like the thing that would read them;
* **Archon's own column was scored from books the fixture had already posted
  correctly**, while the method it was measured against started from raw text.
  That is not a comparison of methods. It is a ledger agreeing with itself.

## The protocol, fixed before the run

* **Same raw inputs.** Every method receives the same list of email strings and
  nothing else. Nobody is handed books.
* **Same allowed context.** Every email in the case, plus today's date. No
  method is told the answer, the shape of the case, or how many emails matter.
* **A declared baseline.** `reference matching` — match a payment to an invoice
  by its reference and chase the remainder — is what small-business software
  actually does. It is named as the thing to beat before the run, not chosen
  afterwards.
* **Answers fixed first.** They arrived with the fixtures.
* **Held-out cases.** Four are excluded from every published figure and reported
  separately. Nothing was tuned against them.

## Where the inputs came from

Twenty-four independent agents each wrote one month of a small firm's post. Each
was told only the business situation — an overdue invoice, a part payment, a
dispute, a client proposing instalments — and **nothing whatever about how
anything here reads an email**. Each set was then audited by a different agent
for realism and for whether its stated answer follows from its own emails.

They came back as real post. Line items, VAT at the local rate, IBANs, a
Saturday call-out charge, and a note asking someone to look at a condenser fan
that is starting to rattle.

`python -m archon.evidence.fair` reproduces the deterministic rows.

## The result

Twenty scored cases:

| method | wrong money | wrong recipient | missed | correct |
|---|---|---|---|---|
| reference matching (baseline) | **10 / 20** | 0 | 6 | 4 |
| naive text extraction | **11 / 20** | 0 | 5 | 4 |
| **Archon, offline rule reader** | **0 / 20** | 0 | **15** | 5 |
| **Archon, live Bedrock reader** | **1 / 20** | 0 | **14** | 5 |

Four held-out cases, never used to tune anything:

| method | wrong money | missed | correct |
|---|---|---|---|
| reference matching (baseline) | 3 / 4 | 1 | 0 |
| naive text extraction | 3 / 4 | 1 | 0 |
| **Archon, offline** | **0 / 4** | 3 | 1 |
| **Archon, live** | **0 / 4** | 3 | 1 |

Live rows: `global.anthropic.claude-opus-5`, us-west-2, 2026-09-09, one call per
email. Transcript: [`FAIR-LIVE-2026-09-09.txt`](FAIR-LIVE-2026-09-09.txt).

## What it says, both ways

**Archon does not demand money that is not owed.** Zero of 20 scored and zero of
4 held out with the offline reader; one of 20 with the live one. Both baselines
demand a wrong figure in **half** the cases, and the held-out set says the same
thing at 3 of 4. That is the axis this product is built around, and it is the
one where it wins by a distance.

**It is much quieter than either baseline.** It says nothing on 14 to 15 of 20
where reference matching misses only 6. A method that never sends is useless, so
this is a real cost and not a footnote. **On this evidence Archon collects less
money than the baseline while embarrassing its owner far less often.** Which of
those a small firm should prefer is a judgement, not a measurement, and nothing
here settles it.

## Why it goes quiet

Every miss by the offline reader is the same thing: it read nothing at all. It
wants `dated 2026-07-24` and a person writes "dated today, 24 July 2026". That
is a fact about a regular expression, not about the product.

The live reader is what ships, and it read most of them — after a defect found
during this run. **Every live read was coming back empty with `stopReason:
max_tokens`**, because the token budget was 400 and a reasoning model spends
that before it reaches the JSON it was asked for. The adapter reported "the reply
carried no JSON" and refused the email. It looked exactly like a model that
could not read an invoice. It was a model that was not allowed to finish the
sentence.

A second question had never been answered: `purchase_invoice` and
`sales_invoice` are the same email seen from two sides, and nothing told the
reader which side the firm was on. It guessed, and turned money owed **to** the
firm into money owed **by** it. It is now told which end of the email it is —
"the sender" or "the recipient", never an address, because two existing tests
failed the moment the first attempt put a real address into the prompt.

## What this still does not show

Twenty-four cases is a small number. The authors were agents, not the small
firms themselves; they wrote convincing post, but nobody has run this against a
real inbox. The audit of each fixture was also done by an agent. And this is one
firm's worth of shapes, in one currency, in Europe.

**No claim is made that Archon is better overall.** It is better on one measured
axis, worse on another, and the two are stated together everywhere they appear.
