# Wire conformance corpus

Audience: anyone implementing a Pantheon runner. Job: pin the kernel wire
format across languages with examples, not prose.

Every file here is one serialised kernel value or envelope. Each implementation
must, for every file: **parse it into its typed representation, re-serialise,
and produce the same JSON** (compared canonically — keys sorted, whitespace
ignored, so the files stay readable).

The corpus is HAND-WRITTEN, not generated from either implementation. Generating
it from Rust would bake a Rust bug into the thing meant to catch bugs; a
hand-written corpus is an independent third opinion that both sides answer to.

Naming decides which type parses a file:

| Prefix | Parsed as |
|---|---|
| `value_` | the kernel `Value` union |
| `envelope_` | `Envelope` |

Read by:
- `pantheon-rs/crates/ptn-vocab/tests/wire_compat.rs`
- `pantheon-go/kernel/wire_compat_test.go`

A file added here is a requirement on every implementation. That is the point:
adding a case is how you state a new expectation once and have both sides
answer for it.
