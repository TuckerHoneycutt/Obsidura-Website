# Extension pack — features and contracts

Python agent actions and YAML definitions that extend the Pantheon engine
(`Dev/cum/pantheon-v1/pantheon`, branch `Pantheon-v0.1-TuckerDev`). The
engine imports the actions as the `ext_actions` package via a symlink at
`<engine>/runner/ext_actions -> extension-pack/actions`.

Design rules every action follows:

- **Kernel values at every seam.** Payloads arrive as kernel Records and
  are unwrapped with `_compat.value_in`; outputs are wrapped with
  `_compat.record(...)` or returned as kernel File handles
  (`{"kind": "file", **ctx.blob_put(...)}`).
- **Mutable state is a blob-index.** The engine's postgres connector runs
  read-only transactions by design, so the catalog
  (`ingest/catalog.json`) and web registry (`web/registry.json`) are JSON
  objects in the `pantheon-ingest` bucket — every read and write crosses
  the proxy under the caller's grant and lands in the audit.
- **Deterministic where possible, model only where it earns its seat.**
  Extraction, cataloguing, and template rendering are code; agents hold
  exactly the judgment calls (describe, answer, market analysis).

## Packages

### `definitions/ingestion` — desktop upload chain

`POST /hooks/upload` → `ingest_normalize` → `catalog_register` →
`agent_describe`.

- `ingest_normalize.py` routes by media type: CSV → typed table profile
  (header, row count, cheap dtype sniff); **xlsx/xlsm → converted to CSV
  up front** (first worksheet via openpyxl, sheet name noted in the
  summary; unreadable workbooks fall through to the document branch);
  small JSON → inline record; images/documents/unknown → stored Files.
  Table bytes land at `ingest/tables/<sha256>.csv`.
- `catalog_register.py` upserts the catalog entry (idempotent on sha256).
- `agent_describe.py` proposes a description and tags (live model when a
  key is present, deterministic mock otherwise); the commit of its
  proposal is deterministic code.

### `definitions/agents` — ask your data

`POST /hooks/ask` → `agent_answer` (output: a JSON answer blob the console
renders as a thread bubble). The agent reads the catalog through its
granted tools only; the answer carries `question / answer / sources /
model / audit`.

### `definitions/mydata` — the instant "Your data" report

`POST /hooks/report-mydata` → `extract_report_data` → `mydata_render`.
Same GATHER → DESIGN seam as the engine's verticals with **both seats held
by scripts**:

- `extract_report_data.py` picks the prompt-named file (else the newest
  uploads, up to 3), and computes row counts, per-numeric-column
  totals/mean/min/max, and every category×number group-by (≤24 distinct
  values counts as a category), plus capped sample rows. Correctness by
  construction — no tokens, no invented numbers.
- `render_template.py` lays those figures out as a styled page (KPI tiles,
  ranked breakdown tables, sample rows) in milliseconds, with the full
  extract JSON in a `<details>` block for checking. Typical end-to-end:
  ~1 s.

### `definitions/benchmark` — your numbers vs the market

`POST /hooks/benchmark` → `market_compare` (output: a comparison page).

- **One resource per host** — `worldbank`, `datausa`, `bls` — because the
  connector composes `base_url + path`; the host pin *is* the governance.
  alice holds all three, bob only World Bank.
- `market_compare.py`: the caller's figures come from the deterministic
  extractor; a live analyst agent (Sonnet 5; labeled illustrative mock
  when keyless) holds read-only request access to the three APIs and must
  source every `benchmark_value` from a tool call it actually made, with
  the comparison basis stated per row. The page prints the summary, the
  comparison table with source links, the model, **and the full audit of
  every call attempted** — failures included.

### `definitions/external` — curated snapshots + liveness cron

Pre-existing package: `web_snapshot` on `/hooks/curate`, hourly
`api_liveness` over the web registry. Cron fires as the `system` user,
which now holds the grants these runs need (see the briefs package).

## Shared modules

- `_compat.py` — every assumption about the shim's ctx API, reconciled
  against the real connectors: `value_in`/`record`, blob-index helpers,
  `blob_put`/`blob_get`, `db_query`, `http_request` normalization.
- `_agent.py` — the provider-generic agent harness: `mock:` models are
  deterministic and keyless; a key upgrades mock specs to live; the final
  answer is forced through a tool call; model-correctable errors return
  in-conversation; every proxied call lands in an audit list; **HTTP
  bodies are base64-decoded to `body_text` before the model sees them**;
  capability envelope enforced per resource+verb (refusals never reach
  the audit).

## Tests

`tests/` — stdlib-only, no pytest; run any file directly with a Python
that has `openpyxl` (the engine's `.venv` works):

    <engine>/.venv/bin/python3 tests/test_extract_report_data.py

`_fakes.py` provides the ctx fake (same envelope shapes as the real
connectors) and the shared runner. One suite per action module; see each
file's docstring for what it pins down.

## Round two additions

### Data quality at ingest (`ingestion`)

`_profile_csv` audits while it profiles: null rates per column, exact
duplicate rows, extreme numeric outliers (3×IQR), and mostly-numeric
columns polluted by text. Findings land in `table.quality` on the catalog
entry; the describe agent is instructed to name them and the deterministic
commit re-appends them if the description doesn't; extracts carry them as
`quality_issues`, and the template renders a "data quality — noted at
ingest" note. Measurement is code; narration is the model's only part.

### `definitions/briefs` — saved prompts, answered every morning

`POST /hooks/schedule` saves a prompt to `config/schedules.json`
(idempotent on text, capped at 12). `morning_brief` answers every saved
prompt — daily via cron at 07:00 UTC and on demand via
`POST /hooks/brief` — using the same extractor and template voice as the
Your-data report, so a daily re-answer costs nothing. A prompt whose data
is missing gets its say on the page instead of failing the brief. The
package also introduces the `system` user with the grants cron-fired runs
need (fixing the standing hourly liveness failure).

### The ask agent is a SQL analyst (`agents`)

`agent_answer`'s envelope now includes `financial_ledger`,
`clinical_patients`, and `rocket_test_logs` (query-only) alongside the
catalog. Aggregates are computed in SQL and copied digit for digit;
refused calls are reported as grant boundaries, not worked around.
Verified live: the same patient-count question returns 30 for alice and
22 for bob (his `ward <> 'Ward-R'` row filter), with the SQL visible in
the audit trail.

### `definitions/connections` — external sources, synced into the catalog

Every connection is an importer, not a new query surface: the sync task
pulls through a governed per-host resource, shapes the result into the
same typed table an upload takes (profile and quality audit included),
and hands it to the existing catalog chain — Ask, the reports, and the
briefs work on synced data with zero changes.

- **Jira** (`POST /hooks/sync-jira`, optional `jql`): issues become
  `jira-issues.csv` — key, type, status, assignee, priority, created,
  resolved, computed cycle_days — which feeds the Delivery report with
  real tickets. The site URL and credentials are *operator settings*
  (`PANTHEON_JIRA_URL`, `PANTHEON_JIRA_AUTH`), resolved at call time via
  the engine's new `base_url_env` connector field; the console composes
  the Basic header from an email + API token so nobody hand-builds
  base64.
- **Slack** (`POST /hooks/sync-slack`, `channel` as `C…` id or `#name`):
  channel history becomes `slack-<name>.csv` (ts, user, text, replies,
  reactions); `#names` resolve through conversations.list. Token in
  `PANTHEON_SLACK_AUTH` as `Bearer xoxb-…`.
- Grants: alice may sync both; bob holds neither — refused at the proxy.
  Truncation (partial pages, more history) is said plainly in the
  catalog summary. Tests stub both APIs via the connector-faithful fake.

### Workspaces

Every surface scopes to the person using it. Catalog entries carry their
`requester`: the deterministic extractor, the benchmark, and each saved
brief prompt narrow to that person's files (unattributed legacy entries
stay shared), and the ask agent is told whose workspace it serves and to
say when an answer draws on someone else's file. The engine's run list
now exposes the firing user, so the console's gallery, its Default-chip
leans, and its per-user chat stores all follow the viewer chip — switch
from alice to bob and the chats, reports and data leans swap wholesale,
while grants were already his. Verified: bob's your-data report finds
nothing in his empty workspace while alice's still builds.
