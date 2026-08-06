"""Spec 5.4: the defences against a branch's forge being mistaken for
production's, and against a commit being pushed into one.

Three independent layers, and this module owns the two that are built:

1. **Structural** -- a branch worktree inherits `origin`, which points at
   production's forge; a branch's forge is a different host entirely, so
   pushing to it takes a deliberate `git remote add`. Already true.
   `test_crosswire.py` asserts it rather than this module building it.
2. **Mechanical** -- `hooks/pre-push`. `install_pre_push()` puts it in a
   worktree, executable, and reports whether git will actually run it.
3. **Visual** -- `branch_app_name()` makes a branch's Forgejo render as
   ``<app name> [BRANCH: <name>]``. `compose.yml` reads it from
   ``FORGEJO_APP_NAME``, defaulting to production's current value, and
   `branch-env.yaml` derives the marked form for every branch.

Why installation cannot write ``.git/hooks/pre-push``
----------------------------------------------------
Measured on git 2.55 from this repository's own branch worktree:

    $ git rev-parse --path-format=absolute --git-path hooks
    <production checkout>/.git/hooks

Git worktrees SHARE the hooks directory with the main checkout -- `hooks` is on
git's list of paths that live in the *common* git dir. So the obvious
implementation ("write the hook into the branch worktree's .git/hooks") writes
into PRODUCTION's checkout. That is the exact class of mistake this project
keeps paying for: a plausible mechanism that quietly reaches production.

The three config-based alternatives were measured too, and all of them write to
production as well, because a linked worktree has no config file of its own:

* ``git config core.hooksPath X`` from a worktree lands in the COMMON config
  (verified: the line appeared in the fabricated main checkout's
  ``.git/config``), and an absolute value would point PRODUCTION's hooks at a
  branch worktree's directory.
* ``git config --worktree`` is refused outright unless
  ``extensions.worktreeConfig`` is enabled -- and enabling it is itself a write
  to the common config, one that also makes the repository unreadable to older
  git.

What *is* clean is a **relative** ``core.hooksPath``, which git resolves against
each worktree's own root. Measured: with ``core.hooksPath = hooks`` in the
shared config, ``--git-path hooks`` resolved to ``<main>/hooks`` from the main
checkout and ``<worktree>/hooks`` from the linked one, including when invoked
from a subdirectory. So ONE line in the shared config, written ONCE, arms every
present and future worktree -- and this module never writes it. It is a human
step (`arming_command()`), documented in `docs/post-implementation-steps.md`,
because it is a write to production's ``.git/config``.

It is production-neutral: the hook allows production's own forge, so an armed
production behaves exactly like an unarmed one. Until a human runs it the
mechanical layer is INERT -- `install_pre_push()` reports that in
`HookInstall.armed` rather than pretending otherwise, and a hook that is not
armed, or not executable, does nothing AT ALL and says nothing about it.

Dependencies: standard library only. `identity` for every derived value.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from aurora_cli import identity

#: The hook git runs before a push, and the only hook this repository ships.
HOOK_NAME = "pre-push"

#: The value `core.hooksPath` must carry, and the directory the hook lives in.
#: RELATIVE on purpose -- that is the entire reason this design does not write
#: to production. An absolute path here would arm one worktree and disarm every
#: other, production included.
HOOKS_DIRNAME = "hooks"

#: How a branch's forge announces itself in its own UI. Spec 5.4 layer 3.
BRANCH_MARKER_TEMPLATE = "[BRANCH: {name}]"

#: The compose variable `compose.yml` reads the Forgejo application name from.
APP_NAME_VAR = "FORGEJO_APP_NAME"

#: The compose environment entry that consumes it. Forgejo maps
#: ``FORGEJO__<section>__<KEY>`` onto app.ini at boot; an empty section is
#: app.ini's default section, so this is the top-level `APP_NAME`.
COMPOSE_APP_NAME_KEY = "FORGEJO____APP_NAME"

_COMPOSE_FILE = "compose.yml"

# `FORGEJO____APP_NAME=${FORGEJO_APP_NAME:-null-hub}` -> the default. Anchored
# on the variable name so a second `${...}` elsewhere in compose.yml cannot
# satisfy it.
_APP_NAME_DEFAULT_RE = re.compile(
    r"^\s*-?\s*"
    + re.escape(COMPOSE_APP_NAME_KEY)
    + r"=\$\{"
    + re.escape(APP_NAME_VAR)
    + r":-(?P<default>[^}]*)\}\s*$",
    re.MULTILINE,
)


class CrosswireError(RuntimeError):
    """A cross-wiring defence could not be established.

    Raised rather than warned. Every caller of this module is on the path that
    creates a branch, and a warning printed during branch creation is a line of
    output nobody reads -- which would leave a developer believing a defence
    exists when it does not.
    """


# ---------------------------------------------------------------------------
# the shipped hook
# ---------------------------------------------------------------------------


def hook_source_path(root: Path | None = None) -> Path:
    """Where the shipped hook lives in a checkout: ``<root>/hooks/pre-push``.

    The same path git resolves ``core.hooksPath = hooks`` to, which is what
    makes a fresh worktree armed the moment git checks the file out -- the
    tracked artifact and the installed one are the same file.
    """
    return (root if root is not None else identity.package_root()) \
        / HOOKS_DIRNAME / HOOK_NAME


def hook_text(root: Path | None = None) -> str:
    """The shipped hook's source.

    Read from disk, never templated. A hook rendered per branch would be a
    generated file that differs from the tracked one, so every branch worktree
    would report a dirty tree, and the committed artifact would stop being the
    thing under test.
    """
    path = hook_source_path(root)
    if not path.is_file():
        raise CrosswireError(
            f"No {HOOK_NAME} hook at {path}. It is a tracked file; a checkout "
            "without it cannot arm the mechanical layer of spec 5.4."
        )
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# arming: the one write this module refuses to make
# ---------------------------------------------------------------------------


def arming_command(root: Path | None = None) -> str:
    """The one-time human step that makes git run the hook.

    Deliberately returned as a string rather than executed. It writes to the
    shared ``.git/config``, which for every worktree of this repository IS
    production's checkout, and nothing in this package may write there. One
    place produces the command so the documentation, the tests and Task 10's
    access document cannot disagree about it.
    """
    target = root if root is not None else identity.production_root()
    return f"git -C {target} config core.hooksPath {HOOKS_DIRNAME}"


def resolved_hooks_dir(worktree: Path) -> Path:
    """The directory git will look in for hooks, asked of git itself.

    Not computed. The question "will git run this file" has exactly one
    authority, and a second implementation of git's resolution rules is how a
    test comes to pass against a hook git never runs.
    """
    proc = subprocess.run(
        ["git", "-C", str(worktree), "rev-parse",
         "--path-format=absolute", "--git-path", HOOKS_DIRNAME],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise CrosswireError(
            f"git could not resolve a hooks directory for {worktree}: "
            f"{proc.stderr.strip() or '(no stderr)'}"
        )
    return Path(proc.stdout.strip()).resolve()


def _is_armed(worktree: Path, hooks_dir: Path) -> bool:
    return hooks_dir == (Path(worktree).resolve() / HOOKS_DIRNAME)


def hook_is_armed(worktree: Path) -> bool:
    """True when git resolves hooks to this worktree's OWN hooks directory.

    False both when nothing is configured -- in which case git resolves into
    the shared, i.e. production's, ``.git/hooks`` -- and when someone
    configured an absolute path that points somewhere else entirely.
    """
    return _is_armed(worktree, resolved_hooks_dir(worktree))


# ---------------------------------------------------------------------------
# installation
# ---------------------------------------------------------------------------


def _git_common_dir(worktree: Path) -> Path | None:
    proc = subprocess.run(
        ["git", "-C", str(worktree), "rev-parse",
         "--path-format=absolute", "--git-common-dir"],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        return None
    out = proc.stdout.strip()
    return Path(out).resolve() if out else None


def assert_hook_destination(destination: Path, worktree: Path) -> None:
    """Refuse any destination that is not inside `worktree`'s working tree.

    Three refusals, and each exists because of a specific way this could reach
    production:

    * the worktree IS production's checkout -- installing there writes into the
      live tree (and, before this branch is merged, leaves an untracked file in
      it);
    * the destination is inside the SHARED git directory -- the default
      ``.git/hooks`` a worktree inherits, which is production's;
    * the destination escapes the worktree by any other route.

    Both sides of every comparison are resolved and parentage is checked with
    `Path.parents`, never a string prefix: ``/home`` is a symlink to
    ``/var/home`` on this host and that has already cost this project three
    debugging sessions.
    """
    worktree = worktree.resolve()
    destination = Path(destination).resolve()

    try:
        production = identity.production_root()
    except identity.IdentityError:
        production = None       # no git, no production; the checks below still
                                # bound the destination to the worktree.
    if production is not None and worktree == production:
        raise CrosswireError(
            f"Refusing to install the {HOOK_NAME} hook into {worktree}: that "
            "is PRODUCTION's checkout, not a branch worktree. The hook belongs "
            "to production by being a tracked file, not by being written there."
        )

    common = _git_common_dir(worktree)
    if common is not None and (
        destination == common or common in destination.parents
    ):
        raise CrosswireError(
            f"Refusing to write {destination}: it is inside the SHARED git "
            f"directory {common}, which every worktree of this repository has "
            "in common with production's checkout. Git worktrees share "
            "`.git/hooks`; that is why this hook is armed with a relative "
            "`core.hooksPath` instead."
        )

    if worktree not in destination.parents:
        raise CrosswireError(
            f"Refusing to write {destination}: it is not inside the worktree "
            f"{worktree} the hook was requested for."
        )


def _write_hook(destination: Path, text: str, *, worktree: Path) -> None:
    """The ONLY function in this module that touches the filesystem.

    Every write lives here -- `mkdir`, the bytes, and the mode -- because the
    lesson of Task 5 is that a tripwire over the function that MOVES BYTES
    misses the function that TOUCHES THE DESTINATION. `mkdir`, `chmod`,
    `copystat` and `open(..., "w")` are all writes; a seam that covers only one
    of them let a `copystat` move production's `forgejo/` mtime. Tests wrap
    this one function and are then covering all three.
    """
    assert_hook_destination(destination, worktree)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="utf-8")
    destination.chmod(0o755)


@dataclass(frozen=True)
class HookInstall:
    """What `install_pre_push` did, and whether it will have any effect."""

    path: Path
    worktree: Path
    hooks_dir: Path
    executable: bool
    armed: bool
    activation_command: str

    @property
    def effective(self) -> bool:
        """True only when git will actually run the hook.

        Both halves matter and both are silent when false: git skips a
        non-executable hook with nothing but a hint, and an unarmed repository
        never looks at this directory at all.
        """
        return self.armed and self.executable

    def advice(self) -> str:
        """One line a caller can print. Empty when the hook is effective."""
        if self.effective:
            return ""
        return (
            f"The {HOOK_NAME} hook is installed at {self.path} but git will "
            f"NOT run it: git resolves hooks to {self.hooks_dir}. Arm this "
            f"repository once with:\n    {self.activation_command}"
        )


def install_pre_push(worktree: Path, *, root: Path | None = None) -> HookInstall:
    """Install the shipped hook into `worktree`, and report whether it is live.

    Idempotent, and byte-identical to the tracked ``hooks/pre-push`` -- so in a
    worktree whose checkout already contains it (every worktree of a branch
    that includes this commit) installing changes nothing and leaves the tree
    clean. In a worktree checked out from a commit that predates the hook the
    file is created untracked, which is the correct trade: the defence exists
    before the merge does.

    Writes only inside `worktree`. It does not, and cannot, arm the repository
    -- see `arming_command()`.
    """
    worktree = Path(worktree)
    if not worktree.is_dir():
        raise CrosswireError(
            f"Cannot install the {HOOK_NAME} hook: {worktree} is not a "
            "directory."
        )
    text = hook_text(root)
    # Resolved BEFORE anything is written: it is also the proof that `worktree`
    # is a git worktree at all, and a failure after a write would leave a hook
    # behind that this function then reported nothing about.
    hooks_dir = resolved_hooks_dir(worktree)
    destination = worktree.resolve() / HOOKS_DIRNAME / HOOK_NAME

    # Checked here AND inside `_write_hook`. Not redundancy for its own sake:
    # this call refuses production's checkout before the function so much as
    # stats a file inside it, and the one in the writer is what still holds if
    # this line is deleted. It is the same function both times, so the two
    # cannot drift -- the pattern `branch_harness._hard_branch_guard` already
    # uses in front of the destructive docker paths.
    assert_hook_destination(destination, worktree)

    current = None
    if destination.is_file():
        current = destination.read_text(encoding="utf-8")
    executable = destination.is_file() and destination.stat().st_mode & 0o111
    if current != text or not executable:
        _write_hook(destination, text, worktree=worktree)

    return hook_status(worktree)


def hook_status(worktree: Path) -> HookInstall:
    """What `install_pre_push` reports, WITHOUT installing anything.

    Task 10 needs this: `aurora branch access` renders a branch's document
    from live state, and a document that claimed the pre-push hook was
    protecting the worktree while git was not running it would be worse than
    one that said nothing. It must not install to find that out -- `access` is
    a read.

    `install_pre_push` returns this function's result rather than building its
    own, so "installed" and "inspected" cannot report a worktree differently.
    A non-existent hook is reported as not executable, which is exactly what
    it is: git skips a missing OR non-executable hook with nothing but an
    advice hint, and the push succeeds (measured in Task 7).
    """
    worktree = Path(worktree)
    hooks_dir = resolved_hooks_dir(worktree)
    destination = worktree.resolve() / HOOKS_DIRNAME / HOOK_NAME
    return HookInstall(
        path=destination,
        worktree=worktree.resolve(),
        hooks_dir=hooks_dir,
        executable=bool(
            destination.is_file() and destination.stat().st_mode & 0o111
        ),
        armed=_is_armed(worktree, hooks_dir),
        activation_command=arming_command(),
    )


# ---------------------------------------------------------------------------
# layer 3: the visual marker
# ---------------------------------------------------------------------------


def production_app_name(root: Path | None = None) -> str:
    """The Forgejo application name production's forge renders under.

    Derived, in this order:

    1. ``FORGEJO_APP_NAME`` in production's ``.env``, if it is set there;
    2. otherwise the DEFAULT declared in ``compose.yml``, which is what
       production actually gets today because production's ``.env`` does not
       set the variable at all.

    Parsed out of the compose file rather than typed. `tests/
    test_repo_conformance.py` checks the same declaration by three independent
    routes -- the file's text, the resolved compose config, and the environment
    of production's RUNNING Forgejo container -- so this parse is not also the
    thing that validates itself.
    """
    root = root if root is not None else identity.package_root()
    try:
        from_env = identity.production_env().get(APP_NAME_VAR, "")
    except identity.IdentityError:
        from_env = ""
    if from_env:
        return from_env

    compose = root / _COMPOSE_FILE
    if not compose.is_file():
        raise CrosswireError(
            f"No {_COMPOSE_FILE} at {compose}, so the Forgejo application name "
            "cannot be derived."
        )
    match = _APP_NAME_DEFAULT_RE.search(compose.read_text(encoding="utf-8"))
    if match is None:
        raise CrosswireError(
            f"{compose} does not declare "
            f"{COMPOSE_APP_NAME_KEY}=${{{APP_NAME_VAR}:-<default>}}. Spec 5.4 "
            "layer 3 needs it parameterised WITH production's current value as "
            "the default, so that parameterising it changes nothing for "
            "production and a branch can still mark itself."
        )
    default = match.group("default").strip()
    if not default:
        raise CrosswireError(
            f"{compose} declares {COMPOSE_APP_NAME_KEY} with an EMPTY default. "
            "An empty default satisfies 'no literal' while expanding to "
            "nothing, which is the defect Chunk 2's Caddyfile placeholders "
            "already taught this repository."
        )
    return default


def branch_marker(name: str) -> str:
    """The marker a branch's forge carries: ``[BRANCH: <name>]``."""
    return BRANCH_MARKER_TEMPLATE.format(name=identity.sanitise_branch_name(name))


def branch_app_name(name: str, root: Path | None = None) -> str:
    """Production's application name with this branch's marker appended.

    Spec 5.4 layer 3. This is the layer a human reads: the mechanical one stops
    a push, and this one stops the mistake earlier, in the tab title of the
    forge someone is about to click "merge" in.

    The base is production's, derived -- not the literal. If production ever
    renames its forge, every branch follows, and the marker stays the thing
    that distinguishes them.
    """
    return f"{production_app_name(root)} {branch_marker(name)}"
