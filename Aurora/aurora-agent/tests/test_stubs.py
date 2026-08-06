"""Guard/lease stub interfaces hold before implementation exists.

Mutation: implement the predicate to return allow -> test_guard_predicate_unimplemented fails.
Mutation: change refuse exit code to 1 in check.py argparse layer -> test_guard_bad_argv fails.
"""
import subprocess, sys, re
from conftest import REPO, parse_frontmatter

PY = sys.executable

def run(args, **kw):
    return subprocess.run([PY, *args], capture_output=True, text=True, **kw)

def test_guard_bad_argv():
    r = run([str(REPO / "core/guard/check.py")])
    assert r.returncode == 2

def test_guard_predicate_unimplemented():
    r = run([str(REPO / "core/guard/check.py"), "compose-down", "aurora-eph-deadbeef"])
    assert r.returncode != 0
    assert "NotImplementedError" in r.stderr

def test_guard_override():
    r = run([str(REPO / "core/guard/check.py"), "compose-down", "anything"],
            env={"AURORA_GUARD_OVERRIDE": "1", "PATH": "/usr/bin:/bin"})
    assert r.returncode == 0
    assert "OVERRIDE" in r.stderr

def test_lease_id_format_documented():
    spec = (REPO / "core/lease/SPEC.md").read_text()
    assert re.search(r"aurora-eph-\[0-9a-f\]\{8\}|aurora-eph-<8hex>", spec)

def test_specs_marked_stub():
    for p in ["core/guard/SPEC.md", "core/lease/SPEC.md"]:
        assert parse_frontmatter(REPO / p).get("status") == "stub"

def test_lease_unimplemented():
    r = run([str(REPO / "core/lease/lease.py"), "acquire"])
    assert r.returncode != 0 and "NotImplementedError" in r.stderr
