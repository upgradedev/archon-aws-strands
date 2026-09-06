# Archon

**Archon reads the invoices landing in your inbox, keeps your books current, and sends the one email chasing what you are owed once you approve.**

Built for **Agents for Humans (AWS)**, track **Professional Agents**, on the **Strands Agents SDK** and **Amazon Bedrock**.

---

## The person this is for

A sole trader or micro-business owner who runs the whole back office alone, out of an inbox. Supplier invoices to enter, payments to make, money to collect, payroll, tax deadlines, and no view of how any of it connects. Nothing is delegated, because there is nobody to delegate to, and every one of those chores arrives as another email.

They do not have accounting software. That is the point: the software assumes a bookkeeper operates it, and they are the bookkeeper, at the kitchen table, on a Sunday night.

## The one thing it does

It sends **one email**, after a human approves **that exact text**: the chase to the client who has not paid.

Everything else — reading the post, keeping double-entry books across six domains, producing the P&L and the cash position — exists to make that one email correct.

---

## The number

Twenty months of one firm's post, every answer known by construction. Re-run it yourself:

```bash
python -m archon.evidence.compare
```

| method | wrong money | missed | correct | 95% CI on wrong money |
|---|---|---|---|---|
| reference matching, how small-business software reconciles | 0 / 20 | **13** | 7 | 0.0% to 16.1% |
| naive text extraction | 19 / 20 | 0 | 1 | 76.4% to 99.1% |
| **a real Claude model, one pass, no ledger** | **0 / 20** | **3** | 17 | 0.0% to 16.1% |
| **Archon** | 0 / 20 | 0 | 20 | 0.0% to 16.1% |

**Wrong money** is an email demanding a figure that is not owed. It reaches a client and cannot be recalled. **A missed chase** is silence where money was owed. Both are shown, because a method that never sends anything scores zero on the first.

### What this does and does not show

**It was built expecting the opposite result.** The hypothesis was that a plain model would demand the invoice total from a client who had part paid. It does not. A frontier model reading the same post got **no figure wrong** and seventeen of twenty right. The number is published as it came.

So the claim is narrower, and it survives the model being good:

> The model was right seventeen times and silent three times, and **nothing in its answer tells you which**. Archon's answer carries its check with it.

**Archon's twenty out of twenty is partly circular** and is not the interesting row. Archon's answer and the scenario's truth are computed from the same postings, so it cannot lose. What the offline rows honestly measure is whether a method's *data model* can represent the answer at all: reference matching cannot represent a part payment, which is why it goes quiet thirteen times.

**This is a friendly test.** Twenty clean scenarios, one client each, no contradictory messages, no adversarial text. The interval on every zero runs to 16.1% because n is twenty. Full write-up: [`evidence/RESULTS-2026-09-04.md`](evidence/RESULTS-2026-09-04.md).

---

## Run it

No AWS account, no key, no network.

```bash
pip install -e ".[dev]"
python -m archon.demo
```

That walks the whole journey: post arrives, books are kept, six Strands agents read one domain each, a chase is drafted from claims the ledger confirmed, the gate decides, a human approves, the email leaves, the receipt is read back.

The screen:

```bash
python -m uvicorn archon.web.app:app --port 8000
```

Add `ARCHON_STORE=books.db` in front of that and the month survives a restart. Without it everything is
in memory, which is what the public walkthrough wants: one visitor should not leave the next visitor
somebody else's books.

A **static walkthrough** of the same three states, for anyone who would rather not run anything, is
published from the real code on every push to `main`:

```bash
python -m archon.web.export site
```

It is rendered by the same functions from the same ledger, so it cannot drift from what the code does.
It is not interactive, and every page says so.

Attach a PDF invoice, or paste one into **forward it an email**, and watch what gets hidden before anything reads it, then change a figure so the total stops adding up. Then press **the client pays at lunchtime** and try to send the draft you were reading.

With AWS:

```bash
python -m archon.demo --live-model     # reason on Bedrock
python -m archon.demo --live-send      # send through SES, needs verified addresses
```

Offline mode uses a scripted model. It walks the graph; **it does not judge**. Tone and the decision to chase are a model's work.

---

## How it is put together

```mermaid
flowchart TB
  mail["Email arrives"] --> san["Redact locally<br/>IBAN, cards, tax IDs, phones"]
  san --> read["Bedrock reads fields only<br/>never decides"]
  read --> led["Double-entry ledger<br/>refuses what does not add up"]

  led --> r1["suppliers"] & r2["sales"] & r3["payroll"] & r4["trading"] & r5["cash"] & r6["metrics"]
  r1 & r2 & r3 & r4 & r5 & r6 --> comp["Composer<br/>holds no tools"]

  comp --> draft["Draft: agent writes two lines<br/>every figure is a verified claim"]
  draft --> gate["Gate: re-derive everything<br/>match the approved bytes"]
  gate -->|released| ses["SES: send once, keep the receipt"]
  gate -->|held| stop["Nothing is sent"]
```

Every edge into the composer carries a condition satisfied only when **all six** readers have reported. The Strands graph fires a node under OR semantics in Python, so six edges alone would let the composer start on one report.

```mermaid
flowchart LR
  subgraph trust["What the model is allowed to touch"]
    a["reads redacted email text"]
    b["writes a greeting and a sign-off"]
    c["chooses which verified claims to state"]
  end
  subgraph never["What only code does"]
    d["every figure"]
    e["which invoice is chased"]
    f["whether the email may leave"]
  end
  trust -.->|"proposes"| never
  never -->|"refuses or releases"| out["one email"]
```

### Why six agents and not one query

It is the fair objection, and the first version of this deserved it: six agents
that restate what a deterministic tool returned are six model calls that add
nothing. So each reader is now asked a question only somebody looking at that
domain can answer, told that a colleague may reasonably disagree, and asked to
end with URGENT, WATCH or FINE.

They do disagree. From a real run on 2026-09-05, captured in
[`evidence/SIX-VIEWS-2026-09-05.txt`](evidence/SIX-VIEWS-2026-09-05.txt):

> **payroll** — "staff have gone unpaid for the entire subsequent month, which in a sole-operator firm
> almost certainly means the owner has not had the cash or has simply not acted, either way it cannot be
> left to slip further into the new quarter. **URGENT**"
>
> **suppliers** — "it is not yet overdue, the amount is modest, and there is nothing else in the queue,
> but the due date lands exactly on quarter-close so payment must be confirmed before books are shut.
> **WATCH**"

Same books, same moment, different pressure. The composer weighs six views rather than following the
loudest, and that is the work an LLM is actually for here. Every figure in both quotations came from a
tool; the judgement did not.

### The rules that carry it

- **A journal entry that does not balance is refused at construction.** No report downstream can silently lose money.
- **Every entry names the email it came from.** A number on screen walks back to the document.
- **Settlement is derived, never stored.** A "paid" flag that can disagree with the ledger is how books start lying.
- **No digit reaches a client except through a verified claim.** The agent writes the greeting and the sign-off, and a draft whose free text contains a number is refused outright.
- **Approval binds to a SHA-256 of the exact bytes.** One edited character invalidates it, and the gate re-derives every fact at send time — so a client who paid at lunchtime is not chased with a draft that was correct that morning.
- **It claims what the law already owes them.** A late commercial debt accrues statutory interest under Directive 2011/7/EU, and almost nobody claims it, because working it out means knowing the ECB reference rate and the day count. Archon knows both and puts the figure in the email that is asking for the money anyway. It is checked like every other figure and refused inside the thirty-day statutory window, where a small number would only invite an argument the sender would lose.
- **Every agent tool is a read.** No sequence of tool calls an agent invents can change the books or reach a client.

---

## What is real and what is not

| | |
|---|---|
| the ledger, six domains, P&L, cash, metrics | real, 323 tests, 93% branch coverage |
| the six-agent Strands graph | real, runs on `strands-agents` 1.53 and 1.54 |
| Bedrock | real, `global.anthropic.claude-opus-5`, verified by a live call |
| SES send, idempotent, with receipt | real code; **the account is in the SES sandbox**, so it can send only to verified addresses |
| reading an attached PDF | real. The text is extracted **on this machine**, redacted here, and only the redacted text is sent, because redaction cannot reach inside a file. A scan is refused rather than guessed at: there is no OCR |
| reading a forwarded email | real; redaction, typed extraction and the ledger's arithmetic check. Offline it is read by rules and the page says so, with Bedrock it reads anything |
| the firm, its clients, its staff | **entirely invented.** No customer data is present anywhere in this repository |
| the static walkthrough | real, rendered from the ledger on every push, published by GitHub Pages once the repository is public |
| the books between sessions | real. Set `ARCHON_STORE` to a path and the post is written down; loading replays it through the same validation, so a store cannot hold books that do not balance |
| a running deployment | not yet. The screen runs locally |

---

## Why this is a business

**The problem is measured and it is not niche.** 47% of invoices in Western Europe are overdue, 53% in
Central and Eastern Europe. Suppliers wait 61.8 days on average, five days longer than in 2022. Small
businesses spend close to **ten hours a week chasing payment**. Sources: Intrum's EU Payment Report 2026
and the European Commission's EU Payment Observatory, read 2026-09-05.

**Nobody sells to this person, and the reason is structural.** Accounting software assumes a bookkeeper
operates it. The sole trader is the bookkeeper, on a Sunday, after the work. Every existing product asks
them to migrate, to categorise, to learn a chart of accounts. So they do none of it, and the position
they are in is invisible to them until an accountant tells them in April.

**The wedge is that they already forward emails.** No migration, no data entry, no chart of accounts, no
setup call. They forward what already arrives and the books appear behind it.

**What they would pay for is not bookkeeping.** It is the money. On the fixture in this repository:
2,000.00 EUR that reference matching reports as settled, plus 37.67 EUR of statutory interest that the
law already owes them and nobody works out. One recovered debt pays for years of a tool like this.

**Measured unit cost**, from one real run against Bedrock on 2026-09-05, on the SDK's default model
rather than the Opus 5 this project configures: **12,070 tokens and 13 seconds for a whole month-close**,
across seven model calls, six readers and a composer. Converting that to money needs the Bedrock price
sheet, which this file does not quote because it has not been stamped here. The shape is the point: a
month-close is small, bounded and priced per run, not per seat.

**What defends it is the boring half.** Anyone can put an LLM in front of an inbox in a weekend, and the
comparison in this README shows a frontier model is genuinely good at reading one. What is hard is the
ledger that makes the model's output checkable, the claim that refuses to be stated unless the books
confirm it, and the gate that binds a human's yes to exact bytes. That is the work, and it is the part
that decides whether a business can let it send anything.

**What would have to be true, and is not yet.** These are the questions to ask before believing any of
the above:

- that people will forward mail to a third party at all, which nothing here has tested with a real person;
- that reading generalises past conventional invoices to the messy ones, which the twenty scenarios do not probe;
- that one governed write is enough to be worth paying for, rather than the first of many they would want;
- that the recovered money is attributable, so a customer can see what the tool got back for them.

None of those is answered by this repository, and a version of this section that implied otherwise would
be the same failure the comparison above refused to commit.

## Pre-existing work, disclosed

Archon is a product line and this is a new build on AWS. The submission rules require prior work to be disclosed, and the honest position is that this project **shares a name and a domain** with earlier entries while the persona, the trigger, the hero mechanism and the write are all different: this one is triggered by an inbox and ends in one governed email, where the others started from a file, an upload or a document store.

Prior Archon repositories, from other hackathons:

`archon-cockroach-memory` (AWS Bedrock) · `h0-archon` (AWS + Vercel) · `archon-gcp-agentic` · `archon-gcp` · `archon-vibecoding` · `archon_azure` · `archon_nebius` · `archon-qwen-autopilot` · `archon-qwen-memoryagent` · `archon-datahub`

No code from any of them is in this repository. The shapes of `pyproject.toml` and `.github/workflows/ci.yml` follow a sibling project, `lasttake-aws`; pattern followed, no lines copied.

## Limitations

- One firm. There is no tenancy: `ARCHON_STORE` keeps one set of books, not one per person.
- The inbound reader is exercised against pasted text, PDFs and a fake Bedrock client. No mailbox is connected: nothing polls IMAP and no SES receipt rule is deployed.
- There is no OCR. A photographed or scanned invoice is refused rather than guessed at, and that refusal says what to do instead.
- Payroll is ledger state only. No payroll provider is called and no real person's pay is handled.
- VAT is recorded, not filed. Nothing is submitted to any tax authority.
- The statutory interest rate is the ECB reference rate as at 2026-07-01 plus eight points. It moves twice a year and Archon does not fetch it; the date it was true is in the source and on the record.
- The comparison is twenty clean scenarios. It says nothing about behaviour under noise.

## Licence

MIT. See [`LICENSE`](LICENSE).
