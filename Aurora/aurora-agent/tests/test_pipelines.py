"""All manifests parse, validate, reference real skills/gates, share invariants.

Mutation: drop practical-testing from f0.yaml invariants -> test_invariants_identical fails.
Mutation: reference skill 'code-review' in a stage -> test_stage_skills_exist fails.
Mutation: remove tripwires from chore.yaml -> schema validation fails.
Mutation: add a gate to f1.yaml -> test_documented_gate_counts fails until the five docs are updated.
"""
import jsonschema
from conftest import REPO, load_yaml, skill_dirs

CANON = ["prime-directives", "verification-law", "output-based-assertions",
         "mutation-proof", "practical-testing", "lease-discipline"]
NAMES = ["chore", "fix", "probe", "incident", "f0", "f1", "f2", "f3"]
GATES = ["G-CLASS","G-FACTS","G-SEAMS","G-SPEC","G-DESIGN","G-DECISION",
         "G-CHECKPOINT","G-PLANCONFLICT","G-BLOCKED","G-E2E","G-DEPLOY"]

# Human-blocking gate entries each manifest declares. These figures are published to
# humans in five places; the counts rotted once already, so they are pinned here.
EXPECTED_GATES = {"chore": 1, "fix": 1, "probe": 2, "incident": 3,
                  "f0": 1, "f1": 4, "f2": 7, "f3": 10}
GATE_COUNT_DOCS = ["skills/framework-guide/SKILL.md", "docs/guide.md", "README.md",
                   "skills/routing/SKILL.md", "docs/framework.md"]

def manifests():
    return {n: load_yaml(REPO / "pipelines" / f"{n}.yaml") for n in NAMES}

def test_schema_validates_all():
    schema = load_yaml(REPO / "pipelines" / "schema.yaml")
    jsonschema.Draft202012Validator.check_schema(schema)
    for n, m in manifests().items():
        jsonschema.validate(m, schema)

def test_invariants_identical():
    for n, m in manifests().items():
        assert m["invariants"] == CANON, f"{n}: invariants drifted"

def test_stage_skills_exist():
    have = {d.name for d in skill_dirs()}
    for n, m in manifests().items():
        for s in m["stages"]:
            assert s["skill"] in have, f"{n}: unknown skill {s['skill']}"

def test_stage_gates_exist():
    for n, m in manifests().items():
        for s in m["stages"]:
            for g in s.get("gates", []):
                assert g in GATES, f"{n}: unknown gate {g}"

def test_feature_tiers():
    ms = manifests()
    for n in ["f0", "f1", "f2", "f3"]:
        assert ms[n]["class"] == "feature" and ms[n]["tier"] == int(n[1])
    for n in ["chore", "fix", "probe", "incident"]:
        assert ms[n]["class"] == n and "tier" not in ms[n]

def test_tripwires_present():
    for n, m in manifests().items():
        assert len(m["tripwires"]) >= 3, f"{n}: too few tripwires"

def _table_rows(text: str) -> list[list[str]]:
    """Markdown table rows as lists of cells, normalised ('**10+**' -> '10')."""
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("|"):
            rows.append([c.strip().strip("*").rstrip("+") for c in line.strip("|").split("|")])
    return rows

def _tiers_across_a_row(rows, tiers) -> bool:
    """Transposed table: one row holds the four counts side by side (a 'Human gates' row)."""
    n = len(tiers)
    return any(r[i:i + n] == tiers for r in rows for i in range(len(r) - n + 1))

def _tiers_down_a_column(rows, tiers) -> bool:
    """Row-per-tier table: the counts are the last cell of four consecutive rows."""
    last = [r[-1] for r in rows]
    n = len(tiers)
    return any(last[i:i + n] == tiers for i in range(len(last) - n + 1))

def test_documented_gate_counts():
    """The published gate counts match the manifests, and the docs match both.

    Read together with the module docstring's mutation: the first assertion catches a
    manifest that moved, the second catches a doc that did not move with it.
    """
    actual = {n: sum(len(s.get("gates") or []) for s in m["stages"])
              for n, m in manifests().items()}
    assert actual == EXPECTED_GATES, f"manifest gate counts moved: {actual}"

    tiers = [str(EXPECTED_GATES[t]) for t in ["f0", "f1", "f2", "f3"]]
    for rel in GATE_COUNT_DOCS:
        rows = _table_rows((REPO / rel).read_text())
        assert _tiers_across_a_row(rows, tiers) or _tiers_down_a_column(rows, tiers), \
            f"{rel}: F0-F3 gate counts {tiers} not published as a contiguous run " \
            f"(one row of a transposed table, or the last cell of four consecutive tier rows)"

def test_journal_convention():
    for n, m in manifests().items():
        j = m["journal"]
        assert j["path"] == ".aurora/runs/<run-id>/journal.jsonl"
        assert j["schema"] == "core/journal.schema.json"
