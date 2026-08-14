# Runner protocol (proposed)

Audience: whoever implements the Pantheon executor in Rust, and anyone writing a second runner. Job: pin the wire contract this SDK implements, so the Rust side has nothing left to invent.

**Status: proposal, not agreed.** At the time of writing the executor does not exist — there is no shim, no proxy, and no schema registry to read. `04-open-questions.md` asks Q1–Q4 as questions to settle against source; with no source, this document answers them by *proposing* an answer and implementing it. Every answer here is cheap to change and expensive to leave implicit.

Where this conflicts with `pantheon-spec-v0.md`, the spec wins and this document is the bug.

## Two sockets, two jobs

Spec §8 separates them and so do we.

| Channel | Carries | Direction |
|---|---|---|
| **stdio** | Task invocation and its result; log and event streaming | Executor ↔ runner process |
| **UDS proxy** | All resource access | Runner → executor, over the per-run Unix domain socket |

Both speak JSON-RPC 2.0, newline-delimited, one message per line. The runner writes protocol traffic on **stdout only**; anything the body prints to stderr is captured as unstructured logs and never parsed.

## stdio: executor → runner

### `hello` — the handshake (answers Q1)

Sent once, before any invocation.

```json
{"jsonrpc":"2.0","id":1,"method":"hello",
 "params":{"protocol_version":1,"kernel_version":1}}
```

```json
{"jsonrpc":"2.0","id":1,
 "result":{"protocol_version":1,"kernel_version":1,
           "runner":"pantheon-go/0.1.0",
           "actions":[{"name":"finance.reconcile_ledger","version":1,
                       "input":"LedgerQuery@1","output":"ReconciliationReport@1"}]}}
```

**A version mismatch is a fatal error, refused at the handshake.** This is the whole point: an SDK built for kernel v1 talking to an executor on kernel v2 must fail loudly, not misread an envelope and emit plausible wrong output. A second runner image against an unversioned protocol is a silent-corruption generator.

The `actions` list also lets the executor verify that every task definition referencing this image is actually served by it — a deploy-time check that costs nothing.

### `invoke` — run one task (answers Q4)

```json
{"jsonrpc":"2.0","id":2,"method":"invoke",
 "params":{"action":"finance.reconcile_ledger",
           "envelope":{...},
           "payload":{"kind":"record","type_ref":"LedgerQuery@1","data":{...}},
           "capabilities":{"socket":"/run/pantheon/r-abc.sock","token":"..."}}}
```

The action name arrives in `params.action`, not argv and not an env var, because one image serves many actions (spec §8) and a process-level answer cannot vary per invocation.

Result:

```json
{"jsonrpc":"2.0","id":2,
 "result":{"envelope":{...},"payload":{"kind":"record",...}}}
```

A body that fails returns a **successful JSON-RPC result carrying an `Error` kernel value**, not a JSON-RPC error. JSON-RPC errors are reserved for protocol faults — malformed frame, unknown action, handshake mismatch. A business failure is a value that flows in the run log (spec §5, "route Errors"); a protocol fault is not.

Panics recover into that same `Error` value. A crashed body produces a typed failure, never a mystery exit code.

## stdio: runner → executor (notifications, no `id`)

```json
{"jsonrpc":"2.0","method":"log",
 "params":{"level":"info","message":"matched 412 receipts","fields":{"unmatched":8}}}
```

```json
{"jsonrpc":"2.0","method":"event",
 "params":{"event_type":"task.progress","payload":{"pct":40}}}
```

`event` lands in `run_events` (spec §8). This is the **product's** run log. It is not the Aurora development journal — see `01-constraints.md`, "the two-journal trap".

## UDS proxy (answers Q2, Q3, Q5, Q7)

`capabilities.socket` is the path; `capabilities.token` is presented on every call. The socket alone is the capability per spec §8; the token is belt-and-braces and lets the executor distinguish concurrent bodies sharing a mount if it ever wants to.

**Q2:** capabilities carry the socket path and a token — nothing else. No connection strings, no credentials. The SDK never logs this struct.

### `resource.call`

One method for all three connector kinds. The verb varies; the framing does not.

```json
{"jsonrpc":"2.0","id":7,"method":"resource.call",
 "params":{"token":"...","resource":"ledger","verb":"query",
           "args":{"sql":"select * from entries where period = $1","params":["2026-Q2"]}}}
```

| Connector | Verbs | Args |
|---|---|---|
| `postgres` | `query` | `{sql, params}` → `{columns, rows}` |
| `s3` | `get`, `put`, `list` | `{key}` / `{key, body, media_type}` / `{prefix}` |
| `http` | `request` | `{method, url, headers, body}` |

### `blob.put` / `blob.get` — File handles (answers Q7)

The body PUTs bytes through the proxy and receives a content-addressed handle. It never constructs a handle itself, because it cannot compute a hash the executor will trust and should not try.

```json
{"jsonrpc":"2.0","id":8,"method":"blob.put",
 "params":{"token":"...","media_type":"text/html","body":"<base64>"}}
→ {"result":{"kind":"file","blob":"sha256:ab…","media_type":"text/html","size":9114,"capability":"…"}}
```

### `table.open` / `table.read` — Table handles (answers Q5)

The proxy mediates, so the body never touches the blob store directly and row access stays metered (spec §5, "meter Tables").

```json
{"jsonrpc":"2.0","id":9,"method":"table.open","params":{"token":"…","handle":{…}}}
→ {"result":{"cursor":"c-1","columns":[{"name":"t","type":"float"},…]}}

{"jsonrpc":"2.0","id":10,"method":"table.read","params":{"token":"…","cursor":"c-1","max":1000}}
→ {"result":{"rows":[[…],[…]],"eof":false}}
```

Chunked by design. An action that materialises tens of thousands of rows to pass them on has defeated the handle system.

### Concurrency (Q3)

**Requests are multiplexed by `id` over one connection.** The client may have many in flight; responses may arrive in any order.

This is a request *of* the Rust proxy, and it is the single largest determinant of whether Go's concurrency is worth anything here. The SDK is written to multiplex either way: **if the proxy serialises, everything still works, just without the speedup.** No correctness depends on concurrency, so this can be measured and improved later without touching action code.

## What this protocol deliberately does not have

- **No action-to-action calls.** An action reaches another action only through the graph. Direct calls would put wiring inside Go code and break invariant 3, which this whole design exists to protect (`04-open-questions.md` Q12).
- **No credential passing.** There is no message that carries a secret to the body. If one is ever needed, the design is wrong.
- **No expression evaluation.** Nothing here interprets a string as code.
