# Archon film: source-backed books, human-approved email

**Production script, not a completed video.** The executable narration
and scene order live in [video/story.json](../video/story.json). This page explains the cut,
its evidence boundaries and how to reproduce it.

For a joiner inspecting Records in the [AWS app](https://d2ssmv59q16d0b.cloudfront.net/),
controlled-live uses real Bedrock and six Strands readers. Retained simulation uses a scripted
model and simulated acceptance, with no real email. [Evidence](EVALUATION.md) and
[disclosures](../README.md#pre-existing-work-disclosed) distinguish these modes.

## The story

Alex runs a small joinery. An invoice for 1,860.00 EUR has a recorded payment of 600.00 EUR.
Archon prepares a collection email for the remaining 1,260.00 EUR after checking the books.
A person approves the exact recipient and content before the controlled SES attempt.

The [official rules](https://agentsforhumans.devpost.com/rules), checked on 2026-09-14,
cap the video at **five minutes**. The planned cut is 290 seconds; this is a target, not a
measured final duration. The real app starts at approximately 28 seconds.

| Scene | Planned seconds | What is shown |
|---|---:|---|
| Introduction | 8 | Archon and its mechanism |
| Problem | 12 | Invoice, payment, remaining balance |
| Solution | 8 | Evidence, ledger checks, human approval |
| Enter the app | 15 | Actual public welcome and demo setup |
| Dashboard | 23 | 240 fictional records and populated financial widgets |
| Records | 23 | Sales, credits and supplier payments |
| One case | 23 | Separate five-source tutorial and linked payment |
| AWS infrastructure | 20 | CloudFront/S3, API Gateway, Lambda API/worker, S3 persistence, Bedrock and SES |
| Strands orchestration | 16 | Suppliers, sales, payroll, trading, cash and metrics readers; tool-less composer |
| Real model execution | 22 | Actual saved job and Bedrock usage |
| Draft and evidence | 23 | Actual generated wording and linked figures |
| Exact review | 22 | Disabled send, review binding and fingerprint |
| Controlled send | 20 | One explicitly approved SES attempt |
| Durable outcome | 20 | Receipt survives reload; acceptance is not delivery |
| Product tour | 15 | Optional explanatory navigation |
| Limits | 10 | Fictional data, controlled recipient, no bank feed |
| Closing | 10 | Product promise and Strands on AWS |

The seventeen beats form seven editorial chapters. These planned windows sum to the same
290-second target; the final gate measures the generated media, not this table.

### 1. Problem and promise — 28 seconds

Introduction, problem and solution.

### 2. The working books — 84 seconds

Enter the app, dashboard, records and the small case.

### 3. AWS and Strands — 36 seconds

Deployed infrastructure and the six-reader orchestration.

### 4. Actual execution — 22 seconds

Run the live graph and inspect model usage.

### 5. Draft and review — 45 seconds

Read the generated email and review its exact binding.

### 6. Consequence and recovery — 40 seconds

One controlled send and durable readback.

### 7. User guidance and closing — 35 seconds

Tour, explicit limits and closing.

## Recording identity

The recording freeze is frontend `2932fdc6fc90d2a3c965c31316c1c945c0b380c6` and
backend `2e2b3757f9d2bb8e95e2338fdc5ae40c6a35c3a4`.
Its accepted [AWS run](https://github.com/upgradedev/archon-aws-strands/actions/runs/34833237908)
is separate from the new video take. Before capture, the pipeline fetches the public app,
[release.json](https://d2ssmv59q16d0b.cloudfront.net/release.json) and
[/api/health](https://d2ssmv59q16d0b.cloudfront.net/api/health), and refuses a different pair.

No application, infrastructure or provider configuration is changed by producing the film.
New media commits are not represented as a new deployed runtime.

## Measured narration and honest footage

[The CI workflow](../.github/workflows/archon-film.yml) verifies deliberately broken media
before it can generate speech. Local installations, builds and rendering are not needed.

1. `video/media.py narrate` uses ElevenLabs with exact-content caching, character-aligned
   captions and a cumulative 12,000-character attempt ceiling against runaway regeneration.
   It requires text-to-speech access only, not account/subscription read permissions.
2. Each visual window is measured speech plus a tail, rounded to a 25 fps frame boundary,
   or the planned scene minimum if longer. There is no whole-film time stretch.
3. `video/render.py` animates the original introduction, problem and architecture slides.
4. `video/capture.py` drives the frozen live application, keeps actual browser pixels, and
   captures original project-media PNGs. It never substitutes mocked provider responses.
5. Only explicitly logged processing waits may be shortened, with an on-screen disclosure.
   The approved email and provider result are actual outputs from the recorded session.
6. The composer emits 1080p H.264/AAC video, selectable English captions, a separate SRT,
   measured timings and a hash-bound receipt. Audio/video drift beyond one frame fails.
   Sampled output pixels must match the corresponding source clips.

Reuse the narration and capture cache when editing. An incomplete provider take refuses
automatic replay and needs reconciliation; creating a new CI run is not authorization for
another send. An incomplete billed speech attempt also stops instead of being silently charged again.

If the API is unavailable, refresh durable state before any retry. There is no SES fallback shot.
Provider acceptance does not prove arrival. A hash identifies bytes, not truth. The earlier
comparisons are withdrawn; the retained evaluation had zero Archon chases, achieved by not
acting. Human UAT and independent benefit measurement remain NOT_RUN. None is claimed as a win.

## Claims and limits

- The 240-record portfolio is typed fictional data, **not** a 240-document AI extraction test.
- The smaller example is seeded before the live Strands graph runs. Do not narrate seed loading as AI.
- Strands and Bedrock produce reports and wording. Ledger code checks and inserts monetary claims.
- The film does not display private chain-of-thought. It shows observable execution and results.
- A recorded payment is source evidence, not verified bank settlement.
- Real email is limited to the verified test recipient and requires exact approval.
- SES acceptance and an identifier do not prove mailbox delivery. Sending does not collect money.
- No deployed Aurora, AgentCore, Gmail/Outlook connection, bank feed, OCR or payment execution is claimed.
- No measured time-saving, independent benchmark win, legal compliance or competitive rank is claimed.
- [Cover artwork](GRAPHICS.md) is editorial, not a screenshot or evidence of a connector.

## What must not be said

- Do not call the offline run agentic reasoning; its scripted model walks the graph.
- Do not claim a live mailbox, bank connection, OCR, AgentCore or Aurora deployment.
- Do not claim real email delivery from an SES identifier.
- Do not present a withdrawn or circular benchmark as current evidence.
- Do not claim compliance, competitive superiority, measured time savings or collected money.
- Do not narrate a scripted decision as a live model result or the seed as AI extraction.

The video must show the product actually working, explain the problem and solution, and name
**Strands Agents** and its load-bearing role. Design is demonstrated by the coherent user journey;
impact is the specific collection decision, not an invented economic result. Technical implementation
is supported by the real execution and architecture. Creativity is the separation of model wording,
source-grounded money and human authorization. Public hosting, final playback review and upload
remain separate completion gates.
