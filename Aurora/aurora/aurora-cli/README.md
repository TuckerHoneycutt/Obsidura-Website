# `aurora-cli`

The branch tooling. `aurora branch up` mints a complete second copy of the
stack; `aurora branch down` destroys it. Production is never touched.

**4,250 lines of executable code across 11 modules.** Stdlib + pyyaml only.

---

## Mental model

A branch is **a second Compose project on the same host**. That is the whole
idea; everything else follows from it.

- Production is Compose project `<name>`. A branch is `br-<name>`.
- Docker keys containers, volumes and networks by project, so two stacks
  coexist without knowing about each other.
- The branch gets its own Tailscale node, so it has its own domain and
  certificate.
- It publishes **no host ports** — collision with production is
  unrepresentable rather than avoided.
- It is seeded *from* production by reading, never writing.

The only config difference between the two is `compose.branch.yml`, which is
generated.

---

## Where the logic lives

Read in this order; each builds on the ones above.

| Module | Code | What it does |
|---|---:|---|
| `identity.py` | 208 | Derives production's checkout, project and domain. Names the `br-` namespace. **Hardcodes neither project name** — correct before and after the rename. |
| `guards.py` | 63 | Two assertions every destructive path goes through. Small on purpose: this is the last thing between a bug and production. |
| `envfile.py` | 417 | Strict `KEY=value` parsing, and rendering a branch's `.env` from `branch-env.yaml`. |
| `overlay.py` | 197 | Generates `compose.branch.yml` from the resolved compose config. |
| `exclusions.py` | 273 | `--without <service>`, and closing over its dependents. |
| `seed.py` | 948 | Copies production's state into a branch: SQLite snapshots, reflink file copy, volumes, `pg_dump`/`pg_restore`. The largest module because it handles the most host reality. |
| `crosswire.py` | 152 | The pre-push hook that stops commits landing in a branch's Forgejo. |
| `branch.py` | 1029 | Orchestration: `up`, `down`, `ls`, `access`, `shell`, `rebuild`. Mostly ordering — the work is done by the modules above. |
| `access_doc.py` | 354 | Renders `BRANCH-ACCESS.md` and `.worktrees/INDEX.md`. Owns secret redaction. |
| `mcp.py` | 376 | Hand-written JSON-RPC over stdio so an agent can drive branches. No SDK. |
| `__main__.py` | 234 | argparse entry point. |

`devspawn.py` (500 lines, added 2026-07-31) is not in that list because it is
not part of the branch lifecycle: it is the policy layer above it — roster,
namespace, ownership, quota, leases, reaper — and it issues no command. Its
only callers are `mcp.developer_server` (the four-tool developer table behind
`ops/aurora-spawn-broker`) and `aurora dev-spawn ls|reap`. Design:
`docs/superpowers/specs/2026-07-31-developer-ephemeral-spawn-design.md`.
The `Code` column above was last measured on 2026-07-30; every module has
grown since, `mcp.py` most of all.

**If you change one thing, change it here:**

| To change | Edit |
|---|---|
| What a branch must override in `.env` | `branch-env.yaml` (repo root) |
| What a branch may omit | `branch-services.yaml` (repo root) |
| What the branch overlay resets | regenerate `compose.branch.yml`, don't hand-edit |

---

## Running the tests

There is no system pytest. Always set `AURORA_PROJECT` to the project the
**deployed** containers actually carry, or two tests fail for reasons that are
not yours.

```bash
# find the live project name
docker ps -a --format '{{.Label "com.docker.compose.project"}}' | sort -u

# default suite — no containers created, ~3 minutes
AURORA_PROJECT=<live project> .venv/bin/python -m pytest

# one module
AURORA_PROJECT=<live project> .venv/bin/python -m pytest aurora-cli/tests/test_seed.py -v
```

Three tiers, opt-in by environment variable:

| Tier | Enable | What it does |
|---|---|---|
| default | — | Unit + conformance. Touches no containers. |
| A1 | `AURORA_ACCEPTANCE_STACK=1` | Brings up **one real branch stack** beside production, measures it, destroys it. |
| B | `AURORA_EXPECT_TIER_B=1` | Everything needing the branch's own tailnet identity: node registration, certificate, agent routing. |

Tiers A1 and B create real Docker objects. They are project-scoped to `br-*`
and tear down after themselves; production is snapshotted before and asserted
unchanged afterwards.

**Guard tests run against a stub `docker`, never the real one** — a guard
tested against a live daemon has its failure mode as the thing it guards
against.

```bash
bash ops/guardtest.sh          # ops/docker-guard
bash ops/devspawntest.sh       # the developer MCP surface, stub daemon + synthetic roster
```

---

## Reading the diff

This package is ~4k lines of code and ~8k lines of tests. The ratio is
deliberate — every destructive operation is mutation-tested — but it means the
diff does not read in file order.

- **Behaviour** is in the modules above.
- **Why a line is the way it is** is usually in a comment directly above it,
  citing the measurement that forced it.
- **Proof it works** is in `aurora-cli/tests/` (unit) and `tests/` (conformance
  and acceptance).

For operating the system rather than modifying it, read `USERGUIDE.md` at the
repo root instead.
