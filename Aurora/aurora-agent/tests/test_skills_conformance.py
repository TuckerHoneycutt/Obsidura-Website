"""Every skill is well-formed; vendored skills carry provenance; no collisions.

Mutation: delete origin key from one vendored SKILL.md -> test_vendored_provenance fails.
Mutation: duplicate a skill dir under two names with same frontmatter name -> test_unique_names fails.
Mutation: reintroduce a superpowers: cross-reference in a vendored file -> test_no_upstream_refs fails.
"""
from conftest import REPO, skill_dirs, parse_frontmatter

OMITTED = {"brainstorming", "using-superpowers", "systematic-debugging",
           "ask-matt", "code-review", "implement", "research",
           "resolving-merge-conflicts", "setup-matt-pocock-skills",
           "triage", "grill-me", "grill-with-docs", "handoff", "teach",
           "writing-great-skills", "qa", "design-an-interface",
           "request-refactor-plan", "ubiquitous-language"}

def test_skills_exist():
    assert len(skill_dirs()) >= 10

def test_frontmatter_complete():
    for d in skill_dirs():
        fm = parse_frontmatter(d / "SKILL.md")
        assert fm.get("name") == d.name, f"{d.name}: frontmatter name mismatch"
        assert fm.get("description"), f"{d.name}: missing description"

def test_unique_names():
    names = [parse_frontmatter(d / "SKILL.md").get("name") for d in skill_dirs()]
    assert len(names) == len(set(names))

def test_vendored_provenance():
    for d in skill_dirs():
        fm = parse_frontmatter(d / "SKILL.md")
        origin = fm.get("origin", "")
        assert origin in {"aurora", "obra/superpowers@6.2.0", "mattpocock/skills@2ab9580"}, \
            f"{d.name}: bad origin {origin!r}"
        if origin != "aurora":
            assert fm.get("license") == "MIT", f"{d.name}: vendored without license"

def test_no_omitted_names():
    present = {d.name for d in skill_dirs()}
    assert not (present & OMITTED)

def test_no_upstream_refs():
    for d in skill_dirs():
        for md in d.rglob("*.md"):
            text = md.read_text()
            assert "superpowers:" not in text, f"{md}: unrewritten superpowers: ref"
            assert "setup-matt-pocock-skills" not in text, f"{md}: mp setup ref"

def test_vendor_manifest_matches_tree():
    """Mutation: add a skill dir not listed in the manifest -> fails."""
    from conftest import load_yaml
    m = load_yaml(REPO / "docs" / "vendor-manifest.yaml")
    vendored = set(m["superpowers"]["vendored"]) | set(m["mattpocock"]["vendored"])
    present = {d.name for d in skill_dirs()}
    new = {d.name for d in skill_dirs()
           if parse_frontmatter(d / "SKILL.md").get("origin") == "aurora"}
    assert vendored == present - new

def test_third_party_license():
    text = (REPO / "LICENSE-THIRD-PARTY.md").read_text()
    assert "obra/superpowers" in text and "mattpocock/skills" in text and "MIT" in text
