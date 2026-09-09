# Third-party components, and what each is used under

The submission rules require an entrant to be authorised to use every third-party
integration in accordance with its terms, and they require an entry that uses
open source to build on it rather than wrap it. This is that list, read from the
installed packages rather than from memory:

```bash
python -m archon.evidence.licences
```

## Runtime

| package | version read | licence | what it does here |
|---|---|---|---|
| `strands-agents` | 1.53.0 | Apache-2.0 | the six-agent graph and the composer. The load-bearing dependency |
| `boto3` | 1.43.4 | Apache-2.0 | Bedrock and SES clients |
| `fastapi` | 0.115.6 | MIT | the screen |
| `uvicorn` | 0.32.1 | BSD-3-Clause | serves it |
| `python-multipart` | 0.0.31 | Apache-2.0 | the attachment upload |
| `pypdf` | 6.15.0 | BSD-3-Clause | extracts PDF text **on the host**, so redaction still applies |

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
| **Amazon Bedrock** | the AWS Customer Agreement and the Bedrock service terms, on the entrant's own account. Model access for `eu.anthropic.claude-opus-5` is granted per account and per region and is enabled on the account this was built against |
| **Amazon SES** | the same agreement. The account is in the SES sandbox, which permits sending only to verified addresses, and this project does not attempt to send anywhere else |
| **GitHub Actions and Pages** | the GitHub Terms of Service, on the entrant's own account |

No paid third-party API is called, no dataset is redistributed, and nothing here
is used under a licence that forbids commercial use or requires attribution
beyond what this file gives.

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
