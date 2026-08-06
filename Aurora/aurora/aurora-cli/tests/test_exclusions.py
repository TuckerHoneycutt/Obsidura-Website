"""The exclusion manifest and its transitive closure (spec §7.2, Task 4).

Where the expectations come from, and why it matters
----------------------------------------------------
Three ways this project has already shipped tests that pass while testing
nothing, all three of which apply here:

* **self-blinding** (Task 2's PLAN DEFECT 5) — if the checker read the same
  `also_exclude` lists the closure reads, deleting an entry would blind both in
  one stroke. So the dependency expectations here come from the RESOLVED
  compose configuration, and the necessity of the closure is proved by handing
  real Compose an incomplete one and reading its exit code.
* **artifact vs generator** (Task 3) — `branch-services.yaml` is the artifact
  and `exclusions.py` is the reader; a test of one says nothing about the
  other. Both directions are covered: the manifest is checked against the
  compose graph, and the renderer's output is checked by running Compose on it.
* **sequential-guard `raises`** (Task 1) — `validate_excludable` raises
  `ExclusionError` from two different guards and `load_manifest` from a dozen.
  Every `pytest.raises` here asserts on the message, and where two guards could
  both fire it asserts the OTHER one's wording is absent.

Every `docker compose` invocation below is `config` — read-only — and every one
of them runs under a `br-` project name, so nothing here can name, touch or
resolve production's project even by accident.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml

from aurora_cli import branch, envfile, exclusions, identity, overlay

REPO_ROOT = identity.package_root()

#: Everything `docker compose config` needs to resolve the branch overlay. The
#: project name is inside the `br-` namespace for the same reason every other
#: probe in this chunk is: it is the only structural difference between a test
#: and the command that destroyed production.
BRANCH_ENV = {
    "COMPOSE_PROJECT_NAME": "br-t4exclusions",
    "TS_HOSTNAME": "aurora-t4exclusions",
    "TS_AUTHKEY": "tskey-fake",
}

#: One developer, never `agents`. Spec D7: a branch provisions the developers
#: it was asked for, and `agents` starts every one of them.
#:
#: Read from `developers.yaml` rather than typed. This was `agent-testuser`
#: until that QA account was deleted on 2026-07-30, and the failure mode was
#: instructive: `COMPOSE_PROFILES=agent-<gone>` activates no profile and is
#: not an error anywhere in Compose, so every probe below silently resolved a
#: config with no agent in it. The tests that survived that were the ones
#: asserting on a named service; the rest would have gone quietly vacuous.
BRANCH_DEV = branch.known_developers()[0]
BRANCH_PROFILES = f"agent-{BRANCH_DEV}"

BRANCH_FILES = (overlay.BASE_COMPOSE_NAME, overlay.OVERLAY_NAME)


# --------------------------------------------------------------- helpers


def compose_config(files, profiles=BRANCH_PROFILES, env=None):
    """Raw `docker compose … config`, kept as a CompletedProcess.

    `overlay.resolve_config` is the one implementation for "give me the
    resolved configuration" and is used below wherever a dict is what is
    wanted. It cannot be used here because it raises on a non-zero exit and
    this module's central test is ABOUT the non-zero exit — the exit code and
    the stderr are the measurement, not an obstacle to it.
    """
    environ = dict(os.environ)
    environ["COMPOSE_PROFILES"] = profiles
    environ.update(BRANCH_ENV)
    environ.update(env or {})
    cmd = ["docker", "compose"]
    for name in files:
        cmd += ["-f", str(name)]
    cmd += ["config", "--services"]
    return subprocess.run(
        cmd, cwd=REPO_ROOT, capture_output=True, text=True, env=environ
    )


def branch_services(exclude_file, profiles=BRANCH_PROFILES):
    """The service names a branch would actually resolve to. Asserts non-empty."""
    result = compose_config(BRANCH_FILES + (exclude_file,), profiles)
    assert result.returncode == 0, (
        f"`docker compose config` failed for {exclude_file}:\n{result.stderr}"
    )
    names = sorted(n.strip() for n in result.stdout.splitlines() if n.strip())
    assert len(names) > 1, (
        f"the branch resolved to {names}, too few to be this stack; every "
        "assertion below would pass vacuously"
    )
    return names


def base_services():
    """Every service key the repo declares, with every profile active."""
    config = overlay.resolve_config(REPO_ROOT)
    services = sorted(config.get("services") or {})
    assert len(services) > 1, (
        "the resolved compose configuration named no services; check that "
        'COMPOSE_PROFILES="*" reached `docker compose config`'
    )
    return services


@pytest.fixture(scope="module")
def manifest():
    return exclusions.load_manifest()


@pytest.fixture(scope="module")
def config():
    return overlay.resolve_config(REPO_ROOT)


def write_manifest(tmp_path, document) -> Path:
    path = tmp_path / exclusions.MANIFEST_NAME
    path.write_text(yaml.safe_dump(document), encoding="utf-8")
    return path


#: A three-level chain and a cycle, in one fixture manifest.
#:
#: THREE levels, not two, on purpose: a `closure` that recursed exactly one
#: level would close a two-link chain correctly and this test would pin
#: nothing. `a → b → c → d` is the shortest chain that a one-level expansion
#: gets wrong (it stops at `b`).
CHAIN = {
    "services": {
        "a": {"excludable": True, "also_exclude": ["b"]},
        "b": {"excludable": False, "why": "only via a", "also_exclude": ["c"]},
        "c": {"excludable": False, "why": "only via b", "also_exclude": ["d"]},
        "d": {"excludable": False, "why": "leaf"},
        "loop-x": {"excludable": True, "also_exclude": ["loop-y"]},
        "loop-y": {"excludable": False, "why": "cycle", "also_exclude": ["loop-x"]},
    }
}


# ------------------------------------------------------------- the closure


def test_closure_is_transitive(tmp_path):
    chain = exclusions.load_manifest(write_manifest(tmp_path, CHAIN))

    assert exclusions.closure(["a"], chain) == {"a", "b", "c", "d"}, (
        "the closure stopped short of the end of the chain; a service whose "
        "dependent is still declared makes the whole compose project invalid"
    )
    # The single-link case a one-level implementation also gets right, kept so
    # the assertion above is clearly about DEPTH and not about arity.
    assert exclusions.closure(["c"], chain) == {"c", "d"}


def test_closure_terminates_on_a_cycle(tmp_path):
    chain = exclusions.load_manifest(write_manifest(tmp_path, CHAIN))

    assert exclusions.closure(["loop-x"], chain) == {"loop-x", "loop-y"}
    assert exclusions.closure(["loop-y"], chain) == {"loop-x", "loop-y"}


def test_closure_of_nothing_is_nothing(manifest):
    assert exclusions.closure([], manifest) == set()


def test_excluding_forgejo_pulls_in_forgejo_mcp(manifest):
    """Against the REAL manifest, not a fixture."""
    closed = exclusions.closure(["forgejo"], manifest)

    assert "forgejo-mcp" in closed, (
        "forgejo-mcp `depends_on: forgejo`; leaving it behind makes every "
        "subsequent `docker compose` call fail with `depends on undefined "
        "service`"
    )
    assert "forgejo" in closed


# -------------------------------------------- the manifest names real things


def test_manifest_names_only_real_service_keys(manifest):
    """Service KEYS, never `container_name` values.

    `affine/compose.yml` declares `affine`, `affine_migration`, `redis`,
    `postgres`; `docker ps` shows `affine_server`, `affine_migration_job`,
    `affine_redis`, `affine_postgres`. The second list matches nothing.
    """
    declared = base_services()
    named = exclusions.manifest_services(manifest)
    assert named, "the manifest named no services at all"

    unknown = sorted(named - set(declared))
    assert unknown == [], (
        f"{exclusions.MANIFEST_NAME} names {unknown}, which are not compose "
        f"service keys. Declared services are {declared}. A `container_name` "
        "value (affine_server, affine_migration_job, affine_redis, "
        "affine_postgres) matches nothing and excludes nothing."
    )


def test_the_manifest_uses_no_container_name_values(manifest, config):
    """The same mistake, named explicitly, so its failure message says so.

    Note the subtraction: several services legitimately declare a
    `container_name` EQUAL to their key (`forgejo`, `dev-admin`, `hermes`), so
    "is a container_name value" is not by itself the error. The error is a name
    that is a container_name value and is NOT a service key — which is exactly
    the `affine_server` / `affine_migration_job` / `affine_postgres` family.
    """
    services = config.get("services") or {}
    assert services
    container_names = {
        body["container_name"]
        for body in services.values()
        if (body or {}).get("container_name")
    }
    assert container_names, "no service declares a container_name — check the config"

    offenders = sorted(
        (exclusions.manifest_services(manifest) & container_names) - set(services)
    )
    assert offenders == [], (
        f"{exclusions.MANIFEST_NAME} names {offenders}, which are "
        "`container_name` VALUES rather than compose service keys, and so "
        "match no service and exclude nothing"
    )


def test_every_excludable_service_is_a_real_one(manifest):
    excludable = exclusions.excludable_services(manifest)
    assert excludable, "no service is excludable, so the feature does nothing"
    assert set(excludable) <= set(base_services())


# ------------------------------------------- the closure is not optional


def test_excluding_without_the_closure_is_a_compose_error(tmp_path, manifest):
    """The empirical proof. Without it, the closure is justified by prose.

    Compose v5.3.1: a `depends_on` target behind an inactive profile is not a
    loose end, it is `invalid compose project` and exit 1 — for `config`, `up`
    and `down` alike.
    """
    # Deliberately NOT closed: exactly what `--without forgejo` would produce
    # if `also_exclude` were ignored.
    (tmp_path / "short").mkdir()
    short = exclusions.write_exclusion_overlay(
        ["forgejo"], tmp_path / "short", manifest
    )

    result = compose_config(BRANCH_FILES + (short,))
    assert result.returncode != 0, (
        "excluding forgejo while forgejo-mcp and dev-admin still declare "
        "`depends_on: forgejo` resolved cleanly. Either Compose stopped "
        "validating depends_on, or nothing was actually excluded — check that "
        f"{short.name} parks the service behind the "
        f"{exclusions.EXCLUDED_PROFILE!r} profile:\n{short.read_text()}"
    )
    assert "depends on undefined service" in result.stderr, (
        f"expected a dangling-dependency error, got:\n{result.stderr}"
    )

    (tmp_path / "closed").mkdir()
    full = exclusions.write_exclusion_overlay(
        exclusions.closure(["forgejo"], manifest), tmp_path / "closed", manifest
    )
    result = compose_config(BRANCH_FILES + (full,))
    assert result.returncode == 0, (
        "the closure of `--without forgejo` still leaves a dangling "
        f"dependency:\n{result.stderr}\noverlay was:\n{full.read_text()}"
    )

    resolved = sorted(n.strip() for n in result.stdout.splitlines() if n.strip())
    assert len(resolved) > 1
    for gone in exclusions.closure(["forgejo"], manifest):
        assert gone not in resolved, (
            f"{gone} is in the closure of `--without forgejo` but Compose still "
            f"resolves it: {resolved}"
        )


@pytest.mark.parametrize("service", exclusions.excludable_services())
def test_the_manifests_closures_leave_no_dangling_dependent(service, manifest, config):
    """Derived from the compose graph, so a short `also_exclude` cannot survive.

    This is the gate that caught the plan's own starting content: it gave
    `forgejo: also_exclude: [forgejo-mcp]` and stopped there, but `dev-admin`
    also `depends_on: forgejo`, so the plan's manifest produced `service
    "dev-admin" depends on undefined service "forgejo"` on the very next
    compose call.

    Parametrised over every EXCLUDABLE service. The protected ones are excluded
    on purpose: `caddy`'s closure is incoherent — `forgejo` and `dev-admin`
    both `depends_on: caddy` — and that incoherence is precisely why it carries
    `excludable: false`. `test_a_protected_service_is_protected_for_a_reason`
    below holds the other end.
    """
    closed = exclusions.closure([service], manifest)
    dangling = exclusions.dangling_dependents(closed, config)

    assert dangling == {}, (
        f"excluding {service} closes to {sorted(closed)}, which leaves "
        f"{dangling} depending on services that would no longer exist. Compose "
        "refuses the whole project. Add the dependents to "
        f"`{service}: also_exclude:` in {exclusions.MANIFEST_NAME}."
    )


def test_a_protected_service_is_protected_for_a_reason(manifest, config):
    """`caddy` cannot be excluded coherently: two services `depends_on` it and
    the branch's whole tailnet identity hangs off it. Measured, so
    `excludable: false` is a fact about the graph rather than an opinion in a
    comment."""
    dangling = exclusions.dangling_dependents(
        exclusions.closure(["caddy"], manifest), config
    )
    assert dangling, (
        "nothing depends on caddy any more, so the mechanical half of its "
        "`excludable: false` no longer holds — re-read the sidecar argument in "
        f"{exclusions.MANIFEST_NAME} before changing it"
    )
    assert manifest["caddy"].excludable is False


def test_the_dangling_check_can_actually_fail(config):
    """Without this, `dangling_dependents` returning `{}` unconditionally would
    make every parametrisation above pass."""
    dangling = exclusions.dangling_dependents(["forgejo"], config)
    assert "forgejo-mcp" in dangling and "forgejo" in dangling["forgejo-mcp"]
    assert "dev-admin" in dangling


def test_the_dangling_check_refuses_an_empty_configuration():
    with pytest.raises(exclusions.ExclusionError) as excinfo:
        exclusions.dangling_dependents(["forgejo"], {"services": {}})
    assert "vacuously" in str(excinfo.value)


# ------------------------------------------------------------ refusals


def test_a_non_excludable_service_is_refused(manifest):
    with pytest.raises(exclusions.ExclusionError) as excinfo:
        exclusions.validate_excludable(["agent-authz"], manifest)
    message = str(excinfo.value)

    assert "forward_auth" in message, (
        "the refusal must quote the manifest's `why:` — the type alone tells "
        f"the caller nothing about what to do instead. Got: {message}"
    )
    # `validate_excludable` raises this same type for an UNKNOWN service too.
    # Without this the mutation "accept anything" would still be red whenever
    # the other guard happened to fire, and the test would pin the wrong guard.
    assert "is not listed" not in message, (
        f"agent-authz was refused as unknown rather than as protected: {message}"
    )


def test_caddy_is_refused_too(manifest):
    with pytest.raises(exclusions.ExclusionError) as excinfo:
        exclusions.validate_excludable(["caddy"], manifest)
    assert "tailnet node" in str(excinfo.value)


def test_an_unknown_service_is_refused_for_a_different_reason(manifest):
    with pytest.raises(exclusions.ExclusionError) as excinfo:
        exclusions.validate_excludable(["affine_server"], manifest)
    message = str(excinfo.value)
    assert "is not listed" in message
    assert "cannot be excluded" not in message


def test_a_transitively_excluded_service_cannot_be_named_directly(manifest):
    """`postgres` goes when `affine` goes, but `--without postgres` is refused.

    The two are different questions and conflating them would let a caller
    remove AFFiNE's database out from under a running AFFiNE.
    """
    assert "postgres" in exclusions.closure(["affine"], manifest)
    with pytest.raises(exclusions.ExclusionError):
        exclusions.validate_excludable(["postgres"], manifest)


def test_every_excludable_service_is_accepted(manifest):
    """The control case. Without it an unconditionally-raising
    `validate_excludable` satisfies every refusal test above."""
    exclusions.validate_excludable(exclusions.excludable_services(manifest), manifest)


# ------------------------------------------------------- the loader refuses


@pytest.mark.parametrize(
    "entry, phrase",
    [
        ({"why": "no verdict"}, "does not declare `excludable:`"),
        ({"excludable": "yes"}, "not a boolean"),
        ({"excludable": False}, "carries no `why:`"),
        ({"excludable": True, "also_excludes": ["x"]}, "unknown key"),
        ({"excludable": True, "also_exclude": "x"}, "not a list"),
        ({"excludable": True, "also_exclude": ["svc"]}, "lists itself"),
        ({"excludable": True, "also_exclude": ["x", "x"]}, "repeats a name"),
        ({"excludable": True, "on_exclude": {"envs": {}}}, "unknown `on_exclude` key"),
        (
            {"excludable": True, "on_exclude": {"env": {"X": "{producton_url}"}}},
            "unknown placeholder",
        ),
    ],
)
def test_the_loader_refuses_an_underspecified_entry(tmp_path, entry, phrase):
    path = write_manifest(tmp_path, {"services": {"svc": entry}})
    with pytest.raises(exclusions.ExclusionError) as excinfo:
        exclusions.load_manifest(path)
    assert phrase in str(excinfo.value), (
        f"entry {entry} was refused, but for the wrong reason: {excinfo.value}"
    )


def test_the_loader_refuses_an_empty_manifest(tmp_path):
    path = write_manifest(tmp_path, {"services": {}})
    with pytest.raises(exclusions.ExclusionError) as excinfo:
        exclusions.load_manifest(path)
    assert "empty" in str(excinfo.value)


def test_the_real_manifest_loads_and_keeps_its_why(manifest):
    assert "forward_auth" in manifest["agent-authz"].why
    assert manifest["agent-authz"].excludable is False
    assert manifest["forgejo"].excludable is True


# ---------------------------------------------------------------- profiles


def test_profiles_for_is_empty_when_nothing_is_excluded(manifest):
    assert exclusions.profiles_for([], manifest) == ""


def test_profiles_for_parks_an_excluded_service(manifest):
    assert exclusions.profiles_for(["arcadedb"], manifest) == exclusions.EXCLUDED_PROFILE


def test_profiles_for_never_activates_every_developers_agent(manifest):
    """Spec D7. `agents` starts every developer's agent, and the branch's
    COMPOSE_PROFILES is the union of the agent profiles and whatever this
    emits."""
    for service in exclusions.excludable_services(manifest):
        emitted = exclusions.profiles_for([service], manifest).split(",")
        assert envfile.ALL_DEVELOPERS_PROFILE not in emitted


def test_the_exclusion_profile_is_not_a_profile_any_service_already_declares(config):
    """A collision would mean activating one developer's agent un-excluded
    something, or vice versa."""
    declared = {
        profile
        for body in (config.get("services") or {}).values()
        for profile in ((body or {}).get("profiles") or [])
    }
    assert declared, "no service declares a profile — check the resolved config"
    assert exclusions.EXCLUDED_PROFILE not in declared


def test_the_branch_profile_string_refuses_to_activate_the_exclusion_profile(manifest):
    """The silent direction: if the parked profile ever reached
    COMPOSE_PROFILES, every excluded service would come straight back."""
    assert exclusions.branch_profiles(BRANCH_PROFILES, ["forgejo"], manifest) == (
        BRANCH_PROFILES
    )
    with pytest.raises(exclusions.ExclusionError) as excinfo:
        exclusions.branch_profiles(
            f"{BRANCH_PROFILES},{exclusions.EXCLUDED_PROFILE}", ["forgejo"], manifest
        )
    assert "silently do nothing" in str(excinfo.value)


def test_activating_the_exclusion_profile_undoes_the_exclusion(tmp_path, manifest):
    """Measured, not asserted from the docstring of the test above."""
    path = exclusions.write_exclusion_overlay(
        exclusions.closure(["forgejo"], manifest), tmp_path, manifest
    )
    without = branch_services(path)
    assert "forgejo" not in without

    with_it = branch_services(
        path, profiles=f"{BRANCH_PROFILES},{exclusions.EXCLUDED_PROFILE}"
    )
    assert "forgejo" in with_it, (
        "activating the parked profile did not bring the service back, so the "
        "service was omitted for some other reason and this test's premise is "
        "wrong"
    )


# ------------------------------------------------- no holes in the stack


def test_a_branch_with_no_exclusions_starts_the_whole_stack(tmp_path, manifest):
    """The other silent failure: an exclusion mechanism that removes something
    nobody asked to remove.

    Compared against the SAME configuration without the exclusion overlay, so
    the expectation is Compose's own answer rather than a list maintained here.
    """
    path = exclusions.write_exclusion_overlay([], tmp_path, manifest)

    with_overlay = branch_services(path)
    baseline = compose_config(BRANCH_FILES)
    assert baseline.returncode == 0, baseline.stderr
    without_overlay = sorted(
        n.strip() for n in baseline.stdout.splitlines() if n.strip()
    )

    assert with_overlay == without_overlay, (
        "adding an empty exclusion overlay changed which services a branch "
        f"resolves to: {sorted(set(without_overlay) ^ set(with_overlay))}"
    )
    assert overlay.SIDECAR_SERVICE in with_overlay, (
        "the branch overlay was not applied, so this proves nothing"
    )


def test_a_branch_provisions_only_the_developers_it_was_asked_for(tmp_path, manifest):
    """The union direction: the branch profile string must select one agent,
    not `agents`."""
    path = exclusions.write_exclusion_overlay([], tmp_path, manifest)
    resolved = branch_services(
        path, profiles=exclusions.branch_profiles(BRANCH_PROFILES, [], manifest)
    )

    agents = [n for n in resolved if n.startswith("hermes-")]
    assert agents == [f"hermes-{BRANCH_DEV}"], (
        f"a branch asked for one developer resolved {agents}; `agents` or a "
        "wildcard profile leaked into COMPOSE_PROFILES"
    )


def test_excluding_affine_removes_its_database_and_nothing_else(tmp_path, manifest):
    path = exclusions.write_exclusion_overlay(
        exclusions.closure(["affine"], manifest), tmp_path, manifest
    )
    resolved = branch_services(path)

    for gone in ("affine", "affine_migration", "postgres", "redis"):
        assert gone not in resolved
    for kept in ("caddy", "forgejo", "hermes", overlay.SIDECAR_SERVICE):
        assert kept in resolved, (
            f"excluding affine also removed {kept}; the closure over-reaches"
        )


# --------------------------------------------------- on_exclude.env rewiring


def test_on_exclude_env_is_applied(manifest):
    overrides = exclusions.env_overrides_for(["forgejo"], manifest)
    domain = identity.production_domain()

    assert overrides["FORGEJO_URL"] == f"https://{domain}/git", (
        "excluding forgejo must point FORGEJO_URL at PRODUCTION's forge "
        "(spec §5.4), and the hostname must come from Task 1's derivation"
    )
    assert domain not in exclusions.manifest_path().read_text(), (
        f"{exclusions.MANIFEST_NAME} names production's domain as a literal; "
        "it must use the {production_url} placeholder so the manifest is "
        "correct on more than one host"
    )
    assert domain not in Path(exclusions.__file__).read_text(), (
        "exclusions.py names production's domain as a literal"
    )


def test_on_exclude_env_matches_productions_own_value(manifest):
    """Derived from production's `.env`, so a moved route path fails loudly
    instead of pointing a branch at a 404."""
    production = envfile.parse_env(envfile.production_env_text())
    overrides = exclusions.env_overrides_for(["forgejo"], manifest)

    assert overrides["FORGEJO_URL"] == production["FORGEJO_URL"], (
        "the manifest's suffix no longer matches production's FORGEJO_URL "
        f"({production['FORGEJO_URL']!r}); a branch without its own forge would "
        "be pointed at a URL that resolves to nothing"
    )


def test_nothing_is_rewired_when_nothing_is_excluded(manifest):
    assert exclusions.env_overrides_for([], manifest) == {}
    assert exclusions.production_reference_exemptions([], manifest) == frozenset()


def test_on_exclude_env_reaches_the_rendered_branch_env(manifest):
    """Task 2's renderer is the consumer; the rewiring is worthless if it stops
    at a dict."""
    overrides = exclusions.env_overrides_for(["forgejo"], manifest)
    text = envfile.render_branch_env(
        "t4-exclusions",
        devs=(BRANCH_DEV,),
        authkey="tskey-fake",
        exclusions_env=overrides,
    )
    rendered = envfile.parse_env(text)

    assert rendered["FORGEJO_URL"] == overrides["FORGEJO_URL"]
    assert f"FORGEJO_URL={overrides['FORGEJO_URL']}" in text

    # And the branch's OWN identity still wins everywhere else — an exclusion
    # applied last must not drag the rest of the file back to production.
    assert rendered["COMPOSE_PROJECT_NAME"] == identity.branch_project("t4-exclusions")
    assert rendered["DOMAIN_NAME"] == identity.branch_domain("t4-exclusions")


def test_the_production_reference_is_exempted_only_because_forgejo_is_excluded(manifest):
    """Task 2's rule 1 — no branch variable may name production — is the most
    valuable thing in that task (finding N1). This is the ONE exemption, and it
    is derived from the exclusion set rather than kept in a list."""
    exempt = exclusions.production_reference_exemptions(["forgejo"], manifest)
    assert exempt == frozenset({"FORGEJO_URL"})

    text = envfile.render_branch_env(
        "t4-exclusions",
        devs=(BRANCH_DEV,),
        authkey="tskey-fake",
        exclusions_env=exclusions.env_overrides_for(["forgejo"], manifest),
    )
    unexempted = envfile.missing_overrides(text, "t4-exclusions")
    assert "FORGEJO_URL" in envfile.defect_variables(unexempted), (
        "Task 2's hazard rule no longer notices a branch variable naming "
        "production; the exemption below would then be exempting nothing"
    )

    exempted = envfile.missing_overrides(
        text, "t4-exclusions", allowed_production_references=exempt
    )
    assert exempted == [], (
        f"a branch with `--without forgejo` is not renderable: {exempted}"
    )


def test_the_exemption_forgives_only_what_it_names(manifest):
    """An exemption that swallowed every production reference would silently
    re-open N1. Both halves of Task 2's checker are exercised, because the
    exemption had to be threaded through both."""
    domain = identity.production_domain()
    rendered = {
        "COMPOSE_PROJECT_NAME": identity.branch_project("t4"),
        "COMPOSE_PROFILES": BRANCH_PROFILES,
        "FORGEJO_URL": f"https://{domain}/git",
        "SOMETHING_ELSE": f"https://{domain}/other",
    }
    hazards = envfile.inherited_hazards(
        rendered, "t4", allowed_production_references=frozenset({"FORGEJO_URL"})
    )
    names = envfile.defect_variables(hazards)
    assert "SOMETHING_ELSE" in names
    assert "FORGEJO_URL" not in names

    # manifest_gaps: exempting FORGEJO_URL must not exempt a DIFFERENT fatal
    # variable that was inherited rather than derived...
    source = {"FORGEJO_URL": f"https://{domain}/git", "DOMAIN_NAME": domain}
    gaps = envfile.manifest_gaps(
        {**rendered, "DOMAIN_NAME": domain},
        source=source,
        allowed_production_references=frozenset({"FORGEJO_URL"}),
    )
    assert "DOMAIN_NAME" in envfile.defect_variables(gaps)
    assert "FORGEJO_URL" not in envfile.defect_variables(gaps)

    # ...and must not forgive an ABSENT variable either. Being allowed to point
    # at production is not the same as being allowed to be missing.
    gaps = envfile.manifest_gaps(
        {k: v for k, v in rendered.items() if k != "FORGEJO_URL"},
        source=source,
        allowed_production_references=frozenset({"FORGEJO_URL"}),
    )
    assert "FORGEJO_URL" in envfile.defect_variables(gaps)


def test_every_rewired_variable_is_covered_by_the_consumer_gate(manifest):
    """The gate below must not be able to go stale by omission.

    Review of Tasks 1-4 measured this: giving an unrelated service an
    `on_exclude.env` rewire (e.g. arcadedb ->
    AFFINE_SERVER_EXTERNAL_URL: "{production_url}/affine") produced a branch
    .env pointing at production's AFFiNE, `missing_overrides(...) == []`, and
    a fully green suite -- because the consumer gate names FORGEJO_URL and
    nothing else. A new rewire must therefore either be covered here or fail.

    FORGEJO_URL is the only variable spec 5.4 sanctions pointing at
    production. Anything else that acquires a rewire is a decision somebody
    has to make explicitly, not one that arrives with a YAML block.
    """
    rewired = set()
    for rule in manifest.values():
        rewired |= set(rule.env or {})

    assert rewired <= {"FORGEJO_URL"}, (
        f"Manifest rewires {sorted(rewired - {'FORGEJO_URL'})}, which the "
        "consumer gate below does not examine. Either extend that gate to "
        "cover them, or do not rewire them: an on_exclude.env entry grants an "
        "automatic N1 exemption, and N1 is the property that stops a branch "
        "reconciling against production's Forgejo."
    )


def test_the_only_consumers_of_a_rewired_variable_outside_the_closure_are_agents(
    manifest, config
):
    """`--without forgejo` points FORGEJO_URL at production, so it is worth
    knowing exactly who reads it.

    Who "reads FORGEJO_URL" is derived by asking Compose: resolve the config
    twice, once normally and once with FORGEJO_URL set to a sentinel, and take
    the services whose definition changed. That is exact, needs no list of
    source files, and — unlike matching on the resolved VALUE — does not
    mistake `agent-authz`, whose `OIDC_ISSUER=https://${DOMAIN_NAME}/git`
    merely happens to equal production's FORGEJO_URL today and correctly
    becomes the BRANCH's issuer in a branch.

    `forgejo-mcp` and `dev-admin` are in the closure and therefore not running.
    What is left must be the per-developer agents and nothing else — that is
    the deliberate cross-wire spec §5.4 asks for ("no branch forge, so use
    production's"), and a NEW consumer appearing here is a cross-wire nobody
    decided on.
    """
    sentinel = "https://sentinel.invalid/git"
    probed = overlay.resolve_config(REPO_ROOT, env={"FORGEJO_URL": sentinel})

    services = config.get("services") or {}
    assert services
    assert set(probed.get("services") or {}) == set(services)

    consumers = {
        name
        for name, body in services.items()
        if json.dumps(body, sort_keys=True)
        != json.dumps(probed["services"][name], sort_keys=True)
    }
    assert consumers, (
        "changing FORGEJO_URL changed no service definition; the derivation is "
        "broken and every assertion below is vacuous"
    )

    survivors = consumers - exclusions.closure(["forgejo"], manifest)
    unexpected = sorted(s for s in survivors if not s.startswith("hermes-"))
    assert unexpected == [], (
        f"{unexpected} would still be running in a branch with `--without "
        f"forgejo` and would talk to PRODUCTION's forge. Either add them to "
        "forgejo's `also_exclude`, or decide the cross-wire deliberately and "
        "record it."
    )
    assert survivors, (
        "no surviving service reads FORGEJO_URL, so pointing it at production "
        "is dead configuration — the `on_exclude.env` entry should say so or go"
    )


# ------------------------------------------------------- the rendered overlay


def test_the_empty_overlay_is_a_valid_compose_document(tmp_path, manifest):
    """`services:` with nothing under it is `services must be a mapping` and
    exit 1; `services: {}` is fine. Measured on v5.3.1."""
    path = exclusions.write_exclusion_overlay([], tmp_path, manifest)
    document = yaml.safe_load(path.read_text())
    assert document == {"services": {}}
    assert compose_config(BRANCH_FILES + (path,)).returncode == 0


def test_the_overlay_parks_every_service_it_names(tmp_path, manifest):
    closed = exclusions.closure(["forgejo"], manifest)
    path = exclusions.write_exclusion_overlay(closed, tmp_path, manifest)
    document = yaml.safe_load(path.read_text())

    assert set(document["services"]) == closed
    for name, body in document["services"].items():
        assert body["profiles"] == [exclusions.EXCLUDED_PROFILE], (
            f"{name} was rendered with profiles {body['profiles']!r}; an EMPTY "
            "list means no profile at all, which starts the service"
        )


def test_the_ergonomic_entry_point_closes_first(manifest):
    """`branch up` calls this one; if it did not close, every branch with an
    exclusion would fail to start."""
    assert exclusions.exclusion_overlay_for(
        ["forgejo"], manifest
    ) == exclusions.render_exclusion_overlay(
        exclusions.closure(["forgejo"], manifest), manifest
    )


def test_the_overlay_is_written_even_when_nothing_is_excluded(tmp_path, manifest):
    """Trap 4: Compose's `-f` is a hard error on a missing file, so `branch up`
    must be able to pass the flag unconditionally."""
    path = exclusions.write_exclusion_overlay([], tmp_path, manifest)
    assert path.is_file()
    assert path.name == exclusions.EXCLUSION_OVERLAY_NAME


# ----------------------------------------------------- the sidecar decision


def test_caddy_is_not_excludable_while_the_sidecar_has_no_profile(manifest):
    """Task 3 left this open and asked Task 4 to decide it rather than discover
    it.

    The link is mechanical: `compose.branch.yml`'s tailscale sidecar carries no
    `profiles:`, so it always starts. Whatever service is flipped into its
    network namespace is the only thing bound to :443 there — exclude it and
    the branch is a live tailnet node that resolves and refuses. So the service
    in the sidecar's netns must not be excludable, and this reads BOTH facts out
    of the committed overlay rather than restating either.
    """
    document = overlay.load_overlay(
        overlay.overlay_path(REPO_ROOT).read_text()
    )
    services = document.get("services") or {}

    sidecar = services[overlay.SIDECAR_SERVICE]
    assert not sidecar.get("profiles"), (
        "the sidecar now declares a profile, so this test's premise has "
        "changed — revisit whether caddy may be excluded after all"
    )

    in_netns = sorted(
        name
        for name, body in services.items()
        if isinstance(body, dict)
        and body.get("network_mode") == f"service:{overlay.SIDECAR_SERVICE}"
    )
    assert in_netns, "no service shares the sidecar's network namespace"

    for name in in_netns:
        rule = manifest.get(name)
        assert rule is not None and not rule.excludable, (
            f"{name} is bound to :443 inside the sidecar's network namespace "
            "and the sidecar has no profile of its own. Excluding it leaves a "
            "branch with a live tailnet node and nothing behind it. Mark it "
            f"`excludable: false` in {exclusions.MANIFEST_NAME}."
        )


# ----------------------------------------------------------- housekeeping


def test_the_manifest_is_tracked_by_git():
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", exclusions.MANIFEST_NAME],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        f"{exclusions.MANIFEST_NAME} is not tracked; a fresh branch worktree "
        "would have no exclusion manifest at all"
    )


def test_the_generated_overlay_is_not_committed(tmp_path, manifest):
    """It is per-branch, unlike `compose.branch.yml`. A committed one would be
    one branch's exclusions applied to every branch."""
    result = subprocess.run(
        ["git", "ls-files", exclusions.EXCLUSION_OVERLAY_NAME],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    assert result.stdout.strip() == ""


def test_a_rewire_that_does_not_name_production_gets_no_exemption():
    """Pins the filter that keeps the N1 exemption narrow.

    `production_reference_exemptions` exempts only those rewired variables
    whose value actually embeds production's domain. Replacing that filter
    with `if True` survives the whole suite today, because `forgejo` is the
    only entry with a rewire and its one variable happens to be the
    production-pointing one -- so the narrowing is real but untested.

    A synthetic manifest supplies a second rewire that names nothing:
    it must NOT be exempted, or the exemption widens to "anything a manifest
    entry rewires", which is precisely the hole this filter exists to prevent.
    """
    from aurora_cli import exclusions

    domain = "prod.example.invalid"
    fake = {
        "svc-points-at-prod": exclusions.ServiceRule(
            name="svc-points-at-prod",
            excludable=True,
            also_exclude=(),
            env={"POINTS_AT_PROD": f"https://{domain}/thing"},
        ),
        "svc-points-elsewhere": exclusions.ServiceRule(
            name="svc-points-elsewhere",
            excludable=True,
            also_exclude=(),
            env={"POINTS_ELSEWHERE": "https://somewhere.else/thing"},
        ),
    }

    both = exclusions.production_reference_exemptions(
        ["svc-points-at-prod", "svc-points-elsewhere"], fake, domain=domain
    )
    assert both == frozenset({"POINTS_AT_PROD"}), (
        "the exemption must cover only values that actually name production; "
        f"got {sorted(both)}"
    )

    neither = exclusions.production_reference_exemptions(
        ["svc-points-elsewhere"], fake, domain=domain
    )
    assert neither == frozenset(), (
        "a rewire that names nothing must earn no exemption at all"
    )
