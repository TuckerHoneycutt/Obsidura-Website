# Open questions

Audience: Tucker, and whoever owns the Rust executor. Job: everything the plan needs that the spec does not answer. Q1–Q4 are blocking on Phase 0 and are cheap to settle by reading the executor source.

These are not design debates. They are facts about a system that either does or does not already work a certain way — `reality-gate` applies: **measure or read the source, do not reason about what it probably does.**

## Blocking on Phase 0

**Q1 — Does the runner protocol have a versioned handshake?**
If not, a second runner image against an unversioned protocol is a silent-corruption generator: an SDK built for kernel v1 talking to an executor on kernel v2 misreads an envelope and produces plausible wrong output. This is Phase 0 kill criterion #2. If the answer is no, adding one is a small change and worth making *before* a second runner exists, not after.

**Q2 — What exactly is in `capabilities`?**
Spec §8 says the socket is the capability and the UDS is mounted per run. Is `capabilities` in the RPC payload the socket path alone, or a token set the body presents per call? The `res/` package's shape depends on the answer, and so does whether an action can leak anything by logging it.

**Q3 — Does the proxy handle concurrent requests on one run's socket, or serialise them?**
The single largest determinant of whether Go's concurrency is worth anything here. Fan-out over 200 receipt PDFs is either the library's best feature or entirely unavailable. Do not design around the optimistic answer. Measure it in Phase 2 even if the source suggests an answer.

**Q4 — How does the task name reach the body?**
Spec §8 mandates one generic image serving many tasks, so multi-name dispatch must already exist. Is the name in the envelope, in argv, or in an env var? The `serve/` dispatcher needs it.

## Needed by Phase 1

**Q5 — Is there a `Table` handle read API, or does the body fetch the blob itself?**
"Column meta + blob-store row source" (§5) suggests the body fetches, but if the proxy mediates it, `table/` is a proxy client rather than a blob reader. Different package entirely.

**Q6 — Can `ptn plan` consume a directory produced by a build step?**
The drift gate assumes yes and that generated YAML is indistinguishable from hand-authored. Confirm there is no "authored by a human" assumption anywhere in the plan/apply path.

**Q7 — How are `File` handles produced from inside a body?**
Content-addressed blob ref plus media type plus capability (§5). Does the body PUT through the proxy and receive a handle, or construct the handle itself? Affects every action that emits an artifact — which is most of the interesting ones.

**Q8 — Are Record schemas readable from the registry at build time?**
`ptn-gen structs --from-registry` needs a way to pull `name@version` schemas out of Postgres in CI. A read endpoint, a dump command, or direct SQL — any is fine, but one must exist.

## Needed by Phase 2

**Q9 — How does a Go action declare its grants, and how does the proxy learn them?**
Spec §8 has `grants(user_id, resource, verbs, scope)` enforced at the proxy. Emitted YAML declares `uses: [resource + verbs]`. Confirm those are the same mechanism and that nothing extra is needed per runner kind.

**Q10 — What is the image build and registration path for a second runner kind?**
If this turns out to require an executor change, that is Phase 0 kill criterion #1 arriving late. Worth checking early even though it is a Phase 2 need.

## Product-shaped, not blocking

**Q11 — Is the deck catalog (Phase 4) generated from the registry, or maintained by the frontend?**
Recommendation is registry-generated, one source of truth. Needs whoever owns the GUI to agree.

**Q12 — Does a Go action ever need to call another action directly, or always through the graph?**
Recommendation: **always through the graph.** Direct calls would put wiring inside Go code and break invariant 3, which is the thing this whole design is arranged to protect. Worth stating as a rule now, before someone needs it under deadline and does the easy thing.
