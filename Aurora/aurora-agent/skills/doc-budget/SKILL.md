---
name: doc-budget
description: Use whenever writing or reviewing any markdown a human will read — README, user guide, deploy steps, spec, plan, ledger, issue list, skill, or PR description. Use when a doc is growing to match the effort that went into the code, when a README starts restating logic, when explanation is creeping into a deploy guide, and when deciding whether a document belongs in the human-facing set or the agent-facing ledger.
origin: aurora
---

# Doc budget

Audience: anyone about to write or review a document in this repo. Job: keep documents sized by the interface they describe, not by the work that produced them.

**Docs scale with the interface, never with implementation effort.** A hard problem solved in one function gets one line. An easy problem exposing nine knobs gets nine rows.

There is no line cap here, and there will not be one. A cap gets gamed by compression; the tests below are about whether a sentence does work.

## The deletion test

Applied per sentence, to every document:

> Remove the sentence. Can the reader still act? If yes, it stays removed.

- Every doc opens with **one line naming its audience and its job**. Any sentence that does not serve that job is cut, however true it is.
- Explanations get one line — unless the explanation records a failure someone paid for. Those earn their length, because they are the reason the rule exists.
- The same rule as comments in code: comment the surprising, never the evident. When roughly half a document is prose about the other half, most of it is restatement.

## Long is allowed. Narrative is not.

Complex systems genuinely need long documents. The constraint is on **shape**, not size:

| Long in | Not long in |
|---|---|
| Tables | Narrative |
| Numbered imperatives | Background essays |
| Contracts, schemas, argv and exit-code tables | Restated code |
| Ground-truth transcripts | Recaps of the previous section |

A five-hundred-line table of knobs is fine. A fifty-line explanation of why the knobs exist is not.

## Route, don't restate

A README says **where** the logic lives and **how** to run the tests, then stops. Include a module table with real line counts — it tells a reader where the mass is.

**One aggregation point.** Operator knobs must not live as asides in a compose comment, a spec section, and three issue docs. One guide, tables over prose. A reader who has to assemble the truth from four files does not have documentation.

**A deploy guide is numbered imperatives.** `1. Do this. 2. Do this if X. <one line why>.` It is read under pressure with production down; a paragraph is a hazard there.

## Ledgers and guides never merge

| | Ledger | Guide |
|---|---|---|
| Audience | Agent, auditing or resuming | Human, skim-reading, no context |
| Budget | Unbounded | Bounded, tight |
| Purpose | Reconstruction | Action |
| Failure mode | Missing detail | Extra detail |

Keep ledgers thorough. Keep guides short. A merged document fails both audiences: too long to act on, too summarised to reconstruct from.

## The audience table

| Document | Audience & job | Budget | Home |
|---|---|---|---|
| Spec | Human deciding | Bounded | Tracker |
| Plan tickets | Agent dispatching | Bounded | Tracker |
| Implementation | Agent resuming | Unbounded | Ledger |
| Issues | Human and agent | One line each | Tracker |
| Testing | Agent auditing | Unbounded | Mutation record |
| User guide & deploy | Human with no context | Concise — **written first** | Repo |

## Write the human-facing set first

The user guide, the README, and the deploy steps are written **before** the audit trail, to their budget, and the audit trail grows around them.

Written last, the human-facing set becomes a summary of everything that happened — which is precisely the thing being avoided. This is the observed failure: a ~29,000-line change of which ~4,000 do the work, correct in every line, and unskimmable by anyone who did not write it. A system only an agent can safely modify is a failed system even when it works.

## Review checklist

1. Does line one name the audience and the job?
2. Run the deletion test on every sentence. What survived?
3. Is anything long here long in tables, or long in narrative?
4. Does this restate logic that lives in code, instead of routing to it?
5. Are operator knobs aggregated in one place, or scattered as asides?
6. Is this a ledger wearing a guide's name, or the reverse?
7. Was the human-facing set written first?

## Red flags

- A document whose length tracks how hard the work was.
- "For completeness…" — the sentence after it fails the deletion test.
- A README that explains what the code does.
- A deploy guide with paragraphs.
- The same knob documented in three files, each slightly different.
- A user guide assembled at the end from the implementation ledger.
- An explanation longer than one line that names no failure anyone actually hit.
