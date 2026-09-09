# Bedrock AgentCore: a design note, not a description of what runs

> **Read this first.** **None of the AgentCore runtime described below is implemented.** This document
> is a sketch of what Archon would look like deployed on Bedrock AgentCore, kept because the rules note
> that AgentCore strengthens a Technical Implementation score and because the mapping is worth having
> written down before anyone attempts it. It is a plan. Nothing in the repository calls an AgentCore
> API, and `grep -ri agentcore src/` returns nothing.
>
> It also predates parts of the product it describes, and two of its claims were simply wrong when read
> today. Both are corrected below rather than left to be found by a judge:
>
> - it called Archon a **dispute resolution** engine. Archon chases an unpaid invoice; it does not
>   arbitrate disputes, and no dispute logic exists anywhere in the code.
> - it named **Claude 3.5 Sonnet**. The model is `eu.anthropic.claude-opus-5`, verified by a live
>   call, and `python -m archon.evidence.licences` prints what is actually installed.
>
> **What of it does exist today**, and where:
>
> | described here | in the repository | evidence |
> |---|---|---|
> | the pre-LLM redaction filter | **yes**, and it is the only place untrusted text meets a model | `archon.security.sanitizer`, `archon.adapters.inbound` |
> | the deterministic ledger with a balance invariant | **yes** | `archon.domain.ledger` |
> | human-in-the-loop before the one write | **yes**, and bound to exact bytes rather than to a threshold | `archon.agents.gate` |
> | session memory as an audit trail | **yes**, as documents replayed through the same validation | `archon.store.sqlite` |
> | AgentCore runtime, Action Groups, Guardrails as a service | **no** | nothing; the graph runs on the Strands SDK against `bedrock-runtime` |
> | API Gateway, Lambda, S3 audit seals, DynamoDB | **no** | nothing is deployed at all |
>
> The threshold in the mapping below, holding a draft when an amount exceeds €5,000, is **not** how the
> gate works and never was. The gate holds on facts that stopped being true, on an approval that does
> not match the bytes, and on an address that is not the one on the invoice. There is no amount at which
> it stops caring.

---

The rest of this document is the original sketch, kept as written apart from the corrections above, so that what was planned can be compared with what was built.

---

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
