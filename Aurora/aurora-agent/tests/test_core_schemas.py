"""Gate/journal schemas are valid and their examples validate.

Mutation: set an example gate's shape to "confirm" -> its validation test fails.
Mutation: remove "event" from a journal example line -> journal test fails.
Mutation: delete G-CHECKPOINT row from gates.md -> test_gate_inventory fails.
"""
import json, jsonschema
from conftest import REPO

GATES = ["G-CLASS","G-FACTS","G-SEAMS","G-SPEC","G-DESIGN","G-DECISION",
         "G-CHECKPOINT","G-PLANCONFLICT","G-BLOCKED","G-E2E","G-DEPLOY"]

def _schema(name):
    return json.loads((REPO / "core" / name).read_text())

def test_schemas_are_valid_jsonschema():
    for name in ["gate.schema.json", "journal.schema.json"]:
        jsonschema.Draft202012Validator.check_schema(_schema(name))

def test_gate_examples_validate():
    schema = _schema("gate.schema.json")
    shapes = set()
    for p in sorted((REPO / "core" / "examples").glob("gate-*.json")):
        obj = json.loads(p.read_text())
        jsonschema.validate(obj, schema)
        shapes.add(obj["shape"])
    assert shapes == {"approve", "choice", "text", "checklist"}

def test_journal_examples_validate():
    schema = _schema("journal.schema.json")
    lines = (REPO / "core" / "examples" / "journal-lines.jsonl").read_text().strip().splitlines()
    assert len(lines) >= 6
    events = set()
    for line in lines:
        obj = json.loads(line)
        jsonschema.validate(obj, schema)
        events.add(obj["event"])
    assert {"run.started", "gate.opened", "gate.closed", "mutation.result"} <= events

def test_gate_inventory():
    text = (REPO / "core" / "gates.md").read_text()
    for g in GATES:
        assert g in text, f"gates.md missing {g}"

def test_verbs_doc():
    text = (REPO / "core" / "verbs.md").read_text()
    for verb in ["dispatch(", "run(", "read(", "write(", "ask(", "emit("]:
        assert verb in text
