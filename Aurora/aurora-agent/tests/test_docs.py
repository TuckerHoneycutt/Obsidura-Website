"""Docs cover omissions, carry the operative tables, and route consumers.

Mutation: delete the omissions row for brainstorming -> test_omissions_cover fails.
Mutation: remove the tier table from framework.md -> test_framework_tables fails.
"""
from conftest import REPO, load_yaml

def test_omissions_cover():
    m = load_yaml(REPO / "docs" / "vendor-manifest.yaml")
    text = (REPO / "docs" / "omissions.md").read_text()
    for name in m["superpowers"]["omitted"] + m["mattpocock"]["omitted"]:
        assert name in text, f"omissions.md missing {name}"

def test_framework_tables():
    text = (REPO / "docs" / "framework.md").read_text()
    for token in ["chore", "fix", "probe", "incident", "F0", "F1", "F2", "F3",
                  "G-CLASS", "G-CHECKPOINT", "dispatch", "emit",
                  "prime-directives", "practical-testing"]:
        assert token in text, f"framework.md missing {token}"

def test_readme_quickstarts():
    text = (REPO / "README.md").read_text()
    for token in ["hermes profile install", "plugin", "pipelines/", "skills/",
                  "distribution.yaml"]:
        assert token in text
