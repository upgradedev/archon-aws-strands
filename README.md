# Archon

**Archon helps a joiner reconcile inbox invoices and approve an exact collection draft with the source evidence beside it.**

For a joiner doing client collections alone, an invoice and a remittance can tell different stories.
Archon brings those records together so the owner can see what remains owed, why collection is
ready or held, and exactly what a proposed email would say.

[Try the AWS demo](https://d2ssmv59q16d0b.cloudfront.net/) ·
[Evidence and limits](#evidence-and-limits) · [Docs](#documentation) ·
[Disclosures](#pre-existing-work-disclosed)

[![CI](https://github.com/upgradedev/archon-aws-strands/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/upgradedev/archon-aws-strands/actions/workflows/ci.yml)
[![licence](https://img.shields.io/badge/licence-MIT-blue)](LICENSE)

<a id="react-workstation-usage"></a>

## Try it

1. Open the demo without an account. Choose **Explore populated demo**, then **Load demo workspace**.
2. Open **Records** to inspect the five fictional source emails: two customer invoices, their
   payments, and one supplier invoice. Loading these records uses deterministic parsing and ledger
   checks. It creates no AI report, draft, email, or Bedrock call.
3. Follow **Try the example** for the invoice → payment → review → outcome walkthrough, or
   continue to the dashboard and review the partially paid invoice.
4. Check the session's mode before running Strands. In controlled-live mode, subsequent intake
   and reasoning use real Amazon Bedrock. Review the source evidence, recipient and exact draft.
5. Sending is a separate, explicit approval. Controlled-live approval sends only to the configured
   verified test recipient; simulation records only simulated acceptance. Reload History to see
   the retained outcome.

<a id="what-changes-the-decision"></a>

The sample invoice is **1,860.00 EUR**, its payment is **600.00 EUR**, and **1,260.00 EUR** remains.
Those figures come from supplied records; no bank has verified them. A duplicate transfer
reference cannot credit the same payment again. Missing or conflicting evidence holds collection.

**Demo data and execution mode are separate choices.** The examples are entirely invented in
both modes. A loaded sample workspace is ready to inspect, but it is not an AI result.

| Path | What actually happens | Email boundary |
|---|---|---|
| Load populated demo | Deterministic seed, no model call or draft | No email |
| Controlled-live session | Source-checked Bedrock intake; real Strands six-reader graph and composer | Exact human approval; SES restricted to a verified test recipient |
| Retained simulation | Real Strands graph; model is **scripted**, outbox is **simulated** | No real email; the script walks the graph, it does not judge |

Check [frontend identity](https://d2ssmv59q16d0b.cloudfront.net/release.json),
[backend identity and mode](https://d2ssmv59q16d0b.cloudfront.net/api/health), and
[release acceptance](https://d2ssmv59q16d0b.cloudfront.net/acceptance.html) together.
Health reports configuration; it does not prove a model call or delivery.

<a id="limitations"></a>

## What you can bring

Paste fictional English plain-text invoice or remittance email in Records, or preview a UTF-8
`.txt` or plain-text `.eml` file up to 32 KB before posting it. Controlled-live extraction
requires explicit ISO dates, two-decimal EUR amounts and source-backed references.
PDFs, images, OCR, HTML and multipart email are not supported by the public intake.

No mailbox is connected. There is no bank feed, payment execution, payroll provider, or ERP
integration. Nothing is submitted to any tax authority. Recorded transfer references and headers
are supplied evidence, not proof of authenticity. Real customer data is outside this demo's scope.

### Automated input: provisional, not yet deployed

A session-scoped HTTP webhook is being implemented for external mail/export systems.
The user explicitly enables it and supplies the external system with a separate intake-only
bearer token, never the workspace credential. Its lifetime is at most 24 hours and ends no later
than workspace expiry. It deduplicates exact event IDs durably and uses live Bedrock intake under
the existing budget and job limits.
It cannot approve a draft or send an email. This is not direct Gmail or Outlook login.
See the [provisional incoming-webhook contract](docs/incoming-webhook.md); backend ingress is
not active until deployment and acceptance establish it.

## Run it

The browser walkthrough above is the shortest reproducible path and needs no installation.
For a source demonstration, use Python 3.11+ in an isolated CI runner with this repository checked
out. These are the offline commands exercised by the existing CI workflow; dependency installation,
builds and tests for this workspace run in CI only.

```bash
pip install -e ".[dev]"
python -m archon.demo
python -m uvicorn archon.web.app:app --port 8000
```

The console demo and server at `http://localhost:8000` are legacy regression surfaces with
scripted tone and simulated acceptance. They are separate from the React workstation.
There is no tenancy in the legacy one-firm store. See [Operations](docs/OPERATIONS.md) for
React/API setup, configuration, static export and the separate operator live modes.

## How it is put together

<img src="docs/architecture.svg" alt="Archon architecture: six Strands readers feed a composer with no tools; ledger checks and exact human approval govern a separate controlled email worker." width="100%">

This is an architecture diagram, not a screenshot or deployment receipt. It also renders where
there is no Mermaid support. [Architecture and infrastructure](docs/ARCHITECTURE.md) explains
the deployed components and the separate optional AgentCore sketch.

Six Strands readers inspect suppliers, sales, payroll, trading, cash and metrics from the retained
ledger. Each reports before the composer can run; the composer holds no tools. Bedrock supplies
model interpretation and wording, while deterministic code selects the invoice and verifies
amounts. Removing Strands prevents draft preparation.

CloudFront serves React from private S3 and routes `/api/*` through API Gateway to Lambda.
The API saves jobs and dispatches a separate durable worker; its role cannot invoke Bedrock or
SES directly. Private S3 sessions use compare-and-swap writes to reject stale changes.
The worker reserves finite provider budget before calling Bedrock or the controlled SES outbox.
AgentCore and Aurora are not deployed.

An exact draft fingerprint binds human consent. New evidence, changed ledger revisions, holds
or expiry require fresh review. A hash is not proof that an invoice is true.
Session access expires after seven days; storage retention is separate. Refresh durable state
after an uncertain action. Never retry unknown sends automatically.

## Evidence and limits

The last supplied release record, checked on 2026-09-13, identifies frontend `40c7ade` and
backend/worker `2bb3db3`. [AWS run 34778777702](https://github.com/upgradedev/archon-aws-strands/actions/runs/34778777702)
recorded three actual browser cases, 45 model calls and three SES acceptances.
These are historical results for that pair, not proof that later source changes pass or are deployed.
Use exact-SHA CI and matching served identities for any newer revision.

The owner subsequently reported six received messages and provided a screenshot: **HUMAN-ATTESTED**
mailbox arrival. Their per-run Message-ID correlation and full approved-body comparison are unknown.
That does not replace the machine receipt's `delivery_proven=false`.
Human UAT stays NOT_RUN until a person completes the full
[UAT testbook](https://d2ssmv59q16d0b.cloudfront.net/UAT.testbook.html).

Both earlier comparisons are withdrawn. The retained evaluation reported zero Archon chases,
achieved by not acting; it establishes no useful accuracy. The historical injection transcript
establishes no current advantage. New synthetic regressions are not independent held-out evidence.
Human active time, time saved and recovered money remain Unknown.

[Evaluation and evidence](docs/EVALUATION.md) retains original result links, withdrawn comparisons,
frozen protocols, failure categories, and the boundary between product acceptance and model benefit.
This documentation revision has not been tested locally or accepted by CI.

<a id="contents"></a>
<a id="third-party-components"></a>
<a id="for-whoever-submits-this"></a>

## Documentation

| Need | Read |
|---|---|
| Source formats, duplicate holds, arrangements and recovery | [User guide](docs/USER-GUIDE.md) |
| Strands graph, storage and actual AWS infrastructure | [Architecture](docs/ARCHITECTURE.md) |
| CI quickstart, configuration and controlled provider operations | [Operations](docs/OPERATIONS.md) |
| Incoming automation and its deployment boundary | [Incoming webhook](docs/incoming-webhook.md) |
| Historical measurements and frozen evaluation instruments | [Evaluation and evidence](docs/EVALUATION.md) |
| What the workflow demonstrates and does not measure | [Workflow and limits](docs/DIFFERENTIATION.md) |
| Prior work and dependency notices | [Prior work](docs/PRIOR-WORK.md) · [Third-party components](docs/THIRD-PARTY.md) |
| Optional, unimplemented AgentCore design | [Historical design note](docs/BEDROCK_AGENTCORE_ARCHITECTURE.md) |
| Image disclosures | [Graphics: concept art only](docs/GRAPHICS.md) |
| Unsubmitted description and unrecorded script | [Description draft](docs/SUBMISSION-DESCRIPTION.md) · [Video script](docs/VIDEO-SCRIPT.md) |

## Pre-existing work, disclosed

Archon shares its name and domain with ten earlier Archon repositories. No code from any of them is in this repository.
The [full disclosure](docs/PRIOR-WORK.md) names each repository, the `lasttake-aws` package/CI
pattern and Kerdon's earlier visual influence. Prior work does not establish novelty or eligibility.
The four supplied JPGs are concept art, not product screenshots or current infrastructure.

## Licence

MIT. See [LICENSE](LICENSE) and [third-party notices](docs/THIRD-PARTY.md).
