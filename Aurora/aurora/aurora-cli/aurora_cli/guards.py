"""Positive guards in front of every destructive branch operation.

This module exists because of a real incident. On 2026-07-29 an agent working
on this chunk ran

    docker compose --profile '*' -p <production> down -v --remove-orphans

-- with production's actual project name in that slot, which this file does
not type for the reason `identity`'s docstring gives: the rename is blocked,
not cancelled, and a comment carrying a live identity is a copy-paste source.
It ran against live production while executing a mutation table, destroying
12 containers, 9 named volumes and the project network. Recovery needed a human.
Chunk 2 produced a second incident from a *unit test*, where a `@patch` that
did not bind let a real `docker exec` reach production's Caddy.

So the rule here is: a destructive call must PROVE its target is a branch.
Not "is not production" — proving a negative passes on `""`, on `None`, on
`"BR-x"`, on `" br-x"`, and on every typo nobody thought of. `docker compose
-p "" down -v` is not a no-op: Compose resolves the project from the current
directory's basename.
"""

from __future__ import annotations

from pathlib import Path

from aurora_cli import identity

#: An alias, not a second literal: `identity` states it is defined once,
#: there, and this module's callers reach it through this name. `branch.py`
#: slices project names with `project[len(guards.BRANCH_PROJECT_PREFIX):]`
#: while `identity.branch_paths` builds them with
#: `identity.BRANCH_PROJECT_PREFIX`; two literals that have to agree by hand
#: is a wrong branch name for `branch_down_all` to tear down.
BRANCH_PROJECT_PREFIX = identity.BRANCH_PROJECT_PREFIX
_WORKTREE_DIRNAME = ".worktrees"
_INDEX_NAME = "INDEX.md"


class GuardViolation(RuntimeError):
    """A destructive operation could not prove its target was a branch."""


def assert_branch_project(project: object) -> str:
    """Refuse any project that is not provably a branch. Returns it on success.

    TWO clauses, and the second is deliberately best-effort. That asymmetry is
    the whole design and it resolves a genuine conflict between two documents:

      * The Task 9 brief asks for `project != production_project()` as well as
        the prefix test, so that a production project which happened to start
        with `br-` would still be refused.
      * The Tasks 1-4 review established that `production_project()` RAISES
        when production is down — and teardown is most needed exactly when
        production is down or half-up. A guard that raises then does not fail
        safe; it fails *closed against the operator* and leaves branch
        containers running with no supported way to remove them.

    Resolution: the prefix test is mandatory and always available. The
    identity comparison runs only when production's identity can be resolved,
    and an unresolvable production degrades to prefix-only rather than to an
    exception. Both clauses are therefore exercised in the normal case, and
    the guard still works with the daemon on fire.
    """
    if not isinstance(project, str):
        raise GuardViolation(
            f"Refusing a destructive operation: project must be a string, got "
            f"{type(project).__name__}. A non-string reaches the shell as "
            "something unpredictable."
        )
    # Exact prefix, no normalisation. `" br-x"`, `"BR-x"` and `"br-"` are all
    # refused on purpose: anything that needs stripping or case-folding to
    # look like a branch is a bug somewhere upstream, and silently repairing
    # it here would hide that bug behind a destructive command.
    if not project.startswith(BRANCH_PROJECT_PREFIX) or project == BRANCH_PROJECT_PREFIX:
        raise GuardViolation(
            f"Refusing a destructive operation on project {project!r}: it is "
            f"not in the {BRANCH_PROJECT_PREFIX!r} namespace. Only branch "
            "stacks may be torn down by this tool."
        )

    try:
        live = identity.production_project()
    except Exception:
        # Production unresolvable — daemon down, or mid-deploy. Prefix-only.
        # Deliberately broad: any failure to *learn* production's name must
        # not become a failure to tear down a branch.
        return project

    if project == live:
        raise GuardViolation(
            f"Refusing a destructive operation on project {project!r}: it is "
            "PRODUCTION. The branch namespace prefix is not sufficient "
            "evidence when production itself carries it."
        )
    return project


def assert_not_production_path(
    path: object, *, worktrees_root: object | None = None,
) -> Path:
    """Refuse any path that is not a branch worktree. Returns it resolved.

    Compared with `Path.resolve()` and `Path.parents`, never `str.startswith`:
    `<root>/.worktrees-evil/x` string-prefixes `<root>/.worktrees` and is not
    under it. `/home` is a symlink to `/var/home` on this host, so both sides
    must be resolved or a correct path compares unequal to itself.

    `worktrees_root` is the SAME seam `branch.branch_up(worktrees_root=...)`
    already has, and it exists for the same measured reason: on this host
    `<production>/.worktrees` is root-owned, so a test cannot create a worktree
    there and could not drive `runtime.relabel_worktree` or
    `runtime.reclaim_worktree_ownership` AT ALL -- which is how both came to be
    "tested" by reimplementation, with the product functions never invoked.
    `runtime.record_runtime` was exempted from this guard outright for the same
    reason and says so; this is the same exemption made narrower, because these
    two mutate SELinux labels and ownership across a whole tree rather than
    writing one inert file.

    IT CANNOT WIDEN THE GUARD. Whatever is passed, production's checkout and
    everything inside it stays refused except under production's own
    `.worktrees` -- so the override can only move the permitted directory OUT
    of production, never into it. Pinned by
    `tests/test_guards.py::test_a_worktrees_root_override_cannot_reach_into_production`.
    """
    if not isinstance(path, (str, Path)):
        raise GuardViolation(
            f"Refusing a destructive operation: path must be a path, got "
            f"{type(path).__name__}."
        )
    candidate = Path(path).resolve()
    root = identity.production_root().resolve()
    production_worktrees = (root / _WORKTREE_DIRNAME).resolve()
    worktrees = (
        production_worktrees if worktrees_root is None
        else Path(worktrees_root).resolve()
    )

    # The non-widening clause, checked before anything the override decides.
    if (candidate == root or root in candidate.parents) \
            and production_worktrees not in candidate.parents:
        raise GuardViolation(
            f"Refusing a destructive operation on {candidate}: it is inside "
            f"PRODUCTION's checkout {root} and not under "
            f"{production_worktrees}. No `worktrees_root` override reaches "
            "in there."
        )

    if candidate == root:
        raise GuardViolation(
            f"Refusing to remove {candidate}: that is PRODUCTION's checkout."
        )
    if candidate == worktrees or candidate == production_worktrees:
        raise GuardViolation(
            f"Refusing to remove {candidate}: that is the worktrees directory "
            "itself, not a branch inside it."
        )
    if worktrees not in candidate.parents:
        raise GuardViolation(
            f"Refusing to remove {candidate}: it is not inside {worktrees}. "
            "Branch worktrees live there and nowhere else."
        )
    return candidate


def assert_worktrees_index_path(path: object) -> Path:
    """Refuse any index destination but `<production>/.worktrees/INDEX.md`.

    `.worktrees/INDEX.md` is the one file this tool writes INSIDE production's
    checkout, and it is deliberate: decision D-F puts branch worktrees there
    because the directory is already inside the tree production's Hermes
    bind-mounts, which is what makes spec 7.4's "production's agent reads
    every branch's access document with no extra wiring" true for free.

    A write into production's tree with a computed path is exactly the shape
    that has already cost this project one directory mtime, so the guard is
    POSITIVE -- it proves the destination is that one file, rather than
    checking it is not some list of bad ones. `assert_not_production_path`
    cannot be reused here: it refuses `.worktrees` itself, and that is this
    file's parent.
    """
    if not isinstance(path, (str, Path)):
        raise GuardViolation(
            f"Refusing to write an index: path must be a path, got "
            f"{type(path).__name__}."
        )
    candidate = Path(path).resolve()
    expected = (
        identity.production_root().resolve()
        / _WORKTREE_DIRNAME / _INDEX_NAME
    )
    if candidate != expected:
        raise GuardViolation(
            f"Refusing to write {candidate}: the branch index is "
            f"{expected} and nothing else. This is the only file this tool "
            "writes inside production's checkout."
        )
    return candidate
