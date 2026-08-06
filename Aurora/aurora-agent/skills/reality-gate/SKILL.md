---
name: reality-gate
description: Use before any claim about an external system enters a spec, plan, brief, or report — library versions, API shapes, service behaviour, host state, config defaults, file layouts. Use when writing a Ground Truth block, when you are about to say "the library takes a callback" or "the endpoint returns JSON", when a plan repeats a fact from an earlier agent's ledger, and whenever you must decide between marking something UNVERIFIED and going to measure it.
origin: aurora
---

# Reality gate

Audience: anyone writing a spec, plan, task brief, or design note. Job: keep every external-system claim either measured this session or cited to a doc read this session, and mark the rest loudly.

> If you believe a library is version x.x.x because that's what you were trained on, you are wrong. If you believe it because you read it in the docs this session, you are right.

## The rule

**Measured or cited. Nothing else enters the document.**

No claim about an external system — library version, API shape, service behaviour, host state, config default, on-disk layout — enters a spec, plan, or brief unless it is:

| Basis | What it requires |
|---|---|
| **Measured** | You ran something this session and the transcript is pasted inline. |
| **Cited** | You read the doc this session and the citation names the source and the section. |
| **Neither** | Mark it `UNVERIFIED`. It blocks. |

An `UNVERIFIED` mark on a load-bearing claim opens `G-FACTS` and holds the run at F1 or above (../routing/SKILL.md, tripwire table). It is not a caveat you write and walk past.

Training-derived belief is the third category. It feels exactly like the first two from the inside — that is why the rule is mechanical rather than a judgement call.

## Ground Truth block

Every spec carries one. Every task brief's constraints section carries the rows that bear on that task, **copied verbatim** — not summarised, not paraphrased into prose.

| Fact | How measured | Transcript or citation |
|---|---|---|
| `hermes profile install` requires `distribution.yaml` at the repo root | *illustrative — not measured here*: shows the shape a probe row takes | `$ hermes profile install …` / `error: distribution.yaml not found` |
| pyyaml resolves to 6.0.3 in this venv | `.venv/bin/python -c 'import yaml; print(yaml.__version__)'` | `6.0.3` |
| The gate schema requires `blocking` | Read `core/gate.schema.json` this session | `core/gate.schema.json`, `required: [...]` |
| Upstream rate limit is 100/min | — | `UNVERIFIED` — blocks `G-FACTS` |

Rules for the block:

1. One row per load-bearing claim. A claim is load-bearing if a design decision or a task instruction depends on it.
2. The transcript column holds the actual command and the actual output, trimmed for volume but never for the part that carries the proof.
3. A citation names the file or URL **and** the section. "the docs say so" is not a citation.
4. `UNVERIFIED` rows stay in the table. Deleting the row does not resolve the gate.
5. A row that demonstrates the format rather than records a measurement is marked
   *illustrative — not measured here*, as the first row above is. An unlabeled row asserts a
   measurement. A table carrying a borrowed example unlabeled has already broken the rule it teaches.

## Probe or research

Two different acts. Pick by what the claim is about.

| | Probe | Research |
|---|---|---|
| Answers | What is true of *this* host, cluster, repo, or account right now | What is true of the software in general |
| Method | Run a command, inspect the state, capture the output | Read the current docs, the changelog, the source |
| Evidence | A transcript | A citation with a section |
| Fails by | Sampling a tree another agent is writing to | Reading a version of the docs that is not the version installed |

A probe never substitutes for research and research never substitutes for a probe. "The docs say the default is 30s" does not tell you what this deployment's config file says; "this deployment sets 30s" does not tell you whether the flag still exists upstream.

Probes are read-only by default. A probe that needs a write is a checkpoint task — ../../core/prime-directives.md governs, and `G-CHECKPOINT` is the way through.

## Measure, do not cite

**Re-measure claims that matter, even when a previous agent already recorded them.**

An earlier agent's ledger note is not a measurement you performed. Two results in this system were nearly explained by quoting one; one of those notes was wrong, and the wrong one cost a debugging session. Re-measuring costs a minute.

- A ledger line is a pointer to a measurement, not the measurement.
- A fact copied from a spec into a brief into a report has been through three hands and measured once.
- If the claim decides something, re-run the command and paste the fresh transcript.
- If the claim is background colour, cite the ledger and mark it as inherited, not as measured.

Re-measurement is cheap; the whole point of the ephemeral environment is that running things there costs nothing (../practical-testing/SKILL.md).

## Where the gate sits

| Artefact | What must hold before it ships |
|---|---|
| Spec | Ground Truth block present; no load-bearing `UNVERIFIED` row unresolved or `G-FACTS` is open. |
| Plan | Every checkable claim traces to a Ground Truth row. A plan vague enough to always be right is worthless. |
| Task brief | The rows that bear on the task, copied verbatim into constraints. |
| Report | Claims about what happened are transcripts, not recollections (../verification-before-completion/SKILL.md). |

## Red flags

- A version number, port, path, or flag written from memory because it "is standard."
- "The API probably returns…" anywhere in a spec.
- A Ground Truth row whose evidence column paraphrases rather than quotes.
- An `UNVERIFIED` mark added and the document shipped anyway.
- A brief that summarises the Ground Truth block instead of copying the rows.
- Citing a doc you read in a previous session, or read about, or remember reading.
- A measurement taken against a worktree another agent is mid-write on.
