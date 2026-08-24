# Pantheon — Connectors & Connections Spec (v1, draft)

**How to use this document.** Companion to `pantheon-spec-v0.md`; where they conflict, v0's invariants win. This is the shape of the connector surface: how Pantheon grows from three connector kinds to the systems a company actually keeps its information in — Google Workspace, Microsoft 365/Azure, Slack, Jira, NAS shares, more databases — and how a tenant sets one up without a credential ever touching YAML or a container. UX sketches for the Connections surface are in §8. Nothing here is implementation; it exists to be argued with first.

**The sentence everything must stay true to:** a new service is never a new engine feature. The executor's Rust stays constant (v0 invariant 1); adding a service means answering four questions at the proxy layer — **what transport and auth, what verbs, what scope grammar, what audit shape** — and registering the answers as data.

---

## 1. The connector contract

Every connector kind, present or future, is fully described by:

1. **Transport + auth** — how the proxy reaches the service and what secret material it custodies (OAuth token pair, connection string, service-account key, SMB credential). Custody is always executor-side; containers see only the per-run socket (v0 §8).
2. **Verbs** — the closed set of operations a Resource of this kind may expose (`query`, `get`, `put`, `list`, `search`, `post`, `request`, ...). Declared per-resource in YAML, enforced per-grant at the proxy.
3. **Scope grammar** — how a grant narrows the service *in the service's own terms*. v0 established the pattern: SQL row filter, key prefix, URL allowlist. Every new connector must define its grammar before it ships; "full access" is not a grammar.
4. **Audit shape** — what one call writes to the run log: verb, normalized target (table/path/channel/issue), scope decision (allowed | denied + which grant), payload size moved by handle, latency. One event per call, no exceptions, including denials.

A connector that cannot answer all four is not ready to exist.

## 2. Connection vs. Resource (new split)

v0 folded connection config into the Resource. v1 splits them:

- **Connection** — credential + endpoint, created interactively in the manage surface (§8) or by CLI, stored executor-side, named (`conn: workspace-prod`). Never present in YAML, never in the registry diff, never in a container. Rotating or revoking a Connection touches no definitions.
- **Resource** — YAML as today: `connector:` kind, exposed verbs, and now a `connection:` ref by name. `ptn plan` validates the ref exists and the verbs are legal for the kind; it cannot and does not validate the secret.

```yaml
kind: resource
name: crm.db@1
connector: postgres
connection: crm-replica          # named credential, lives executor-side
verbs: [query]
```

This split is what makes "the user sets up a connection" a safe, self-serve act: the interactive surface only ever creates Connections; making one *reachable from a job* still requires a Resource definition through plan/apply, reviewed like any other change.

## 3. Three lanes for new services

**Lane A — HTTP profiles.** The `http` connector already reaches any REST API. A *profile* is data layered on it: an auth mode the proxy executes (OAuth2 refresh, header token), pagination and rate-limit behavior, and a scope grammar finer than a URL allowlist. Slack, Jira, Google, and Microsoft Graph all begin here; a profile is days of work, not weeks.

**Lane B — family extensions.** Siblings of existing kinds reuse a grammar wholesale. `mysql | sqlserver | snowflake | bigquery | azure.sql` are the `postgres` family (row filter). `azure.blob | gcs` are the `s3` family (key prefix). `smb | nfs` (a NAS) is the `s3` family applied to a filesystem: share + path prefix.

**Lane C — the `mcp` connector** (deferred in v0, scheduled here). One connector kind covering the long tail: an MCP server is a Resource, its tool list is the verb list, scope = tool allowlist + per-tool argument constraints, and the proxy wraps every tool call with the same grant check and audit event as a SQL query. This is the escape valve that keeps the first-class catalog small.

## 4. The catalog (named services, their grammars)

| Service | Connector | Lane | Scope grammar (the grant, in its own terms) |
|---|---|---|---|
| Google Drive | `google.drive` | A | shared-drive / folder-ID prefix |
| Google Sheets | `google.sheets` | A | spreadsheet ID + range |
| Gmail | `google.mail` | A | label and/or query filter (subsumes v0's deferred `imap`) |
| SharePoint / OneDrive / Excel-online / Outlook | `ms.graph` | A | site ID, drive ID, path prefix; workbook + range for live Excel |
| Azure Blob | `azure.blob` | B | container + key prefix |
| Azure SQL | `azure.sql` | B | SQL row filter |
| Azure (provisioning) | `http` + ARM profile | A | resource-group allowlist |
| Slack | `slack` | A | channel allowlist (read and write verbs; also a trigger source) |
| Jira | `jira` | A | project keys + a mandated JQL fragment ANDed onto every query |
| NAS | `smb` / `nfs` | B | share + path prefix |
| Databases | `postgres` family | B | row filter |
| Everything else | `mcp` | C | tool allowlist + argument constraints |

Notes that carry weight:

- **`ms.graph` is the highest-leverage single build**: one connector, one consent, and SharePoint, OneDrive, live Excel, and Outlook all fall out of it.
- **Slack and Jira are two-way**: sources, destinations (post message, file issue — write verbs on the same resource), *and* trigger sources (§7).
- The Jira grant — a JQL fragment ANDed onto every query — is deliberately the same move as the Postgres row filter. Grammars should rhyme across connectors wherever the service allows it.

## 5. Identity & token custody

Two identity modes per Connection, chosen at setup:

- **Delegated** — the Connection stores per-user OAuth tokens; a run executes calls with *the requester's* token. The v0 permission beat ("same prompt, two users, different answers") comes free from the service's own ACLs. Required for services whose sharing model is per-person (Drive, OneDrive, Gmail, Outlook).
- **Service** — one app-level credential; the proxy narrows it per-user with grants, exactly the v0 model. Required for unattended runs (nobody's token is present at 2am) and right for infrastructure services (databases, blob stores, NAS).

A Connection may hold both; the run uses delegated when the trigger carries a requester, service otherwise — and which mode executed each call is part of the audit event. Token refresh happens centrally in the proxy. The container-never-sees-a-credential rule is unchanged and non-negotiable.

## 6. Parsing: files are not data yet

The rule: **an agent never reads a binary.** Fetched artifacts (xlsx from Drive, PDF from a NAS, .eml thread) land in the blob store as `File` handles, then a *deterministic* parser task from a standard library turns them into typed values:

- `parse.xlsx`, `parse.csv` → `Table`
- `parse.pdf` → `Text` + extracted `Table`s
- `parse.eml` → `Record{message@1}`

Parsers are ordinary script tasks shipped in the runner image — judgment is not involved, so agents are not either. Every parsed value's envelope carries provenance (source resource, path/ID, version or etag, fetched-at) so a report can cite its inputs. Live reads (Sheets range, Graph Excel range) skip parsing and produce `Table` directly. An Excel file is therefore *not a connector*: it is a `File` reached through one, parsed by a task.

## 7. Services as triggers

The same services start runs: Slack mention or slash command, Jira webhook on transition, Drive/Graph change notification, mail arrival. All are the existing `webhook` trigger source with a service-shaped adapter in front — each declares `emits:` a registered schema (`slack.mention@1`, `jira.issue_event@1`), and v0 invariant 6 holds: the definitions behind them are ordinary tasks that could equally sit behind cron.

## 8. Connections surface (UX sketch)

The first web manage surface. It creates and monitors **Connections only** (§2) — Resources stay in YAML through plan/apply. Four screens.

**8.1 — Connections index.** The tenant's wall of sockets: what is connected, in which identity mode, health from last use, and what Resources reference it.

```
┌─ CONNECTIONS ──────────────────────────────────────── [ + connect ] ─┐
│                                                                      │
│  ▣ workspace-prod      google      delegated+service   ● healthy     │
│      referenced by: crm.docs@2, board-pack@1        last call 2m ago │
│  ▣ crm-replica         postgres    service             ● healthy     │
│      referenced by: crm.db@1                        last call 11m    │
│  ▣ eng-slack           slack       service             ○ token stale │
│      referenced by: standup-digest@1                [ reauthorize ]  │
│  ▣ finance-nas         smb         service             ● healthy     │
│      referenced by: receipts.archive@1                               │
└──────────────────────────────────────────────────────────────────────┘
```

**8.2 — Add connection.** Pick a service (the catalog, §4), then the fork: OAuth services open the provider's consent screen; credential services take a connection string / key / SMB credential. Either way the secret goes straight to executor custody — the browser session never re-displays it.

```
┌─ CONNECT A SERVICE ──────────────────────────────────────────────────┐
│  google workspace   microsoft 365   slack      jira                  │
│  postgres           azure           nas (smb)  mcp server            │
│                                                                      │
│  ▸ microsoft 365 (graph)                                             │
│    identity   (●) delegated — users consent individually             │
│               (○) service   — one app credential, scoped by grants   │
│               (○) both                                               │
│    name       [ m365-prod ]                                          │
│                                          [ continue → consent ]     │
└──────────────────────────────────────────────────────────────────────┘
```

**8.3 — Verify.** After consent/entry, the proxy performs one least-privilege probe call and shows its result *as an audit event* — the surface teaches the audit log from the first minute.

```
┌─ VERIFYING m365-prod ────────────────────────────────────────────────┐
│  graph.get  /me/drive/root · allowed · 213ms · 1 call               │
│  ● connection healthy — credential held by the executor.            │
│                                                                      │
│  next: reference it from a resource definition —                    │
│    kind: resource                                                    │
│    name: board-files@1                                               │
│    connector: ms.graph                                               │
│    connection: m365-prod                                             │
│    verbs: [get, list]                                                │
│  then:  ptn plan && ptn apply                                        │
└──────────────────────────────────────────────────────────────────────┘
```

**8.4 — Grants.** Per user × resource: verbs + scope written in the connector's grammar (§4), with the grammar's shape prompted by the connector kind. Mirrors the `grants` table one-to-one; nothing new is invented here.

```
┌─ GRANTS · board-files@1 (ms.graph) ──────────────────────────────────┐
│  u_ellis    verbs [get,list]   scope  site:finance  path:/board/*   │
│  u_okafor   verbs [get]        scope  site:finance  path:/board/q*  │
│  + add grant                                                         │
└──────────────────────────────────────────────────────────────────────┘
```

## 9. New invariants (additions to v0's six)

7. **A connector ships with all four contract answers (§1) or does not ship.** Scope grammar and audit shape are not fast-follows.
8. **Secrets never appear in YAML, in the registry, in a diff, or in a container.** The Connection/Resource split (§2) exists to make this structural, not disciplinary.
9. **Setup is self-serve; reachability is reviewed.** Creating a Connection requires no code review; a job touching it always does, because Resources only enter through plan/apply.

## 10. Acceptance tests

1. A Connection created in the surface is usable by a Resource after `ptn apply`, and its secret is absent from YAML, registry rows, and container environment (inspected).
2. Same prompt, two users, `delegated` Drive connection → different file lists, with the service's own ACLs doing the narrowing; audit shows both.
3. A `service`-mode Slack resource under a channel-allowlist grant: a call to a granted channel succeeds, a non-granted channel is denied, both audited.
4. An xlsx fetched from OneDrive → `parse.xlsx` → typed `Table` → agent answer citing provenance (file, etag, fetched-at).
5. A Jira grant's JQL fragment is provably ANDed onto every query issued through the proxy.
6. Revoking a Connection stales every referencing Resource visibly (index shows it; next run fails typed, not silently).
7. An `mcp` resource: granted tool callable, non-granted tool denied, both audited with arguments recorded.
8. A NAS (`smb`) resource behind a path-prefix grant serves a file by handle; the container never sees the SMB credential.

## 11. Build plan (priority-ordered)

**C1 — custody + profiles groundwork:** Connection store (executor-side), OAuth token custody + refresh in the proxy, HTTP profile mechanism. Unlocks every Lane A service.
**C2 — `ms.graph` + `google.*`:** the two consent flows, delegated + service modes, scope grammars. Six named services fall out.
**C3 — parser task library:** `parse.xlsx`, `parse.csv`, `parse.pdf`, `parse.eml`, provenance in envelopes. This is what turns "connected" into "can answer questions."
**C4 — Connections surface:** §8 screens, backed by the same registry + run-log reads as everything else.
**C5 — `slack` + `jira`:** profiles + write verbs + trigger adapters.
**C6 — families:** `azure.blob`, `azure.sql`, `mysql`, `smb`.
**C7 — `mcp`:** the long-tail connector.

## 12. Explicitly deferred

SSO/SCIM for the surface itself; automatic grant inference from service ACLs (grants stay explicit); Drive/Graph *push* change-notification triggers (poll first, push later); writing *to* Excel; per-tool MCP argument-constraint grammar beyond allowlists; connection sharing across tenants; secrets backends beyond the executor store (Vault/KMS integration is a deployment concern, not a connector one).
