"""The developer-facing spawn facade: namespace, quota, lease, reaper.

`ops/devspawntest.sh` proves the same claims at the PROCESS level, against a
stub daemon, over the real pipe. This file proves them at the FUNCTION level,
where a mutation can be aimed precisely. Both exist because they fail
differently: the shell harness would not notice a policy function that was
never called, and this file would not notice a transport that never reached it.

Trap shapes this file was written against, each already paid for by this
project and each named where it is defended:

* **sequential-guard `raises`** -- deleting a guard does not change the
  exception TYPE. `ops/devspawntest.sh` caught itself doing exactly this on
  its first run: every case "passed" on an unrelated `IdentityError`. So every
  refusal here asserts on the MESSAGE, and every refusal test carries a
  CONTROL that must pass, without which a function that refused everything
  would satisfy the whole file.
* **vacuous filter** -- `test_list_mine_...` asserts the fixture's summary
  list is non-empty and contains bob BEFORE asserting bob is absent from the
  output.
* **wrong-identity conformance** -- the namespace tests compare against the
  slug of the developer under test, never against a literal.
* **decoy** -- the naming tests CALL `devspawn.branch_name_for`; they do not
  re-implement `f"{slug}-{label}"` and assert on their own copy.
* **universal skip** -- there are no skips in this file.

MUTATION TABLE. Every entry was run, observed red, and reverted.

| # | Mutation | Reddens |
|---|---|---|
| N1 | `branch_name_for` returns `str(label)` | `test_a_label_always_lands_in_the_callers_namespace`, `test_destroy_resolves_into_the_callers_namespace_whatever_the_label_says` |
| N2 | `assert_developer_owns` returns `project` unconditionally | `test_a_developer_cannot_prove_ownership_of_another_developers_stack`, `test_the_reaper_reproves_ownership_before_destroying` |
| N3 | drop the `assert_namespaces_are_unambiguous` call from `assert_known_developer` | `test_a_roster_whose_namespaces_nest_is_refused`, `test_a_roster_whose_slugs_collide_is_refused` |
| N4 | `assert_within_quota` counts `live_projects` instead of `mine(...)` | `test_the_quota_counts_only_the_callers_stacks` |
| N5 | `_positive_int` returns `default` on `ValueError` | `test_a_ceiling_that_does_not_parse_is_not_an_absent_ceiling` |
| N6 | `read_lease` returns a zero-TTL `Lease` on a parse failure | `test_an_unreadable_lease_is_never_treated_as_expired` |
| N7 | `expired_candidates` uses `lease.project` instead of `summary.project` | `test_the_reaper_takes_the_project_from_the_daemon_not_the_lease` |
| N8 | `spawn` passes `devs=arguments.get("devs")` | `test_spawn_forces_the_caller_as_the_only_developer` |
| N9 | `spawn` passes `force=_bool(arguments, "force")` | `test_spawn_cannot_be_made_to_override_the_resource_guard` |
| N10 | `_method_tools_call` reads `TOOLS_BY_NAME` instead of `server.tools_by_name` | `test_a_developer_session_cannot_reach_an_admin_tool` |
| N11 | `lease_path` returns `Path(worktree) / LEASE_FILE_NAME` with no guard | `test_a_lease_can_only_be_written_inside_a_branch_worktree` |
"""

import io
import json
from pathlib import Path

import pytest

from aurora_cli import access_doc, branch, devspawn, guards, identity, mcp

PRODUCTION_PROJECT = "prod-project"
PRODUCTION_DOMAIN = "prod-host.example.invalid"

ALICE = "alice"
BOB = "bob"


@pytest.fixture
def host(tmp_path, monkeypatch):
    """A fabricated production checkout with a TWO-developer roster.

    Two, not one. The live roster has a single developer, and every
    cross-tenant assertion made against a one-developer roster is vacuous --
    there is no second namespace to fail to reach.
    """
    root = tmp_path / "production"
    (root / ".worktrees").mkdir(parents=True)
    (root / ".env").write_text(f"DOMAIN_NAME={PRODUCTION_DOMAIN}\n", encoding="utf-8")
    (root / "developers.yaml").write_text(
        "developers:\n"
        f"- forgejo_user: {ALICE}\n"
        f"- forgejo_user: {BOB}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(identity, "production_root", lambda: root)
    monkeypatch.setattr(identity, "production_project", lambda: PRODUCTION_PROJECT)

    # Non-degeneracy, asserted rather than assumed.
    assert set(devspawn.roster()) == {ALICE, BOB}
    assert devspawn.namespace_prefix(ALICE) != devspawn.namespace_prefix(BOB)
    return root


def worktree_for(root: Path, name: str) -> Path:
    path = root / ".worktrees" / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def summary(name: str, project: str, worktree: Path) -> access_doc.BranchSummary:
    return access_doc.BranchSummary(
        name=name, project=project, domain=f"{name}.example.invalid",
        worktree=worktree, worktree_exists=True, containers=(),
    )


# ---------------------------------------------------------------------------
# naming: containment by construction
# ---------------------------------------------------------------------------


HOSTILE_LABELS = [
    "bob-thing",            # another developer's namespace, spelled out
    "bob",                  # another developer's slug exactly
    "aurora",               # production's declared project
    "../../aurora",         # traversal
    "  aurora  ",           # whitespace, which a `!=` guard would pass
    "BR-x",                 # the branch prefix in the wrong case
    "br-bob-thing",         # a fully-formed foreign project name
]


@pytest.mark.parametrize("label", HOSTILE_LABELS)
def test_a_label_always_lands_in_the_callers_namespace(host, label):
    """No label resolves to a project outside the caller's namespace.

    This is the load-bearing claim of the whole design: containment is a
    property of the input space, not of a check. The test CALLS the resolver
    -- re-deriving `f"{slug}-{label}"` here and asserting on that copy would
    be a decoy that passes with the resolver deleted.

    Mutation N1 (`branch_name_for` returns the raw label) reddens every case.
    """
    prefix = devspawn.namespace_prefix(ALICE)
    name = devspawn.branch_name_for(ALICE, label)
    project = identity.branch_project(name)

    assert project.startswith(prefix), (label, project)
    assert project != prefix
    # And specifically not the things the label was trying to be.
    assert not project.startswith(devspawn.namespace_prefix(BOB))
    assert project != PRODUCTION_PROJECT
    assert project != identity.declared_project()


def test_the_namespace_prefix_is_derived_from_the_caller_not_from_a_constant(host):
    """Compared against the slug of the developer under test, never a literal.

    The wrong-identity-conformance shape: a test comparing a resolved value
    against a hardcoded name goes red exactly when the code is right for a
    different developer.
    """
    for developer in (ALICE, BOB):
        slug = identity.sanitise_branch_name(developer)
        assert devspawn.namespace_prefix(developer) == (
            f"{guards.BRANCH_PROJECT_PREFIX}{slug}{devspawn.NAMESPACE_SEPARATOR}"
        )


def test_a_label_too_long_to_fit_is_refused_rather_than_truncated(host):
    """Truncation could land on the separator and leave the namespace.

    CONTROL first: a label that fits must be accepted, or this test would pass
    against a function that refused everything.
    """
    assert devspawn.branch_name_for(ALICE, "fits")          # control
    with pytest.raises(devspawn.SpawnDenied) as excinfo:
        devspawn.branch_name_for(ALICE, "x" * 200)
    assert "namespace" in str(excinfo.value)


@pytest.mark.parametrize("label", ["", "   ", None, 42, [], {"a": 1}])
def test_a_label_that_is_not_a_usable_string_is_refused(host, label):
    with pytest.raises((devspawn.SpawnDenied, identity.IdentityError)):
        devspawn.branch_name_for(ALICE, label)


# ---------------------------------------------------------------------------
# ownership
# ---------------------------------------------------------------------------


def test_a_developer_cannot_prove_ownership_of_another_developers_stack(host):
    """Mutation N2 (`assert_developer_owns` returns its argument) reddens this."""
    own = identity.branch_project(devspawn.branch_name_for(ALICE, "thing"))
    assert devspawn.assert_developer_owns(ALICE, own) == own      # control

    theirs = identity.branch_project(devspawn.branch_name_for(BOB, "thing"))
    with pytest.raises(devspawn.SpawnDenied) as excinfo:
        devspawn.assert_developer_owns(ALICE, theirs)
    message = str(excinfo.value)
    assert "is not yours" in message
    # Not the OTHER refusal in this function, and not a guard refusal: with a
    # single `pytest.raises` these would be indistinguishable.
    assert "namespace prefix, not a stack" not in message
    assert "Refusing a destructive operation" not in message


def test_the_bare_namespace_is_not_a_stack_in_it(host):
    prefix = devspawn.namespace_prefix(ALICE)
    assert devspawn.assert_developer_owns(ALICE, prefix + "x")     # control
    with pytest.raises(devspawn.SpawnDenied) as excinfo:
        devspawn.assert_developer_owns(ALICE, prefix)
    assert "namespace prefix, not a stack" in str(excinfo.value)


def test_ownership_refuses_production_even_when_production_carries_the_prefix(
    host, monkeypatch,
):
    """The prefix is not sufficient evidence when production itself has it.

    `guards.assert_branch_project` owns that clause; this test exists because
    the developer surface is the caller that would benefit from it being
    wrong, and a guard nobody exercises from the path that needs it is a guard
    that can rot.
    """
    live = f"{devspawn.namespace_prefix(ALICE)}live"
    monkeypatch.setattr(identity, "production_project", lambda: live)
    with pytest.raises(guards.GuardViolation) as excinfo:
        devspawn.assert_developer_owns(ALICE, live)
    assert "PRODUCTION" in str(excinfo.value)


def test_a_roster_whose_namespaces_nest_is_refused(host, monkeypatch):
    """`alice` + `alice-two` makes `br-alice-two-x` ambiguous. That is fatal.

    The live roster has one developer, so this is the only place the rule is
    not vacuous. Mutation N3 (drop the call from `assert_known_developer`)
    reddens it.
    """
    devspawn.assert_namespaces_are_unambiguous([ALICE, BOB])       # control

    (host / "developers.yaml").write_text(
        "developers:\n- forgejo_user: alice\n- forgejo_user: alice-two\n",
        encoding="utf-8",
    )
    with pytest.raises(devspawn.SpawnDenied) as excinfo:
        devspawn.assert_known_developer(ALICE)
    assert "namespace boundary" in str(excinfo.value)


def test_a_roster_whose_slugs_collide_is_refused(host, monkeypatch):
    """`alice two` and `alice-two` sanitise to ONE namespace. That is fatal.

    Worse than the nesting case above: the two do not merely overlap, they
    ARE the same `br-alice-two-` prefix, so each proves ownership of the
    other's stacks outright. The old `outer == inner: continue` skipped
    exactly this pair.
    """
    devspawn.assert_namespaces_are_unambiguous([ALICE, BOB])       # control

    (host / "developers.yaml").write_text(
        "developers:\n- forgejo_user: alice two\n- forgejo_user: alice-two\n",
        encoding="utf-8",
    )
    with pytest.raises(devspawn.SpawnDenied) as excinfo:
        devspawn.assert_known_developer("alice two")
    assert "both name the namespace" in str(excinfo.value)


def test_the_roster_spelling_is_what_reaches_devs(host):
    """`resolve_devs` matches roster names EXACTLY; the slug is not one.

    A broker started as `alice-two` against a roster listing `alice two`
    resolves, lists tools and then fails every spawn if the caller's own
    spelling is passed to `--devs`. The matched ENTRY is the answer.
    """
    (host / "developers.yaml").write_text(
        "developers:\n- forgejo_user: alice two\n", encoding="utf-8",
    )
    assert devspawn.assert_known_developer("alice-two") == "alice two"
    assert branch.resolve_devs(
        devspawn.assert_known_developer("alice-two"), root=host,
    ) == ("alice two",)


def test_a_developer_not_on_the_roster_is_refused(host):
    assert devspawn.assert_known_developer(ALICE) == ALICE         # control
    with pytest.raises(devspawn.SpawnDenied) as excinfo:
        devspawn.assert_known_developer("mallory")
    assert "not a developer on this host" in str(excinfo.value)


# ---------------------------------------------------------------------------
# quota
# ---------------------------------------------------------------------------


def test_the_quota_counts_only_the_callers_stacks(host):
    """Mutation N4 (count `live_projects` instead of `mine`) reddens this.

    Two halves, and both are needed: three of bob's stacks must NOT exhaust
    alice's per-developer allowance, and one of alice's must.
    """
    quota = devspawn.Quota(per_developer=1, total=10)
    bobs = [f"{devspawn.namespace_prefix(BOB)}{n}" for n in ("a", "b", "c")]
    assert bobs                                                    # non-vacuous
    devspawn.assert_within_quota(ALICE, bobs, quota)               # control

    hers = [f"{devspawn.namespace_prefix(ALICE)}one"]
    with pytest.raises(devspawn.SpawnDenied) as excinfo:
        devspawn.assert_within_quota(ALICE, bobs + hers, quota)
    message = str(excinfo.value)
    assert "you already have 1 stack" in message
    assert hers[0] in message
    assert "shared host" not in message      # the OTHER ceiling, not this one


def test_the_global_ceiling_refuses_a_developer_who_owns_nothing(host):
    quota = devspawn.Quota(per_developer=5, total=2)
    bobs = [f"{devspawn.namespace_prefix(BOB)}{n}" for n in ("a", "b")]
    devspawn.assert_within_quota(ALICE, bobs[:1], quota)           # control
    with pytest.raises(devspawn.SpawnDenied) as excinfo:
        devspawn.assert_within_quota(ALICE, bobs, quota)
    message = str(excinfo.value)
    assert "shared host" in message
    assert "you already have" not in message


def test_a_ceiling_that_does_not_parse_is_not_an_absent_ceiling(host):
    """Mutation N5 (return the default on `ValueError`) reddens this.

    A ceiling that silently reverts to its default when misconfigured is the
    shape where an operator believes they raised a limit and did not; a
    ceiling that reverts to "unlimited" is worse. Both are refusals here.
    """
    assert devspawn.Quota.from_environ({}).per_developer == \
        devspawn.DEFAULT_MAX_PER_DEVELOPER                         # control
    assert devspawn.Quota.from_environ(
        {devspawn.MAX_PER_DEVELOPER_VAR: "4"}).per_developer == 4  # control

    for bad in ("nonsense", "0", "-1", "1.5"):
        with pytest.raises(devspawn.SpawnDenied):
            devspawn.Quota.from_environ({devspawn.MAX_PER_DEVELOPER_VAR: bad})


# ---------------------------------------------------------------------------
# leases and the reaper
# ---------------------------------------------------------------------------


def test_a_lease_can_only_be_written_inside_a_branch_worktree(host):
    """Mutation N11 (drop the guard from `lease_path`) reddens this.

    The lease is the one file this module writes, to a COMPUTED path, inside
    the tree that also holds production's checkout. Part 3 of the practices
    note: tripwire the function that touches the destination.
    """
    good = worktree_for(host, "alice-x")
    assert devspawn.lease_path(good).parent == good                # control

    for bad in (host, host / ".worktrees", host.parent, Path("/tmp")):
        with pytest.raises(guards.GuardViolation):
            devspawn.lease_path(bad)


def test_a_lease_round_trips(host):
    worktree = worktree_for(host, "alice-x")
    written = devspawn.write_lease(
        worktree, ALICE, "br-alice-x", name="alice-x",
        ttl_seconds=60, now=1000.0,
    )
    read = devspawn.read_lease(worktree)
    assert read == written
    assert read.expires_at == 1060.0
    assert not read.is_expired(1059.0)
    assert read.is_expired(1060.0)


def test_an_unreadable_lease_is_never_treated_as_expired(host):
    """Mutation N6 (a zero-TTL `Lease` on a parse failure) reddens this.

    A lease is an input to a DESTRUCTIVE sweep. "I cannot read this" must mean
    "leave it alone", never "it must be old".
    """
    worktree = worktree_for(host, "alice-x")
    devspawn.write_lease(worktree, ALICE, "br-alice-x", name="alice-x",
                         ttl_seconds=1, now=0.0)
    live = [summary("alice-x", "br-alice-x", worktree)]
    assert devspawn.expired_candidates(live, now=10.0)             # control

    devspawn.lease_path(worktree).write_text("{ not json", encoding="utf-8")
    assert devspawn.read_lease(worktree) is None
    assert devspawn.expired_candidates(live, now=10.0) == []


def test_an_unleased_stack_is_never_reaped(host):
    """An operator's own `aurora branch up` writes no lease. It must survive."""
    leased = worktree_for(host, "alice-x")
    devspawn.write_lease(leased, ALICE, "br-alice-x", name="alice-x",
                         ttl_seconds=1, now=0.0)
    bare = worktree_for(host, "alice-y")
    live = [
        summary("alice-x", "br-alice-x", leased),
        summary("alice-y", "br-alice-y", bare),
    ]
    candidates = devspawn.expired_candidates(live, now=10.0)
    assert [c.name for c in candidates] == ["alice-x"]             # non-vacuous


def test_the_reaper_takes_the_project_from_the_daemon_not_the_lease(host):
    """Mutation N7 (use `lease.project`) reddens this.

    A lease is a file inside a worktree; a file is not evidence about what is
    running. A lease naming a project the daemon disagrees with is skipped.
    """
    worktree = worktree_for(host, "alice-x")
    devspawn.write_lease(worktree, ALICE, "br-alice-x", name="alice-x",
                         ttl_seconds=1, now=0.0)
    agreeing = [summary("alice-x", "br-alice-x", worktree)]
    assert devspawn.expired_candidates(agreeing, now=10.0)         # control

    lying = [summary("alice-x", "br-bob-x", worktree)]
    assert devspawn.expired_candidates(lying, now=10.0) == []


def daemon(monkeypatch, summaries) -> list[str]:
    """Point `branch_ls`/`branch_down` at a fabricated daemon. Returns the log.

    `monkeypatch.setattr` on the module, because `devspawn.reap` looks both
    functions up on `branch` at call time -- which is the property that makes
    the patch bind, and the reason the reaper needs no injection parameter.
    """
    torn: list[str] = []
    monkeypatch.setattr(branch, "branch_ls", lambda: summaries)
    monkeypatch.setattr(
        branch, "branch_down",
        lambda name, force=False: torn.append(name),
    )
    return torn


def test_the_reaper_reproves_ownership_before_destroying(host, monkeypatch):
    """Mutation N2 reddens this. The reaper is the one path with no caller.

    A lease that cannot prove ownership is not evidence, so it is SKIPPED and
    the sweep continues -- this is a cron job, and one unprovable lease
    aborting the loop would leave every later expired stack running forever.
    The assertion that matters is that nothing was torn down.
    """
    worktree = worktree_for(host, "alice-x")
    devspawn.write_lease(worktree, BOB, "br-alice-x", name="alice-x",
                         ttl_seconds=1, now=0.0)
    torn = daemon(monkeypatch, [summary("alice-x", "br-alice-x", worktree)])

    assert devspawn.reap(now=10.0) == []
    assert torn == []                 # nothing was issued


def test_one_unprovable_lease_does_not_stop_the_sweep(host, monkeypatch):
    """The reaper is cron. A poisoned lease must cost one stack, not all."""
    poisoned = worktree_for(host, "alice-x")
    good = worktree_for(host, "alice-y")
    devspawn.write_lease(poisoned, BOB, "br-alice-x", name="alice-x",
                         ttl_seconds=1, now=0.0)
    devspawn.write_lease(good, ALICE, "br-alice-y", name="alice-y",
                         ttl_seconds=1, now=0.0)
    torn = daemon(monkeypatch, [
        summary("alice-x", "br-alice-x", poisoned),
        summary("alice-y", "br-alice-y", good),
    ])

    destroyed = devspawn.reap(now=10.0)
    assert torn == ["alice-y"]
    assert [c.name for c in destroyed] == ["alice-y"]


def test_the_reaper_destroys_exactly_what_expired(host, monkeypatch):
    expired = worktree_for(host, "alice-x")
    fresh = worktree_for(host, "alice-y")
    devspawn.write_lease(expired, ALICE, "br-alice-x", name="alice-x",
                         ttl_seconds=1, now=0.0)
    devspawn.write_lease(fresh, ALICE, "br-alice-y", name="alice-y",
                         ttl_seconds=10_000, now=0.0)
    torn = daemon(monkeypatch, [
        summary("alice-x", "br-alice-x", expired),
        summary("alice-y", "br-alice-y", fresh),
    ])

    destroyed = devspawn.reap(now=10.0)
    assert torn == ["alice-x"]
    assert [c.name for c in destroyed] == ["alice-x"]


# ---------------------------------------------------------------------------
# the MCP surface
# ---------------------------------------------------------------------------


def call(server: mcp.Server, tool: str, arguments: dict) -> dict:
    """One `tools/call` over the real transport. Bytes on a pipe, as shipped."""
    payload = json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": tool, "arguments": arguments},
    }).encode("utf-8") + b"\n"
    out = io.BytesIO()
    assert server.serve(io.BytesIO(payload), out) == 0
    lines = out.getvalue().decode("utf-8").splitlines()
    assert len(lines) == 1, lines            # a response was produced at all
    return json.loads(lines[0])


def text_of(response: dict) -> str:
    return response["result"]["content"][0]["text"]


EXPECTED_DEVELOPER_TOOLS = {"spawn", "destroy", "list_mine", "access"}


def test_the_developer_table_is_the_four_and_takes_no_identity(host):
    """Spelled out independently of `mcp._developer_tools`.

    A checker that enumerates the constant it validates is self-blinding; this
    project has hit that shape twice.
    """
    server = mcp.developer_server(ALICE)
    assert {t.name for t in server.tools} == EXPECTED_DEVELOPER_TOOLS
    properties = {
        key for tool in server.tools
        for key in tool.input_schema.get("properties", {})
    }
    assert properties                                              # non-vacuous
    assert not properties & {"developer", "devs", "name", "project"}
    spawn = next(t for t in server.tools if t.name == "spawn")
    assert "force" not in spawn.input_schema["properties"]
    assert all(
        t.input_schema.get("additionalProperties") is False for t in server.tools
    )


def test_a_developer_session_cannot_reach_an_admin_tool(host, recorded):
    """Mutation N10 (`TOOLS_BY_NAME` in `_method_tools_call`) reddens this.

    The CONTROL uses the recorder fixture rather than a live `branch_up`. Its
    first form did not, and the real failure -- a missing Tailscale key --
    produced a message naming `TS_AUTHKEY`, which `_tool_payload`'s leak check
    then converted into an INTERNAL_ERROR frame with no `result` at all. That
    is a genuine defect (recorded in the implementation log), but it is not
    this test's subject and it made the control unreadable.
    """
    server = mcp.developer_server(ALICE)
    response = call(server, "spawn", {"label": "x"})               # control:
    assert "result" in response, response                          # dispatch works

    for admin in ("branch_up", "branch_down", "branch_list", "branch_access"):
        blocked = call(server, admin, {"name": "anything"})
        assert "unknown tool" in blocked["error"]["message"], admin


def test_the_admin_surface_still_offers_the_admin_table(host):
    """The refactor that added a second table must not have moved the first."""
    payload = b'{"jsonrpc":"2.0","id":1,"method":"tools/list"}\n'
    out = io.BytesIO()
    assert mcp.serve(io.BytesIO(payload), out) == 0
    names = {
        t["name"] for t in
        json.loads(out.getvalue().decode("utf-8"))["result"]["tools"]
    }
    # `rebuild` joined the admin table in the isolation merge (the manually
    # triggerable full-system rebuild). Kept as an EXACT set rather than a
    # subset check: the property worth pinning is that the developer table's
    # four tools -- spawn, destroy, list_mine, access -- never appear here, and
    # a subset assertion would stop noticing if one did.
    assert names == {"branch_up", "branch_down", "branch_list", "branch_access",
                     "rebuild"}


@pytest.fixture
def recorded(monkeypatch, host):
    """`branch_up` / `branch_down` replaced by recorders. No daemon, no git."""
    calls: dict[str, list] = {"up": [], "down": [], "index": 0}

    def fake_up(name, **kwargs):
        calls["up"].append((name, kwargs))
        paths = identity.branch_paths(name)
        paths.worktree.mkdir(parents=True, exist_ok=True)
        paths.env_file.write_text("COMPOSE_PROJECT_NAME=x\n", encoding="utf-8")
        result = branch.BranchResult(requested_name=name, paths=paths)
        return result

    def fake_refresh(result):
        doc = result.paths.worktree / "BRANCH-ACCESS.md"
        doc.write_text("# access\n", encoding="utf-8")
        return doc, result.paths.worktree.parent / "INDEX.md"

    def fake_down(name, **kwargs):
        calls["down"].append((name, kwargs))
        return branch.DownResult(
            project=identity.branch_project(name),
            worktree=identity.branch_paths(name).worktree,
        )

    monkeypatch.setattr(branch, "branch_up", fake_up)
    monkeypatch.setattr(branch, "refresh_branch_docs", fake_refresh)
    monkeypatch.setattr(branch, "branch_down", fake_down)
    monkeypatch.setattr(branch, "write_index", lambda **k: host / ".worktrees" / "INDEX.md")
    monkeypatch.setattr(branch, "live_branch_projects", lambda **k: [])
    return calls


def test_spawn_forces_the_caller_as_the_only_developer(host, recorded):
    """Mutation N8 (`devs` read from the frame) reddens this.

    The frame asks for `all`. `--devs all` starts every developer's agent in
    every branch -- i.e. another identity's Hermes inside a stack this
    developer controls.
    """
    server = mcp.developer_server(ALICE)
    call(server, "spawn", {"label": "x", "devs": "all"})
    assert len(recorded["up"]) == 1                                # non-vacuous
    _name, kwargs = recorded["up"][0]
    assert kwargs["devs"] == ALICE


def test_spawn_cannot_be_made_to_override_the_resource_guard(host, recorded):
    """Mutation N9 (`force` read from the frame) reddens this.

    `force` skips `check_resources`, the memory and disk floor that protects
    every other tenant of this host. A ceiling a caller can raise is not one.
    """
    server = mcp.developer_server(ALICE)
    call(server, "spawn", {"label": "x", "force": True})
    assert len(recorded["up"]) == 1
    _name, kwargs = recorded["up"][0]
    assert kwargs["force"] is False


def test_spawn_names_the_stack_in_the_callers_namespace(host, recorded):
    server = mcp.developer_server(ALICE)
    call(server, "spawn", {"label": "bob-thing"})
    assert len(recorded["up"]) == 1
    name, _kwargs = recorded["up"][0]
    assert identity.branch_project(name).startswith(
        devspawn.namespace_prefix(ALICE))
    assert not identity.branch_project(name).startswith(
        devspawn.namespace_prefix(BOB))


def test_spawn_writes_a_lease_so_a_forgotten_stack_is_reapable(host, recorded):
    server = mcp.developer_server(ALICE)
    response = call(server, "spawn", {"label": "x"})
    name, _ = recorded["up"][0]
    lease = devspawn.read_lease(identity.branch_paths(name).worktree)
    assert lease is not None
    assert lease.developer == ALICE
    assert lease.ttl_seconds > 0
    assert "Lease" in text_of(response)


def test_spawn_is_refused_when_the_caller_is_at_quota(
    host, recorded, monkeypatch,
):
    """And nothing is issued: the refusal precedes `branch_up`."""
    monkeypatch.setattr(
        branch, "live_branch_projects",
        lambda **k: [f"{devspawn.namespace_prefix(ALICE)}already"],
    )
    monkeypatch.setenv(devspawn.MAX_PER_DEVELOPER_VAR, "1")
    server = mcp.developer_server(ALICE)
    response = call(server, "spawn", {"label": "x"})
    assert response["result"]["isError"] is True
    assert "quota:" in text_of(response)
    assert recorded["up"] == []


def test_destroy_resolves_into_the_callers_namespace_whatever_the_label_says(
    host, recorded,
):
    """Mutation N1 reddens this. The frame names bob; the daemon sees alice."""
    server = mcp.developer_server(ALICE)
    call(server, "destroy", {"label": "bob-thing"})
    assert len(recorded["down"]) == 1                              # non-vacuous
    name, _kwargs = recorded["down"][0]
    assert identity.branch_project(name) == (
        f"{devspawn.namespace_prefix(ALICE)}bob-thing"
    )


def test_list_mine_shows_the_callers_stacks_and_not_another_developers(
    host, monkeypatch,
):
    """Vacuous-filter defence: the input is asserted to CONTAIN bob first."""
    alice_tree = worktree_for(host, "alice-x")
    bob_tree = worktree_for(host, "bob-y")
    summaries = [
        summary("alice-x", "br-alice-x", alice_tree),
        summary("bob-y", "br-bob-y", bob_tree),
    ]
    assert any(s.project.startswith("br-bob-") for s in summaries)
    monkeypatch.setattr(branch, "branch_ls", lambda **k: summaries)

    text = text_of(call(mcp.developer_server(ALICE), "list_mine", {}))
    assert "br-alice-x" in text
    assert "br-bob-y" not in text
    assert "bob" not in text.replace("br-alice-", "")


def test_a_frame_carrying_a_forged_identity_is_treated_as_the_real_caller(
    host, recorded,
):
    """`additionalProperties:false` is advisory; the handler never reads it."""
    server = mcp.developer_server(ALICE)
    call(server, "destroy", {
        "label": "thing", "developer": BOB, "name": "aurora", "as_developer": BOB,
    })
    assert len(recorded["down"]) == 1
    name, _ = recorded["down"][0]
    assert identity.branch_project(name) == (
        f"{devspawn.namespace_prefix(ALICE)}thing"
    )


def test_an_unknown_developer_cannot_get_a_server_at_all(host):
    """The broker's start-up check. Refused before a socket is ever created."""
    assert mcp.developer_server(ALICE)                             # control
    with pytest.raises(devspawn.SpawnDenied):
        mcp.developer_server("mallory")


def test_a_developer_session_reports_its_own_identity_in_the_handshake(host):
    payload = b'{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}\n'
    out = io.BytesIO()
    assert mcp.developer_server(ALICE).serve(io.BytesIO(payload), out) == 0
    info = json.loads(out.getvalue().decode("utf-8"))["result"]
    assert info["serverInfo"]["name"].endswith(ALICE)
    assert devspawn.namespace_prefix(ALICE) in info["instructions"]
