# Archon

![Archon: source-backed books, a Strands review, and an email only after your exact approval. Editorial banner, not a product screenshot.](docs/banner.svg)

[![Backend CI](https://github.com/upgradedev/archon-aws-strands/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/upgradedev/archon-aws-strands/actions/workflows/ci.yml)
[![Frontend CI](https://github.com/upgradedev/archon-aws-strands/actions/workflows/frontend-ci.yml/badge.svg?branch=main)](https://github.com/upgradedev/archon-aws-strands/actions/workflows/frontend-ci.yml)
[![AWS release](https://github.com/upgradedev/archon-aws-strands/actions/workflows/frontend-deploy.yml/badge.svg?branch=main)](https://github.com/upgradedev/archon-aws-strands/actions/workflows/frontend-deploy.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-459A80)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](pyproject.toml)
[![React 19](https://img.shields.io/badge/React-19-149ECA?logo=react&logoColor=white)](frontend/package.json)
[![TypeScript 5.9](https://img.shields.io/badge/TypeScript-5.9-3178C6?logo=typescript&logoColor=white)](frontend/package.json)
[![Tailwind CSS 4.1](https://img.shields.io/badge/Tailwind%20CSS-4.1-0891B2?logo=tailwindcss&logoColor=white)](frontend/package.json)
[![Strands Agents SDK 1.53+](https://img.shields.io/badge/Strands%20Agents-SDK%201.53%2B-8B6DDB)](src/archon/agents/graph.py)
[![Amazon Bedrock](https://img.shields.io/badge/Amazon%20Bedrock-controlled%20live-5270A8)](docs/ARCHITECTURE.md)

**Archon helps an independent joiner check what is still owed before approving a collection email.**

For a joiner doing client collections alone, an invoice and a remittance can tell different stories.
Archon brings those records together so the owner can see what remains owed, why collection is
ready or held, and exactly what a proposed email would say.

[Open the live AWS app](https://d2ssmv59q16d0b.cloudfront.net/) ·
[Judge walkthrough](#judge-walkthrough) · [How Strands is used](#how-it-is-put-together) ·
[Built with](#built-with) · [Docs](#documentation)

Built for **AWS Agents for Humans · Professional Agents**.

> Fictional business data; real Amazon Bedrock and Strands Agents in controlled-live sessions.
> Email requires separate approval and goes only to the configured test recipient. No money moves.

<a id="react-workstation-usage"></a>
<a id="try-it"></a>

## Judge walkthrough

No account or installation is required. Start with the books, then choose whether to run the agent.

| Step | What to do | What you can verify |
|---|---|---|
| 1. Open real books | [Open the demo setup](https://d2ssmv59q16d0b.cloudfront.net/#/demo) → **Load business portfolio** | 240 fictional records: sales, purchases, both credit types, receipts and supplier payments. No AI or email operation on load. |
| 2. Follow the evidence | Dashboard → a financial widget → Records | Real retained documents, filters and linked sources, not a static mockup. Credits and cash are distinct. |
| 3. Ask the agent | Workspace → **Run Strands & prepare draft** | In a controlled-live session, actual Bedrock execution through the Strands graph, followed by a checked draft. This is a metered action, not part of loading the demo. |
| 4. Keep control | Inspect the recipient, balance and exact draft | Sending needs explicit consent and approval. Skip sending if you only want to inspect the application. |
| 5. Read the outcome | History → recorded attempt → reload | The durable outcome survives reload. SES acceptance is not independent proof of inbox delivery. |

Use **Take a tour** in the workspace header for six short explanations. Next/Previous only change
the guide; opening a page is optional. The tour never seeds books, runs AI, enables Incoming or
approves a message. **Guided check** is the separate invoice → payment → review → outcome workflow.

<a id="what-changes-the-decision"></a>

Prefer one small case? Choose the optional **Load demo workspace** tutorial: a **1,860.00 EUR**
invoice, **600.00 EUR** payment and **1,260.00 EUR** remaining. This is separate from the full
portfolio. A duplicate transfer cannot credit the payment again; conflicting evidence holds
collection. Supplied records are not bank-verified facts.

**Demo data and execution mode are separate choices.** The examples are entirely invented in
both modes. A loaded sample workspace is ready to inspect, but it is not an AI result.

| Path | What actually happens | Email boundary |
|---|---|---|
| Load populated demo | Deterministic seed, no model call or draft | No email |
| Controlled-live session | Source-checked Bedrock intake; real Strands six-reader graph and composer | Exact human approval; SES restricted to a verified test recipient |
| Retained simulation | Real Strands graph; model is **scripted**, outbox is **simulated** | No real email; the script walks the graph, it does not judge |

The full portfolio covers 16 clients and 10 suppliers. [Dataset, counts and limits](docs/BUSINESS-DEMO.md)
explain the fixtures; the seed is not an AI extraction benchmark over 240 documents.

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

### Automated input: opt-in extension

A session-scoped HTTP webhook accepts input from external mail/export systems.
The per-workspace key starts disabled; producer setup is required. The user explicitly enables
the connection and supplies the external system with a separate intake-only
bearer token, never the workspace credential. Its lifetime is at most 24 hours and ends no later
than workspace expiry. It deduplicates exact event IDs durably and uses live Bedrock intake under
the existing budget and job limits.
It cannot approve a draft or send an email. This is not direct Gmail or Outlook login.
See the [incoming-webhook contract](docs/incoming-webhook.md). Check served identities and
matching acceptance before using the extension; source availability alone does not establish activation.

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

[View architecture at full size](docs/architecture.svg).

These are architecture diagrams, not screenshots or deployment receipts. They also render where
there is no Mermaid support. [Architecture and infrastructure](docs/ARCHITECTURE.md) explains
the deployed components and the separate optional AgentCore sketch.

Six Strands readers inspect suppliers, sales, payroll, trading, cash and metrics from the retained
ledger. Each reports before the composer can run; the composer holds no tools. Bedrock supplies
model interpretation and wording, while deterministic code selects the invoice and verifies
amounts. Removing Strands prevents draft preparation.
The controlled model is `eu.anthropic.claude-opus-5` in `eu-west-1`; its configured identity
is not, by itself, invocation evidence.

<img src="docs/infrastructure.svg" alt="Archon AWS infrastructure: CloudFront serves React from private S3 and routes through API Gateway to Lambda; conditional S3 sessions and a separate worker govern Bedrock and controlled SES. The dashed incoming webhook is an opt-in source extension; verify served identity and acceptance before use." width="100%">

[View infrastructure at full size](docs/infrastructure.svg). The dashed extension requires opt-in and producer setup.

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

The [live release receipt](https://d2ssmv59q16d0b.cloudfront.net/acceptance.html) identifies the
exact tested frontend/backend pair, observed model calls and SES acceptances. The
[AWS deployment workflow](https://github.com/upgradedev/archon-aws-strands/actions/workflows/frontend-deploy.yml)
also retains separate real-AWS portfolio browser results. These execute the application, not slides.
Check the served identities against the receipt; a green source build alone does not prove deployment.

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
For this revision's validation, inspect exact-SHA CI and matching release acceptance.

## Built with

| Layer | Technology and role |
|---|---|
| Agent orchestration | **Strands Agents SDK**: `Agent`, scoped `@tool` readers and `GraphBuilder` fan-in to a tool-less composer. [Implementation](src/archon/agents/graph.py) |
| AI inference | **Amazon Bedrock**: source-checked interpretation and draft wording, not authority to send. [Execution modes](docs/ARCHITECTURE.md) |
| User application | **React 19, TypeScript, Tailwind CSS, Vite**: Dashboard, Records, Incoming, Guided check, Workspace and History. |
| AWS runtime | **CloudFront, private S3, API Gateway and Lambda**: frontend hosting, isolated durable sessions and a separate provider worker. |
| Controlled email | **Amazon SES** after exact human approval; no arbitrary-recipient sending. |
| Delivery and verification | **CloudFormation, GitHub Actions, pytest, Vitest and Playwright**. Tests, release and observed AWS acceptance are separate checks. |

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
| Richer books, six document types and dataset provenance | [Business portfolio](docs/BUSINESS-DEMO.md) |
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
