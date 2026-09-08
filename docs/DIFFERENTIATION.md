# What is new here, checked against the earlier Archons rather than asserted

The organisers published a clarification on 2026-09-08 that is stricter than a
casual reading of the rules:

> "Projects must be newly created during the Submission Period." Rebuilding an
> existing project's architecture, modifying features, and updating UI/UX while
> keeping core features unchanged **does not** constitute a new project.
>
> — Agents for Humans forum, topic 44877. The determination is the organisers',
> under Official Rules section 4.

So the question is not whether this repository is new. It is whether the **core
feature** is. Ten earlier Archon repositories exist. Two are close enough to be
worth checking properly, and both were checked by reading their code, not their
descriptions.

## The closest by domain: `archon-gcp-agentic`

"The month-end close for firms that back-office software never reaches ... then
writes the letters chasing what leaked."

That is this product's domain almost exactly. It is also the one that settles the
question, because of what it deliberately does not do:

```
tests/integration/test_close.py:168
def test_no_draft_is_ever_sent(documents):
    """The one human gate. If this goes red, the product changed shape."""
    assert {draft.status for draft in close(documents).drafts} == {"filed"}
```

and, in its own delivery adapter:

> "a letter to the broker is composed and filed unsent, **because sending it is
> irreversible and it goes to somebody else**."

**The GCP Archon composes chase letters and files them. It never sends one, by
design, and its own test says that if it ever did, the product would have changed
shape.** That is the change. Archon AWS sends.

## The closest by mechanism: `archon-qwen-autopilot`

"A human-gated accounts-payable agent ... nothing executes until a human approves
the exact arguments", and on approval an `SmtpEmailSink` submits the message. So a
prior Archon does gate a human approval and then send.

The difference is what the approval is attached to. Searching that repository for
`sha256`, `fingerprint`, `digest` returns **zero**; for `re-derive`, `stale`,
`expire`, `revalidate`, **zero**.

Its gate protects against **the model proposing something wrong**: the tool
catalogue contains only proposing verbs, so an injected instruction cannot execute.
That is a good defence and this project keeps the same property.

It does not protect against **a correct proposal that stopped being true.** Approve
a vendor reply there, and it is sent, whatever has happened in between.

## The new mechanism, in one sentence

**An approval that expires when the world changes, not only when the text changes.**

The draft is fingerprinted with SHA-256 over its exact rendered bytes; the approval
binds to that fingerprint; and at the moment of sending every fact in it is
re-derived from the ledger and compared. A client who pays at lunchtime invalidates
an approval given that morning, without anybody editing a word.

This is demonstrable in one click on the screen, and it is the thing neither
earlier Archon can be made to fail at, because neither re-derives.

| | earlier Archon | here |
|---|---|---|
| chase letters for a month-end close | `archon-gcp-agentic` composes and **files them unsent** | sent, once, to a third party |
| human approval before an outbound act | `archon-qwen-autopilot` approves the model's **arguments** | binds the **rendered bytes** and re-derives every fact at send |
| what invalidates an approval | the arguments changing | **the books moving**, a word changing, thirty minutes passing, the address not matching |
| what the buyer is | a broker's loads; a vendor to pay | a sole trader's own clients, who owe them |

## Where this is weak, said plainly

The direction of the money changes (payable to receivable) and so does the buyer,
but a reasonable organiser could still read "another Archon that reads invoices and
emails somebody" as a modified feature rather than a new one. **Eligibility is the
organisers' call under section 4 and nothing here overrides it.**

What can honestly be said is narrower and it is what the description says: the
governed outbound write, with an approval bound to bytes and facts re-derived at
send time, is not present in any earlier Archon, and the closest one refuses to
send at all as a matter of design.
