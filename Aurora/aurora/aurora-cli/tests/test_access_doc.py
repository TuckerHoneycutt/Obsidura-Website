"""`BRANCH-ACCESS.md`, `INDEX.md`, `ls`, `access`, `shell`, `rebuild` (Task 10).

The documents here are the PRODUCT (spec 7.4): the same string is CLI stdout,
the file in the worktree, and the MCP tool result. So these tests are about
what a human is told, and the three things they must never be told are a
secret, a URL that does not work, and a container name this package invented.

Trap shapes this file was written against, each of which has already cost this
project real time:

* **sequential-guard `raises`** -- `AccessDocError` comes from four distinct
  checks, so every `pytest.raises` here asserts on the MESSAGE and, where two
  checks could fire on one input, that the other's wording is ABSENT. Each
  such test ends with a control: a legitimate input that returns normally,
  without which a renderer that refused everything would satisfy all of them.
* **self-blinding artefact** -- the secret scrubber is driven by
  `branch-env.yaml`'s `secret:` flag, so deleting that flag would blind it.
  The independent pressure is `test_the_manifest_marks_the_auth_key_secret`,
  which names the variable, plus `secret_variables()`'s own refusal to return
  an empty set.
* **artifact-vs-generator** -- the renderer is exercised here against
  fabricated rows, and `tests/test_branch_access.py` exercises the same
  renderer against a REAL `br-` stack's real `docker compose ps`. Neither one
  alone would catch a parser that agreed with a double and disagreed with
  Compose.
* **vacuous pass** -- no assertion is made over a set without first asserting
  the set is non-empty, and the fixture asserts its own non-degeneracy: the
  fabricated production domain and the fabricated branch domain must DIFFER
  while sharing a tailnet suffix (Task 7's fixture lesson), or "the document
  never names production" is true of a document that names nothing.
* **code-path vacuity** -- Task 9's first mutation run caught 6 of 10 because
  two tests never executed the branch of the `if` they asserted about. Every
  test here that asserts about an argv also asserts that at least one command
  was issued.
"""

import json
import subprocess
from pathlib import Path

import pytest

from aurora_cli import access_doc, branch, crosswire, envfile, guards, identity, seed
from aurora_cli import __main__ as cli
from aurora_cli import runtime as runtimes

# ---------------------------------------------------------------------------
# doubles
# ---------------------------------------------------------------------------

PRODUCTION_DOMAIN = "prod-host.example.invalid"
PRODUCTION_PROJECT = "prod-project"

#: Recorded verbatim from this host, `docker compose -p br-psprobe ps -a
#: --format json` on Compose v5.3.1, trimmed to the fields the parser reads.
#: A recorded transcript rather than a hand-built dict: the parse is pinned
#: against what Compose actually emits, which is NDJSON and not a JSON array.
#:
#: **The probe was scaled to two replicas of `beta` on purpose, and the first
#: version of this transcript was not.** Without `br-psprobe-beta-2` in it,
#: every name here is exactly what `f"{Project}-{Service}-1"` produces, and
#: the mutation that replaces the parse with that concatenation SURVIVED --
#: the decoy pattern this project has now hit three times, in my own recorded
#: evidence. A transcript whose names a mutant could have invented pins
#: nothing.
RECORDED_PS = (
    '{"Health":"","Name":"br-psprobe-alpha-1","Names":"br-psprobe-alpha-1",'
    '"Project":"br-psprobe","Service":"alpha","State":"running",'
    '"Status":"Up Less than a second"}\n'
    '{"Health":"","Name":"br-psprobe-beta-1","Names":"br-psprobe-beta-1",'
    '"Project":"br-psprobe","Service":"beta","State":"running",'
    '"Status":"Up Less than a second"}\n'
    '{"Health":"healthy","Name":"br-psprobe-beta-2","Names":"br-psprobe-beta-2",'
    '"Project":"br-psprobe","Service":"beta","State":"exited",'
    '"Status":"Exited (0) 1 second ago"}\n'
)

#: A container name Compose would produce that NO concatenation of project,
#: service and `-1` produces. The whole point of the decoy: a test that used
#: `br-demo-forgejo-1` would pass against the mutation it exists to catch.
SURPRISING = "br-demo-forgejo-2"


class FakeRunner(branch.CommandRunner):
    """Canned stdout per command, and a full recording. No subprocess."""

    def __init__(self, replies=None):
        super().__init__()
        self.replies = list(replies or [])

    def _execute(self, argv, *, cwd, env, input, stdin, timeout):
        for match, stdout in self.replies:
            if all(token in argv for token in match):
                return branch.CommandResult(argv, 0, stdout, "")
        return branch.CommandResult(argv, 0, "", "")


class ExplodingRunner(branch.CommandRunner):
    """Any command at all is a failure. Not a recorder -- a mine."""

    def run(self, argv, **kwargs):  # pragma: no cover - must never run
        raise AssertionError(f"a guard let a command through: {list(argv)!r}")


def ps_reply(rows, project="br-demo"):
    lines = "".join(
        json.dumps({
            "Service": r.service, "Name": r.name, "State": r.state,
            "Status": r.status, "Health": r.health,
        }) + "\n"
        for r in rows
    )
    return ((project, "ps"), lines)


ROWS = (
    access_doc.ContainerRow("caddy", "br-demo-caddy-1", "running", "Up 3m"),
    access_doc.ContainerRow("forgejo", SURPRISING, "running", "Up 3m", "healthy"),
    access_doc.ContainerRow("tailscale", "br-demo-tailscale-1", "running", "Up 3m"),
)


# ---------------------------------------------------------------------------
# the fabricated production
# ---------------------------------------------------------------------------


@pytest.fixture
def fabricated(tmp_path, monkeypatch):
    """A production checkout, a branch worktree, and nothing real anywhere.

    Production's `.env` and the branch's `.env` are DIFFERENT files carrying
    DIFFERENT domains, deliberately. Task 7 recorded the fixture defect this
    avoids: with one shared `.env`, code that read the branch's own file
    instead of production's was indistinguishable from correct code.
    """
    root = tmp_path / "production"
    (root / ".worktrees" / "demo").mkdir(parents=True)
    (root / ".env").write_text(f"DOMAIN_NAME={PRODUCTION_DOMAIN}\n", encoding="utf-8")
    monkeypatch.setattr(identity, "production_root", lambda: root)
    monkeypatch.setattr(identity, "production_project", lambda: PRODUCTION_PROJECT)

    worktree = root / ".worktrees" / "demo"
    (worktree / ".env").write_text(
        "COMPOSE_PROJECT_NAME=br-demo\n"
        "COMPOSE_PROFILES=agent-testuser\n"
        "TS_AUTHKEY=tskey-auth-kFAKEfake0000000000\n",
        encoding="utf-8",
    )
    (worktree / "compose.yml").write_text("services: {}\n", encoding="utf-8")

    paths = identity.branch_paths("demo")
    # Non-degeneracy, asserted rather than assumed: if these two were equal,
    # "the document never names production" would be trivially true of a
    # document that named the branch.
    assert paths.domain != PRODUCTION_DOMAIN
    assert paths.domain.endswith(identity.tailnet_suffix())
    assert identity.production_domain() == PRODUCTION_DOMAIN
    return paths


def make_result(paths, **kwargs):
    result = branch.BranchResult(requested_name="demo", paths=paths)
    result.devs = kwargs.pop("devs", ("testuser",))
    for key, value in kwargs.items():
        setattr(result, key, value)
    return result


def seed_report():
    report = seed.SeedReport()
    report.add("forgejo/gitea/gitea.db", seed.SNAPSHOT, bytes=2_400_000,
               seconds=0.02, detail="VACUUM INTO, read-only")
    report.add("forgejo/ssh", seed.SKIP, detail="root-owned host keys")
    return report


def inert_hook(paths):
    return crosswire.HookInstall(
        path=paths.worktree / "hooks" / "pre-push",
        worktree=paths.worktree,
        hooks_dir=identity.production_root() / ".git" / "hooks",
        executable=True, armed=False,
        activation_command="git -C <production> config core.hooksPath hooks",
    )


# ---------------------------------------------------------------------------
# the document: what it must never say
# ---------------------------------------------------------------------------


def test_the_access_doc_names_the_branch_domain_and_never_productions(fabricated):
    """One line may name production. Asserted by EXACT match, not by allowance.

    An allowance ("some production references are fine") is how the next one
    gets through -- so the permitted sentence is spelled out here, in the
    test, rather than compared against the constant the renderer used. The
    duplication is the point: it is the independent copy.
    """
    doc = access_doc.render_access_doc(make_result(fabricated), ROWS)

    permitted = (
        "- Commits from this worktree still go to production's Forgejo at "
        f"https://{PRODUCTION_DOMAIN}/git/ -- that is this repository's "
        "`origin`, it is the normal case, and the pre-push hook allows it."
    )
    hits = [line for line in doc.splitlines() if PRODUCTION_DOMAIN in line]
    assert hits == [permitted], (
        "a branch's access document named production somewhere other than the "
        "one labelled line"
    )

    branch_urls = [
        line for line in doc.splitlines() if fabricated.domain in line
    ]
    assert len(branch_urls) >= 4, (
        f"the document barely mentions the branch's own domain: {branch_urls}"
    )


def test_the_access_doc_marks_the_admin_dashboard_unavailable(fabricated):
    """Finding N5. No URL is printed for `/agent`, and the reason is given."""
    doc = access_doc.render_access_doc(make_result(fabricated), ROWS)

    assert access_doc.UNAVAILABLE in doc
    assert "tailscale serve" in doc
    for expected in ("only on the host", "Caddyfile.d/agents.conf"):
        assert expected in doc, f"the reason omits {expected!r}"

    # The live-URL check. Every URL against the branch's domain is extracted,
    # and the bare /agent must not be among them -- while the per-developer
    # route must.
    dead = f"https://{fabricated.domain}/agent"
    offered = _offered_urls(doc, fabricated.domain)
    assert offered, "no URLs were offered at all; this assertion would be vacuous"
    assert dead not in offered, (
        f"the document offers {dead}, which redirects to a `tailscale serve` "
        "port that does not exist in a branch"
    )
    assert f"{dead}/testuser/" in offered, (
        "the per-developer agent route is missing; N5 removes the ADMIN "
        f"dashboard only. offered={offered}"
    )


def _offered_urls(doc: str, domain: str) -> set[str]:
    """URLs the document OFFERS: the ones in its URL table and shell block.

    Not every occurrence of the domain -- the N5 paragraph names the dead URL
    in order to say it is dead, and a test that could not tell those apart
    would forbid the explanation along with the mistake.
    """
    offered = set()
    for line in doc.splitlines():
        if not line.startswith("| "):
            continue
        for cell in line.split("|"):
            cell = cell.strip()
            if cell.startswith(f"https://{domain}"):
                offered.add(cell)
    return offered


def test_the_url_set_the_result_reports_omits_the_admin_dashboard(fabricated):
    """The renderer cannot print what the result does not carry.

    Belt and braces on purpose: `urls()` is what `--json` and Task 11's MCP
    payload expose, so a dead URL added there would escape the document's
    checks entirely.
    """
    urls = make_result(fabricated).urls()
    assert urls, "an empty URL set would make this assertion vacuous"
    assert f"https://{fabricated.domain}/agent/" not in set(urls.values())
    assert f"https://{fabricated.domain}/agent" not in set(urls.values())
    assert urls["fjell"] == f"https://{fabricated.domain}/"
    assert urls["agent-testuser"] == f"https://{fabricated.domain}/agent/testuser/"


def test_the_access_doc_container_names_come_from_compose_ps(fabricated):
    """Fed a SURPRISING name, the document prints it.

    `br-demo-forgejo-2` is a name Compose really does produce -- it appends
    `-2` when it recreates a container beside one that still exists -- and no
    concatenation of project, service and `-1` yields it. A test that used the
    name the concatenation WOULD produce proves nothing, which is the decoy
    pattern that has already appeared twice in this project.
    """
    doc = access_doc.render_access_doc(make_result(fabricated), ROWS)

    assert ROWS, "no rows: this assertion would be vacuous"
    for row in ROWS:
        assert f"`{row.name}`" in doc, f"{row.name} is missing from the table"
        assert f"docker exec -it {row.name} bash" in doc, (
            f"no paste-ready shell line for {row.name}"
        )
    constructed = f"{fabricated.project}-forgejo-1"
    assert constructed not in doc, (
        f"the document printed {constructed}, which it constructed; Compose "
        f"named that container {SURPRISING}"
    )


def test_the_access_doc_records_exclusions_and_seeding(fabricated):
    """Both halves of "why is this missing", from the manifest.

    "I asked to drop `forgejo` and `forgejo-mcp` vanished too" is the question
    this table answers, so the transitively-added services must be named AND
    attributed.
    """
    result = make_result(
        fabricated,
        excluded=("forgejo", "forgejo-mcp", "dev-admin"),
        seeded=True, seed_report=seed_report(),
    )
    doc = access_doc.render_access_doc(result, ROWS)

    assert "requested with `--without`" in doc
    for pulled in ("forgejo-mcp", "dev-admin"):
        row = [
            line for line in doc.splitlines()
            if line.startswith(f"| `{pulled}`")
        ]
        assert len(row) == 1, f"no exclusion row for {pulled}: {doc}"
        assert "pulled in by `forgejo`" in row[0], row[0]

    assert "forgejo/gitea/gitea.db" in doc and "snapshot" in doc
    assert "forgejo/ssh" in doc and "skip" in doc, (
        "what was NOT seeded is the half a branch's user actually needs"
    )


def test_the_access_doc_says_seeding_is_unrecorded_rather_than_empty(fabricated):
    """Three states, not two.

    `aurora branch access` cannot re-derive what was seeded -- seeding is an
    event. Rendering that as "Nothing (--no-seed)" would tell a developer
    their branch does not share production's users when it does.
    """
    unknown = make_result(fabricated, seeded=None)
    assert "Not recorded here" in access_doc.render_access_doc(unknown, ROWS)

    unseeded = make_result(fabricated, seeded=False)
    doc = access_doc.render_access_doc(unseeded, ROWS)
    assert "--no-seed" in doc and "start empty" in doc
    assert "Not recorded here" not in doc


# ---------------------------------------------------------------------------
# secrets
# ---------------------------------------------------------------------------


def test_the_manifest_marks_the_auth_key_secret():
    """Independent pressure on the flag the scrubber is driven by.

    Without this, deleting `secret: true` from `branch-env.yaml` would blind
    the scrubber and every test that exercises it in one edit -- the
    self-blinding shape Tasks 5 and 6 both shipped.
    """
    names = access_doc.secret_variables()
    assert "TS_AUTHKEY" in names, (
        f"{envfile.MANIFEST_NAME} no longer marks the ephemeral Tailscale auth "
        f"key `secret: true`; it marks {names}"
    )
    entry = [r for r in envfile.load_manifest() if r.name == "TS_AUTHKEY"]
    assert len(entry) == 1 and entry[0].secret and entry[0].fatal


def test_the_secret_set_is_driven_by_the_flag_and_not_by_the_name():
    """A variable is secret because the manifest says so, never because of
    what it is called."""
    manifest = [
        envfile.Requirement(name="TOKEN_LOOKING_THING", fatal=False,
                            literal="x", secret=False),
        envfile.Requirement(name="innocuous", fatal=False, literal="x",
                            secret=True),
    ]
    assert access_doc.secret_variables(manifest) == ("innocuous",)


def test_the_secret_check_refuses_a_manifest_that_marks_nothing_secret():
    """Trap 2, in a redaction costume: an empty set passes over everything."""
    manifest = [envfile.Requirement(name="A", fatal=True, literal="x")]
    with pytest.raises(access_doc.AccessDocError) as excinfo:
        access_doc.secret_variables(manifest)
    assert "marks no variable" in str(excinfo.value)


def test_the_document_refuses_to_carry_a_secrets_name_or_its_value(fabricated):
    """Two legs, and each must fire on its own.

    The VALUE leg is the one that matters: a key printed under some other
    label, or inside a note, is still a key in a file that decision D-F puts
    inside production's agent workspace.
    """
    env_file = fabricated.env_file
    key = envfile.parse_env(env_file.read_text())["TS_AUTHKEY"]
    assert key.startswith("tskey-"), "fixture is not carrying a plausible key"

    with pytest.raises(access_doc.AccessDocError) as by_name:
        access_doc._assert_no_secret_leaked("TS_AUTHKEY=redacted\n", env_file)
    assert "naming TS_AUTHKEY" in str(by_name.value)
    assert "VALUE" not in str(by_name.value), (
        "the name check reported itself as the value check; the two are "
        "different defects and the message must say which fired"
    )

    with pytest.raises(access_doc.AccessDocError) as by_value:
        access_doc._assert_no_secret_leaked(
            f"the sidecar joined with {key}\n", env_file)
    assert "VALUE" in str(by_value.value)
    assert "naming TS_AUTHKEY" not in str(by_value.value)

    # The control. Without it, a checker that refused everything would satisfy
    # both assertions above.
    access_doc._assert_no_secret_leaked("nothing sensitive here\n", env_file)


def test_a_rendered_document_never_carries_the_branchs_auth_key(fabricated):
    """End to end, through the real renderer, with a real branch `.env`."""
    key = envfile.parse_env(fabricated.env_file.read_text())["TS_AUTHKEY"]
    doc = access_doc.render_access_doc(
        make_result(fabricated, notes=["nothing to see"]), ROWS)
    assert key not in doc and "TS_AUTHKEY" not in doc


# ---------------------------------------------------------------------------
# the two document-level guards, discriminated
# ---------------------------------------------------------------------------


def test_the_document_guards_each_refuse_on_their_own(fabricated):
    """`AccessDocError` has four sources; a bare `raises` proves nothing."""
    key = envfile.parse_env(fabricated.env_file.read_text())["TS_AUTHKEY"]

    with pytest.raises(access_doc.AccessDocError) as domain_leak:
        access_doc._assert_production_is_named_once(
            f"| fjell | https://{PRODUCTION_DOMAIN}/ | |\n", PRODUCTION_DOMAIN)
    assert "outside the one permitted line" in str(domain_leak.value)
    assert "secret" not in str(domain_leak.value).lower()

    with pytest.raises(access_doc.AccessDocError) as empty_domain:
        access_doc._assert_production_is_named_once("anything\n", "")
    assert "resolved empty" in str(empty_domain.value)
    assert "outside the one permitted line" not in str(empty_domain.value)

    with pytest.raises(access_doc.AccessDocError) as secret:
        access_doc._assert_no_secret_leaked(key, fabricated.env_file)
    assert "outside the one permitted line" not in str(secret.value)

    # Controls, both directions.
    access_doc._assert_production_is_named_once(
        access_doc.PRODUCTION_FORGE_LINE.format(domain=PRODUCTION_DOMAIN) + "\n",
        PRODUCTION_DOMAIN,
    )
    access_doc._assert_no_secret_leaked("clean\n", fabricated.env_file)


# ---------------------------------------------------------------------------
# the pre-push hook's honesty
# ---------------------------------------------------------------------------


def test_the_document_says_the_hook_is_inert_when_git_will_not_run_it(fabricated):
    """Layer 2 is inert on this host until a human runs one line.

    A document implying the hook protects the worktree while git resolves
    hooks elsewhere is worse than one that says nothing: the developer would
    believe a defence exists.
    """
    result = make_result(fabricated, hook=inert_hook(fabricated))
    doc = access_doc.render_access_doc(result, ROWS)
    assert "INERT" in doc
    assert "core.hooksPath hooks" in doc, "the arming command is not printed"
    assert "not refused" in doc


def test_the_document_does_not_cry_inert_once_the_hook_is_armed(fabricated):
    """The other direction, so the warning cannot become unconditional noise."""
    armed = crosswire.HookInstall(
        path=fabricated.worktree / "hooks" / "pre-push",
        worktree=fabricated.worktree,
        hooks_dir=fabricated.worktree / "hooks",
        executable=True, armed=True, activation_command="irrelevant",
    )
    doc = access_doc.render_access_doc(make_result(fabricated, hook=armed), ROWS)
    assert "INERT" not in doc and "ARMED" in doc


def test_the_document_does_not_overstate_what_the_hook_prevents(fabricated):
    """Plan defect 33: it stops the ref update, not the connection."""
    doc = access_doc.render_access_doc(
        make_result(fabricated, hook=inert_hook(fabricated)), ROWS)
    assert "does not prevent CONTACT" in doc
    assert "stops the push, not the handshake" in doc


# ---------------------------------------------------------------------------
# compose ps
# ---------------------------------------------------------------------------


def test_the_ps_parser_reads_what_compose_actually_emits():
    """Against a real transcript that contains a name no rule produces."""
    rows = branch.parse_compose_ps(RECORDED_PS)
    assert len(rows) == 3, rows
    alpha, beta1, beta2 = rows
    assert (alpha.service, alpha.name, alpha.state) == (
        "alpha", "br-psprobe-alpha-1", "running")
    assert beta2.name == "br-psprobe-beta-2", (
        "the second replica's name was not read from `Name`; a parser that "
        "built it from Project and Service would have produced "
        f"br-psprobe-beta-1 twice, and got {[r.name for r in rows]}"
    )
    assert len({r.name for r in rows}) == 3, [r.name for r in rows]
    assert beta2.health == "healthy" and beta2.state == "exited"
    assert beta2.condition == "exited / healthy"


def test_the_ps_parser_also_accepts_a_json_array_and_shrugs_at_rubbish():
    rows = branch.parse_compose_ps(
        '[{"Service":"a","Name":"br-x-a-1","State":"running"}]')
    assert [r.name for r in rows] == ["br-x-a-1"]
    assert branch.parse_compose_ps("") == []
    assert branch.parse_compose_ps("not json at all") == []


def test_compose_ps_asks_for_the_project_and_needs_no_compose_file(fabricated):
    """Measured on this host: `ps -p <project>` resolves from container LABELS
    and works from an empty directory.

    That is what lets `access` and `ls` report a branch whose worktree was
    deleted by hand -- which is exactly the branch nobody remembers is still
    running.
    """
    runner = FakeRunner([ps_reply(ROWS)])
    rows = branch.compose_ps("br-demo", runner=runner)
    assert [r.name for r in rows] == sorted(r.name for r in ROWS)
    assert runner.invocations, "no command was issued at all"
    argv = runner.invocations[-1].argv
    assert "-p" in argv and "br-demo" in argv and "ps" in argv
    assert "-f" not in argv, (
        "compose ps asked for a compose file; a branch whose worktree is gone "
        "would then be invisible"
    )
    assert runner.invocations[-1].cwd is None


# ---------------------------------------------------------------------------
# rebuild: scoping is the whole feature
# ---------------------------------------------------------------------------


def _resolved_project(inv) -> str:
    """What COMPOSE would resolve this invocation's project to.

    Not "does `-p` appear": Compose falls back to `$COMPOSE_PROJECT_NAME` and
    then to the working directory's basename, and a branch worktree is named
    `demo` while its project is `br-demo` -- one prefix away from the
    namespace that is the only thing between a rebuild and production.
    """
    argv = list(inv.argv)
    if "-p" in argv:
        return argv[argv.index("-p") + 1]
    if "--project-name" in argv:
        return argv[argv.index("--project-name") + 1]
    env = inv.env or {}
    if env.get("COMPOSE_PROJECT_NAME"):
        return env["COMPOSE_PROJECT_NAME"]
    return Path(inv.cwd).name if inv.cwd else ""


def test_rebuild_is_scoped_to_the_branch_project(fabricated):
    runner = FakeRunner()
    branch.branch_rebuild("demo", ("fjell",), runner=runner)

    assert runner.invocations, "rebuild issued no command at all"
    compose = [i for i in runner.invocations if i.argv[:2] == ("docker", "compose")]
    assert compose, f"no compose invocation: {[i.argv for i in runner.invocations]}"
    for inv in compose:
        resolved = _resolved_project(inv)
        assert resolved == fabricated.project, (
            f"{list(inv.argv)} resolves to compose project {resolved!r}, not "
            f"{fabricated.project!r}"
        )
        assert resolved != PRODUCTION_PROJECT

    argv = compose[-1].argv
    assert argv[:4] == ("docker", "compose", "-p", "br-demo")
    assert "up" in argv and "-d" in argv and "--build" in argv
    assert argv[-1] == "fjell", "the service was not passed to compose"
    assert compose[-1].cwd == fabricated.worktree.resolve()
    assert "COMPOSE_PROFILES" not in (compose[-1].env or {})


def test_rebuild_refuses_a_project_that_is_not_a_branch(fabricated, monkeypatch):
    """The guard fires BEFORE any command is issued."""
    monkeypatch.setattr(
        identity, "branch_paths",
        lambda name: identity.BranchPaths(
            name=name, project=PRODUCTION_PROJECT, hostname="h",
            domain="d", worktree=fabricated.worktree,
            env_file=fabricated.env_file, access_doc=fabricated.access_doc),
    )
    with pytest.raises(guards.GuardViolation) as excinfo:
        branch.branch_rebuild("demo", runner=ExplodingRunner())
    assert "namespace" in str(excinfo.value)


def test_rebuild_refuses_a_worktree_outside_the_branch_directory(
    fabricated, tmp_path, monkeypatch
):
    """A VALID `br-` project with an invalid path: the only shape that reaches
    the second guard. Task 9's M10 survived until a test supplied it."""
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.setattr(
        identity, "branch_paths",
        lambda name: identity.BranchPaths(
            name=name, project="br-demo", hostname="h", domain="d",
            worktree=elsewhere, env_file=elsewhere / ".env",
            access_doc=elsewhere / "A.md"),
    )
    with pytest.raises(guards.GuardViolation) as excinfo:
        branch.branch_rebuild("demo", runner=ExplodingRunner())
    assert "not inside" in str(excinfo.value)


def test_rebuild_refuses_when_the_worktree_has_no_compose_file(fabricated):
    (fabricated.worktree / "compose.yml").unlink()
    with pytest.raises(branch.BranchError) as excinfo:
        branch.branch_rebuild("demo", runner=ExplodingRunner())
    assert "compose.yml" in str(excinfo.value)


# ---------------------------------------------------------------------------
# shell
# ---------------------------------------------------------------------------


def test_shell_refuses_a_service_not_in_the_branch(fabricated):
    """And issues no `exec` while refusing.

    This is also the case where a naive implementation falls through to a
    daemon-wide name lookup: `docker exec -it forgejo bash` reaches
    PRODUCTION's forge from any directory on this host.
    """
    runner = FakeRunner([ps_reply(ROWS)])
    with pytest.raises(branch.BranchError) as excinfo:
        branch.branch_shell("demo", "hermes-testuser", runner=runner,
                            exec_fn=lambda *a: pytest.fail("execed anyway"))
    message = str(excinfo.value)
    assert "hermes-testuser" in message
    assert "caddy" in message and "forgejo" in message, (
        f"the refusal does not say what the branch DOES run: {message}"
    )
    assert runner.invocations, "nothing ran; the ps lookup never happened"
    assert not any("exec" in i.argv for i in runner.invocations), (
        "an exec was issued for a service that is not in the branch"
    )


def test_shell_resolves_the_container_from_ps_and_not_from_the_service_name(
    fabricated
):
    runner = FakeRunner([ps_reply(ROWS)])
    execed = []
    argv = branch.branch_shell(
        "demo", "forgejo", runner=runner,
        exec_fn=lambda file, args: execed.append((file, list(args))))
    assert argv == ["docker", "exec", "-it", SURPRISING, "bash"]
    assert execed == [("docker", argv)]
    assert f"{fabricated.project}-forgejo-1" not in " ".join(argv)


def test_shell_takes_a_command_and_refuses_a_non_branch_project(
    fabricated, monkeypatch
):
    runner = FakeRunner([ps_reply(ROWS)])
    argv = branch.shell_argv("demo", "caddy", ("sh", "-c", "id"), runner=runner)
    assert argv[-3:] == ["sh", "-c", "id"]

    monkeypatch.setattr(
        identity, "branch_paths",
        lambda name: identity.BranchPaths(
            name=name, project=PRODUCTION_PROJECT, hostname="h", domain="d",
            worktree=fabricated.worktree, env_file=fabricated.env_file,
            access_doc=fabricated.access_doc),
    )
    with pytest.raises(guards.GuardViolation):
        branch.shell_argv("demo", "caddy", runner=ExplodingRunner())


def test_shell_says_so_when_the_branch_runs_nothing(fabricated):
    runner = FakeRunner()
    with pytest.raises(branch.BranchError) as excinfo:
        branch.shell_argv("demo", "caddy", runner=runner)
    assert "no running container" in str(excinfo.value)


# ---------------------------------------------------------------------------
# ls and INDEX.md: derived from the daemon
# ---------------------------------------------------------------------------


def _daemon(projects, rows_by_project=None):
    """A runner double whose `ps`/`inspect` answers describe a live daemon."""
    replies = [
        (("ps", "-aq"), "".join(f"cid-{p}\n" for p in projects)),
    ]
    for project in projects:
        replies.append(((f"cid-{project}",), f"{project}\n"))
        rows = (rows_by_project or {}).get(project, ROWS)
        replies.append(ps_reply(rows, project))
    return FakeRunner(replies)


def test_index_lists_live_branches_only(fabricated, tmp_path, monkeypatch):
    """Derived from the daemon, never from a cached file.

    The stale index on disk names `ghost`, which no longer exists, and does
    NOT name `demo`, which does. Reading the file back would produce exactly
    the wrong answer in both directions -- which is the point: a branch whose
    worktree was deleted by hand is still running, and an index that read
    itself keeps advertising a branch torn down an hour ago.
    """
    stale = fabricated.worktree.parent / access_doc.INDEX_NAME
    stale.write_text(
        "# Branch stacks on this host\n\n| ghost | `br-ghost` | ... |\n",
        encoding="utf-8",
    )
    runner = _daemon(["br-demo"])

    path = branch.write_index(runner)
    assert path == stale.resolve()
    text = path.read_text(encoding="utf-8")

    assert "br-demo" in text, f"the live branch is missing from the index: {text}"
    assert "ghost" not in text, (
        "the index still lists a branch that no longer exists; it was read "
        "from the file rather than derived from the daemon"
    )
    assert str(fabricated.worktree) in text
    assert f"https://{fabricated.domain}/" in text


def test_the_index_marks_a_branch_whose_worktree_is_gone(fabricated, monkeypatch):
    runner = _daemon(["br-demo", "br-ghost"])
    summaries = branch.branch_ls(runner)
    assert len(summaries) == 2, summaries
    text = access_doc.render_index(summaries)
    assert "MISSING" in text, (
        "a branch whose worktree was deleted by hand must be visible AS such: "
        "it is still running and still costs memory"
    )
    demo = [s for s in summaries if s.name == "demo"][0]
    ghost = [s for s in summaries if s.name == "ghost"][0]
    assert demo.worktree_exists and not ghost.worktree_exists
    assert demo.running == 3 and len(demo.containers) == 3


def test_an_empty_index_says_so_rather_than_rendering_an_empty_table():
    text = access_doc.render_index([])
    assert "No branch stack is running." in text
    assert "|" not in text


def test_ls_and_teardown_ask_the_daemon_the_same_question(monkeypatch):
    """One implementation, proved by patching it and watching both paths.

    `--all` teardown and the index must not disagree about which branches
    exist; two enumerations is how a branch gets torn down that the index
    still lists, or listed that teardown cannot find.
    """
    seen = []
    # `env` too, since P4: `live_branch_projects` takes the runtime's
    # environment so it can query the BRANCH's daemon rather than whichever
    # one this process defaults to. A stub whose signature lags the function
    # it replaces fails here as a TypeError rather than as a wrong answer --
    # the right direction, but it still has to track it.
    monkeypatch.setattr(
        branch, "live_branch_projects",
        lambda runner=None, env=None: seen.append(
            (env or {}).get(runtimes.DOCKER_HOST_VAR, "docker")) or [])
    branch.branch_ls(FakeRunner())
    assert seen == ["docker"], (
        "`ls` enumerated branches some other way, or asked more than the one "
        "runtime its docstring says it asks"
    )

    # `--all` goes through the SAME function -- but once per RUNTIME, and that
    # asymmetry is deliberate. `ls` omitting a podman branch is a gap in a
    # report; `--all` -- the "clean the host" command -- omitting one leaves a
    # whole stack running and costing memory while reporting that everything
    # was torn down, and `_tool_branch_down` has no `runtime` argument at all,
    # so over MCP the one-daemon default was the only reachable behaviour.
    seen.clear()
    branch.branch_down_all(runner=FakeRunner())
    assert len(seen) == len(runtimes.RUNTIMES), (
        f"`--all` asked {seen}; it must ask every runtime, or a branch on the "
        "other daemon survives a sweep that reports success"
    )
    assert len(set(seen)) == len(seen), (
        f"`--all` asked the same daemon twice: {seen}"
    )

    # ...and a named runtime still asks exactly that one.
    seen.clear()
    branch.branch_down_all(runner=FakeRunner(), runtime="docker")
    assert seen == ["docker"], seen


def test_live_branch_projects_filters_by_the_branch_prefix(fabricated):
    runner = FakeRunner([
        (("ps", "-aq"), "cid-a\ncid-b\ncid-c\n"),
        (("cid-a",), "br-demo\n"),
        (("cid-b",), f"{PRODUCTION_PROJECT}\n"),
        (("cid-c",), "br-other\n"),
    ])
    assert branch.live_branch_projects(runner) == ["br-demo", "br-other"]


# ---------------------------------------------------------------------------
# writing the documents
# ---------------------------------------------------------------------------


def test_the_index_writer_refuses_any_other_destination(fabricated, tmp_path):
    """Positive guard: the ONE file this tool writes in production's checkout."""
    assert branch.index_path() == fabricated.worktree.parent / "INDEX.md"
    for bad in (tmp_path / "INDEX.md",
                identity.production_root() / "INDEX.md",
                fabricated.worktree / "INDEX.md"):
        with pytest.raises(guards.GuardViolation) as excinfo:
            guards.assert_worktrees_index_path(bad)
        assert "the branch index is" in str(excinfo.value)
    # Control.
    assert guards.assert_worktrees_index_path(branch.index_path())


def test_both_documents_are_written_through_one_seam(fabricated, monkeypatch):
    """Tripwire the DESTINATION, not only the bytes.

    Task 5 moved production's `forgejo/` mtime through a `mkdir` that no
    tripwire covered, and Task 8 found a second one. `_write_document` does
    the `mkdir` AND the write, so one patch here proves nothing else reaches a
    destination.
    """
    written = []
    monkeypatch.setattr(branch, "_write_document",
                        lambda path, text: written.append((Path(path), text)) or Path(path))
    result = make_result(fabricated, hook=inert_hook(fabricated))
    doc_path, index = branch.refresh_branch_docs(result, runner=_daemon(["br-demo"]))

    assert [p for p, _ in written] == [
        (fabricated.worktree / access_doc.ACCESS_DOC_NAME).resolve(),
        (fabricated.worktree.parent / access_doc.INDEX_NAME).resolve(),
    ], written
    assert doc_path == written[0][0] and index == written[1][0]
    assert "# Branch `demo`" in written[0][1]
    assert "Branch stacks on this host" in written[1][1]


def test_write_access_doc_refuses_production_and_writes_a_real_file(fabricated):
    runner = _daemon(["br-demo"])
    result = make_result(fabricated, hook=inert_hook(fabricated))
    path = branch.write_access_doc(result, branch.compose_ps("br-demo", runner=runner))
    assert path.read_text(encoding="utf-8").startswith("# Branch `demo`")
    assert path == fabricated.access_doc.resolve()

    result.paths = identity.BranchPaths(
        name="demo", project="br-demo", hostname="h", domain="d",
        worktree=identity.production_root(),
        env_file=identity.production_root() / ".env",
        access_doc=identity.production_root() / "BRANCH-ACCESS.md")
    with pytest.raises(guards.GuardViolation) as excinfo:
        branch.write_access_doc(result)
    assert "PRODUCTION's checkout" in str(excinfo.value)


def test_the_access_doc_filename_matches_the_one_identity_resolves(fabricated):
    """Two spellings of one filename is a reader told to open a missing file."""
    assert fabricated.access_doc.name == access_doc.ACCESS_DOC_NAME


# ---------------------------------------------------------------------------
# access: regenerated from live state
# ---------------------------------------------------------------------------


def test_branch_access_regenerates_from_live_state(fabricated):
    """Container names from `ps`, developers and exclusions from the branch's
    own artefacts, and seeding honestly reported as unknown."""
    (fabricated.worktree / "compose.exclude.yml").write_text(
        "services:\n  forgejo:\n    profiles: [excluded]\n"
        "  forgejo-mcp:\n    profiles: [excluded]\n", encoding="utf-8")
    doc = branch.branch_access("demo", runner=_daemon(["br-demo"]))

    assert SURPRISING in doc
    assert "/agent/testuser/" in doc, "developers were not recovered from the .env"
    assert "`forgejo-mcp`" in doc and "pulled in by `forgejo`" in doc
    assert "Not recorded here" in doc
    assert "TS_AUTHKEY" not in doc


def test_branch_access_refuses_a_branch_that_does_not_exist(fabricated):
    runner = FakeRunner()
    with pytest.raises(branch.BranchError) as excinfo:
        branch.branch_access("nosuch", runner=runner)
    assert "no branch 'nosuch'" in str(excinfo.value)


def test_branch_access_still_works_when_the_worktree_is_gone(fabricated):
    import shutil
    shutil.rmtree(fabricated.worktree)
    doc = branch.branch_access("demo", runner=_daemon(["br-demo"]))
    assert "THE WORKTREE" in doc and "IS GONE" in doc
    assert SURPRISING in doc, (
        "the container table came from the worktree rather than from the "
        "daemon; a branch whose worktree is gone is still running"
    )


def test_developers_round_trip_through_the_profile_string():
    """One spelling of `agent-<user>`, written and read by the same module."""
    ctx = envfile.BranchContext(name="demo", devs=("testuser", "newuser"))
    rendered = envfile.DERIVATIONS["agent_profiles"](
        ctx, envfile.Requirement(name="COMPOSE_PROFILES", fatal=True,
                                 derive="agent_profiles"))
    assert rendered == "agent-testuser,agent-newuser"
    assert envfile.developers_from_profiles(rendered) == ("testuser", "newuser")
    assert envfile.developers_from_profiles("") == ()
    assert envfile.developers_from_profiles("excluded,agent-x") == ("x",)


# ---------------------------------------------------------------------------
# the CLI is a thin adapter, and it is wired
# ---------------------------------------------------------------------------


def test_the_cli_up_prints_the_document_verbatim_and_writes_both_files(
    fabricated, monkeypatch, capsys
):
    """Spec 4.1 step 9: the access document's content IS the output.

    Also the pin on the wiring: `refresh_branch_docs` is called from here
    rather than from `branch_up`, so nothing else proves it is called at all.
    """
    result = make_result(fabricated, hook=inert_hook(fabricated))
    monkeypatch.setattr(branch, "branch_up", lambda *a, **kw: result)
    monkeypatch.setattr(branch, "CommandRunner", lambda: _daemon(["br-demo"]))

    assert cli.main(["branch", "up", "demo", "--devs", "testuser"]) == 0
    printed = capsys.readouterr().out
    on_disk = fabricated.access_doc.read_text(encoding="utf-8")
    assert printed == on_disk, (
        "stdout and the file on disk disagree; they are the same product"
    )
    assert (fabricated.worktree.parent / "INDEX.md").is_file()


def test_the_cli_down_exists_and_regenerates_the_index(
    fabricated, monkeypatch, capsys
):
    """Task 9 wired no `down` subcommand, so every document printed a command
    that did not exist."""
    calls = []
    monkeypatch.setattr(branch, "branch_down", lambda name, **kw: calls.append(name) or
                        branch.DownResult(project="br-demo", worktree=fabricated.worktree))
    monkeypatch.setattr(branch, "CommandRunner", lambda: _daemon([]))

    assert cli.main(["branch", "down", "demo"]) == 0
    assert calls == ["demo"]
    index = fabricated.worktree.parent / "INDEX.md"
    assert index.is_file() and "No branch stack is running." in index.read_text()
    assert "br-demo" in capsys.readouterr().out


def test_the_cli_exposes_every_task_10_verb():
    """Deletion pressure on the wiring itself."""
    parser = cli.build_parser()
    actions = parser.parse_args(["branch", "ls"])
    assert actions.func is cli._cmd_branch_ls
    for argv, func in (
        (["branch", "access", "demo"], cli._cmd_branch_access),
        (["branch", "shell", "demo", "caddy"], cli._cmd_branch_shell),
        (["branch", "rebuild", "demo", "caddy"], cli._cmd_branch_rebuild),
        (["branch", "down", "demo"], cli._cmd_branch_down),
    ):
        assert parser.parse_args(argv).func is func, argv


def test_branch_ls_json_still_carries_the_derived_identity(fabricated, monkeypatch, capsys):
    """Task 1's shim tests read these keys from the top level."""
    monkeypatch.setattr(branch, "CommandRunner", lambda: _daemon(["br-demo"]))
    monkeypatch.setattr(identity, "describe", lambda: {"production_project": PRODUCTION_PROJECT})
    assert cli.main(["--json", "branch", "ls"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["production_project"] == PRODUCTION_PROJECT
    assert [b["name"] for b in payload["branches"]] == ["demo"]


# ---------------------------------------------------------------------------
# the documents are runtime-aware (P4, 2026-08-01)
# ---------------------------------------------------------------------------


def test_a_branchs_document_is_regenerated_from_the_daemon_it_was_built_on(
    fabricated, monkeypatch
):
    """`.aurora-runtime` sits in the worktree and was not read.

    So a `--runtime podman` branch's `BRANCH-ACCESS.md` -- the string
    `branch_access`'s own docstring calls "the feature" -- was regenerated
    from the ROOT docker daemon: zero container rows, and `result.runtime`
    falling back to the default so the document positively asserted the branch
    was on docker. Both were written after a successful `up`, with nothing
    saying the list was empty for a reason.
    """
    from aurora_cli import runtime as rt
    rt.record_runtime(fabricated.worktree, "podman")

    asked: list[str] = []

    class Recording(FakeRunner):
        def _execute(self, argv, *, cwd, env, input, stdin, timeout):
            if "ps" in argv:
                asked.append((env or {}).get(rt.DOCKER_HOST_VAR, "<root docker>"))
            return super()._execute(
                argv, cwd=cwd, env=env, input=input, stdin=stdin, timeout=timeout)

    result, _rows = branch.branch_state("demo", runner=Recording([ps_reply(ROWS)]))

    assert result.runtime == "podman", (
        "the document does not know which daemon this branch is on, so it "
        "asserts the default and lists whatever the default daemon holds"
    )
    assert asked, "no `ps` was issued; this assertion would be vacuous"
    assert all(a.startswith("unix://") and "podman" in a for a in asked), (
        f"the branch's containers were looked up on {asked}, not on the "
        "daemon its own worktree records"
    )


def test_a_branch_with_no_runtime_record_says_it_assumed_the_default(
    fabricated
):
    """"Built on docker" and "predates the record" are different answers.

    A document that quietly assumed one would be a document that lists no
    containers for a branch that is running, with nothing to explain it.
    """
    result, _rows = branch.branch_state("demo", runner=FakeRunner())
    assert result.runtime == "docker"
    assert any("assumes the default runtime" in n for n in result.notes), \
        result.notes


def test_the_index_names_the_daemon_it_was_generated_from():
    """`branch_ls` asks ONE daemon per call, so an index regenerated from
    docker cannot see a podman branch. That omission is now stated in the
    document; silently deleting a running branch from the index is the same
    lie as a teardown that reports success over a live stack."""
    text = access_doc.render_index([], runtime="docker")
    assert "docker" in text and "runtime only" in text
    # ...and the un-annotated form is still available for callers that have
    # not been taught the question.
    assert "runtime only" not in access_doc.render_index([])
