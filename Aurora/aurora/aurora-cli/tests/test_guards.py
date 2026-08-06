"""The guards in front of teardown. Refusal is the feature.

Every row here asserts that ZERO commands were issued, not merely that an
exception was raised. "It refused" and "it refused before doing anything" are
different claims, and only the second one is worth having: Chunk 2's
production incident came from a call that happened before anyone noticed the
patch had not bound.
"""

import ast
import inspect
from pathlib import Path

import pytest

from aurora_cli import branch, guards, identity, mcp


class ExplodingRunner(branch.CommandRunner):
    """Any command at all is a failure. Not a mock that records — a mine."""

    def _execute(self, *args, **kwargs):  # pragma: no cover - must never run
        raise AssertionError(
            "a destructive path issued a command after the guard should have "
            "refused"
        )

    def run(self, argv, **kwargs):  # pragma: no cover - must never run
        raise AssertionError(f"guard let a command through: {list(argv)!r}")


# Both production names appear deliberately. Chunk 2's rename is blocked, so
# production is `tai-review` today and becomes `aurora` if it ever lands. A
# guard that refused only one of them would be wrong in one of the two
# worlds, and nobody would notice until that world arrived.
REFUSED = [
    ("", "empty string — compose resolves the project from the CWD basename"),
    (None, "None"),
    ("aurora", "production, post-rename name"),
    ("tai-review", "production, current name"),
    ("br", "prefix without the separator"),
    ("notbr-x", "contains the prefix but does not start with it"),
    ("BR-x", "wrong case"),
    ("br-", "prefix and nothing else"),
    (" br-x", "leading space — would need stripping to look like a branch"),
    (b"br-x", "bytes, not str"),
]


@pytest.mark.parametrize("value,why", REFUSED, ids=[r[0] for r in REFUSED])
def test_assert_branch_project_refuses(value, why):
    with pytest.raises(guards.GuardViolation) as excinfo:
        guards.assert_branch_project(value)
    # Assert on the message, not merely the type: this module raises the same
    # exception from several distinct conditions, so a bare `raises` would
    # pass against a mutant whose FIRST guard was deleted and whose SECOND
    # happened to fire on the same input (Task 1's finding).
    assert "Refusing" in str(excinfo.value), why


def test_assert_branch_project_accepts_a_real_branch():
    assert guards.assert_branch_project("br-x") == "br-x"


def test_the_prefix_clause_alone_is_not_enough(monkeypatch):
    """The second clause, exercised.

    `startswith("br-")` is correct today and after the rename — but only
    because production is not called `br-something`. A guard whose two
    clauses cannot both be made to fire is half-tested, so this forces the
    case the prefix cannot catch.
    """
    monkeypatch.setattr(identity, "production_project", lambda: "br-legacy")
    with pytest.raises(guards.GuardViolation) as excinfo:
        guards.assert_branch_project("br-legacy")
    assert "PRODUCTION" in str(excinfo.value)
    # A different branch is still fine in that world.
    assert guards.assert_branch_project("br-other") == "br-other"


def test_an_unresolvable_production_does_not_disable_teardown(monkeypatch):
    """Teardown must work when production is DOWN — that is when it is needed.

    `production_project()` raises when no containers carry a project label
    (Task 1, deliberately: it refuses to guess). If the guard let that
    propagate, `branch down` would fail exactly during an outage, leaving
    branch stacks running with no supported way to remove them. The prefix
    clause stands alone in that case.
    """
    def boom():
        raise identity.IdentityError("no containers carry a project label")

    monkeypatch.setattr(identity, "production_project", boom)
    assert guards.assert_branch_project("br-x") == "br-x"
    # And it still refuses what it always refused.
    with pytest.raises(guards.GuardViolation):
        guards.assert_branch_project("tai-review")


def test_path_guard_refuses_production_and_near_misses(tmp_path, monkeypatch):
    root = tmp_path / "prod"
    (root / ".worktrees" / "real").mkdir(parents=True)
    (root / ".worktrees-evil" / "x").mkdir(parents=True)
    monkeypatch.setattr(identity, "production_root", lambda: root)

    assert guards.assert_not_production_path(root / ".worktrees" / "real")

    for bad, why in [
        (root, "production's checkout itself"),
        (root / ".worktrees", "the worktrees directory, not a branch in it"),
        # `<root>/.worktrees-evil/x` STRING-PREFIXES `<root>/.worktrees`.
        # This row is why the guard compares Path.parents and never
        # str.startswith.
        (root / ".worktrees-evil" / "x", "string-prefix near miss"),
        (tmp_path / "elsewhere", "outside production entirely"),
    ]:
        with pytest.raises(guards.GuardViolation), pytest.MonkeyPatch.context():
            guards.assert_not_production_path(bad)


def test_a_worktrees_root_override_cannot_reach_into_production(
    tmp_path, monkeypatch
):
    """The seam `relabel_worktree` / `reclaim_worktree_ownership` need, and the
    proof it cannot widen the guard.

    It exists for a measured reason: `<production>/.worktrees` is root-owned
    on this host, so a test cannot create a worktree there and could not drive
    either host-mutating function at all -- which is how both came to be
    "tested" by reimplementation, with the product function never invoked.
    `runtime.record_runtime` was exempted from this guard outright for the
    same reason; this is that exemption made narrower.

    Narrower has to MEAN something, so: whatever root is passed, production's
    checkout and everything inside it stays refused except under production's
    own `.worktrees`. An override can only move the permitted directory OUT of
    production, never into it.
    """
    root = tmp_path / "prod"
    (root / ".worktrees" / "real").mkdir(parents=True)
    (root / "affine" / "data").mkdir(parents=True)
    elsewhere = tmp_path / "elsewhere"
    (elsewhere / "br-probe" / "inner").mkdir(parents=True)
    monkeypatch.setattr(identity, "production_root", lambda: root)

    # It permits what it is for, and only under the root it was given.
    assert guards.assert_not_production_path(
        elsewhere / "br-probe", worktrees_root=elsewhere)

    for bad, why in [
        # The whole point: an override naming production's checkout, or a
        # directory inside it, buys nothing.
        (root, "production's checkout, with production as the override"),
        (root / "affine" / "data",
         "a real production data directory, with production as the override"),
        (root / ".worktrees",
         "the worktrees directory itself, however it is reached"),
        # An override that does not contain the path is still an override that
        # does not contain the path.
        (elsewhere / "br-probe" / "inner",
         "not a direct child of the given root"),
    ]:
        with pytest.raises(guards.GuardViolation):
            guards.assert_not_production_path(bad, worktrees_root=root)

    # ...and specifically: pointing the override AT production's data
    # directory does not make its contents removable.
    with pytest.raises(guards.GuardViolation):
        guards.assert_not_production_path(
            root / "affine" / "data", worktrees_root=root / "affine")


@pytest.mark.parametrize("module", [branch, mcp], ids=["branch", "mcp"])
def test_every_destructive_call_is_reachable_only_through_a_guard(module):
    """Structural, via AST — not a source-text search.

    Chunk 2 had three separate tests satisfied by a DOCSTRING that happened to
    contain the token being grepped for. So this walks real call nodes: every
    function that issues a destructive docker or git verb must also call a
    guard.

    Task 11 added `aurora_cli.mcp`, which exposes teardown to a caller nobody
    in this repository controls, so the sweep runs over it too. The sweep
    finds nothing there today — `mcp` issues no verb of its own, it dispatches
    to `branch` — and that is the point of running it: the first tool that
    grows its own `docker rm` is caught the day it is written. Because a sweep
    that finds nothing is indistinguishable from a sweep that ran over
    nothing, the source is asserted non-empty first.
    """
    source = inspect.getsource(module)
    assert source.strip(), module.__name__
    tree = ast.parse(source)
    assert any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        for node in ast.walk(tree)
    ), f"{module.__name__} parsed to no functions; this sweep is vacuous"
    destructive = {"rm", "down", "remove", "prune"}
    guard_names = {"assert_branch_project", "assert_not_production_path"}

    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        segment = ast.get_source_segment(source, node) or ""
        issues_destructive = any(
            f'"{verb}"' in segment or f"'{verb}'" in segment
            for verb in destructive
        ) and ("docker" in segment or "git" in segment)
        if not issues_destructive:
            continue
        called = set()
        for inner in ast.walk(node):
            if isinstance(inner, ast.Call):
                target = inner.func
                if isinstance(target, ast.Attribute):
                    called.add(target.attr)
                elif isinstance(target, ast.Name):
                    called.add(target.id)
        if not (called & guard_names):
            offenders.append(node.name)

    assert offenders == [], (
        f"{module.__name__}: functions issuing destructive verbs with no "
        f"guard call: {offenders}"
    )


def test_branch_down_refuses_before_issuing_any_command(monkeypatch):
    """The whole point: refusal happens BEFORE the first subprocess."""
    monkeypatch.setattr(
        identity, "branch_paths",
        lambda name: identity.BranchPaths(
            name="x", project="tai-review", hostname="h", domain="d",
            worktree=identity.production_root() / ".worktrees" / "x",
            env_file=Path("/tmp/none"), access_doc=Path("/tmp/none"),
        ),
    )
    with pytest.raises(guards.GuardViolation):
        branch.branch_down("x", runner=ExplodingRunner())


# ---------------------------------------------------------------------------
# Task 10: rebuild, shell and the two document writers
# ---------------------------------------------------------------------------
#
# The AST sweep above looks for the verbs `rm`, `down`, `remove` and `prune`.
# `aurora branch rebuild` issues NONE of them -- it is `docker compose -p
# br-<name> up -d --build <service>` -- and it recreates a container, which is
# destructive to whatever was in it. Without `-p` the identical command
# recreates PRODUCTION's container of that name. So it is invisible to a verb
# sweep and needs its own gate.
#
# Widening the sweep's verb set to include `up` was the obvious alternative
# and is wrong: `branch_up`'s own compose calls would become offenders, and
# their scoping comes from `identity.branch_paths` forcing the `br-` prefix
# rather than from a guard call. This gate names the functions instead, which
# also makes it fail LOUDLY if one of them is renamed away.

REQUIRED_GUARDS = {
    "branch_down": {"assert_branch_project", "assert_not_production_path"},
    "branch_rebuild": {"assert_branch_project", "assert_not_production_path"},
    "resolve_service_container": {"assert_branch_project"},
    "write_access_doc": {"assert_not_production_path"},
    "write_index": {"assert_worktrees_index_path"},
}


def _calls_in(node) -> set[str]:
    called = set()
    for inner in ast.walk(node):
        if isinstance(inner, ast.Call):
            target = inner.func
            if isinstance(target, ast.Attribute):
                called.add(target.attr)
            elif isinstance(target, ast.Name):
                called.add(target.id)
    return called


def test_every_branch_scoped_command_calls_its_guards():
    """Structural, via AST, per named function.

    Not a source-text search: Chunk 2 had three tests satisfied by a DOCSTRING
    that happened to contain the token being grepped for.
    """
    tree = ast.parse(inspect.getsource(branch))
    functions = {
        node.name: node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    missing = sorted(set(REQUIRED_GUARDS) - set(functions))
    assert not missing, (
        f"these functions no longer exist in branch.py: {missing}. This gate "
        "would otherwise pass by asserting nothing about them."
    )
    offenders = {}
    for name, required in REQUIRED_GUARDS.items():
        absent = sorted(required - _calls_in(functions[name]))
        if absent:
            offenders[name] = absent
    assert offenders == {}, f"guard calls missing: {offenders}"


# ---------------------------------------------------------------------------
# Task 11: the MCP facade hands a destructive operation to an untrusted caller
# ---------------------------------------------------------------------------
#
# The verb sweep above finds nothing in `mcp` on purpose: the facade issues no
# docker verb of its own, it dispatches to `branch`. What makes it dangerous is
# the OTHER end -- the branch name arrives in a JSON-RPC frame from a caller
# nobody in this repository controls. So the gate here is by name, in two
# levels, and it fails loudly if either is renamed away:
#
#   * every tool that can destroy must resolve its target through
#     `_guarded_paths`, and
#   * `_guarded_paths` must call BOTH guards.
#
# One level would not be enough. A gate that only required `_guarded_paths`
# would pass against a `_guarded_paths` that guarded nothing; a gate that only
# required the guard names inside the tools would pass against a tool that
# called them on a value it then discarded.

# `rebuild` is the exception that has to be spelled out rather than waved
# through. It is POINTED AT PRODUCTION deliberately -- that is the whole point
# of it -- so `_guarded_paths`, which refuses production by construction, is
# the wrong guard and demanding it here would mean demanding a tool that could
# never do its job. Its safety argument is a different one and gets a
# different pair of names:
#
#   * `_safe_service_names`, because the service list arrives in a JSON-RPC
#     frame from an untrusted caller and becomes argv, and
#   * `_rebuild_argv`, because that is the ONLY place a command is spelled,
#     which is what makes `test_the_rebuild_tool_can_only_ever_issue_up`
#     able to enumerate every command this tool can issue.
#
# Naming it here rather than adding it to a read-only allowlist is the point:
# an allowlist entry asserts nothing, and `rebuild` is not read-only.
MCP_REQUIRED_GUARDS = {
    "_tool_branch_up": {"_guarded_paths"},
    "_tool_branch_down": {"_guarded_paths"},
    "_tool_rebuild": {"_safe_service_names", "_rebuild_argv"},
    "_guarded_paths": {"assert_branch_project", "assert_not_production_path"},
}


def test_every_destructive_mcp_tool_resolves_its_target_through_the_guards():
    tree = ast.parse(inspect.getsource(mcp))
    functions = {
        node.name: node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    missing = sorted(set(MCP_REQUIRED_GUARDS) - set(functions))
    assert not missing, (
        f"these functions no longer exist in mcp.py: {missing}. This gate "
        "would otherwise pass by asserting nothing about them."
    )
    offenders = {}
    for name, required in MCP_REQUIRED_GUARDS.items():
        absent = sorted(required - _calls_in(functions[name]))
        if absent:
            offenders[name] = absent
    assert offenders == {}, f"guard calls missing: {offenders}"


def test_every_tool_the_facade_declares_is_covered_by_that_gate():
    """Deletion pressure on the gate itself.

    A further mutating tool added to `mcp.TOOLS` without an entry above would
    be unguarded AND invisible, because the gate only inspects the functions
    it names. So the tool table is compared against the gate's own key set,
    and `read_only` is kept as short as it can honestly be -- every name
    parked there is a name this gate stops asserting anything about.
    """
    declared = {tool.name for tool in mcp.TOOLS}
    assert declared, "the facade declares no tools; the gate is vacuous"
    read_only = {"branch_list", "branch_access"}
    destructive = declared - read_only
    assert destructive, "every tool was classified read-only; check this list"
    gated = {
        name[len("_tool_"):] for name in MCP_REQUIRED_GUARDS
        if name.startswith("_tool_")
    }
    assert destructive == gated, (
        f"tools that can destroy but are not named in MCP_REQUIRED_GUARDS: "
        f"{sorted(destructive - gated)}"
    )


#: Service names the rebuild tool must refuse. Every one of these is a string
#: that becomes argv, and the first four are the shapes that turn a service
#: list into a command line. `fjell; rm -rf /` is here because a `re.match`
#: (rather than `fullmatch`) accepts it -- the prefix is a valid service name
#: and the rest is ignored, which is the exact mutation this row pins.
REFUSED_SERVICES = [
    ("--check", "a flag"),
    ("-p", "a short flag Compose reads as a project name"),
    ("--project-name", "the flag that chose the project in the 2026-07-29 incident"),
    ("", "empty string"),
    ("fjell; rm -rf /", "a shell metacharacter after a valid prefix"),
    ("fjell rm", "a space, so two words reach argv as one service"),
    ("../../etc/passwd", "path traversal"),
    ("FJELL", "wrong case; Compose service names are lower-case"),
    ("_fjell", "leading underscore, which no Compose service carries"),
    ("fjell\n", "trailing newline"),
]


@pytest.mark.parametrize(
    "value,why", REFUSED_SERVICES, ids=[repr(r[0]) for r in REFUSED_SERVICES]
)
def test_the_rebuild_tool_refuses_a_service_name_that_is_not_one(value, why):
    with pytest.raises(mcp.ProtocolError) as excinfo:
        mcp._safe_service_names({"services": [value]})
    assert excinfo.value.code == mcp.INVALID_PARAMS, why
    assert "nothing was built" in str(excinfo.value), why


def test_the_rebuild_tool_accepts_the_names_that_are_real():
    """The control. Without it a sanitiser that refused everything would
    satisfy every row above and still be useless."""
    assert mcp._safe_service_names({}) == ()
    assert mcp._safe_service_names(
        {"services": ["fjell", "agent-authz", "dev-admin"]}
    ) == ("fjell", "agent-authz", "dev-admin")


def test_the_rebuild_tool_can_only_ever_issue_up():
    """Enumerate every command this tool can build, and prove none destroys.

    `ops/docker-guard` refuses the destructive verbs at the shell. This asserts
    the same property one layer earlier, over the argv this package produces,
    so a rebuild that started reaching for `down` is caught by a unit test
    rather than by the guard at 3am. `up` is deliberately absent from the
    guard's destructive set, so the guard alone would NOT catch it.
    """
    forbidden = {"down", "rm", "stop", "kill", "restart", "prune", "-v"}
    seen = []
    for check in (True, False):
        for services in ((), ("fjell",), ("fjell", "dev-admin")):
            argv = mcp._rebuild_argv(check, services)
            seen.append(argv)
            assert argv[:2] == ["bash", mcp.REBUILD_SCRIPT], argv
            assert not forbidden & set(argv), argv
            if services:
                assert "--" in argv and argv.index("--") < argv.index(services[0]), (
                    "service names are not separated from flags by `--`, so a "
                    f"name could still be read as one: {argv}"
                )
    assert len(seen) == 6, "the enumeration did not run; this proves nothing"


def test_the_document_writers_delegate_every_write_to_one_seam():
    """One tripwire must cover the `mkdir` AND the bytes.

    Task 5 moved production's `forgejo/` mtime through a `mkdir` that the
    tripwire did not cover, and Task 8's delegation gate immediately found a
    second one. `.worktrees/INDEX.md` is written INSIDE production's checkout
    by design, so this is the same hazard with a shorter fuse.
    """
    source = inspect.getsource(branch)
    tree = ast.parse(source)
    functions = {
        node.name: node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    for name in ("write_access_doc", "write_index", "refresh_branch_docs"):
        assert name in functions, name
        called = _calls_in(functions[name])
        inline = called & {"write_text", "write_bytes", "mkdir", "open", "chmod"}
        assert not inline, (
            f"{name} writes inline ({sorted(inline)}) instead of delegating to "
            "_write_document; one tripwire no longer covers every write"
        )
        assert "_write_document" in called or name == "refresh_branch_docs", (
            f"{name} does not go through the single write seam"
        )
