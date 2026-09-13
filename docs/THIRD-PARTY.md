# Third-party components, and what each is used under

For the joiner reviewing inbox records in the [AWS workstation](https://d2ssmv59q16d0b.cloudfront.net/),
controlled-live mode uses Bedrock and restricted SES; retained simulation uses a scripted
Strands model and simulated acceptance. Read [release.json](https://d2ssmv59q16d0b.cloudfront.net/release.json),
[/api/health](https://d2ssmv59q16d0b.cloudfront.net/api/health), and
[exact-pair acceptance](https://d2ssmv59q16d0b.cloudfront.net/acceptance.html).
[Evidence](EVALUATION.md) and [disclosures](../README.md#pre-existing-work-disclosed) apply to both modes.

The submission rules require an entrant to be authorised to use every third-party
integration in accordance with its terms, and they require an entry that uses
open source to build on it rather than wrap it. The Python versions below are historical observations, not a current lock or guarantee.
CI records installed versions; frontend exact versions remain in frontend/package-lock.json:

```bash
python -m archon.evidence.licences
```

## Runtime

Current served identities: [frontend SHA](https://d2ssmv59q16d0b.cloudfront.net/release.json),
[backend SHA and modes](https://d2ssmv59q16d0b.cloudfront.net/api/health).
These live records, not the historical version table, identify the deployment.

| package | version read | licence | what it does here |
|---|---|---|---|
| `strands-agents` | 1.53.0 | Apache-2.0 | the six-agent graph and the composer. The load-bearing dependency |
| `boto3` | 1.43.4 | Apache-2.0 | Bedrock and SES clients |
| `fastapi` | 0.115.6 | MIT | public JSON API and the legacy server-rendered screen |
| `uvicorn` | 0.32.1 | BSD-3-Clause | serves it |
| `python-multipart` | 0.0.31 | Apache-2.0 | legacy operator attachment upload; not the public text intake |
| `pypdf` | 6.15.0 | BSD-3-Clause | legacy operator PDF text extraction before redaction; not public OCR |

## Development only, not shipped

| package | version read | licence |
|---|---|---|
| `pytest` | 9.0.2 | MIT |
| `pytest-cov` | 7.1.0 | MIT |
| `ruff` | 0.16.0 | MIT |
| `markdown-it-py` | 4.0.0 (CI pin) | MIT |

`markdown-it-py==4.0.0` parses and renders CommonMark with tables for the CI documentation review
in `tools/docs_review.py`. It is a development dependency, not a product runtime or frontend dependency.

All permissive, all compatible with this project's MIT licence, and none
requiring the source of a derived work to be released under their terms.

## Services

| service | terms it is used under |
|---|---|
| **Amazon Bedrock (controlled-live worker and separate operator mode)** | the AWS Customer Agreement and the Bedrock service terms, on the entrant's own account. Model access for `eu.anthropic.claude-opus-5` depends on account and region; operators must check current eligibility before any call |
| **Amazon SES** | the same agreement. Past observations recorded SES sandbox restrictions. Controlled-live sends are restricted to the configured verified test recipient after exact human consent; retained simulation uses no mail provider |
| **AWS hosting: CloudFront, private S3, API Gateway and Lambda** | the AWS Customer Agreement and applicable service terms; public React frontend, session API and separate controlled provider worker |
| **GitHub Actions** | the GitHub Terms of Service, on the entrant's own account; CI, not the public frontend host |

Controlled-live calls use paid Bedrock/SES under a finite operating grant; AWS hosting costs are
separate. Loading the deterministic demo seed and retained scripted/simulated mode make no paid
model or mail calls. Account-wide cost is not established by the grant's reservations.
No third-party dataset is redistributed.
Existing licence notices remain authoritative; preserve transitive dependency notices when distributing.

## Frontend dependencies

React and React DOM are MIT-licensed runtime dependencies. TypeScript is Apache-2.0;
Playwright is Apache-2.0; Vite, Vitest and Tailwind CSS are MIT-licensed development tools.
Exact versions and transitive packages are retained in frontend/package-lock.json. These additions
do not replace any Python licence disclosure above.

## What this adds to the open source it builds on

The rules ask an entrant using open source to create something that **enhances
and builds upon** it rather than wrapping it. What Archon adds to the Strands
Agents SDK, none of which the SDK provides:

- **an edge condition that makes six readers a requirement rather than a
  suggestion.** The Python graph fires a node under OR semantics, so six edges
  into a composer let it start on one report. Archon conditions every edge on all
  six having reported, and fails closed on an unrecognised state shape.
- **a composer that holds no tools at all**, so its whole view arrives along
  those edges and cannot be short-circuited by a lookup.
- **a claim layer between the model and the reader.** No figure reaches a client
  except through a claim the ledger confirmed, and the agent's own free text is
  refused if it contains a digit.
- **a release gate in plain code**, binding a human approval to a SHA-256 of the
  exact bytes and re-deriving every fact at send time.
- **a redaction boundary before the model**, with PDF text extraction only in the legacy operator reader. The public
  intake is plain text; this does not claim public OCR or perfect removal of sensitive content.

The SDK orchestrates agents. The earlier phrase “None of the above is orchestration” was too
broad: the edge condition is graph orchestration. The ledger, source checks and exact release
boundary are application controls beyond the SDK. They are implemented in this repository.


## Additional disclosures

[Prior work](PRIOR-WORK.md) retains the earlier product names and pattern/visual influences.
[Graphics](GRAPHICS.md) labels supplied JPGs as concept art, not deployed capabilities.
The opt-in [incoming webhook](incoming-webhook.md) in this source revision adds no direct mailbox
service integration. Its per-workspace key starts disabled and producer setup is required;
check served identities and matching acceptance before use. This table does not authorize new
accounts, providers or paid calls.
