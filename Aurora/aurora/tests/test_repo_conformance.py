import os
import subprocess
import sys
from pathlib import Path, PurePosixPath

from conftest import ALLOWED_EXTERNAL_BINDS, PRODUCTION_PROJECT, REPO_ROOT, is_tracked


def _dev_administration_on_path():
    path = str(REPO_ROOT / "dev-administration")
    if path not in sys.path:
        sys.path.insert(0, path)


def test_agents_compose_matches_developers_yaml():
    """compose.agents.yml is generated AND committed. Committed, because
    Compose's `include:` is a hard failure on a missing file and a fresh
    worktree must still resolve `docker compose config`. Generated, so a
    developer is added by editing one YAML list — hence this drift check."""
    _dev_administration_on_path()
    from dev_administration.agents_compose import agent_specs, render_agents_compose
    from dev_administration.models import parse_developers_yaml

    devs = parse_developers_yaml(REPO_ROOT / "developers.yaml")
    expected = render_agents_compose(agent_specs(devs))
    actual = (REPO_ROOT / "compose.agents.yml").read_text()

    assert actual == expected, (
        "compose.agents.yml is stale relative to developers.yaml — run "
        "`dev-admin render-agents` and commit the result"
    )


def test_every_developer_has_a_declared_agent_service(config):
    _dev_administration_on_path()
    from dev_administration.models import parse_developers_yaml

    devs = parse_developers_yaml(REPO_ROOT / "developers.yaml")
    missing = [
        d.username for d in devs
        if f"hermes-{d.username}" not in config["services"]
    ]
    assert missing == [], (
        f"Developers with no compose service: {missing}. Before M4 these were "
        "`docker run` containers Compose could not see at all."
    )


def _env_assignment(path: Path, key: str) -> str | None:
    """Last uncommented `KEY=value` in a dotenv file, or None.

    Parsed rather than substring-matched: `#COMPOSE_PROFILES=agents` and
    `COMPOSE_PROFILES=agents-disabled` both satisfied the old `in` check
    while meaning the opposite.
    """
    if not path.exists():
        return None
    found = None
    for line in path.read_text().splitlines():
        line = line.strip()
        if line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        if name.strip() == key:
            found = value.strip()
    return found


def _activating_agent_profiles(profiles: list[str]) -> list[str]:
    """Which of these COMPOSE_PROFILES entries start developer agents.

    Extracted and pinned below for the same reason as
    _volume_scope_offenders: the live repo only ever exercises production's
    value, so a rule that accepts anything at all -- or that reverts to
    demanding the literal `agents` and so goes red on a correct branch --
    is invisible in a default run.
    """
    return [p for p in profiles if p == "agents" or p.startswith("agent-")]


def test_agent_profile_rule_accepts_a_branch_and_rejects_a_non_agent_profile():
    """Both directions, no live stack.

    `agent-juan` is what spec 4.1 requires a branch to set, so it MUST count
    as activating. `debug` must not -- otherwise the assertion passes for a
    stack that starts no agents at all, which is the whole thing this test
    is for.
    """
    assert _activating_agent_profiles(["agents"]) == ["agents"]
    assert _activating_agent_profiles(["agent-juan"]) == ["agent-juan"]
    assert _activating_agent_profiles(["debug"]) == []
    assert _activating_agent_profiles(["debug", "agent-juan"]) == ["agent-juan"]


def test_env_activates_an_agent_profile(config):
    """Agents carry `profiles:`, so a default `docker compose up -d` starts
    none of them unless COMPOSE_PROFILES says otherwise.

    Checks .env when it exists and .env.template otherwise: .env is
    gitignored, so keying only off it raised FileNotFoundError in a fresh
    clone — in a repo whose whole Chunk 1 premise is that a fresh worktree
    works. The template is what a fresh checkout actually copies from.

    Deliberately NOT `"agents" in profiles`. Spec §4.1 requires a branch to
    override this variable to `agent-<username>` (D7: only the requesting
    developer), so demanding the literal `agents` would go RED exactly when a
    branch is correct — the same defect as comparing a resolved volume name
    against PRODUCTION_PROJECT, one variable over, and it would have blocked
    Chunk 3. What actually matters is that SOME agent profile is active;
    which one is a property of the project, so only production is held to
    `agents`.
    """
    live, template = REPO_ROOT / ".env", REPO_ROOT / ".env.template"
    source = live if live.exists() else template
    raw = _env_assignment(source, "COMPOSE_PROFILES")

    assert raw is not None, (
        f"No COMPOSE_PROFILES assignment in {source.name}, so "
        "`docker compose up -d` brings the stack up with no developer agents."
    )
    profiles = [p.strip() for p in raw.split(",") if p.strip()]
    activating = _activating_agent_profiles(profiles)
    assert activating, (
        f"COMPOSE_PROFILES={raw!r} in {source.name} activates no agent "
        "profile, so the stack comes up with no developer agents at all. "
        "Production uses `agents`; a branch uses `agent-<username>`."
    )
    if config["name"] == PRODUCTION_PROJECT:
        assert "agents" in profiles, (
            f"Production must activate every developer, but "
            f"COMPOSE_PROFILES={raw!r} selects only {activating}."
        )


def _volume_scope_offenders(config) -> list[tuple[str, str]]:
    """Agent volumes that escape their own project's scoping.

    Extracted so it can be exercised against a synthetic BRANCH config
    below. Against the live repo the resolved project is always production,
    so comparing to PRODUCTION_PROJECT instead of config["name"] -- the bug
    this replaced -- is indistinguishable in a default run and stayed green
    under mutation. The synthetic case is what makes the regression visible
    without a branch stack.
    """
    project = config["name"]
    offenders = []
    for name, volume in (config.get("volumes") or {}).items():
        if not name.startswith("hermes-"):
            continue
        if (volume or {}).get("external"):
            offenders.append((name, "external: true"))
        declared_name = (volume or {}).get("name")
        if declared_name and not declared_name.startswith(f"{project}_"):
            offenders.append((name, f"name: {declared_name}"))
    return offenders


def test_volume_scoping_accepts_a_branch_and_rejects_a_leak():
    """Pins the rule itself, in both directions, with no live stack.

    A branch's volumes are `br-demo_hermes-*`; that must PASS. A volume
    pinned to another project's name, or declared external, must FAIL. The
    earlier version compared against PRODUCTION_PROJECT, so the first case
    was reported as a violation with a message claiming the branch would
    delete production's data -- exactly backwards.
    """
    branch = {
        "name": "br-demo",
        "volumes": {"hermes-juan-home": {"name": "br-demo_hermes-juan-home"}},
    }
    assert _volume_scope_offenders(branch) == []

    leaking = {
        "name": "br-demo",
        "volumes": {"hermes-juan-home": {"name": "other-stack_hermes-juan-home"}},
    }
    assert _volume_scope_offenders(leaking) == [
        ("hermes-juan-home", "name: other-stack_hermes-juan-home")
    ]

    external = {
        "name": "br-demo",
        "volumes": {"hermes-juan-home": {"external": True,
                                         "name": "br-demo_hermes-juan-home"}},
    }
    assert ("hermes-juan-home", "external: true") in _volume_scope_offenders(external)


def test_agent_volumes_are_project_scoped(config):
    """Spec §5.1: a branch's `down -v` must be structurally incapable of
    reaching production's agent data.

    Compose prefixes a volume declared in `volumes:` with the project name,
    so `hermes-<u>-home` resolves to `<project>_hermes-<u>-home` and the two
    stacks cannot collide. An `external: true` or a bare `name:` override
    would silently reintroduce the shared volume, and the only symptom would
    be a branch writing into a developer's real Hermes home.
    """
    # Scoped to the project THIS config resolves to, not to production's.
    # Comparing against PRODUCTION_PROJECT made the test assert the opposite
    # of its own message: `docker compose config` always emits
    # `name: <project>_<volume>`, so the check reduced to "the project must
    # be production" and went RED precisely when a branch scoped its volumes
    # correctly (`br-demo_hermes-juan-home`). Chunk 3 would have hit it.
    offenders = _volume_scope_offenders(config)

    assert offenders == [], (
        f"Agent volumes escape project scoping: {offenders}. A branch's "
        "`docker compose down -v` would then delete production's agent data."
    )


def test_every_build_context_is_tracked_in_git(config):
    """A build context that git does not track cannot exist in a worktree,
    so the stack would be unbuildable there."""
    untracked = []
    for name, service in config["services"].items():
        build = service.get("build")
        if not build:
            continue
        context = build["context"]
        if not is_tracked(REPO_ROOT / context):
            untracked.append((name, context))

    assert untracked == [], (
        "Build contexts not tracked in git — a fresh worktree cannot build "
        f"these services: {untracked}"
    )


def test_no_undeclared_containers_in_project(config):
    """Every container carrying the production project's label must
    correspond to a service declared in compose.yml.

    The label is deliberately not taken from config["name"]: in a git
    worktree that resolves to the directory basename, matches nothing, and
    the assertion passes vacuously. Set AURORA_PROJECT to check another
    stack.
    """
    declared = set(config["services"])
    result = subprocess.run(
        [
            "docker", "ps", "-a",
            "--filter", f"label=com.docker.compose.project={PRODUCTION_PROJECT}",
            "--format", "{{.Label \"com.docker.compose.service\"}}",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    running = {line.strip() for line in result.stdout.splitlines() if line.strip()}
    undeclared = sorted(running - declared)

    assert undeclared == [], (
        f"Containers labelled for project {PRODUCTION_PROJECT!r} but declared "
        f"nowhere in compose.yml: {undeclared}. Either declare them or remove them."
    )


def test_affine_is_declared_in_this_project(config):
    """AFFiNE is a hard dependency of the Caddyfile, so it must be declared
    here rather than living in a compose file outside the repo."""
    assert "affine" in config["services"], (
        "AFFiNE is routed by the Caddyfile but not declared in compose.yml"
    )


def test_affine_state_paths_are_inside_the_repo(config):
    """AFFiNE's bind mounts must resolve inside the repo so a worktree gets
    its own isolated copy rather than sharing production's.

    Both sides are resolved before comparison: docker compose reports the
    source from Go's os.Getwd(), which trusts a stale $PWD, so on this host
    (where /home is a symlink to /var/home) it can report an unresolved path
    while REPO_ROOT is always resolved.
    """
    offending = []
    for name in ("affine", "affine_migration", "postgres"):
        service = config["services"].get(name, {})
        for volume in service.get("volumes", []):
            if volume.get("type") != "bind":
                continue
            source = Path(volume["source"]).resolve()
            if source != REPO_ROOT and REPO_ROOT not in source.parents:
                offending.append((name, str(source)))

    assert offending == [], (
        f"AFFiNE bind mounts resolve outside the repo: {offending}"
    )


def test_compose_has_no_commented_out_services():
    """Commented-out service blocks are dead weight that misleads readers
    about what the stack contains."""
    dead_markers = [
        "immich-server", "immich-machine-learning", "falkordb",
        "tai-db", "erichough/nfs-server",
    ]
    text = (REPO_ROOT / "compose.yml").read_text()
    found = [marker for marker in dead_markers if marker in text]

    assert found == [], (
        f"compose.yml still contains dead service definitions: {found}"
    )


def test_compose_config_sees_profiled_services(tmp_path):
    """Regression guard for the defect that broke Chunk 1's conformance gate.

    A service carrying `profiles:` is OMITTED from `docker compose config`
    output unless its profile is active. A gate built on that output then
    reports a declared-but-profiled service's container as *undeclared*.
    COMPOSE_PROFILES="*" activates every profile, which is why
    conftest.compose_config() sets it.

    Self-contained on purpose: it pins the Compose behaviour this repo's
    gate depends on, without depending on this repo's compose.yml.
    """
    (tmp_path / "compose.yml").write_text(
        "services:\n"
        "  always:\n"
        "    image: alpine\n"
        "    command: sleep 1\n"
        "  gated:\n"
        "    image: alpine\n"
        "    command: sleep 1\n"
        '    profiles: ["manual"]\n'
    )

    def services(profiles: str | None) -> list[str]:
        env = dict(os.environ)
        env.pop("COMPOSE_PROFILES", None)
        if profiles is not None:
            env["COMPOSE_PROFILES"] = profiles
        result = subprocess.run(
            ["docker", "compose", "config", "--services"],
            cwd=tmp_path, capture_output=True, text=True, check=True, env=env,
        )
        return sorted(line.strip() for line in result.stdout.split() if line.strip())

    assert services(None) == ["always"], (
        "Compose no longer hides inactive-profile services — re-derive the "
        "gate's assumptions before trusting conftest.compose_config()"
    )
    assert services("*") == ["always", "gated"]


def test_conformance_gate_asks_for_all_profiles(monkeypatch):
    """Pins the mechanism on actual behaviour, not prose.

    An earlier version of this test grepped compose_config()'s source text
    for "COMPOSE_PROFILES" and '"*"'. Both substrings also appear in that
    function's docstring, so a partial revert -- delete the functional
    env-setting lines, leave the docstring -- satisfied the grep and passed
    while the gate was silently blind again. That is exactly the defect
    class that cost Chunk 1 a working gate in the first place. So instead
    this fakes subprocess.run and asserts what compose_config() actually
    passes it: COMPOSE_PROFILES="*" by default, and absent when the caller
    asks the narrower all_profiles=False question.
    """
    from conftest import compose_config

    calls = []

    class FakeResult:
        stdout = "{}"

    def fake_run(*args, **kwargs):
        calls.append(kwargs)
        return FakeResult()

    monkeypatch.setattr(subprocess, "run", fake_run)

    compose_config()
    assert calls[-1]["env"].get("COMPOSE_PROFILES") == "*", (
        "compose_config() must invoke subprocess.run with "
        "env['COMPOSE_PROFILES'] == '*' by default"
    )

    compose_config(all_profiles=False)
    assert "COMPOSE_PROFILES" not in calls[-1]["env"], (
        "compose_config(all_profiles=False) must not set COMPOSE_PROFILES "
        "in the subprocess environment"
    )


CADDYFILE_UPSTREAM_VARS = ("AFFINE_UPSTREAM", "FORGEJO_UPSTREAM", "FJELL_UPSTREAM")


def test_caddyfile_has_no_hardcoded_upstreams():
    """Spec D3 wants a branch to run the SAME Caddyfile as production. It
    cannot while the upstreams are literal 127.0.0.1 addresses: a branch's
    Caddy runs network_mode: service:tailscale and shares the sidecar's
    network namespace, where no localhost port of this stack exists."""
    text = (REPO_ROOT / "Caddyfile").read_text()
    leftovers = [
        line.strip() for line in text.splitlines()
        if "reverse_proxy" in line and "127.0.0.1" in line
        and "{$" not in line
    ]
    assert leftovers == [], (
        f"Caddyfile still routes to literal localhost addresses: {leftovers}"
    )
    missing = [v for v in CADDYFILE_UPSTREAM_VARS if "{$" + v not in text]
    assert missing == [], f"Caddyfile does not parameterise: {missing}"


def test_caddyfile_upstream_defaults_are_productions_addresses():
    """The placeholders must carry production's values as DEFAULTS.

    CORRECTED after review: an earlier version of this docstring claimed an
    unset variable makes "Caddy fail to start". It does not. Probed:
    `caddy validate` with AFFINE_UPSTREAM= reports "Valid configuration" and
    adapts to `"upstreams": null`, so Caddy starts happily and returns 502
    for that route -- a silent outage, which is worse than a refusal, not
    better. The real safety net is compose's `${VAR:-default}`; this default
    is the second one, for anyone running Caddy outside compose.

    Still worth pinning: it is not implied by the test above, since a bare
    `{$AFFINE_UPSTREAM}` satisfies that one.
    """
    text = (REPO_ROOT / "Caddyfile").read_text()
    for var, default in (
        ("AFFINE_UPSTREAM", "127.0.0.1:3010"),
        ("FORGEJO_UPSTREAM", "127.0.0.1:3000"),
        ("FJELL_UPSTREAM", "127.0.0.1:9080"),
    ):
        assert "{$" + var + ":" + default + "}" in text, (
            f"{var} has no production default; an unset variable would "
            "expand to empty and Caddy would refuse to start"
        )


def _forgejo_app_name_declaration() -> str:
    """The raw `FORGEJO____APP_NAME=...` line from compose.yml.

    Extracted so the three assertions below read the SAME line, and so a
    missing declaration is one failure rather than three confusing ones.
    """
    lines = [
        line.strip() for line in (REPO_ROOT / "compose.yml").read_text().splitlines()
        if line.strip().lstrip("- ").startswith("FORGEJO____APP_NAME=")
    ]
    assert len(lines) == 1, (
        f"expected exactly one FORGEJO____APP_NAME declaration in compose.yml, "
        f"found {lines}"
    )
    return lines[0]


def test_the_forgejo_app_name_is_parameterised_with_productions_default():
    """Spec 5.4 layer 3 must not be revertible in silence.

    Three legs, deliberately from three sources, because the module that reads
    this declaration is also the one that produces a branch's marked name -- and
    a checker that reads its own input validates nothing (the self-blinding
    trap, hit in Task 2 and again in Task 5).

    Leg 1 is this file's own text scan: parameterised, WITH a non-empty default.
    The empty-default case is not hypothetical -- `{$AFFINE_UPSTREAM}` with no
    default is exactly the Chunk 2 defect that
    test_caddyfile_upstream_defaults_are_productions_addresses exists for: it
    satisfies "no literal" while expanding to nothing, and Forgejo would then
    render with an empty application name rather than fail.
    """
    line = _forgejo_app_name_declaration()
    value = line.split("=", 1)[1]

    assert value.startswith("${") and value.endswith("}"), (
        f"FORGEJO____APP_NAME is not parameterised: {line!r}. A branch cannot "
        "then mark its own forge, and spec 5.4's visual layer does not exist."
    )
    assert ":-" in value, (
        f"FORGEJO____APP_NAME has no default: {line!r}. An unset variable "
        "expands to EMPTY, which is not a failure -- it is a forge with no "
        "name at all."
    )
    default = value[2:-1].split(":-", 1)[1]
    assert default.strip(), f"FORGEJO____APP_NAME's default is empty: {line!r}"


def test_the_forgejo_app_name_default_is_what_production_actually_runs(config):
    """Leg 2 and leg 3: the resolved config, and the live container.

    The declaration is production-neutral only if the default equals what
    production's Forgejo has TODAY. Compared against two sources that owe
    compose.yml's text nothing: Compose's own interpolation, and the
    environment of the running container. The container leg is the one that
    would catch a default that is merely plausible.
    """
    from conftest import inspect_container, project_containers

    line = _forgejo_app_name_declaration()
    default = line.split("=", 1)[1][2:-1].split(":-", 1)[1]

    resolved = (config["services"]["forgejo"].get("environment") or {})
    assert "FORGEJO____APP_NAME" in resolved, (
        "the resolved compose config carries no FORGEJO____APP_NAME for forgejo"
    )
    assert resolved["FORGEJO____APP_NAME"] == default, (
        f"compose resolves FORGEJO____APP_NAME to "
        f"{resolved['FORGEJO____APP_NAME']!r} but compose.yml's default is "
        f"{default!r} — production's .env is overriding it, so the default is "
        "no longer production's value and parameterising it was NOT neutral."
    )

    containers = project_containers()
    assert "forgejo" in containers, (
        f"no forgejo container in project {PRODUCTION_PROJECT!r}, so this "
        "assertion has nothing to compare against — do not let it pass on an "
        "empty set"
    )
    env = inspect_container(containers["forgejo"])["Config"]["Env"]
    live = [v.split("=", 1)[1] for v in env if v.startswith("FORGEJO____APP_NAME=")]
    assert live, (
        "production's forgejo container declares no FORGEJO____APP_NAME at all"
    )
    assert live[-1] == default, (
        f"production's forge is running as {live[-1]!r} but compose.yml's "
        f"default is {default!r}. Parameterising this was supposed to change "
        "nothing for production."
    )


def test_compose_declares_no_literal_tailnet_ip():
    """100.86.36.78 is THIS host's tailnet address. A branch reaches its own
    address through its own sidecar and publishes nothing."""
    raw = (REPO_ROOT / "compose.yml").read_text()
    assert "100.86.36.78" not in raw.replace(
        "${HERMES_TAILNET_IP:-100.86.36.78}", ""
    ), (
        "compose.yml still hardcodes this host's tailnet IP — use "
        "${HERMES_TAILNET_IP:-100.86.36.78}"
    )


def strict_dotenv_offenders(text: str, label: str = "<text>") -> list[str]:
    """Lines in a dotenv file that are not exactly `KEY=value`.

    Extracted from the test below so Chunk 3's branch `.env` renderer is held
    to the SAME predicate rather than a second copy of it -- the renderer's
    whole job is to produce a file this rule accepts, and two implementations
    of one rule is how this repo has already lost time twice.
    """
    offenders = []
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if "=" not in line:
            continue
        key = line.split("=", 1)[0]
        if key != key.strip() or line != line.lstrip():
            offenders.append(f"{label}:{number}: {line[:40]!r}")
    return offenders


def test_dotenv_files_use_strict_key_equals_value():
    """`KEY = value` is accepted by Compose and by nothing else.

    Compose's dotenv parser trims whitespace, so production ran for months
    with `DOMAIN_NAME = ...` on line 1. But `docker run --env-file` refuses
    the file outright ("variable 'DOMAIN_NAME ' contains whitespaces") and
    `. ./.env` in a shell mis-parses it as a command. That cost a debugging
    detour while validating the Caddyfile, and it matters beyond tooling:
    spec 4.1 renders a BRANCH's .env from production's, so a tolerated
    oddity here propagates into every branch.
    """
    offenders = []
    for name in (".env", ".env.template"):
        path = REPO_ROOT / name
        if not path.exists():
            continue
        offenders += strict_dotenv_offenders(path.read_text(), name)

    assert offenders == [], (
        "dotenv assignments must be exactly KEY=value with no surrounding "
        f"whitespace: {offenders}"
    )


def test_no_service_binds_a_path_outside_the_repo(config):
    """Spec 5.2: `./forgejo`, `./Caddyfile.d`, `./agent-authz/data` are
    already relative, so a worktree's are its own. Two absolute mounts broke
    that -- ~/.hermes made a branch share production's agent state, and
    the absolute repo path made a branch's Hermes see production's tree.

    Both sides are resolved before comparison: `docker compose config`
    reports paths from Go's os.Getwd(), which trusts a stale $PWD, and on
    this host /home is a symlink to /var/home.
    """
    offending = []
    for name, service in config["services"].items():
        for volume in service.get("volumes", []):
            if volume.get("type") != "bind":
                continue
            source = Path(volume["source"]).resolve()
            if source in ALLOWED_EXTERNAL_BINDS:
                continue
            if source != REPO_ROOT and REPO_ROOT not in source.parents:
                offending.append((name, str(source), volume["target"]))

    assert offending == [], (
        "Bind mounts resolving outside the repo -- a second copy of this "
        f"stack would share production's state through them: {offending}"
    )


def test_hermes_sees_its_own_worktree_not_a_fixed_path(config):
    """The workspace mount must be `.`, so a branch's Hermes sees the branch,
    and its TARGET must not encode which checkout it is."""
    hermes = config["services"]["hermes"]
    workspace = [
        v for v in hermes["volumes"]
        if v.get("target", "").startswith("/opt/data/workspace/")
    ]
    assert len(workspace) == 1, f"expected one workspace bind, got {workspace}"
    assert Path(workspace[0]["source"]).resolve() == REPO_ROOT
    assert workspace[0]["target"] == "/opt/data/workspace/aurora"


# The old project name, assembled at runtime. Written this way on purpose:
# the gate below scans tracked files for it, and a literal here would make
# this file its own first offender.
OLD_PROJECT = "tai" + "-review"


def test_the_project_name_is_declared_not_inherited_from_the_directory():
    """Spec 4.3: set COMPOSE_PROJECT_NAME explicitly, do not rely on the
    directory-basename default. Before Chunk 2 it was unset, so the project
    was named after whichever directory the repo happened to be cloned into -
    which is also why Chunk 3's `br-<name>` had no sibling to be named
    against."""
    template = (REPO_ROOT / ".env.template").read_text()
    assert "COMPOSE_PROJECT_NAME=aurora" in template


def test_no_tracked_file_outside_docs_names_the_old_project():
    """The stack was named after an unrelated earlier project until Chunk 2.

    Everything under docs/ is a dated record of what was true when it was
    written and is left verbatim. Anything else naming it is a LIVE
    reference - a container name, a network, a host path - that would either
    break outright or, worse, quietly resolve against nothing.
    """
    # Deliberate exceptions, both of the same shape: a test that asserts a
    # literal is ABSENT, or is REFUSED, has to contain that literal itself.
    #
    #   test_guard_coverage.py asserts the M5 literals are absent from
    #   dev_administration's source.
    #
    #   test_branch_harness.py asserts that branch_harness.assert_not_production
    #   refuses BOTH of production's names - the pre-rename one and the
    #   post-rename one. Chunk 2's rename is blocked, not cancelled, so a guard
    #   that only refused one of them would be wrong in one of the two worlds,
    #   and the test that pins it can only do so by naming both. The harness
    #   MODULE itself names neither; only its test does.
    allowed = {
        "dev-administration/tests/test_guard_coverage.py",
        "tests/test_branch_harness.py",
        # ops/docker-guard exists BECAUSE of the 2026-07-29 incident, in which
        # a `compose down -v` was run against live production. Its refusal
        # message quotes that command verbatim so the next reader knows why
        # the guard is there, and its test asserts production is refused BY
        # NAME -- a guard that cannot name the thing it protects cannot be
        # tested against it. Same justification as the two entries above:
        # those files name the old project in order to FORBID it.
        #
        # Note this comment carefully does NOT spell the old name: writing it
        # here would make THIS file the first offender, which is exactly what
        # happened on the first attempt and why OLD_PROJECT is assembled
        # rather than written out.
        "ops/docker-guard",
        "ops/guardtest.sh",
        # ops/deploy-rename.sh performs the rename, so it must name both
        # the old project and the new one. A rename script that cannot
        # say what it is renaming from is not a rename script.
        "ops/deploy-rename.sh",
        # aurora-cli/tests/test_guards.py, added in Task 10, is the same shape
        # again and was found RED at Task 10's entry: Task 9 committed it
        # without an exemption, and this gate walks `git ls-files`, so an
        # uncommitted run of the suite passed misleadingly. (Task 0 recorded
        # that exact trap; it recurred.) The file parametrises the guard's
        # refusal over BOTH of production's names -- the pre-rename one and
        # the post-rename one -- because a guard that refused only one would
        # be wrong in one of the two worlds and nobody would notice until that
        # world arrived. `aurora_cli/guards.py` itself names NEITHER; Task 10
        # elided the one occurrence in its docstring rather than exempting the
        # module, so only the test that must assert on the literals carries
        # them.
        "aurora-cli/tests/test_guards.py",
    }

    tracked = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=True,
    ).stdout.split("\0")

    offenders = []
    for rel in tracked:
        if not rel or rel.startswith("docs/") or rel in allowed:
            continue
        path = REPO_ROOT / rel
        if not path.is_file():
            continue
        try:
            body = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue        # binary or unreadable: nothing to name anything
        if OLD_PROJECT in body:
            offenders.append(rel)

    assert offenders == [], (
        f"Tracked files still naming {OLD_PROJECT!r}: {offenders}. If one is "
        "a historical record, it belongs under docs/; if it is live, fix it."
    )


def test_the_conformance_gate_has_containers_to_conform_to():
    """PRODUCTION_PROJECT names the project whose containers every runtime
    test compares the declaration against. If that name is wrong the query
    returns an empty set and the entire runtime gate passes VACUOUSLY -
    which is precisely what a project rename does to a conformance suite.

    While the declarations name the new project and the deployed containers
    still carry the old label, run the suite with AURORA_PROJECT set to the
    live project name.
    """
    from conftest import PRODUCTION_PROJECT, project_containers

    assert project_containers(), (
        "No running containers carry com.docker.compose.project="
        f"{PRODUCTION_PROJECT!r}. Either the stack is down, or "
        "PRODUCTION_PROJECT is stale - set AURORA_PROJECT to the live "
        "project name. Do NOT let the runtime gate pass on an empty set."
    )


def test_every_path_dev_admin_writes_is_backed_by_a_bind(config):
    """A write to an unmounted container path is a silent no-op.

    `dev-admin` runs once per deploy and exits, so anything it writes to a
    path with no bind lands in the container's own layer and is discarded
    with the container. That is not hypothetical: `OWNERS_MAP_PATH` defaulted
    to `/output/agent-authz-data/owners.json`, which was mounted nowhere, so
    `reconcile` "succeeded" for three days while `agent-authz` enforced a
    stale owner map. `os.makedirs` inside a container raises nothing, and the
    code's only warning is on `except OSError`, so nothing surfaced.

    Checked against the RESOLVED config rather than the file, so an override
    that removes the bind is caught too.
    """
    service = config["services"]["dev-admin"]

    env = service.get("environment") or {}
    if isinstance(env, list):
        env = dict(item.split("=", 1) for item in env if "=" in item)

    written = {
        key: value for key, value in env.items()
        if key.endswith("_PATH") and str(value).startswith("/")
    }
    assert written, (
        "vacuous: dev-admin declares no absolute *_PATH variable, so this "
        f"test proves nothing about where it writes. environment={sorted(env)}"
    )

    targets = [
        volume["target"] for volume in service.get("volumes", [])
        if volume.get("target")
    ]
    assert targets, "vacuous: dev-admin declares no volumes at all"

    unbacked = []
    for key, value in written.items():
        parent = PurePosixPath(value).parent
        if not any(
            parent == PurePosixPath(t) or PurePosixPath(t) in parent.parents
            or parent in PurePosixPath(t).parents
            for t in targets
        ):
            unbacked.append(f"{key}={value} (no bind covers {parent})")

    assert unbacked == [], (
        "dev-admin writes to container paths that nothing is mounted at, so "
        "the writes are discarded when the container exits:\n  "
        + "\n  ".join(unbacked)
    )
