# Third-party components, and what each is used under

For the joiner reconciling inbox invoices: [live AWS workstation](https://d2ssmv59q16d0b.cloudfront.net/).
Try Records → invoice → payment → Workspace → Run Strands → exact review → History.
Public extraction is bounded, the model scripted and acceptance simulated; the real Strands graph
must finish all six reports before drafting. [Evidence and limits](../README.md#evidence-and-limits) ·
[Required disclosures](../README.md#pre-existing-work-disclosed).

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

All permissive, all compatible with this project's MIT licence, and none
requiring the source of a derived work to be released under their terms.

## Services

| service | terms it is used under |
|---|---|
| **Amazon Bedrock (operator-only live mode)** | the AWS Customer Agreement and the Bedrock service terms, on the entrant's own account. Model access for `eu.anthropic.claude-opus-5` depends on account and region; operators must check current eligibility before any call |
| **Amazon SES** | the same agreement. Past observations recorded SES sandbox restrictions. Current operator authorization and recipient eligibility must be checked separately; the public provider is simulated |
| **AWS hosting: CloudFront, private S3, API Gateway and Lambda** | the AWS Customer Agreement and applicable service terms; public synthetic frontend and session API |
| **GitHub Actions** | the GitHub Terms of Service, on the entrant's own account; CI, not the public frontend host |

The public runtime calls no paid model or mail API. AWS hosting incurs infrastructure costs;
operator Bedrock/SES calls may incur usage costs. No third-party dataset is redistributed.
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
- **a redaction boundary before the model**, including local PDF text extraction,
  because redaction cannot reach inside a file handed to a hosted model.

The SDK orchestrates agents. None of the above is orchestration, and all of it is
in this repository.
