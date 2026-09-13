# Prior work and reuse disclosure

For the joiner reviewing inbox records in the [AWS workstation](https://d2ssmv59q16d0b.cloudfront.net/),
controlled-live mode uses Bedrock and restricted SES; retained simulation uses a scripted
Strands model and simulated acceptance. Read [release.json](https://d2ssmv59q16d0b.cloudfront.net/release.json),
[/api/health](https://d2ssmv59q16d0b.cloudfront.net/api/health), and
[exact-pair acceptance](https://d2ssmv59q16d0b.cloudfront.net/acceptance.html).
[Evidence and limits](../README.md#evidence-and-limits) and [disclosures](../README.md#pre-existing-work-disclosed) apply to both modes.

## Pre-existing work, disclosed

Archon is a product line and this build **shares a name and a domain** with earlier entries.
The submission rules require prior work to be disclosed. This build's public route uses pasted
fictional inbox evidence. Retained synthetic mode ends in simulated acceptance;
controlled mode can send an explicitly approved real email to the verified test recipient.
Prior-work disclosure
does not establish novelty or eligibility; that determination belongs to the organizers.

Prior Archon repositories, from other hackathons:

`archon-cockroach-memory` (AWS Bedrock) · `h0-archon` (AWS + Vercel) · `archon-gcp-agentic` · `archon-gcp` · `archon-vibecoding` · `archon_azure` · `archon_nebius` · `archon-qwen-autopilot` · `archon-qwen-memoryagent` · `archon-datahub`

No code from any of them is in this repository. The shapes of `pyproject.toml` and `.github/workflows/ci.yml` follow a sibling project, `lasttake-aws`; pattern followed, no lines copied.


Pre-existing visual work disclosure: Kerdon's navy/panel/indigo direction informed the earlier
interface work. No components, dependencies, customer data, tenant configuration, identifiers or
metric values were reused. This disclosure is retained; it is not a source for new requirements.


## Scope of this disclosure

The named repositories and pattern/visual influences are author disclosures retained from the
original README. This documentation refresh did not audit every historical repository.
The source disclosure is not a legal determination of novelty, ownership or eligibility.

The product code is MIT-licensed under [LICENSE](../LICENSE).
[Third-party components](THIRD-PARTY.md) records dependency notices and historical version observations.
[Graphics](GRAPHICS.md) separately identifies the four supplied concept images and their incorrect
current-product claims. None is a current screenshot or evidence of additional integrations.
