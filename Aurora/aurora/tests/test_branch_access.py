"""`compose ps` and `ls` against a REAL branch stack on the real daemon.

`aurora-cli/tests/test_access_doc.py` proves the renderer does the right thing
with the rows it is handed. Nothing there proves those rows resemble what
Compose emits -- a parser that agreed with a double and disagreed with Compose
would pass every test in that file. This is the other half of that pair, and
it is deliberately small: bring up a throwaway `br-` project, ask the real
`docker compose ps`, and cross-check the answer against the daemon by a
DIFFERENT route (`docker ps --filter label=...`).

Nothing here writes anything, anywhere. `INDEX.md`'s real destination is
inside production's checkout, so the index is RENDERED and inspected but never
written; the write path is guarded and tested in `test_access_doc.py` against
a fabricated production root. Every test captures its own production snapshot
and asserts production is unchanged afterwards.
"""

import subprocess

import pytest

from aurora_cli import access_doc, branch, guards
from branch_harness import assert_production_unchanged, production_snapshot

# Fixtures live in branch_harness.py, not conftest.py, so they are imported
# rather than discovered -- the same pattern as tests/test_branch_isolation.py.
from branch_harness import throwaway_branch, throwaway_branches  # noqa: F401

COMPOSE = """\
services:
  alpha:
    image: alpine
    command: sleep 120
  beta:
    image: alpine
    command: sleep 120
    profiles: ["extra"]
"""


def _up(project: str, tmp_path, scale_beta: int = 1) -> None:
    """Bring up the probe, optionally with a SECOND replica of `beta`.

    The second replica is not decoration. Compose names it `<project>-beta-2`,
    which is a name no concatenation of project, service and `-1` produces --
    so it is the only shape that can catch a parser or a renderer that builds
    names instead of reading them. A mutation doing exactly that SURVIVED
    against a one-replica probe.
    """
    (tmp_path / "compose.yml").write_text(COMPOSE)
    subprocess.run(
        ["docker", "compose", "-p", project, "--profile", "*", "up", "-d",
         "--scale", f"beta={scale_beta}"],
        cwd=tmp_path, check=True, capture_output=True, stdin=subprocess.DEVNULL,
    )


def _names_from_the_daemon(project: str) -> set[str]:
    """The same question, asked a different way, so `ps` cannot mark its own
    homework."""
    out = subprocess.run(
        ["docker", "ps", "-a", "--filter",
         f"label=com.docker.compose.project={project}", "--format", "{{.Names}}"],
        capture_output=True, text=True, check=True,
    ).stdout
    return {line.strip() for line in out.splitlines() if line.strip()}


def test_compose_ps_reports_the_names_the_daemon_reports(throwaway_branch, tmp_path):
    project = throwaway_branch
    before = production_snapshot()
    _up(project, tmp_path, scale_beta=2)

    rows = branch.compose_ps(project, runner=branch.CommandRunner())
    assert rows, "the probe stack started but compose ps returned nothing"
    assert {r.name for r in rows} == _names_from_the_daemon(project)
    assert {r.service for r in rows} == {"alpha", "beta"}, (
        f"a profiled service is missing from ps: {[r.service for r in rows]}"
    )
    assert all(r.state == "running" for r in rows), [r.state for r in rows]

    # The name Compose invented, which nothing here could have.
    assert f"{project}-beta-2" in {r.name for r in rows}, (
        f"the second replica is missing: {[r.name for r in rows]}"
    )
    assert len({r.name for r in rows}) == 3
    assert_production_unchanged(before)


def test_a_document_built_from_a_real_stack_prints_the_name_compose_chose(
    throwaway_branch, tmp_path
):
    """The generator half of the artifact-vs-generator pair, end to end.

    Real daemon, real `compose ps`, real renderer -- and the name under test
    is one Compose chose for a second replica, so a renderer that built names
    from the project and the service could not have produced it.
    """
    project = throwaway_branch
    name = project[len(guards.BRANCH_PROJECT_PREFIX):]
    before = production_snapshot()
    _up(project, tmp_path, scale_beta=2)

    document = branch.branch_access(name, runner=branch.CommandRunner())
    surprising = f"{project}-beta-2"
    assert f"`{surprising}`" in document, document
    assert f"docker exec -it {surprising} bash" in document
    assert_production_unchanged(before)


def test_compose_ps_needs_no_worktree_and_no_compose_file(throwaway_branch, tmp_path):
    """The probe project has no worktree anywhere near production.

    This is the case the whole "derive it from the daemon" rule exists for: a
    branch whose worktree was deleted by hand is still running, still costs
    memory, and is invisible to anything that walks the filesystem.
    """
    project = throwaway_branch
    before = production_snapshot()
    _up(project, tmp_path)
    (tmp_path / "compose.yml").unlink()

    rows = branch.compose_ps(project, runner=branch.CommandRunner())
    assert {r.service for r in rows} == {"alpha", "beta"}
    assert_production_unchanged(before)


def test_ls_and_the_index_find_a_live_branch_and_mark_its_missing_worktree(
    throwaway_branch, tmp_path
):
    project = throwaway_branch
    name = project[len(guards.BRANCH_PROJECT_PREFIX):]
    before = production_snapshot()
    _up(project, tmp_path)

    summaries = branch.branch_ls(branch.CommandRunner())
    assert summaries, "branch ls found nothing while a branch stack was up"
    mine = [s for s in summaries if s.project == project]
    assert len(mine) == 1, f"{project} missing from {[s.project for s in summaries]}"
    summary = mine[0]
    assert summary.name == name
    assert summary.running == 2
    assert not summary.worktree_exists

    # Rendered, never written: the real index lives inside production's
    # checkout and this suite does not write there.
    text = access_doc.render_index(summaries)
    assert project in text and "MISSING" in text
    assert_production_unchanged(before)


def test_ls_never_reports_production_as_a_branch():
    """Production is running right now, so this is not a hypothetical.

    A summary carrying production's project would mean `--all` teardown could
    be handed it too -- the two share `live_branch_projects`.
    """
    from aurora_cli import identity

    summaries = branch.branch_ls(branch.CommandRunner())
    production = identity.production_project()
    assert all(s.project != production for s in summaries)
    assert all(s.project.startswith(guards.BRANCH_PROJECT_PREFIX)
               for s in summaries), [s.project for s in summaries]


def test_the_index_is_not_written_by_reading_the_daemon():
    """`ls` and a rendered index are READS. Neither may create the index file.

    Regeneration is `up`'s and `down`'s job, through the CLI, precisely
    because its destination is inside production's tree.
    """
    path = branch.index_path()
    existed = path.exists()
    access_doc.render_index(branch.branch_ls(branch.CommandRunner()))
    assert path.exists() is existed, (
        f"{path} appeared (or vanished) merely from listing branches"
    )
