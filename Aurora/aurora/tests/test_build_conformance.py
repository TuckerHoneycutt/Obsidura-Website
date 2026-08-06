"""Built images versus the commits that were supposed to produce them.

WHY THIS EXISTS
Merging a pull request updates the checkout and rebuilds nothing. On
2026-08-01 the internal hub was merged at 23:00 and production went on serving
a fjell binary built two days earlier: `/git/.hub/` returned a 20-byte
placeholder and `hub.css` 404'd for thirteen hours. Every route answered 200.
Every healthcheck stayed green. `docker compose restart` would not have helped
-- it reuses the image it already has.

Nothing detected it because nothing was comparing an IMAGE against a COMMIT.
The runtime gates next door assert that a container runs the image the repo
declares, and that assertion was true the whole time: `aurora-fjell` was
exactly the image compose.yml named. It was simply built from older source.
That is the blind spot, and this file is the only thing pointed at it.

THIS FILE IS EXPECTED TO BE RED when production is behind the checkout. That
is not a broken test, it is the test working -- so its failure message carries
the exact command that fixes it, per this repository's practice for a gate
that is deliberately red.
"""

import os
import subprocess
from datetime import datetime

from conftest import PRODUCTION_PROJECT, REPO_ROOT, buildable_services

REBUILD = "ops/rebuild.sh"


def _parse(stamp: str) -> datetime:
    """An RFC 3339 timestamp from docker or from git, as an aware datetime.

    Both sides are timezone-aware and are compared as instants, never as
    strings: git reports `%cI` in the committer's offset and docker reports
    `.Created` in the daemon's, so `2026-07-26T04:15:49Z` and
    `2026-07-30T23:24:43-05:00` sort the wrong way round lexically. Docker's
    nanoseconds are truncated to microseconds here, which is irrelevant at the
    resolution this compares (a merge and a build are minutes apart at best,
    and were two days apart in the incident).
    """
    return datetime.fromisoformat(stamp)


def _image_created(image: str) -> str | None:
    """When this image was built, or None if it does not exist.

    An absent image is STALE, not an error. It is the normal state of a fresh
    checkout, and "never built" is the most stale an image can be -- raising
    here would turn the loudest case into a crash instead of a finding.
    """
    result = subprocess.run(
        ["docker", "image", "inspect", image, "--format", "{{.Created}}"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _context_commit(context: str) -> str:
    """The last commit touching this build context, as RFC 3339."""
    result = subprocess.run(
        ["git", "log", "-1", "--format=%cI", "--", str(context)],
        cwd=REPO_ROOT, capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


def test_at_least_one_service_builds_from_source(config):
    """Non-vacuity, asserted FIRST and on its own.

    Every other test in this file loops over the buildable services. A loop
    over an empty set succeeds silently, so a gate against a config that had
    stopped declaring `build:` anywhere -- a bad merge, a renamed key, a
    `docker compose config` that quietly failed -- would pass while asserting
    nothing at all. That is the shape that let the incident this file exists
    for run for thirteen hours, so it is checked before anything else and not
    folded into the checks it protects.
    """
    services = buildable_services(config)
    assert services, (
        "no service in the resolved compose config declares `build:`, so "
        "every staleness assertion in this file is vacuous. Three services "
        "build from source (fjell, agent-authz, dev-admin); if that is still "
        "true, `docker compose config` is what is broken."
    )


def test_every_build_context_has_a_commit(config):
    """A context git knows nothing about cannot be judged, and would be
    silently skipped by the gate below rather than failing it."""
    services = buildable_services(config)
    assert services, "vacuous: no buildable services"
    unknown = [
        name for name, (_image, context) in services.items()
        if not _context_commit(context)
    ]
    assert unknown == [], (
        f"no commit touches the build context of {unknown}, so their images "
        "cannot be compared against anything. See "
        "test_repo_conformance.py::test_every_build_context_is_tracked_in_git."
    )


def test_no_image_is_older_than_its_build_context(config):
    """The gate. An image built before the last commit to its source is stale.

    Both timestamps are reported, because "it is stale" and "it is stale by
    thirteen hours" are different operational facts and only the second one
    tells an operator whether they are looking at the merge they just made or
    at something that has been wrong for days.
    """
    services = buildable_services(config)
    assert services, "vacuous: no buildable services to check"

    stale = []
    for name, (image, context) in sorted(services.items()):
        commit = _context_commit(context)
        if not commit:
            continue  # test_every_build_context_has_a_commit owns this case
        created = _image_created(image)
        if created is None:
            stale.append((name, image, "(never built)", commit))
        elif _parse(created) < _parse(commit):
            stale.append((name, image, created, commit))

    rows = "\n".join(
        f"    {name:<13} {image:<20} image={created}  commit={commit}"
        for name, image, created, commit in stale
    )
    fix = " ".join(name for name, _i, _c, _m in stale)
    assert stale == [], (
        "Images older than the last commit touching their build context. "
        "Production is serving source that was merged but never built, and it "
        "will answer 200 on every route while doing so:\n"
        f"{rows}\n\n"
        "Merging does not rebuild, and `docker compose restart` reuses the "
        "image it already has. Fix:\n\n"
        f"    {REBUILD} {fix}\n"
    )


def _script_verdicts(config) -> dict[str, str]:
    """`ops/rebuild.sh --check`, parsed into service -> STALE/FRESH/NEVER-BUILT.

    `COMPOSE_PROJECT_NAME` is forced to PRODUCTION_PROJECT for the same reason
    conftest pins it: run from a worktree, Compose takes the project from the
    directory basename, the script would synthesise `<basename>-fjell`, and
    every build-only service would read NEVER-BUILT no matter what production
    is actually running. Both sides must be asked about the same images or the
    comparison below is theatre.

    `--check` builds nothing, starts nothing and recreates nothing, so this
    cannot deploy by accident whatever the config says.
    """
    result = subprocess.run(
        ["bash", REBUILD, "--check"],
        cwd=REPO_ROOT, capture_output=True, text=True,
        env={**os.environ, "COMPOSE_PROJECT_NAME": PRODUCTION_PROJECT},
    )
    # Exit 1 means STALE, which is the answer and not a failure to run. A
    # higher code, or a shell error, means the script could not be asked.
    assert result.returncode in (0, 1), (
        f"{REBUILD} --check exited {result.returncode}; it could not answer.\n"
        f"{result.stdout}\n{result.stderr}"
    )
    verdicts = {}
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) >= 2 and fields[0] in {"STALE", "FRESH", "NEVER-BUILT"}:
            verdicts[fields[1]] = fields[0]
    return verdicts


def test_the_rebuild_script_sees_the_same_services_and_reaches_the_same_verdict(
    config,
):
    """The script's SET and VERDICT, against this file's. NOT independent.

    This docstring used to claim "two independent derivations ... Neither side
    reads the other". They do not read each other, and they are not
    independent: both compute
    `docker image inspect .Created  <  git log -1 --format=%cI -- <context>`
    over the same two sources, key for key --

      | ops/rebuild.sh                     | here / conftest        |
      |------------------------------------|------------------------|
      | `image inspect --format .Created`  | `_image_created`       |
      | `git log -1 --format=%cI -- ctx`    | `_context_commit`      |
      | `date -d created -lt date -d commit`| `_parse(a) < _parse(b)`|
      | `svc.image or project + "-" + name` | `conftest.declared_image`|

    -- so a systematically wrong RULE is identical on both sides and invisible
    here. TWO SUCH HOLES ARE KNOWN, and both are recorded rather than
    discovered:

      * an UNCOMMITTED edit in a build context reads FRESH on both sides,
        because both compare against the last COMMIT. `ops/rebuild.sh` now
        prints a WARNING naming the dirty paths; there is no honest verdict
        for that case, since the image may or may not match.
      * a fully CACHE-HIT rebuild reads STALE forever, because `.Created` does
        not move when every layer is reused. That used to make
        `ops/rebuild.sh` `die` on a build that was correct and complete; it
        now compares the image ID across the build -- a genuinely different
        measurement -- and reports CACHE-HIT instead of dying.

    What this test IS worth is stated honestly:

      * the SET half is genuinely independent and is the valuable one: bash
        derives it from `docker compose config` with none of this fixture
        available, so "the list is derived, never hardcoded" is a tested claim.
        Add a fourth buildable service and this goes red until the script sees
        it too.
      * the VERDICT half catches a TYPO or a rot in the bash -- a comparison
        that started always answering FRESH, a format string that stopped
        parsing. It cannot catch a rule that is wrong in both spellings.
    """
    expected = buildable_services(config)
    assert expected, "vacuous: no buildable services to compare against"

    verdicts = _script_verdicts(config)
    assert set(verdicts) == set(expected), (
        f"{REBUILD} reports on {sorted(verdicts)} but the compose config "
        f"declares `build:` for {sorted(expected)}. A service the script does "
        "not know about is a service no deploy ever rebuilds."
    )

    disagreements = []
    for name, (image, context) in sorted(expected.items()):
        commit = _context_commit(context)
        created = _image_created(image)
        if created is None:
            mine = "NEVER-BUILT"
        elif _parse(created) < _parse(commit):
            mine = "STALE"
        else:
            mine = "FRESH"
        if verdicts[name] != mine:
            disagreements.append(f"{name}: script says {verdicts[name]}, this file says {mine}")

    assert disagreements == [], (
        "the script and this file disagree about which images are stale, so "
        "one of them is wrong and an operator cannot tell which:\n  "
        + "\n  ".join(disagreements)
    )
