"""SOUL.md and the Claude adapter carry the prime-directives block, in sync with core/.

Mutation: delete the SOUL prime section -> test_soul_contains_directives fails.
Mutation: reword directive 1 in SOUL only -> test_soul_contains_directives fails.
"""
from conftest import REPO

def directive_lines():
    body = (REPO / "core" / "prime-directives.md").read_text()
    lines = [l.strip() for l in body.splitlines() if l.strip().startswith(("1.", "2.", "3."))]
    assert len(lines) == 3, "prime-directives.md must contain exactly 3 numbered directives"
    return lines

def test_soul_contains_directives():
    soul = (REPO / "SOUL.md").read_text()
    assert "AURORA-PRIME-DIRECTIVES-BEGIN" in soul and "AURORA-PRIME-DIRECTIVES-END" in soul
    block = soul.split("AURORA-PRIME-DIRECTIVES-BEGIN")[1].split("AURORA-PRIME-DIRECTIVES-END")[0]
    for line in directive_lines():
        assert line in block, f"SOUL prime block missing: {line}"

def test_claude_adapter_contains_directives():
    """Mutation: append a clause to directive 3 in agents/claude/CLAUDE.md -> fails."""
    adapter = (REPO / "agents" / "claude" / "CLAUDE.md").read_text()
    assert "## Prime directives" in adapter, "Claude adapter lost its Prime directives section"
    section = adapter.split("## Prime directives")[1].split("\n## ")[0]
    adapter_lines = [l.strip() for l in section.splitlines()
                     if l.strip().startswith(("1.", "2.", "3."))]
    assert adapter_lines == directive_lines(), (
        "Claude adapter's numbered directive lines must equal core/prime-directives.md "
        f"exactly and in order; got {adapter_lines}")
