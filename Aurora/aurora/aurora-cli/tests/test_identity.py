"""Pins `aurora_cli.identity`.

The thing under test is not "does this return the right string today" -- it
is "does this DERIVE, or did someone type the answer in". Those two are
indistinguishable while production's name and the repository's declared name
happen to be whatever they are, so most of what follows either drives the
module with a fabricated project name that matches neither real one, or
compares its answer against a value this file computes from the host at run
time.

Nothing in this file types a project name, a checkout path or a tailnet
suffix. Partly because `tests/test_repo_conformance.py::test_no_tracked_file_
outside_docs_names_the_old_project` forbids one of them outright, and partly
because a test that hardcodes the answer it is checking is the same defect as
an implementation that hardcodes it -- this project has shipped that decoy
twice already.
"""

from __future__ import annotations

import inspect
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from aurora_cli import identity

# `dev-administration` is on sys.path via pytest.ini's `pythonpath`, which is
# what makes `tests` resolve to the dev-administration package.
from tests.test_guard_coverage import _strip_docstrings

REPO = identity.package_root()

# Neither of production's two possible names, and not the declared product
# name either. Every derivation test drives the module with this, so an
# implementation that returns a typed constant cannot pass by coincidence.
FIXTURE_PROJECT = "zz-fixture-stack"


def _fabricated_container(working_dir: str) -> dict[str, str]:
    return {"name": f"{FIXTURE_PROJECT}-service-1", "working_dir": working_dir}


# ---------------------------------------------------------------------------
# production's checkout
# ---------------------------------------------------------------------------


def test_production_root_is_the_main_worktree():
    """Computed from git, never typed.

    Writing `Path("~/Desktop/<name>").expanduser()` here would be the very
    bug this module exists to prevent, restated in the test that is supposed
    to catch it.
    """
    porcelain = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        cwd=REPO, capture_output=True, text=True, check=True,
    ).stdout
    first = [
        line.partition(" ")[2].strip()
        for line in porcelain.splitlines()
        if line.startswith("worktree ")
    ]
    assert first, "git reported no worktrees; the derivation has nothing to read"
    expected = Path(first[0]).resolve()

    assert identity.production_root() == expected


def test_production_root_is_not_the_worktree_this_code_runs_from():
    """The two are different objects and conflating them is the whole hazard.

    This suite runs from a linked worktree nested under production's checkout,
    so `production_root()` returning "wherever I am" would pass every naive
    test while being catastrophically wrong for anything destructive.
    """
    root = identity.production_root()
    here = identity.package_root()

    assert root != here
    assert root in here.parents, (
        f"expected this worktree ({here}) to sit under production's checkout "
        f"({root}); if the layout changed, this test's premise did too"
    )
    assert root == root.resolve(), "production_root() must return a resolved path"


# ---------------------------------------------------------------------------
# production's project name
# ---------------------------------------------------------------------------


def test_production_project_matches_the_declaration_in_productions_checkout():
    """The real answer, recomputed independently of the module."""
    root = identity.production_root()
    env = dict(os.environ)
    env.pop("COMPOSE_PROJECT_NAME", None)
    env["COMPOSE_PROFILES"] = "*"
    declared = json.loads(subprocess.run(
        ["docker", "compose", "config", "--format", "json"],
        cwd=root, capture_output=True, text=True, check=True, env=env,
    ).stdout)["name"]

    assert identity.production_project() == declared
    assert declared, "compose declared an empty project name"


def test_production_project_is_derived_not_hardcoded(monkeypatch):
    """Drive both seams with a name that is neither of production's two.

    If the module ever answers from a constant, an environment variable or
    the directory it happens to be sitting in, this fails -- and it fails
    identically before and after Chunk 2's rename, which is the property the
    task was created to guarantee.
    """
    root = identity.production_root()
    monkeypatch.setattr(
        identity, "_compose_declared_project", lambda _root: FIXTURE_PROJECT
    )
    monkeypatch.setattr(
        identity, "_project_containers",
        lambda project: (
            [_fabricated_container(str(root))]
            if project == FIXTURE_PROJECT else []
        ),
    )

    assert identity.production_project() == FIXTURE_PROJECT


def test_production_project_refuses_a_declaration_with_no_containers(monkeypatch):
    """Trap 2 in a new costume.

    A declared project matching nothing on the daemon makes every downstream
    "is this production?" question answer `no`, which is exactly the shape of
    the vacuous conformance pass that cost Chunks 1 and 2 real time. The
    message must name the project AND the label that found nothing, so this
    cannot be satisfied by the later working-directory check raising for its
    own unrelated reason.
    """
    monkeypatch.setattr(
        identity, "_compose_declared_project", lambda _root: FIXTURE_PROJECT
    )
    monkeypatch.setattr(identity, "_project_containers", lambda _project: [])

    with pytest.raises(identity.IdentityError) as excinfo:
        identity.production_project()

    message = str(excinfo.value)
    assert FIXTURE_PROJECT in message
    assert f"{identity.PROJECT_LABEL}={FIXTURE_PROJECT}" in message
    assert identity.WORKING_DIR_LABEL not in message, (
        "this must be the empty-container-set refusal, not the "
        "working-directory check tripping over the same empty set -- if the "
        "non-empty assertion is deleted, this test has to notice"
    )


def test_production_project_refuses_a_working_dir_mismatch(monkeypatch):
    """Containers labelled with the right project, deployed from elsewhere."""
    root = identity.production_root()
    elsewhere = str(root.parent / "some-other-checkout")
    monkeypatch.setattr(
        identity, "_compose_declared_project", lambda _root: FIXTURE_PROJECT
    )
    monkeypatch.setattr(
        identity, "_project_containers",
        lambda _project: [_fabricated_container(elsewhere)],
    )

    with pytest.raises(identity.IdentityError) as excinfo:
        identity.production_project()

    message = str(excinfo.value)
    assert str(root) in message, "the refusal must name the checkout it expected"
    assert elsewhere in message, "the refusal must name the checkout it found"


def test_production_project_accepts_an_unresolved_working_dir_label(monkeypatch):
    """The `/home` -> `/var/home` trap, covered by a test rather than a comment.

    Docker reports the working-directory label exactly as the invoking shell
    spelled it. On this host that is the unresolved form, while Python
    resolves through the symlink -- so comparing the two as strings makes
    `production_project()` raise against a completely healthy production.
    """
    project = identity.production_project()
    labels = {
        c["working_dir"]
        for c in identity._project_containers(project)
        if c["working_dir"]
    }
    assert labels, f"project {project!r} has containers but no working-dir label"
    raw = sorted(labels)[0]

    assert Path(raw).resolve() == identity.production_root()
    assert raw != str(identity.production_root()), (
        f"the label ({raw}) is textually identical to the resolved path on "
        "this host, so this test no longer exercises the symlink trap; "
        "construct an unresolved alias instead of deleting it"
    )

    monkeypatch.setattr(
        identity, "_compose_declared_project", lambda _root: FIXTURE_PROJECT
    )
    monkeypatch.setattr(
        identity, "_project_containers",
        lambda _project: [_fabricated_container(raw)],
    )
    assert identity.production_project() == FIXTURE_PROJECT


# ---------------------------------------------------------------------------
# the literal scan
# ---------------------------------------------------------------------------


def _banned_literals() -> list[str]:
    """Every identity that must not be typed into the module, derived.

    Production's runtime project name, the product name the repository
    declares, and the tailnet suffix. Derived rather than typed so the scan
    keeps meaning the same thing after Chunk 2's rename lands -- and so this
    file does not itself carry the name the repository forbids.
    """
    literals = [
        identity.production_project(),
        identity.declared_project(),
        identity.tailnet_suffix(),
    ]
    for value in literals:
        assert isinstance(value, str) and len(value) >= 4, (
            f"derived a degenerate literal {value!r}; a scan for it would be "
            "vacuous"
        )
    return literals


def test_identity_module_names_no_production_identity_in_executable_source():
    """The defect this task exists to prevent, as a gate.

    Docstrings are stripped; comments are not. Prose explaining which literal
    a derivation supersedes is informative, but a comment carrying a live
    project name is a copy-paste source and reads as executable to the next
    person who needs a quick default.
    """
    source = _strip_docstrings(inspect.getsource(identity))
    banned = _banned_literals()
    assert len(set(banned)) >= 2, (
        "the derived literals collapsed to one value; the scan would still "
        "work but say less than intended"
    )

    offenders = [literal for literal in banned if literal in source]
    assert offenders == [], (
        f"identity.py types production's identity instead of deriving it: "
        f"{offenders}"
    )


def test_the_literal_scan_catches_code_and_forgives_docstrings():
    """Pins the scan itself, from both sides, using the derived literals.

    Without the first half a stripped-to-nothing source would pass the gate
    above forever. Without the second half the gate is over-eager, and an
    over-eager gate is deleted by the first person it annoys.
    """
    literal = _banned_literals()[0]
    as_code = f'_FALLBACK = "{literal}"\n'
    as_docstring = f'"""Superseded the old {literal} default."""\nX = 1\n'

    assert literal in _strip_docstrings(as_code)
    assert literal not in _strip_docstrings(as_docstring)


# ---------------------------------------------------------------------------
# production's env and domain
# ---------------------------------------------------------------------------


def test_production_env_is_read_from_productions_checkout():
    """Not from the worktree this code runs in.

    While the rename is blocked these two files disagree on
    `COMPOSE_PROJECT_NAME` by construction, so reading the wrong one is
    observable today; the assertion is written against the derivation rather
    than against today's values so it survives the rename.
    """
    env = identity.production_env()
    assert env["COMPOSE_PROJECT_NAME"] == identity.production_project(), (
        "production_env() disagrees with the project the daemon confirmed; "
        "the most likely cause is that it read this worktree's .env"
    )
    here = identity.package_root()
    assert here != identity.production_root()
    assert env["DOMAIN_NAME"] == identity.production_domain()


def test_production_env_follows_production_root(monkeypatch, tmp_path):
    """Point the derivation somewhere fabricated and it must follow."""
    (tmp_path / ".env").write_text(
        f"DOMAIN_NAME=host.{FIXTURE_PROJECT}.example\nCOMPOSE_PROJECT_NAME={FIXTURE_PROJECT}\n"
    )
    monkeypatch.setattr(identity, "production_root", lambda: tmp_path)

    assert identity.production_env()["COMPOSE_PROJECT_NAME"] == FIXTURE_PROJECT
    assert identity.production_domain() == f"host.{FIXTURE_PROJECT}.example"
    assert identity.tailnet_suffix() == f"{FIXTURE_PROJECT}.example"


def test_tailnet_suffix_is_the_domain_minus_its_first_label():
    domain = identity.production_domain()
    assert domain.count(".") >= 2, f"unexpected domain shape: {domain!r}"
    assert identity.tailnet_suffix() == domain.partition(".")[2]
    assert not identity.production_domain().startswith(identity.tailnet_suffix())


# ---------------------------------------------------------------------------
# branch naming
# ---------------------------------------------------------------------------


def test_sanitise_lowercases_and_collapses_non_alphanumerics():
    assert identity.sanitise_branch_name("Feature/Foo Bar") == "feature-foo-bar"
    assert identity.sanitise_branch_name("--Foo__/__Bar--") == "foo-bar"
    assert identity.sanitise_branch_name("v1.2.3") == "v1-2-3"


def test_sanitise_is_idempotent():
    for raw in ("Feature/Foo Bar", "--Foo__Bar--", "v1.2.3", "x" * 90):
        once = identity.sanitise_branch_name(raw)
        assert identity.sanitise_branch_name(once) == once


def test_sanitise_truncates_so_the_prefixed_hostname_fits_a_dns_label():
    """The limit is on the whole label, prefix included.

    Truncating the branch name to 63 leaves `<prefix><63 chars>`, which is
    over the limit -- an invalid hostname, and a tailnet node that either
    registers under a name nobody chose or does not register at all.
    """
    long_name = "feature/" + ("a" * 90)
    out = identity.sanitise_branch_name(long_name)
    prefix = identity.branch_hostname_prefix()

    assert len(out) == identity.DNS_LABEL_MAX - len(prefix)
    assert len(prefix + out) == identity.DNS_LABEL_MAX
    assert len(identity.branch_hostname(long_name)) <= identity.DNS_LABEL_MAX
    assert len(identity.branch_domain(long_name).partition(".")[0]) <= \
        identity.DNS_LABEL_MAX


def test_sanitise_rejects_a_name_with_no_alphanumerics():
    for raw in ("///", "", "---", "  "):
        with pytest.raises(identity.IdentityError):
            identity.sanitise_branch_name(raw)


def test_branch_names_are_namespaced():
    assert identity.branch_project("x") == "br-x"
    assert identity.branch_hostname("x") == f"{identity.declared_project()}-x"
    assert identity.branch_domain("x") == (
        f"{identity.branch_hostname('x')}.{identity.tailnet_suffix()}"
    )
    # The product name is what a branch is named after, not production's
    # current runtime label. Spelled out because the two differ today.
    assert identity.branch_hostname("x") == "aurora-x"


def test_branch_project_sanitises_what_it_is_given():
    """The namespace prefix is the only guard in front of destructive calls.

    A caller that forgets to sanitise must still get a `br-` project, not a
    compose project name containing a slash.
    """
    assert identity.branch_project("Feature/Foo Bar") == "br-feature-foo-bar"
    assert identity.branch_project("x").startswith(
        identity.BRANCH_PROJECT_PREFIX
    )


def test_branch_paths_live_under_productions_worktrees_directory():
    paths = identity.branch_paths("Feature/Foo")
    root = identity.production_root()

    assert paths.name == "feature-foo"
    assert paths.project == "br-feature-foo"
    assert paths.worktree == root / ".worktrees" / "feature-foo"
    assert paths.env_file == paths.worktree / ".env"
    assert paths.access_doc == paths.worktree / "BRANCH-ACCESS.md"
    assert root in paths.worktree.parents


def test_the_branch_namespace_matches_the_test_harness():
    """One namespace, two consumers, no drift.

    `tests/branch_harness.py` (Task 0) carries the same prefix as the guard in
    front of every destructive docker call. It is a test module, so this
    package cannot import it -- which is exactly the situation in which two
    copies of a constant quietly diverge. Task 0's ledger records that Chunk 2
    shipped two "identical" docker queries that drifted apart twice.
    """
    sys.path.insert(0, str(REPO / "tests"))
    try:
        import branch_harness
    finally:
        sys.path.remove(str(REPO / "tests"))

    assert branch_harness.BRANCH_PREFIX == identity.BRANCH_PROJECT_PREFIX
    assert identity.branch_project("x").startswith(branch_harness.BRANCH_PREFIX)


# ---------------------------------------------------------------------------
# the entry point
# ---------------------------------------------------------------------------


def test_the_cli_shim_reports_the_derived_identity():
    """`./aurora branch ls`, end to end, from this worktree.

    This is the task's headline evidence: run from a worktree whose own `.env`
    declares the product name, it must still report production's runtime
    project and production's checkout.
    """
    shim = REPO / "aurora"
    assert os.access(shim, os.X_OK), f"{shim} is not executable"

    proc = subprocess.run(
        [str(shim), "--json", "branch", "ls"],
        cwd=REPO, capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    reported = json.loads(proc.stdout)

    assert reported["production_project"] == identity.production_project()
    assert reported["production_root"] == str(identity.production_root())
    assert reported["declared_project"] == identity.declared_project()
    assert reported["branch_project_prefix"] == identity.BRANCH_PROJECT_PREFIX
    assert reported["running_from"] == str(REPO)
    assert reported["running_from"] != reported["production_root"], (
        "the shim ran from a worktree but reported it as production's "
        "checkout; that is the conflation this module exists to prevent"
    )


def test_the_cli_shim_runs_from_a_directory_that_is_not_the_repo():
    """The shim resolves its own location, not the caller's."""
    proc = subprocess.run(
        [str(REPO / "aurora"), "--json", "branch", "ls"],
        cwd="/", capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["running_from"] == str(REPO)
