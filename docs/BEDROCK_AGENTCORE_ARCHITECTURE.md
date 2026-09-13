# Bedrock AgentCore: a design note, not a description of what runs

**None of the AgentCore runtime described below is implemented.** This is an optional historical
sketch, not deployment instructions or an API contract for the current product.
No AgentCore runtime, Action Groups, hosted Guardrails or Aurora DSQL is deployed.

For the joiner reviewing inbox records in the [AWS workstation](https://d2ssmv59q16d0b.cloudfront.net/),
controlled-live mode uses Bedrock and restricted SES; retained simulation uses a scripted
Strands model and simulated acceptance. Read [release.json](https://d2ssmv59q16d0b.cloudfront.net/release.json),
[/api/health](https://d2ssmv59q16d0b.cloudfront.net/api/health), and
[exact-pair acceptance](https://d2ssmv59q16d0b.cloudfront.net/acceptance.html).
[Evidence](EVALUATION.md) and [disclosures](../README.md#pre-existing-work-disclosed) apply to both modes.

## Corrections to the sketch

The original text remains below so the proposal can be distinguished from the implementation.
Its service names, API paths, thresholds and claims are not a specification of what Archon runs.

- it called Archon a **dispute resolution** engine. The public API records bounded human resolutions; it is not a dispute engine.
- it named **Claude 3.5 Sonnet**. The configured current model is `eu.anthropic.claude-opus-5`;
  controlled-live mode uses Bedrock, while retained simulation uses a scripted model.
  `python -m archon.evidence.licences` reports installed dependency versions, not model activation.
- It proposed an inbox, autonomous journal adjustments and cryptographic truth seals. The current
  public input is supplied fictional text and the write is an exact human-approved collection email.
  Hashes bind bytes; they do not verify commercial truth, compliance or bank settlement.
- The proposed Action Group YAML is unimplemented. Bedrock model invocation through Strands does
  not deploy AgentCore or automatically create the services in this sketch.

| described here | in the repository | evidence |
|---|---|---|
| pre-LLM redaction filter | **yes**, with limited field masking; not a guarantee of anonymity | `archon.security.sanitizer`, `archon.adapters.inbound`, `archon.agents.proposal` |
| deterministic ledger with a balance invariant | **yes** | `archon.domain.ledger` |
| human approval before collection email | **yes**, bound to exact draft bytes, not an amount threshold | `archon.agents.gate` |
| retained documents and decisions | **yes**, private conditional S3 sessions for the public API; SQLite for local/legacy surfaces | `archon.store.sessions`, `archon.store.sqlite` |
| AgentCore runtime, Action Groups, hosted Guardrails | **no** | Strands SDK + Bedrock model calls are the actual implementation |
| API Gateway, Lambda, private S3 sessions | **yes**, plus the separate controlled provider worker | `infra/`, `deploy/`, `archon.web.live` |
| S3 truth seals, DynamoDB, Aurora DSQL | **no** | Session hashes are not authenticity certificates |
| direct mailbox/bank integration | **no** | Incoming HTTP intake is separately provisional and not yet deployed |

The threshold in the mapping below, holding a draft only above €5,000, is **not** how the gate works and never was.
The gate checks facts, approval, exact text, recipient, revision and expiry. There is no amount at which
those requirements stop applying.

Source check: `rg -n -i agentcore src/` finds no AgentCore implementation in the supplied baseline.
[Current architecture](ARCHITECTURE.md) describes CloudFront/private S3, API Gateway, Lambda,
S3 compare-and-swap sessions, the durable worker, Bedrock and controlled SES.
[Incoming webhook](incoming-webhook.md) is a separate intake-only proposal, not evidence that the
original sketch's mailbox or Action Group topology exists.

## Historical proposal, retained for comparison

**HISTORICAL UNIMPLEMENTED SKETCH:** every architecture, OpenAPI path, compliance, zero-hallucination,
automation and cloud-topology claim below belongs to an unimplemented proposal. It must not be
copied into current product descriptions, infrastructure diagrams or acceptance evidence.

<details>
<summary>Original AgentCore sketch (not deployed; contains superseded assumptions)</summary>

## 1. Executive Summary

Archon is designed as an autonomous, audit-sealed back-office agent that lives in an inbox. It processes commercial dispute emails and invoices, enforces double-entry arithmetic invariants, and prepares cryptographically verified settlement responses.

By adhering to the Amazon Bedrock AgentCore paradigm, Archon decouples reasoning, deterministic tool execution, privacy guardrails, and persistent memory into first-class cloud-native primitives.

```
                  ┌─────────────────────────────────────────┐
                  │          Inbound Commercial Email       │
                  └────────────────────┬────────────────────┘
                                       │
                                       ▼
                  ┌─────────────────────────────────────────┐
                  │    Pre-LLM Privacy & Sanitizer Filter   │
                  │   (GDPR Art. 32 / IBAN & Tax Redaction) │
                  └────────────────────┬────────────────────┘
                                       │ Sanitized Text
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                       Amazon Bedrock AgentCore Runtime                      │
│                                                                             │
│   ┌───────────────────────┐                 ┌──────────────────────────┐   │
│   │   Claims Intake Agent │                 │   Settlement Draft Agent │   │
│   │ (Claude 3.5 Sonnet)   │                 │ (Claude 3.5 Sonnet)      │   │
│   └───────────┬───────────┘                 └─────────────▲────────────┘   │
│               │                                           │                 │
│               ▼                                           │                 │
│   ┌───────────────────────────────────────────────────────┴────────────┐   │
│   │                  Bedrock Action Group: Double-Entry Ledger         │   │
│   │   - post_entry()           - check_balance()                       │   │
│   │   - get_account_statement()- verify_audit_chain()                  │   │
│   └───────────────────────────────────┬────────────────────────────────┘   │
│                                       │                                     │
│                                       ▼                                     │
│   ┌────────────────────────────────────────────────────────────────────┐   │
│   │        Gatekeeper & Human-in-the-Loop (Bedrock Return-of-Control)  │   │
│   │   - Discrepancy > Threshold -> Escalate for Officer Approval       │   │
│   │   - Invariant Verified      -> Authorize Cryptographic Seal        │   │
│   └────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Bedrock AgentCore Primitive Mapping

| Archon Component | Bedrock AgentCore Equivalent | Implementation & Role |
| :--- | :--- | :--- |
| **`archon.agents.claims`** | **Supervisor / Claims Agent** | Ingests sanitized dispute content, extracts itemized dispute grounds, and constructs candidate journal adjustments. |
| **`archon.agents.draft`** | **Collaborating Agent** | Generates professionally formatted, legally bounded settlement responses based strictly on reconciled ledger state. |
| **`archon.agents.gate`** | **Bedrock Guardrails & Return-of-Control (ROC)** | Enforces human-in-the-loop (HIL) checkpoints whenever dispute amounts exceed enterprise risk thresholds ($> €5,000$) or arithmetic imbalances are detected. |
| **`archon.domain.ledger`** | **Bedrock Action Group** | Deterministic domain service exposed via OpenAPI schemas. Guarantees $\sum \text{Debits} - \sum \text{Credits} = 0$ with zero hallucination. |
| **`archon.security.sanitizer`** | **Pre-Processing Guardrail** | Local zero-trust filter redacting IBANs, payment cards, national tax IDs, and direct employee contact coordinates before LLM dispatch. |
| **`archon.domain.books`** | **Bedrock Agent Session Memory** | Stateful audit trail recording journal sequence numbers, transaction timestamps, and cryptographic state hashes. |

---

## 3. Bedrock Action Group Specification (OpenAPI Contract)

The double-entry ledger is exposed to the Bedrock AgentCore runtime as an Action Group with deterministic OpenAPI 3.0 schema definitions.

```yaml
openapi: 3.0.0
info:
  title: Archon Double-Entry Ledger Action Group
  version: 1.0.0
paths:
  /ledger/entries:
    post:
      summary: Post a verified balanced double-entry journal record
      operationId: postJournalEntry
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [reference, lines]
              properties:
                reference:
                  type: string
                  example: "DISPUTE-INV-2026-09"
                lines:
                  type: array
                  items:
                    type: object
                    required: [account_id, amount_cents, direction]
                    properties:
                      account_id:
                        type: string
                      amount_cents:
                        type: integer
                      direction:
                        type: string
                        enum: [DEBIT, CREDIT]
      responses:
        '200':
          description: Journal entry successfully committed and balanced
        '422':
          description: Unbalanced transaction rejected (Debits != Credits)
```

---

## 4. Privacy & Compliance Layer (GDPR Article 32)

Archon implements an in-process pre-LLM redaction pipeline prior to calling Bedrock endpoints:
1. **Banking Coordinates:** IBANs are masked down to country prefix and terminal 4 digits (`GR16*******************5678`), preventing exposure of vendor bank accounts to the foundation model.
2. **SWIFT / BIC:** Swift routing codes are replaced with `[REDACTED_BIC]`.
3. **Tax Identifiers:** European VAT and national tax IDs are replaced with `[REDACTED_TAX_ID]`.
4. **Preservation Invariant:** Monetary amounts, unit prices, currencies, dates, and disputable line items are preserved verbatim to guarantee exact mathematical reconciliation.

---

## 5. Deployment Topology on AWS

```
AWS Cloud
├── Amazon API Gateway (Inbound Webhooks / Email Receiver)
├── AWS Lambda (Pre-Processing Sanitizer & Graph Dispatcher)
├── Amazon Bedrock AgentCore
│   ├── Bedrock Agent (Claude 3.5 Sonnet Runtime)
│   ├── Bedrock Guardrails (Hallucination & Topic Filtering)
│   └── Bedrock Action Group (Lambda Fulfillment -> DynamoDB / Aurora DSQL)
└── Amazon S3 (Audit Seal Certificates & Cryptographic Receipts)
```

</details>
