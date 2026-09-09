# Devpost description, ready to paste

[Evidence and limits](../README.md#evidence-and-limits) · [Required disclosures](../README.md#pre-existing-work-disclosed)

Archon helps a joiner reconcile inbox invoices and approve an exact collection draft with the
source evidence beside it.

[Try the AWS workstation](https://d2ssmv59q16d0b.cloudfront.net/).
Records → Sample invoice → post → Sample payment → post → Workspace → Run Strands →
inspect the draft → approve simulated acceptance → History.

The joiner works alone, checking invoice and remittance emails before chasing a client. Archon
brings those records together with the amount still outstanding and the reason collection is
ready or held. Text is pasted in this demonstration; no mailbox is connected.

The public route executes real HTTP requests, durable synthetic sessions and the Strands Agents
SDK graph. Six ledger reader tools must finish before a composer with no tools can prepare the
draft. The model is scripted, the reader uses bounded rules and the outbox is simulated.
No real email leaves and no public model call occurs.

The sample invoice is 1,860.00 EUR and its remittance is 600.00 EUR: 1,260.00 EUR remains.
Change the text before posting. An unreadable amount, missing transfer identity or conflicting
invoice direction holds collection. Correct source retains the original. Distinct equal
instalments need distinct supplied bank references; a changed email subject cannot credit the
same reference twice. A supplied reference is not external bank verification.

Human decisions are bounded: link a duplicate to its original receipt, or record the outcome of
an invoice-linked client dispute already resolved by a person. Neither action changes the debt.
Both invalidate the draft so its evidence and exact bytes must be reviewed again.

History exports readable evidence with redacted source excerpts, decisions, corrections, backend
and ledger revisions, model/mode labels and recovery limits. A hash identifies bytes, not truth,
bank settlement or compliance. Dashboard outcomes count this session's recorded actions.
Human active time, money recovered and time saved are unknown.

Two earlier comparisons remain withdrawn. The retained independent benchmark reported zero
Archon chases, earned by not acting. It is not a current success claim. Its evaluator omitted
exact invoice and nonempty recipient checks; fresh synthetic oracles now test those conditions.
No new benchmark result or held-out reuse is claimed. The injection finding was measured on one
of the withdrawn sets and does not establish a current advantage.

The public firm is invented. No bank or mailbox integration, OCR, payroll execution or real
delivery is available. Human UAT is NOT_RUN. An operator may configure separate Bedrock reasoning
with eu.anthropic.claude-opus-5 in eu-west-1; that is not the public scripted mode. SES requires
separate operator authorization and verified account/recipient eligibility; old SES sandbox
observations do not prove current delivery readiness.

[Frontend identity](https://d2ssmv59q16d0b.cloudfront.net/release.json) and
[backend identity](https://d2ssmv59q16d0b.cloudfront.net/api/health) report current deployments.
[CI evidence](https://github.com/upgradedev/archon-aws-strands/actions) is scoped to each exact SHA.
The public path uses CloudFront, private S3, API Gateway, Lambda, Python, React and TypeScript.
Strands is load-bearing for graph execution; removing it prevents draft preparation.

### Disclosure

Ten earlier Archon repositories exist and are named in the README. No code from any of them is
in this repository. Pre-existing package/CI patterns and visual design direction are disclosed
there and third-party licences are retained in docs/THIRD-PARTY.md. Eligibility is the organizer's
decision; this text makes no competitive-superiority or guaranteed eligibility claim.
