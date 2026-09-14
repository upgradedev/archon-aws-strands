# Evaluation and evidence boundaries

For the joiner reviewing inbox records in the [AWS workstation](https://d2ssmv59q16d0b.cloudfront.net/),
controlled-live mode uses Bedrock and restricted SES; retained simulation uses a scripted
Strands model and simulated acceptance. Read [release.json](https://d2ssmv59q16d0b.cloudfront.net/release.json),
[/api/health](https://d2ssmv59q16d0b.cloudfront.net/api/health), and
[exact-pair acceptance](https://d2ssmv59q16d0b.cloudfront.net/acceptance.html).
[Evidence](EVALUATION.md) and [disclosures](../README.md#pre-existing-work-disclosed) apply to both modes.

## Recorded product acceptance, not a new result

[PRIMARY, read-only check 2026-09-14] The public identity and acceptance endpoints returned HTTP 200
and agreed on frontend `3e89590053fb278847652ed6dec1f97966d99447` and backend/worker
`2e2b3757f9d2bb8e95e2338fdc5ae40c6a35c3a4`. The configured mode was `controlled-live`.
[AWS run 34822838436, attempt 1](https://github.com/upgradedev/archon-aws-strands/actions/runs/34822838436/attempts/1)
completed successfully. Its [retained provider receipt](https://d2ssmv59q16d0b.cloudfront.net/acceptance/runs/34822838436-1.json)
records the observations below; reading that receipt is not a new invocation.

| Check | Recorded result | Boundary |
|---|---|---|
| Actual provider journeys | 3/3 passed: desktop, mobile Chromium and WebKit | Real CloudFront/API/worker path, exact consent, reload and replay |
| Bedrock usage in those journeys | 45 model calls; 36,533 input and 5,686 output tokens | Observed provider usage for this run, not an accuracy score or billing statement |
| SES outcome | 3 provider acceptances; `delivery_proven=false` | No new mailbox arrival established |
| Separate AWS portfolio journeys | 6/6 passed | Typed 240-record portfolio, linked views and retained books; no model or mail operations |
| Source CI in the same run | 1,111 Python tests, 90.44% Python coverage; 75 HTTP browser cases, 5 CI provider-double cases, 32 renderer cases | Source checks and doubles are separate from actual provider evidence |
| Human UAT and independent benefit | `NOT_RUN` | No measured time saving, money recovered or comparative superiority |

The read used `Invoke-WebRequest -UseBasicParsing -Uri <url>` against the three public JSON links
below and the retained provider receipt. `curl -fsS <url>` is an equivalent read-only retrieval.
The separate portfolio count and source CI summaries come from
`gh run view 34822838436 --repo upgradedev/archon-aws-strands --log`.
The portfolio job is **not** included in the provider receipt's three-case total. Neither suite
is an independent evaluation over 240 AI-extracted documents. New source changes require their
own exact-SHA CI and matching release acceptance.

### Earlier accepted releases (historical)

The earlier release record was observed on 2026-09-13 and is retained here as history.
It names frontend `40c7ade4877dd2d14569a726a2865da66eb93eb1` and backend/worker `2bb3db3`.
[AWS run 34778777702](https://github.com/upgradedev/archon-aws-strands/actions/runs/34778777702)
recorded three actual CloudFront/API browser journeys (desktop, mobile Chromium and WebKit),
45 model calls, 36,719 input tokens, 5,641 output tokens and three SES acceptances.
The cases exercised exact consent, reload/replay and source-preserving demo switching.
These figures are supplied pipeline evidence, not measurements rerun while editing these docs.

The source-check record for that release is
[PR run 34778228746](https://github.com/upgradedev/archon-aws-strands/actions/runs/34778228746)
and [push run 34778227400](https://github.com/upgradedev/archon-aws-strands/actions/runs/34778227400):
896 Python tests, 155 frontend unit tests, 69 HTTP browser cases, three CI provider-double cases
and 30 acceptance-renderer cases. Provider doubles are not actual AWS calls.
Inspect with `gh run view <run-id> --repo upgradedev/archon-aws-strands --log`.
Those runs cover the named historical revision. Any later revision needs its own exact-SHA CI
and matching release acceptance. The 2026-09-13 frontend `40c7ade` / backend `2bb3db3` pair predates
the opt-in incoming extension and provides no acceptance evidence for that extension.

| Evidence level | What it supports | What it does not support |
|---|---|---|
| Repository | Implemented guards and declared contracts | Deployment, live success or general model accuracy |
| Exact-SHA source CI | That revision's checks with their stated doubles and fixtures | Current AWS identity or human benefit |
| Recorded actual AWS run | The named frontend/backend pair's bounded model and SES journey | New source changes, unrestricted sending or bank verification |
| Owner mailbox screenshot | HUMAN-ATTESTED arrival of six messages | Per-run correlation, full header/body comparison, or a completed UAT |
| Independent benefit evaluation | NOT_RUN for current product | No time-saving, recovery or superiority claim |

On 2026-09-14 the owner reported six received Archon controlled-test messages and supplied a
screenshot. Its retained private SHA256 is
`79786e766851cbccd82fb42ba056c8bd08d06db3dbe3fbe966a43471f0995feb`
(recorded with `Get-FileHash`). This is HUMAN-ATTESTED mailbox arrival, not automated delivery
telemetry. Exact timestamps, full addresses/headers, Message-ID correlation to individual runs,
and a full approved-body comparison remain unknown. Six visible messages do not establish which
run produced which message, nor prove or disprove duplicates. The private image is not published here.

The current machine receipt's `delivery_proven=false` remains unchanged. Human UAT remains NOT_RUN;
mailbox confirmation alone does not execute the [full testbook](https://d2ssmv59q16d0b.cloudfront.net/UAT.testbook.html).
The existing failed provider runs, recovered reporting and historical synthetic receipts remain
separate records. A report repair is not a new model call, send or successful original run.

## Reading current evidence

Read the served frontend SHA from [release.json](https://d2ssmv59q16d0b.cloudfront.net/release.json),
backend SHA and configured modes from [/api/health](https://d2ssmv59q16d0b.cloudfront.net/api/health),
then compare both against the run-scoped acceptance receipt.
[Current aggregate JSON](https://d2ssmv59q16d0b.cloudfront.net/acceptance.json) may change after
publication; the dated run above does not. An unavailable, mismatched or historical receipt
is not current acceptance. A branch CI pass is not evidence that this SHA is deployed.

Incoming has a separate actual intake check:
[run 34788618140](https://github.com/upgradedev/archon-aws-strands/actions/runs/34788618140)
passed one intake/replay/revocation journey against the earlier `4c67363` / `bad8453` release.
That is historical extension evidence, not a rerun against `3e89590` / `2e2b375` and not part of
the three-case provider receipt. See the [webhook verification boundary](incoming-webhook.md#verification-boundary).

## Frozen evaluation instruments

AR3 is source-prepared, not a real-model result. Its [frozen development protocol](../evaluation/ar3_data/protocol.json)
separates twelve synthetic inputs from gold labels and compares the existing rule reader with future
exact-request offline replay using the same redaction and document guards. The evaluation-only citation
contract checks source/revision and literal spans; it is not shipped ingestion functionality or semantic
entailment. Source CI runs `python -m evaluation.ar3 --candidate-sha "$CANDIDATE_SHA" --output ar3-output`
with blocked network/cloud clients, negative fixtures and retained failures. The [prior receipt inventory](../evaluation/ar3_data/prior-inventory.json)
found no comparable full request/response pairs: historical text and scripted runs are not new AI evidence.
Exclusive, fsynced journals preallocate every slot, checkpoint requests before adapters and raw responses
before parsing. Interrupted runs retain completed/started/unrun slots without a successful final summary;
an in-flight response lost before its checkpoint remains unknown. Only `end_turn`/`stop_sequence` are
accepted final response reasons. Original replay bytes are retained before parsing; runs are never pooled.
Author-created development cases, not independent accuracy; arithmetic is deterministic, not AI reasoning.
Evaluation model/infra costs remain unknown. AR3/C1, human benefit and any paid evaluation
activation remain owner-gated. This does not negate the separately recorded controlled-live product run.

### Bounded collector: separate from the product graph

The [bounded collector](../evaluation/ar3_collect.py) is evaluation-only direct Bedrock Converse, **not
the Strands graph**. Source CI exports exact frozen requests/sizes and exercises the full collector
with fake responses before replaying the unchanged evaluator; fake artifacts are labelled offline.
No model ran merely because these checks passed. The frozen 12 cases, prompt, model and `maxTokens=4000`
are unchanged. No CountTokens, tools, media, explicit cache creation, thinking override, fallback or
repair loop is added. Provider-default adaptive thinking may yield reasoning blocks rejected by the
frozen response contract; preserve that outcome, do not strip blocks or retune the protocol.

The new product source is no longer compatible with the frozen collector's whole-source pin.
Current source CI must report `SOURCE_CHANGED_COLLECTION_DENIED`, not export an activation plan.
It tests this refusal and retains a separate positive prepare-only check at compatible snapshot
`d8194c0413d5414e3acf071f55efe2d820565af7`, with its own imports. No old pin, request or model is
changed. A current-product model evaluation needs a separately preregistered instrument and grant.

Reservations use `2 * canonical_serialized_request_UTF8_bytes + 4096` input tokens per request:
the byte term deliberately overcounts visible text/JSON, with an additional multiplier and fixed
template allowance. This is a **conditional conservative assumption**, not a tokenizer measurement
or universal bound. The authorized evaluation operator must verify it for this model, default thinking, implicit caching and
standard-tier billing before granting any call. Input bounds above 20000, output other than 4000,
more than 12 calls, expired/wrong grants and insufficient whole-cohort reservations fail closed.
Botocore `total_max_attempts=1`, a 900-second collector boundary and 5/60-second connect/read timeouts
bound execution. The time boundary is checked between calls, not a hard interruption of an in-flight
SDK call; the workflow has a 20-minute outer limit including install/upload. Unknown outcomes consume
their full reservation. Observed ceiling/cache-write/retry violations halt subsequent calls, not undo
an already-started call. Full SDK envelopes/usage/request IDs are retained before inspection (not
original HTTP wire bytes), with opaque SDK binary values represented by typed base64 objects and
flushed chunked stdout backup; log delivery itself is not guaranteed.

Future evaluation activation is operator-only in the existing manual `ci.yml`, never push/PR. The authorized evaluation operator configures
the protected `ar3-bounded-evaluation` environment with `AR3_EVAL_ROLE_ARN` (an existing eligible role)
and `AR3_GRANT_SHA256` (SHA256 of the **exact UTF-8 JSON input bytes**). No IAM resources or settings are
created here. The inline session policy permits only this model's EU inference profile/foundation
model `bedrock:InvokeModel`; permission/trust compatibility remains untested until evaluation activation.
The grant binds `schema=archon-bounded-converse-v1`, `candidate_sha`, `instrument_sha`,
`protocol_sha256`, exported `plan_sha256`, `model_id`, `region`, `max_calls=12`, `max_output_tokens=4000`,
`max_input_tokens<=20000`, `max_seconds=900`, `input_bound_method` from the export,
`input_bound_verified=true`, `billing_assumptions_verified=true`, `service_tier=standard_default`,
`thinking_policy=FROZEN_PROVIDER_DEFAULT_NO_OVERRIDE`, exact `repository`, `actor`, `workflow_ref`,
next manual `run_number` (string), `run_attempt="1"`, and `expires_utc` within one hour. It also requires
`grant_id`, `parent_budget_ledger_ref`, `price_evidence`, `input_bound_evidence`, `budget_usd`,
`input_usd_per_million` and `output_usd_per_million` as positive finite decimal strings for money/rates.
The reference 5.50/27.50-per-million export estimate is **not** that grant, a bill or a shared budget.
The authorized evaluation operator reserves the whole app slice in the separate aggregate ledger before configuration;
this collector cannot coordinate or infer another app's spend. A new run number or any rerun needs
new authority; rerun attempts above 1 are refused. Concurrent source runs can advance the workflow
counter, which causes safe denial, not automatic grant repair. After approval and green exact-source CI,
the activation command format is `gh workflow run ci.yml --repo upgradedev/archon-aws-strands --ref
<reviewed-branch> --field ar3_grant_json='<exact-approved-JSON>'`. **Do not run this as a source check.**

### X1 browser timing and optional correlation

The opt-in `x1_benchmark` input on [frontend verification](https://github.com/upgradedev/archon-aws-strands/actions/workflows/frontend-ci.yml)
runs the [frozen X1 protocol](../frontend/benchmarks/x1-protocol.json): ten new-payment and ten
forwarded-duplicate journeys, no retries, a 15-minute invocation limit, raw outcomes and nearest-rank
p50/p95 with failures retained in the denominator. Run-specific artifacts include source/served-build
identities, timing boundaries and checksums. Finalized byte snapshots are separate from child-writable
journals; `kill_requested` is not `exit_confirmed`. Corrected-instrument runs remain separate, never pooled.
This measures CI browser orchestration with a scripted
model, not AWS/model latency or human time saved. Paid model calls/cost are zero only for verified
scripted runs; AWS infrastructure and runner dollar costs remain unknown. It never deploys or sends mail.

The separate [X1 correlation component](../telemetry/lambda_entry.py) is **source-only, not deployed**.
It wraps the unchanged Lambda handler with additive response headers and one bounded metadata log;
no event body, path/query, caller identity, session, authorization or exception text is logged by it.
Only runtime `context.aws_request_id` supplies `x-archon-lambda-request-id`; caller request IDs never
become trusted telemetry. Source commit and function-version headers support mismatch detection.
Context is invocation-local and reset on failure. Missing context/logs remain unknown, not inferred.
The [offline exporter](../telemetry/correlate.py) requires a unique API response/structured receipt/text
REPORT join with matching source, function ARN/version and log group/stream. Duplicate, missing or
mismatched rows stay in the denominator. Duration/billed duration retain explicit ms units;
infrastructure/model dollars stay null, never calculated from duration alone.

Future operator input is a JSON object with `expected_runtime` (source_sha, function_arn,
function_version, log_group), `requests` (consecutive ordinal, status, response_headers pairs from
`capture_response`, which retains only the three correlation response headers), and `events`
(logGroupName, logStreamName, message from an independently retained CloudWatch export).
After explicit collection authorization, `python -m telemetry.correlate --input <export.json>
--output <new-directory>` retains exact input bytes before parsing, then checksummed result files;
exit2 means incomplete correlation, not zero usage. Limits:1000 API rows,10000 events,10MiB input.
CI runs synthetic full-flow/negative controls without AWS/network. No new live runner or activation
is wired. A future release must explicitly package `telemetry/` beside `archon/`, review/select
`telemetry.lambda_entry.handler`, capture response headers and verify exact runtime identity/logs.
This telemetry-only component does not alter infra, the frozen AR3 evaluator/collector/protocol
or X1 benchmark. Its source pins remain unchanged by the public product reader documented in the
[user guide](USER-GUIDE.md).
The component adds no IAM, environment or deployment changes.
Log delivery can fail; only text REPORT format is supported. Supplied exports/configured SHA labels
are not cryptographic origin or deployment attestations. This is not full-service cost, model latency
or user time saved. Runtime fields and REPORT units follow the
[AWS context](https://docs.aws.amazon.com/lambda/latest/dg/python-context.html) and
[logging references](https://docs.aws.amazon.com/lambda/latest/dg/python-logging.html).

## Withdrawn comparisons and retained results

Both earlier comparisons are withdrawn and stay withdrawn. They scored Archon from books that
fixtures had already posted correctly: a ledger agreeing with itself. Their historical files and
transcripts remain retained; they are not current product performance claims.

The retained [2026-09-09 evaluation](../evidence/RESULTS-FAIR-2026-09-09.md) reported zero Archon chases.
That zero was achieved by not acting. It is not evidence of accuracy or usefulness.
The prior evaluator did not enforce exact target invoice and nonempty correct recipient.
Fresh synthetic contract tests in the supplied baseline cover those fields and amount separately. No new benchmark
score, held-out reuse, competitive superiority or live model measurement is claimed.
The current classifier rejects a wrong invoice as `wrong-invoice`, and an empty recipient as
`wrong-recipient` when earlier checks pass. Multiple simultaneous faults still fail: the retained
taxonomy reports the first category, not every category. Relabeling a refusal is not a product fix.
python -m archon.evidence.fair is an evaluator command, not evidence of current performance.

Historical material: [first withdrawn set](../evidence/RESULTS-2026-09-04.md),
[withdrawn hard set](../evidence/RESULTS-HARD-2026-09-08.md),
[correction](../evidence/RESULTS-CORRECTED-2026-09-08.md). The injection transcript belongs to a
withdrawn set; it has not been re-run on independent post and establishes no current advantage.

## Historical CI and artifact retention

[Prior AWS acceptance](https://github.com/upgradedev/archon-aws-strands/actions/runs/34357703424)
is bound to 519a1e7c11a995529113161344192240fd031459 and artifact 10106786411, not this branch.
Current counts and coverage come from exact-SHA CI logs and artifacts, never a static estimate badge.
CI asserts the Strands API surface, runs unit/functional tests and real-HTTP desktop/mobile
Playwright, and checks documentation claims. Frontend coverage floors remain 85% in every measure.

Main merges still run offline checks → AWS frontend release → live Playwright acceptance, with
exact frontend SHA preflight/postflight. Backend deployment remains separate. Failure makes
the pipeline red and does not imply rollback. Human UAT stays NOT_RUN until a person executes it.
Future artifacts retain ninety days. Package AWS API has a manual archive-only option for the fixed
prior accepted artifact; it retains original bytes and SHA256 manifest for ninety days without
extracting or executing them. It does not erase or refresh the original artifact.

The full-history secret scan fetches all history (fetch-depth: 0) and uses gitleaks git
--log-opts=--all with redacted output. Its result is bound to the CI revision and retained artifact.
