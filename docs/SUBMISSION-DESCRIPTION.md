# Devpost description, ready to paste

Written to be pasted into the submission form's text description. Every figure
in it is produced by code in this repository and checked by
`tests/test_submission_text_is_true.py`, so if the product changes and this does
not, the build fails.

---

## Archon

**Archon reads the invoices landing in your inbox, keeps your books current, and sends the one email chasing what you are owed once you approve.**

### The person

A sole trader who runs the whole back office alone, out of an inbox. Supplier invoices to enter, payments to make, money to collect, payroll, tax deadlines, and no view of how any of it connects. Nothing is delegated because there is nobody to delegate to.

They do not have accounting software. That is the point: it assumes a bookkeeper operates it, and they are the bookkeeper, at the kitchen table, on a Sunday night.

47% of invoices in Western Europe are overdue. Small businesses spend close to ten hours a week chasing payment.

### What it does

Forward it an email, or attach a PDF invoice. Archon reads it, keeps double-entry books across six domains, and shows you what you are owed, what you owe, whether you can pay your people, and whether you are making money or just busy.

Then it does **one** thing: it sends the email chasing your oldest unpaid invoice, after you approve that exact text.

### Why it does not get the number wrong

**No digit reaches a client except through a claim the ledger confirmed.** The agent writes the greeting and the sign-off, and a draft whose free text contains a number is refused outright. Every figure in the email is rendered by the claim that proved it.

**Approval binds to a SHA-256 of the exact bytes.** One edited character invalidates it, and the gate re-derives every fact at send time. A client who paid at lunchtime is not chased with a draft that was correct that morning.

**Six Strands agents, one per domain, and the composer holds no tools.** Every edge into it is conditioned on all six having reported. They are asked what only a reader of that domain can judge, and they disagree: on a real run, payroll returned URGENT while suppliers returned WATCH on the same books at the same moment.

**It claims the interest the law already owes you.** A late commercial debt accrues statutory interest under Directive 2011/7/EU and almost nobody claims it. On the demo month that is 37.67 EUR nobody was going to ask for.

### The number, and it does not flatter this

Two earlier comparisons were withdrawn: they scored Archon from books the fixture had already posted
correctly, while the method it was measured against read raw text.

So the inputs were written by somebody else. Twenty-four independent agents each wrote one month of a
small firm's post, told only the business situation and nothing about how any of this reads an email.
Four cases are held out of every figure. Twenty scored, thirteen of which genuinely owed a chase:

| method | wrong money | sends | sends and is right |
|---|---|---|---|
| reference matching, the declared baseline | 10 / 20 | 10 | **0** |
| naive text extraction | 11 / 20 | 11 | **0** |
| **Archon** | **0 / 20** | **0** | **0** |

**Nobody collects any money correctly on this benchmark.** The baselines send ten and eleven times and
get the figure wrong every time. **Archon sends nothing at all**, so its zero is earned by not acting
rather than by being right.

On independently written post this product is **safe and not yet useful**, and reading real post is the
unsolved part: every case had at least one email it could not read. That is the honest state of it, and
it is worth more than the flattering version because it says exactly where the work is.

### Honest limits

**Archon sends nothing on the independent benchmark**, so its clean wrong-money column is earned by not
acting. The two earlier comparisons are withdrawn because they scored it from books already posted for
it. Twenty and twenty-four cases are small numbers; the fixture authors and their auditors were agents,
not the firms themselves, and the inputs are labelled synthetic wherever they appear.

The account is in the SES sandbox, so it sends only to verified addresses we control and never to a real
debtor. No mailbox is connected: nothing polls IMAP and no receipt rule is deployed. There is no OCR — a
scanned invoice is refused rather than guessed at. There is no public deployment. The firm in the demo is
invented and no customer data is anywhere in the repository.

The prompt-injection finding was measured on one of the withdrawn sets, and a real attacker would write a
better line than the one I wrote.

### What Archon is that our other entry is not

We have a second entry in this track, LastTake, and the rules make uniqueness the Sponsor's call, so here it is in plain words.

**LastTake stops a film crew being released while a required shot is missing.** Its buyer is a script supervisor, its unit is one shoot day, and nothing it produces ever leaves the production: the output is a hold, addressed inward.

**Archon keeps a sole trader's books out of their inbox and sends one email to somebody outside the firm asking for money.** Its buyer has no bookkeeper and no accounting software, its unit is the month, and that outbound message *is* the product.

One holds an internal decision back. The other reaches a third party — which is why every figure in it has to be provable, and why half this repository is the machinery that proves them.

### Built with

Strands Agents SDK · Amazon Bedrock (`eu.anthropic.claude-opus-5`) · Amazon SES · Python 3.11+ · FastAPI · SQLite

Runs offline with no AWS account: `pip install -e ".[dev]"` then `python -m archon.demo`.

### Disclosure

Archon is a product line and this is a new build. Ten earlier Archon repositories exist from other hackathons, two of them on AWS, and all ten are named in the README. No code from any of them is in this repository. The persona, the trigger, the hero mechanism and the write are all different here: this one is triggered by an inbox and ends in one governed email.
