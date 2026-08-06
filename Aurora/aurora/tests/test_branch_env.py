"""Must-override conformance: a branch `.env` must not be wired to production.

This is the half of Task 2 that matters. `branch-env.yaml` is not paperwork
and this file is what makes that true, in BOTH directions:

* `test_rendered_branch_env_sets_every_required_variable` and
  `test_no_inherited_value_contains_productions_domain` catch a bad render;
* `test_manifest_covers_every_hostname_bearing_variable_in_production_env`
  catches a manifest that has fallen behind reality. Adding a
  hostname-bearing variable to `.env.template` fails HERE, in a unit test,
  instead of in a branch six weeks later. Finding the next N1 automatically
  is the point; a manifest that only lists what somebody remembered is the
  same failure one release later.

Why the two detectors are structurally independent
--------------------------------------------------
The plan's Task 2 asks for `missing_overrides(...) == []` and then requires
that deleting an entry from `branch-env.yaml` reddens it (mutations M1, M2).
A purely manifest-driven checker cannot do that: deleting an entry blinds the
renderer and the checker in the same stroke and the assertion stays green
while the branch is wired to production. So `aurora_cli.envfile` pairs the
manifest with `inherited_hazards()`, a rule set that owes the manifest
nothing, and `test_the_hazard_rules_survive_a_gutted_manifest` below pins
exactly that property. See the Task 2 ledger entry.

Nothing here types production's project name or hostname; both are derived,
partly because `test_repo_conformance.py::test_no_tracked_file_outside_docs_
names_the_old_project` forbids one of them.
"""

from __future__ import annotations

import pytest

# `aurora-cli` is on sys.path via pytest.ini's `pythonpath`, the same
# mechanism `aurora-cli/tests/test_identity.py` already relies on.
from aurora_cli import envfile, identity
from test_repo_conformance import strict_dotenv_offenders

# Neither of production's names, and not a real key.
FIXTURE_BRANCH = "zz-fixture-branch"
FIXTURE_KEY = "tskey-auth-zzfixture-notarealkey"
FIXTURE_DEVS = ("testuser",)


def _rendered(**kwargs) -> str:
    params = dict(devs=FIXTURE_DEVS, authkey=FIXTURE_KEY)
    params.update(kwargs)
    return envfile.render_branch_env(FIXTURE_BRANCH, **params)


@pytest.fixture(scope="module")
def rendered() -> str:
    return _rendered()


@pytest.fixture(scope="module")
def production() -> envfile.EnvFile:
    return envfile.parse_env(envfile.production_env_text())


# ---------------------------------------------------------------------------
# the render
# ---------------------------------------------------------------------------


def test_rendered_branch_env_sets_every_required_variable(rendered):
    defects = envfile.missing_overrides(rendered, FIXTURE_BRANCH)
    assert defects == [], (
        "the rendered branch .env would leave this branch wired to "
        f"production:\n  " + "\n  ".join(defects)
    )


def test_every_fatal_variable_is_actually_different_from_production(
    rendered, production
):
    """A "derivation" that silently returns the inherited value is the defect
    that looks completely fine in a diff.

    Only variables production actually declares can be compared, so the
    non-vacuity assertion below is load-bearing: if the overlap ever fell to
    nothing this test would pass while checking nothing at all.
    """
    branch = envfile.parse_env(rendered)
    fatal = [req.name for req in envfile.load_manifest() if req.fatal]
    comparable = [name for name in fatal if name in production]

    assert len(comparable) >= 6, (
        f"only {comparable} of the fatal variables exist in production's "
        ".env, so this comparison has almost nothing to check"
    )
    identical = [
        name for name in comparable if branch[name] == production[name]
    ]
    assert identical == [], (
        f"fatal variables inherited unchanged from production: {identical}"
    )


def test_no_inherited_value_contains_productions_domain(rendered, production):
    """The scan that finds the next N1 by itself.

    Any value in the rendered file that embeds production's hostname is a
    branch reaching production over HTTP, and spec 5.3's container-label
    guard cannot see it -- there is no container in the path to guard. The
    allow-set is empty today, deliberately; it exists so a future exemption
    is a reviewed line with a reason rather than a weakened scan.
    """
    domain = identity.production_domain()
    source_hits = envfile.hostname_bearing_variables(production, domain)
    assert len(source_hits) >= 4, (
        "production's .env no longer embeds its own hostname in several "
        f"variables ({source_hits}); this scan would then pass vacuously -- "
        "check the premise before deleting the test"
    )

    hits = [
        key for key in envfile.hostname_bearing_variables(
            envfile.parse_env(rendered), domain
        )
        if key not in envfile.ALLOWED_PRODUCTION_REFERENCES
    ]
    assert hits == [], (
        f"rendered branch .env still names production ({domain}) in: {hits}. "
        "dev-admin would create OAuth applications in production's Forgejo "
        "and the agents would register OIDC against production's issuer."
    )


def test_the_allowlist_mechanism_forgives_only_what_it_names(production):
    """Pins the allow-set in both directions while it is empty.

    An empty frozenset makes the scan strongest, but it also means the
    `if key not in ALLOWED...` branch is never taken -- so a mutation that
    made it forgive everything would be invisible. This exercises both
    branches with a synthetic env.
    """
    domain = identity.production_domain()
    synthetic = {"SOMETHING": f"https://{domain}/x", "TZ": "America/Chicago"}

    assert envfile.hostname_bearing_variables(synthetic, domain) == ["SOMETHING"]
    forgiven = [
        key for key in envfile.hostname_bearing_variables(synthetic, domain)
        if key not in frozenset({"SOMETHING"})
    ]
    assert forgiven == []


def test_manifest_covers_every_hostname_bearing_variable_in_production_env(
    production,
):
    """The inverse direction: a manifest that has fallen behind reality.

    Any variable in production's `.env` whose value embeds production's
    domain and is not listed in `branch-env.yaml` fails here. This is what
    turns "somebody adds a hostname-bearing variable to `.env.template`" from
    a silent branch-wired-to-production into a red unit test.
    """
    domain = identity.production_domain()
    bearing = envfile.hostname_bearing_variables(production, domain)
    assert len(bearing) >= 4, (
        f"expected production's .env to embed its own hostname in several "
        f"variables, found {bearing}; the check below would be vacuous"
    )

    unlisted = envfile.unlisted_hostname_variables(production, domain=domain)
    assert unlisted == [], (
        f"production's .env embeds its hostname in {unlisted}, which "
        f"branch-env.yaml does not list. A branch would inherit "
        "them unchanged and reach production. Add them to branch-env.yaml "
        "with a `why:` and a `fatal:`."
    )


def test_the_manifest_lists_the_three_variables_finding_n1_found():
    """N1, pinned by name.

    These three are not derived from `DOMAIN_NAME`; they embed production's
    hostname as a literal. `FORGEJO_URL` is the dangerous one -- it is what
    `dev-admin reconcile` calls to create and delete OAuth applications.
    Named explicitly so deleting them from the manifest is a decision
    somebody has to make in the face of this test, not an omission.
    """
    listed = {req.name: req for req in envfile.load_manifest()}
    for name in ("FORGEJO_URL", "AFFINE_SERVER_EXTERNAL_URL",
                 "AURORA_PROFILE_URL"):
        assert name in listed, f"branch-env.yaml no longer lists {name} (N1)"
        assert listed[name].fatal, f"{name} must be fatal"


def test_declared_suffixes_still_match_productions_urls(production):
    """The manifest's `suffix:` against production's actual value.

    `branch_url` builds `https://<branch domain><suffix>`. If production's
    URL path changes and the manifest's suffix does not, the branch renders a
    URL that resolves to nothing -- a stale manifest that still passes every
    presence check. Compared by swapping the hostname rather than by typing
    either URL.
    """
    domain = identity.production_domain()
    checked = 0
    for req in envfile.load_manifest():
        if req.derive != "branch_url" or req.name not in production:
            continue
        checked += 1
        assert production[req.name] == f"https://{domain}{req.suffix}", (
            f"branch-env.yaml declares suffix {req.suffix!r} for {req.name}, "
            f"but production's value is {production[req.name]!r}; the branch "
            "would render a URL that points at nothing"
        )
    assert checked >= 3, f"only {checked} branch_url entries were comparable"


def test_rendered_branch_env_is_strict_key_equals_value(rendered):
    """The renderer must not regress trap 7.

    Uses the repo's own predicate, imported rather than restated: a branch
    `.env` that `docker run --env-file` refuses is a branch that cannot start
    its agents, and the failure message names neither the file nor the line.
    """
    offenders = strict_dotenv_offenders(rendered, "branch .env")
    assert offenders == [], (
        f"rendered branch .env is not strict KEY=value: {offenders}"
    )
    assert strict_dotenv_offenders("A = 1\n", "probe"), (
        "the imported predicate accepts `A = 1`, so the assertion above "
        "proves nothing -- check test_repo_conformance.strict_dotenv_offenders"
    )


def test_the_branch_env_inherits_everything_it_does_not_override(
    rendered, production
):
    """A branch is a test of production, not of a fiction.

    The renderer starts from production's file, so unrelated variables --
    secrets, ports, the timezone -- must survive verbatim, and production's
    commented bulk must survive too. A renderer that emitted only the
    overrides would pass every test above and produce a stack that does not
    boot.
    """
    branch = envfile.parse_env(rendered)
    overridden = {req.name for req in envfile.load_manifest()}
    inherited = [k for k in production if k not in overridden]

    assert len(inherited) >= 10, f"too few inherited variables: {inherited}"
    differing = [k for k in inherited if branch[k] != production[k]]
    assert differing == [], f"non-override variables were changed: {differing}"

    # Calibrated against production's actual file rather than a constant. The
    # original `> 100` encoded how much commented bulk production happened to
    # carry on the day it was written; the `.env` cleanup on 2026-07-30
    # reddened this for a reason that had nothing to do with the renderer.
    # What the renderer owes is that every comment production has survives.
    rendered_comments = [
        line.raw for line in envfile.parse_env(rendered).lines
        if line.kind == "comment"
    ]
    production_comments = [
        line.raw for line in production.lines if line.kind == "comment"
    ]
    assert production_comments, (
        "premise wrong: production's .env has no comments, so this cannot "
        "show that the renderer preserves them"
    )
    dropped = [c for c in production_comments if c not in rendered_comments]
    assert dropped == [], f"the renderer dropped production's comments: {dropped}"


def test_the_branch_project_is_namespaced_and_profiles_follow_the_devs():
    branch = envfile.parse_env(_rendered(devs=("testuser", "newuser")))

    assert branch["COMPOSE_PROJECT_NAME"] == \
        identity.branch_project(FIXTURE_BRANCH)
    assert branch["COMPOSE_PROJECT_NAME"].startswith(
        identity.BRANCH_PROJECT_PREFIX
    )
    assert branch["COMPOSE_PROFILES"] == "agent-testuser,agent-newuser"

    none = envfile.parse_env(_rendered(devs=()))
    assert none["COMPOSE_PROFILES"] == ""


def test_the_upstreams_leave_loopback_behind(rendered):
    """Trap 8: a branch's Caddy is `network_mode: service:tailscale` and
    `127.0.0.1` reaches nothing there. The Caddyfile defaults are
    production's addresses, so forgetting these is not an error -- it is a
    stack that starts, serves 502s and looks fine."""
    branch = envfile.parse_env(rendered)
    assert branch["AGENT_UPSTREAM_MODE"] == "service"
    for key in ("AFFINE_UPSTREAM", "FORGEJO_UPSTREAM", "FJELL_UPSTREAM"):
        assert "127.0.0.1" not in branch[key] and "localhost" not in branch[key]


# ---------------------------------------------------------------------------
# the checker itself, pinned in both directions
# ---------------------------------------------------------------------------


def test_missing_overrides_condemns_productions_own_env(production):
    """The strongest available negative control.

    Production's `.env` IS the un-overridden file. Feeding it to the checker
    must produce defects naming the variables that matter -- if it comes back
    clean, the checker is inert and every green assertion above is worthless.
    """
    defects = envfile.missing_overrides(
        envfile.production_env_text(), FIXTURE_BRANCH
    )
    named = envfile.defect_variables(defects)

    for key in ("COMPOSE_PROJECT_NAME", "COMPOSE_PROFILES", "FORGEJO_URL",
                "AFFINE_SERVER_EXTERNAL_URL", "AURORA_PROFILE_URL",
                "DOMAIN_NAME"):
        assert key in named, f"{key} was not condemned: {defects}"


def test_the_hazard_rules_survive_a_gutted_manifest():
    """The property that makes `branch-env.yaml` worth having.

    If the renderer and the checker were both driven by the manifest, then
    deleting an entry would blind both at once: the rendered file inherits
    production's value and the checker no longer asks about it, so
    `missing_overrides(...) == []` stays green while the branch is wired to
    production. Mutations M1 and M2 are exactly that experiment.

    `inherited_hazards()` is manifest-free, so an inherited `FORGEJO_URL`
    is caught by the domain scan and an inherited `COMPOSE_PROFILES=agents`
    by spec D7, whatever the manifest says.
    """
    inherited = dict(envfile.parse_env(envfile.production_env_text()))
    hazards = envfile.inherited_hazards(inherited, FIXTURE_BRANCH)
    named = envfile.defect_variables(hazards)

    assert "FORGEJO_URL" in named
    assert "COMPOSE_PROFILES" in named
    assert "COMPOSE_PROJECT_NAME" in named

    clean = envfile.parse_env(_rendered())
    assert envfile.inherited_hazards(clean, FIXTURE_BRANCH) == []


def test_the_hazard_rules_catch_each_condition_on_its_own():
    """One rule at a time, so deleting any single one is visible.

    A blanket "the whole production env is condemned" assertion passes even
    if only one rule survives -- the near-miss recorded in Task 1's ledger,
    where deleting a guard left the next guard raising the same exception on
    the same input.
    """
    domain = identity.production_domain()
    good = dict(envfile.parse_env(_rendered()))

    def named(**overrides) -> list[str]:
        env = dict(good)
        env.update(overrides)
        return envfile.defect_variables(
            envfile.inherited_hazards(env, FIXTURE_BRANCH)
        )

    assert named() == []
    assert named(SOMETHING_NEW=f"https://{domain}/x") == ["SOMETHING_NEW"]
    assert named(COMPOSE_PROJECT_NAME="aurora") == ["COMPOSE_PROJECT_NAME"]
    assert named(COMPOSE_PROFILES="agents") == ["COMPOSE_PROFILES"]
    assert named(COMPOSE_PROFILES="agent-x,agents") == ["COMPOSE_PROFILES"]
    assert named(FORGEJO_UPSTREAM="127.0.0.1:3000") == ["FORGEJO_UPSTREAM"]
    assert named(AFFINE_UPSTREAM="localhost:3010") == ["AFFINE_UPSTREAM"]

    missing = dict(good)
    del missing["COMPOSE_PROJECT_NAME"]
    assert envfile.defect_variables(
        envfile.inherited_hazards(missing, FIXTURE_BRANCH)
    ) == ["COMPOSE_PROJECT_NAME"]


def test_manifest_gaps_notice_an_absent_and_an_inherited_variable(production):
    """The manifest-driven half, on its own, in both directions."""
    good = dict(envfile.parse_env(_rendered()))
    assert envfile.manifest_gaps(good, source=production) == []

    absent = dict(good)
    del absent["FORGEJO_URL"]
    assert envfile.defect_variables(
        envfile.manifest_gaps(absent, source=production)
    ) == ["FORGEJO_URL"]

    inherited = dict(good)
    inherited["FORGEJO_URL"] = production["FORGEJO_URL"]
    gaps = envfile.manifest_gaps(inherited, source=production)
    assert envfile.defect_variables(gaps) == ["FORGEJO_URL"]
    assert "inherited" in gaps[0]
