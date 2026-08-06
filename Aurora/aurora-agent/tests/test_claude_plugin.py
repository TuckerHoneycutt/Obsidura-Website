"""Claude plugin manifests parse; commands map 1:1 to pipelines; prime injected.

Mutation: move .claude-plugin/ under agents/claude/ -> test_plugin_manifests fails.
Mutation: delete commands/incident.md -> test_command_manifest_mapping fails.
Mutation: add commands/foo.md -> test_command_manifest_mapping fails.
Mutation: remove prime-directives mention from chore.md -> test_prime_injected fails.
"""
import json
from conftest import REPO, parse_frontmatter

CLA = REPO / "agents" / "claude"

PIPELINE_BACKED = {"route", "chore", "fix", "probe", "incident", "feature"}
NON_PIPELINE = {"help"}  # explain-only commands; add deliberately, never to silence a failure

def test_plugin_manifests():
    p = json.loads((REPO / ".claude-plugin" / "plugin.json").read_text())
    assert p["name"] == "aurora"
    m = json.loads((REPO / ".claude-plugin" / "marketplace.json").read_text())
    assert any(pl["name"] == "aurora" for pl in m["plugins"])

def test_command_manifest_mapping():
    cmds = {p.stem for p in (CLA / "commands").glob("*.md")}
    assert PIPELINE_BACKED <= cmds, f"missing pipeline commands: {PIPELINE_BACKED - cmds}"
    assert not (cmds - PIPELINE_BACKED - NON_PIPELINE), \
        f"command file backed by no pipeline and not declared non-pipeline: {cmds - PIPELINE_BACKED - NON_PIPELINE}"
    for n in ["chore", "fix", "probe", "incident"]:
        assert f"pipelines/{n}.yaml" in (CLA / "commands" / f"{n}.md").read_text()
    feat = (CLA / "commands" / "feature.md").read_text()
    for t in ["f0", "f1", "f2", "f3"]:
        assert f"pipelines/{t}.yaml" in feat
    assert "skills/routing" in (CLA / "commands" / "route.md").read_text()

def test_prime_injected():
    assert "prime-directives" in (CLA / "CLAUDE.md").read_text()
    for p in (CLA / "commands").glob("*.md"):
        assert "core/prime-directives.md" in p.read_text(), f"{p.name} missing prime ref"

def test_command_frontmatter():
    for p in (CLA / "commands").glob("*.md"):
        assert parse_frontmatter(p).get("description"), f"{p.name}: no description"
