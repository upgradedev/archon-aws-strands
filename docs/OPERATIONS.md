# Development and controlled provider operations

For the joiner reviewing inbox records in the [AWS workstation](https://d2ssmv59q16d0b.cloudfront.net/),
controlled-live mode uses Bedrock and restricted SES; retained simulation uses a scripted
Strands model and simulated acceptance. Read [release.json](https://d2ssmv59q16d0b.cloudfront.net/release.json),
[/api/health](https://d2ssmv59q16d0b.cloudfront.net/api/health), and
[exact-pair acceptance](https://d2ssmv59q16d0b.cloudfront.net/acceptance.html).
[Evidence](EVALUATION.md) and [disclosures](../README.md#pre-existing-work-disclosed) apply to both modes.

## Reproduce the offline surfaces in CI

Use an isolated runner, Python 3.11+ and a checkout of this repository. The workspace's local
machine must not install dependencies, build the app or run tests. The following commands are
documentation for CI execution, not a claim that they ran during this edit.

The login-free AWS URL is the short path: **Explore populated demo → Load business portfolio**.
The optional five-source tutorial is **Load demo workspace**. Both load fictional data with
deterministic checks and no model or mail calls. The data choice does not change the provider
mode of an existing workspace; new workspaces use the currently configured providers.

Offline demonstration, with synthetic documents, scripted tone and simulated acceptance:

```bash
pip install -e ".[dev]"
python -m archon.demo
python -m uvicorn archon.web.app:app --port 8000
```

The server stays running until stopped. To generate the separate noninteractive static export,
stop the server or use another runner process, then run `python -m archon.web.export site`.

The server-rendered app and static export are legacy regression surfaces, separate from the React
workstation. The static export is not interactive. There is no tenancy in that legacy one-firm
ARCHON_STORE configuration; the public API instead isolates synthetic visitor sessions.

Operator-only reasoning:

```bash
python -m archon.demo --live-model
```

ARCHON_BEDROCK_MODEL_ID defaults to eu.anthropic.claude-opus-5;
ARCHON_BEDROCK_REGION to eu-west-1; ARCHON_BEDROCK_MAX_TOKENS to 1024.
The configured Bedrock factory supplies the graph's model, region and token budget.
Extraction has a separate 4000-token budget; it is not a reasoning measurement.
ARCHON_BUSINESS_EMAIL and ARCHON_BUSINESS_NAME identify whose books an operator reads.

Operator live sending is separately gated by --live-send, explicit
ARCHON_OPERATOR_SEND_AUTHORIZATION=I_AUTHORIZE_CONTROLLED_SEND, a durable ARCHON_SEND_LEDGER
and an exact ARCHON_VERIFIED_RECIPIENT. Account/recipient eligibility must be verified by the
operator; historical SES sandbox observations are not current delivery authorization.
Provider acceptance is not delivery; unknown outcomes never retry automatically.



## React workstation and public API

The React application is separate from `archon.web.app`. The existing frontend workflow uses
Node 22.12+ and the committed `frontend/package-lock.json`. On an isolated runner, start the API:

```bash
python -m uvicorn archon.web.api:app --host 127.0.0.1 --port 8000
```

In a second runner process, from `frontend/`:

```bash
npm ci
npm run dev
```

Vite proxies `/api` to `http://127.0.0.1:8000`; the dev command binds to loopback.
With live configuration absent, new sessions are synthetic. No AWS credentials are needed for
scripted intake/reasoning and simulated acceptance. These commands do not deploy the React bundle.
Use the URL printed by Vite; no port is silently assumed. Stop both runner processes afterward.

## Configuration boundaries

| Setting / component | Meaning |
|---|---|
| `ARCHON_SESSION_DB` | Local JSON-session SQLite path for the public API |
| `ARCHON_STATE_BUCKET`, `ARCHON_STATE_PREFIX` | Private S3 session storage for Lambda |
| `ARCHON_STORE` | Separate legacy one-firm store; no tenancy |
| `ARCHON_BUSINESS_EMAIL`, `ARCHON_BUSINESS_NAME` | Whose books the operator reader interprets |
| `ARCHON_BEDROCK_MODEL_ID` | Legacy model factory default `eu.anthropic.claude-opus-5` |
| `ARCHON_BEDROCK_REGION` | Legacy factory default `eu-west-1` |
| `ARCHON_BEDROCK_MAX_TOKENS` | Legacy reasoning default 1024; not the controlled worker's limit |
| Controlled worker model | `adapters.metered.model_for` supplies 2048 output tokens and non-streaming Strands |
| Controlled extraction | Separate 4000-token budget; source-field checks still apply |
| `ARCHON_LIVE_ENABLED`, worker ARN, sender and recipient | Explicit operator deployment configuration; not settable by visitors |

The runtime package declares `strands-agents>=1.53.0`; the resolved dependency version belongs
to the exact CI artifact. The controlled worker has its own model factory and does not silently
inherit every legacy environment override.

## Controlled runtime and budget

The 2026-09-14 snapshot is frontend `3e89590` / backend `2e2b375`; [Evaluation](EVALUATION.md)
records run `34822838436`, its three actual provider journeys and six separate portfolio journeys.
The public `acceptance.json` describes provider acceptance, not every test or incoming producer setup.
The deployment templates describe the runtime; rendering them is not activation or acceptance.

`deploy/live_provider_stack.py` defines the isolated worker and retained failure queue;
`deploy/live_api_stack.py` derives the opt-in API template from historical `infra/` source.
The API retains direct Bedrock/SES denies and may dispatch only its own worker.
`LiveEnabled` defaults to `false`. Activation additionally requires the verified sender and
recipient, an operator-created private `operating-grant` with finite budget/expiry and reviewed
price ceilings. An anonymous request cannot create, extend or reset this grant.

Reservations bound admitted provider usage under those ceilings, not the whole AWS account bill.
Infrastructure costs are separate. The session's twenty-job limit and pending-job exclusion still
apply. Creating another session does not create another global provider budget.
Unknown attempts consume reservations and do not trigger automatic resend or refund.

The twenty-job boundary counts submitted intake, reasoning and approval jobs, not individual
model calls. A Strands graph can make multiple calls within one job. The global operating grant
separately bounds all reservations, including mail; a displayed call allowance is not extra mail
authority or a reason to reset old reservations.

The controlled adapter uses the [Mantle token-count route](https://docs.aws.amazon.com/bedrock/latest/userguide/count-tokens.html)
with SigV4 in eu-west-1. This follows the retained native CountTokens rejection for
`anthropic.claude-opus-5`; it is not a fresh service-capability probe.
Unmapped content fails before inference; a count-only result is not model acceptance.
Do not substitute a characters-to-token estimate. The frozen evaluation collector is a different
instrument with different assumptions, documented in [Evaluation](EVALUATION.md).

The API and worker both require `real-email` consent for the exact fingerprinted draft.
A cached client offering only simulated approval is refused. The worker checks the configured
recipient and durable send reservation before SES. There is no authorization to send to arbitrary
invoice addresses and no guarantee of inbox arrival from a provider ID.

## Recovery and retained state

Refresh durable state after a timeout before deciding what happened. A queued or running job may
have consumed provider capacity even when a response is missing. Interrupted/unknown jobs require
operator reconciliation; never resend automatically to obtain a cleaner report.
Session access expires after seven days. Physical storage retention is separately configured.
S3 failures never silently fall back to temporary storage. New workspace creates a separate session
and does not delete old records.

## Deployment and verification

The public path is CloudFront → private S3 frontend plus API Gateway → Lambda API → separate worker.
[Architecture](ARCHITECTURE.md) maps source files and storage boundaries.
Backend/worker packaging and frontend publication are separate. Compare exact package source,
served frontend/backend identities and the acceptance receipt; matching prose or Git trees does
not replace the existing ancestry/provenance checks.

Main merges run source checks, frontend publication and browser acceptance under the configured
workflows. Browser jobs have no AWS credentials; publication uses a separate scoped publisher.
A failed acceptance makes the pipeline red and does not itself roll back a release.
Do not invoke paid acceptance merely to repair reporting for an already-spent run.

Current counts and coverage come from exact-SHA CI logs. Historical artifact retention is ninety
days with a SHA256 manifest; archival does not make an old result fresh.
The full-history secret scan uses `fetch-depth: 0` and `gitleaks git --log-opts=--all`
with redacted output. No new CI result is claimed by this documentation change.
