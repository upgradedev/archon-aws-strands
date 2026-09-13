# Incoming HTTP webhook: provisional contract

**NOT YET DEPLOYED.** This contract describes the source implementation under integration.
Backend ingress is not active until the reviewed main release and its matching acceptance evidence establish it.

For the joiner reviewing inbox records in the [AWS workstation](https://d2ssmv59q16d0b.cloudfront.net/),
controlled-live mode uses Bedrock and restricted SES; retained simulation uses a scripted
Strands model and simulated acceptance. Read [release.json](https://d2ssmv59q16d0b.cloudfront.net/release.json),
[/api/health](https://d2ssmv59q16d0b.cloudfront.net/api/health), and
[exact-pair acceptance](https://d2ssmv59q16d0b.cloudfront.net/acceptance.html).
[Evidence](EVALUATION.md) and [disclosures](../README.md#pre-existing-work-disclosed) apply to both modes.

## Purpose and limits

An external mail/export system can post a fictional English plain-text document into one Archon
session after its owner explicitly enables Incoming. The external system receives a separate
intake-only bearer token, never the workspace credential. This is not Gmail/Outlook login,
OAuth, IMAP, a hosted mailbox, a bank connector, or an automatic collection workflow.

The producer is configured and operated by the owner outside Archon. Enabling the connection
does not install a mail rule, subscribe to a mailbox, fetch old messages, or arrange forwarding.
Use only fictional document text within the public intake's supported format.
The [user guide](USER-GUIDE.md) documents ISO dates, decimal EUR values and source references.

## Interface prepared in source

The Incoming navigation page exposes setup and queued/completed/refused results. Connection
opt-in is available only in controlled-live mode. Its maximum lifetime is **24 hours**, further
bounded by the existing seven-day workspace expiry. It does not grant another seven days.

| Caller | Method and path | Request | Authority |
|---|---|---|---|
| Workspace owner | `GET /api/incoming/connection` | Existing workspace authentication | Read connection metadata |
| Workspace owner | `POST /api/incoming/connection` | `action`, `request_id`; `consent: "fictional-intake"` required on enable | Explicitly enable or disable the session's connection |
| External producer | `POST /api/incoming` | `Authorization: Bearer <ingestion-only token>`; JSON `event_id` and `body` | Submit document text for intake only |

Owner requests use the existing workspace credential (`X-Archon-Session`); it must not be copied
into the external producer's configuration or used as the bearer token.

`request_id` is 16–80 characters; `event_id` is 8–100 characters. Both accept ASCII letters,
digits, `_` and `-`. `body` is 1–32,000 characters, and the complete JSON request must also fit
the existing 40,000-byte boundary (HTTP 413 if exceeded). Unknown JSON fields are rejected.
Character and byte limits are separate; JSON encoding can make the full request larger.

Enable request body:

```json
{
  "action": "enable",
  "request_id": "enable-incoming-01",
  "consent": "fictional-intake"
}
```

Disable request body:

```json
{
  "action": "disable",
  "request_id": "disable-incoming-01"
}
```

External request example (illustrative only; not a deployed endpoint demonstration):

```http
POST /api/incoming
Authorization: Bearer <ingestion-only token>
Content-Type: application/json

{"event_id":"unique-event-id","body":"fictional raw document text"}
```

Use the actual fictional document source as `body`; the placeholder above is not a parsable
invoice. A successful external response is HTTP 202 with only `event_id`, `job_id` and `status`.
It contains no workspace contents or workspace capability and does not prove successful parsing.

Owner metadata contains `enabled`, `expires_at`, `path`, `scope` and `events`; each listed event
has `event_id`, `job_id`, `status` and `created_at`. `scope` is `fictional-intake-only`.
Only the response to an explicit, active enable action also reveals `token`. GET metadata,
workspace snapshots and event history do not return it. Store it in the external producer's
credential configuration and keep it out of persistent browser storage.

## Connection storage, rotation and revocation

Connection configuration has a separate derived record in the existing private `sessions/`
prefix, with `record_type: "incoming-capability-v1"` and its own conditional-write revision.
The API distinguishes this record from a workspace. Enabling/disabling the connection does not
edit the target workspace, posted source records, ledger, operating grant or global budget.
Intake itself still writes its event metadata into the saved job and workspace history.

A new enable/disable request rotates the secret and records the action durably. Disabling revokes
further intake. Retrying the most recent identical configuration request is idempotent and does
not rotate again; changing its content or replaying it after a newer configuration returns 409.
Refresh metadata before deciding on a new configuration request. The source caps a workspace
at 50 distinct configuration changes. Renewal neither extends workspace life nor creates a grant.

The stored record contains a nonce and secret digest; comparison uses a constant-time digest
check. The token is distinct from the target session handle and authorizes intake only.

## Deduplication, scheduling and recovery

| Result | Producer action |
|---|---|
| Same event ID and same body retried | Durable idempotent replay; retain the same event ID and exact body |
| Same event ID with a changed body | Rejected with HTTP 409; do not silently reuse the ID for different content |
| Session is busy | HTTP 409; wait, then retry the same event and body |
| Enqueue outcome is uncertain | HTTP 503; retry the same event and body, never create a replacement event ID to force work |
| Completed or refused intake | Review the recorded result in Incoming/Records; transport acceptance alone is not a successful ledger post |
| Worker failure or unknown outcome | Inspect durable state and request operator reconciliation; do not generate a new ID to repeat a possibly spent call |
| Invalid, revoked or expired token | HTTP 401; have the owner inspect connection state, not retry with a workspace credential |

Generate an event ID once per source event and retain it across transport retries. Exact-event
deduplication is separate from payment identity: submitting a new event ID cannot legitimize a
duplicate transfer reference. A refusal needs evidence-based correction, not an invented bank ID.

Accepted work uses the existing durable worker and **live Bedrock intake only**, with the existing
global provider budget, session job limits, expiry checks and source validation.
A new connection does not allocate another grant. It cannot bypass a pending job or fabricate
success when provider scheduling is uncertain.

## No outbound authority

The bearer token cannot read a workspace, prepare/approve a collection draft, or send email.
Intake never supplies human approval. After new evidence arrives, the owner must inspect it,
prepare a fresh draft through the ordinary Strands flow and explicitly approve the exact
fingerprinted text with real-email consent. The controlled recipient restriction still applies.

Keep the token out of source control, URLs, public logs and shared evidence bundles. A party
holding it can submit intake for its limited lifetime; treat it as a credential.
Disable the connection when the producer should stop, and inspect already accepted job outcomes.
This contract does not promise cancellation or reversal of a provider call already started.

## Verification boundary

Route models and bounds were read from `archon.web.api`; configuration, token issuance and
deduplication from `archon.web.incoming`; saved event metadata from `archon.web.live` in the
implementation checkout. That was a read-only source inspection, not a live observation or a
test run. Final UI labels, integrated source and negative-path checks still need exact-SHA CI
and release acceptance. Controlled provider calls, mailbox setup and production acceptance
were not performed as part of this documentation work.
