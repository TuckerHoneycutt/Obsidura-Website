"""Distribution manifest stays a valid root-level Hermes profile.

Mutation: move distribution.yaml into agents/hermes/ -> test_root_manifest fails.
Mutation: drop skills/ from distribution_owned -> test_distribution_owned fails.
"""
from conftest import REPO, load_yaml

def test_root_manifest():
    d = load_yaml(REPO / "distribution.yaml")
    assert d["name"] == "aurora"
    assert d["version"] == "0.2.0"
    assert "hermes_requires" in d

def test_distribution_owned():
    d = load_yaml(REPO / "distribution.yaml")
    owned = d["distribution_owned"]
    for p in ["SOUL.md", "config.yaml", "plugins/", "skills/", "pipelines/", "core/"]:
        assert p in owned, f"{p} missing from distribution_owned"
    for p in owned:
        assert (REPO / p.rstrip("/")).exists(), f"distribution_owned lists missing path {p}"

def test_env_requires_shape():
    d = load_yaml(REPO / "distribution.yaml")
    for e in d["env_requires"]:
        assert e.get("name") and e.get("description")
