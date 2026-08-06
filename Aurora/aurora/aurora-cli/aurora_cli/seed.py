"""Seeding: the seam, the state in production's tree, and the state outside it
(spec §6, decision D10; plan Tasks 5 and 6).

A branch is only a test of production if it starts from production's data. This
module copies that data OUT of production and never, under any circumstance,
writes anything back INTO it. Two mechanisms make that structural rather than
careful:

* every database is read through `connect_readonly()`, i.e. a
  ``file:…?mode=ro`` URI. SQLite then *refuses* a write instead of performing
  one, so "seeding only ever reads production" (§6.6) is a property of the
  connection and not of this code's good intentions;
* `assert_seedable()` refuses a destination that is production, is an ancestor
  of production, or sits inside one of the source subtrees being copied.

Why `VACUUM INTO` and not `cp` for databases
--------------------------------------------
Production's SQLite databases are live and in WAL mode, and their WALs are not
checkpointed. Measured on this host, 2026-07-29 (and reproduced before this
module was written):

    forgejo/gitea/gitea.db   2.4 MB main + 4.1 MB UNCHECKPOINTED WAL
                             -> read-only VACUUM INTO: 2.4 MB snapshot, 0.02 s
    .hermes/state.db         47 MB, live -wal/-shm
                             -> read-only VACUUM INTO: 44 MB snapshot, 0.05 s

Copying the main `.db` alone therefore silently discards every write still in
the WAL — for `gitea.db` that is 4.1 MB of recent Forgejo state, which is the
"my login does not work in the branch" failure §6.3 exists to prevent. This is
also why the `-wal`/`-shm` sidecars are NOT copied: a snapshot produced by
`VACUUM INTO` already contains their content, and copying a stale sidecar next
to a fresh main database is how you get a corrupt one.

Why databases are ENUMERATED and never listed
---------------------------------------------
Spec §6.3 listed four and said "at least five". There are seven — one under
`forgejo/` and six under `.hermes/`, at depths 1 to 3, two of which
(`verification_evidence.db`, `mnemosyne/data/mnemosyne.db`) the spec missed
entirely. A hand-maintained list is the wrong shape for a set that grows
whenever an agent adds a feature, and its failure mode is silent: the branch
comes up with one database missing and nothing says so. `enumerate_sqlite()`
walks the tree.

Why the copy is an ALLOWLIST
----------------------------
`seed_paths()` copies the entries in `HOST_PATH_PLAN` and nothing else. The
inverse — copy everything, then delete what should not have come — would put
production's OIDC secrets (`.agent-env`), production's Caddy state and
production's Forgejo SSH host keys into a branch for as long as it took to
delete them, and would clone anything production grew since this was written.
The cost of an allowlist is that a genuinely new state directory is not seeded
until someone adds it here; that is the failure direction that leaves a branch
visibly empty rather than invisibly cross-wired.

What cannot be copied at all, and why it is not an "ignore errors" problem
-------------------------------------------------------------------------
`forgejo/ssh/ssh_host_*` are root-owned mode 600 and unreadable to the user
this runs as, so a naive ``cp -a forgejo/`` fails outright — verified, exit 1
with six `Permission denied` lines. §6.4 already forbids cloning them for an
independent reason (a branch presenting production's host key under a different
hostname trips an SSH host-key warning on every developer machine), so the
directory is excluded EXPLICITLY. A seeder that merely ignored `cp` failures
would also swallow a real one, so `_cp()` raises.

`affine/data/postgres` is `polkitd:root` mode 700 and unreadable even before
the consistency argument; AFFiNE's state goes through `pg_dump` in Task 6.

`.hermes/home/.cache/uv/**` holds 120 BROKEN symlinks pointing at
container-side paths. `find -not -readable` lists them and they look like
permission failures; they are not, and ``cp -a`` (which implies `-d`) preserves
them correctly. Nothing here may dereference a symlink.

Stdlib only (decision D-A); `cp -a --reflink=auto` because `/var/home` is btrfs
and extent sharing makes 2.6 GB of `.hermes` cost approximately nothing. The
same command works, more slowly, on a filesystem without reflink support —
which is precisely why `SeedStrategy` is a real seam and not ceremony (D10): a
CoW-native implementation can replace `FileCopySeeder` without touching a
caller.
"""

from __future__ import annotations

import dataclasses
import inspect
import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Protocol, runtime_checkable

from aurora_cli import envfile, identity, overlay

#: Filename suffixes that mean "this is a SQLite database". Matched by suffix
#: and applied recursively; see `enumerate_sqlite`.
SQLITE_SUFFIXES = (".db", ".sqlite", ".sqlite3")

#: The sidecars SQLite keeps next to a database. Never copied: `VACUUM INTO`
#: folds their content into the snapshot, and a stale sidecar beside a fresh
#: main database is worse than none.
SQLITE_SIDECAR_SUFFIXES = ("-wal", "-shm", "-journal")

#: `-a` implies `-d` (never dereference a symlink), `-p` (preserve mode, owner
#: where possible, timestamps) and `-R`. `--reflink=auto` shares extents on
#: btrfs and falls back to a full copy elsewhere.
CP = ("cp", "-a", "--reflink=auto")

#: The docker CLI, named once. Every invocation goes through `_docker`.
DOCKER = "docker"

#: Batch size for the per-file `cp` invocations used inside a pruned directory.
#: Only pruned directories need them; a directory with no exclusions anywhere
#: beneath it is copied whole in a single `cp`.
_CP_BATCH = 500

COPY = "copy"
SNAPSHOT = "snapshot"
SKIP = "skip"

DEFAULT_STRATEGY = "filecopy"


class SeedError(RuntimeError):
    """Seeding cannot proceed, or would not be a faithful copy.

    One type, several guards, on purpose: what a caller can act on is the
    MESSAGE. `assert_seedable` alone raises this from three different checks
    and two of them fire on overlapping inputs, so a bare
    ``pytest.raises(SeedError)`` proves nothing about which guard held. The
    tests assert on the message and, where two guards could both fire, assert
    the other one's wording is ABSENT.
    """


# ---------------------------------------------------------------------------
# the report
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SeedAction:
    """One decision the seeder took, and what it cost.

    Skips are recorded as loudly as copies. "What was NOT seeded, and why" is
    the half a branch's user actually needs: a Caddy certificate that has to be
    re-issued and OIDC secrets that have to be re-minted are both invisible
    until something fails, and Task 10 prints this table into
    `BRANCH-ACCESS.md`.
    """

    path: str
    action: str
    bytes: int = 0
    seconds: float = 0.0
    detail: str = ""


class SeedReport:
    """Every action, in the order it was taken."""

    def __init__(self, actions: Iterable[SeedAction] = ()) -> None:
        self.actions: list[SeedAction] = list(actions)

    def add(
        self,
        path: str,
        action: str,
        *,
        bytes: int = 0,
        seconds: float = 0.0,
        detail: str = "",
    ) -> SeedAction:
        entry = SeedAction(
            path=str(path), action=action, bytes=bytes, seconds=seconds,
            detail=detail,
        )
        self.actions.append(entry)
        return entry

    def __len__(self) -> int:
        return len(self.actions)

    def __iter__(self):
        return iter(self.actions)

    def paths(self) -> list[str]:
        return [a.path for a in self.actions]

    def of(self, action: str) -> list[SeedAction]:
        return [a for a in self.actions if a.action == action]

    def total_bytes(self) -> int:
        return sum(a.bytes for a in self.actions)

    def total_seconds(self) -> float:
        return sum(a.seconds for a in self.actions)

    def render(self) -> str:
        """A markdown table, for `BRANCH-ACCESS.md` (Task 10)."""
        rows = ["| what | action | bytes | seconds | why |",
                "|---|---|---:|---:|---|"]
        for a in self.actions:
            rows.append(
                f"| `{a.path}` | {a.action} | {a.bytes} | {a.seconds:.3f} | "
                f"{a.detail} |"
            )
        rows.append(
            f"| **total** | | **{self.total_bytes()}** | "
            f"**{self.total_seconds():.3f}** | |"
        )
        return "\n".join(rows)


# ---------------------------------------------------------------------------
# the plan: what is copied, what is snapshotted, what is never cloned
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SeedRule:
    """One entry of the host-path seeding plan (spec §6)."""

    path: str
    copy: bool
    snapshot_databases: bool = False
    #: Paths, relative to `path`, pruned from the bulk copy. Relative paths
    #: rather than bare names: excluding every directory called `ssh` anywhere
    #: beneath `forgejo/` would be a wider rule than the evidence supports.
    exclude_dirs: tuple[str, ...] = ()
    #: Suffixes pruned from the bulk copy because they are runtime artefacts
    #: rather than state. Database files are NOT listed here — see
    #: `bulk_exclude_suffixes`.
    exclude_suffixes: tuple[str, ...] = ()
    #: A copied source that is missing is a hard error, not a quiet no-op.
    required: bool = True
    why: str = ""

    @property
    def exclude_dir_set(self) -> frozenset[str]:
        return frozenset(self.exclude_dirs)

    @property
    def bulk_exclude_suffixes(self) -> tuple[str, ...]:
        """Every suffix the bulk copy skips.

        The database suffixes are DERIVED from `SQLITE_SUFFIXES` rather than
        written out per rule. Two lists would be two sources of truth able to
        drift, and the drift is silent in the dangerous direction: a `.db` that
        the bulk copy grabs byte-wise instead of leaving to `VACUUM INTO`
        arrives without its uncheckpointed WAL and looks fine.
        """
        if not self.snapshot_databases:
            return tuple(self.exclude_suffixes)
        databases = tuple(
            base + side
            for base in SQLITE_SUFFIXES
            for side in ("",) + SQLITE_SIDECAR_SUFFIXES
        )
        return tuple(dict.fromkeys(tuple(self.exclude_suffixes) + databases))


HOST_PATH_PLAN: tuple[SeedRule, ...] = (
    SeedRule(
        path="forgejo",
        copy=True,
        snapshot_databases=True,
        exclude_dirs=("ssh",),
        why=(
            "git objects, LFS and attachments are write-once and `conf/app.ini` "
            "is configuration, so a plain copy is faithful. `ssh/` is excluded "
            "twice over: spec 6.4 forbids cloning host keys (a branch offering "
            "production's key under a different hostname trips an SSH "
            "host-key warning on every developer machine), and the files are "
            "root-owned mode 600 so `cp` cannot read them anyway. Forgejo "
            "regenerates them on first start."
        ),
    ),
    SeedRule(
        path=".hermes",
        copy=True,
        snapshot_databases=True,
        exclude_suffixes=(".pid", ".lock", ".sock"),
        why=(
            "agent memory, skills, cron definitions and mnemosyne state. The "
            "excluded suffixes are runtime artefacts of a RUNNING agent: a pid "
            "file naming a process that does not exist in the branch, a lock "
            "held by production, a unix socket that cannot be copied as a "
            "socket. Broken symlinks under `home/.cache/uv` are preserved as "
            "links, never dereferenced."
        ),
    ),
    SeedRule(
        path="affine/config",
        copy=True,
        why=(
            "`config.json` and `private.key`; root-owned but world-readable, so "
            "readable here. AFFiNE's DATA is separate and goes through "
            "`pg_dump` in Task 6."
        ),
    ),
    SeedRule(
        path="Caddyfile.d",
        copy=False,
        why=(
            "regenerated by `reconcile` against the BRANCH hostname (spec 6.5). "
            "A copy would route the branch's per-developer agent paths using "
            "production's hostname."
        ),
    ),
    SeedRule(
        path="agent-authz/data/owners.json",
        copy=False,
        why="regenerated by `reconcile` (spec 6.5).",
    ),
    SeedRule(
        path=".agent-env",
        copy=False,
        why=(
            "production's OIDC client secrets. Copying them would register the "
            "branch's agents against production's issuer -- the hazard finding "
            "N1 is about, one layer down. Regenerated against the branch "
            "hostname."
        ),
    ),
    SeedRule(
        path="affine/data",
        copy=False,
        why=(
            "`data/postgres` is polkitd:root mode 700 and unreadable to this "
            "user, and a file copy of a live Postgres data directory would not "
            "be consistent even if it were readable. Task 6 dumps and restores "
            "it."
        ),
    ),
    SeedRule(
        path="arcadedb",
        copy=False,
        why=(
            "production's ArcadeDB is Exited 137 and its state is not identity; "
            "the branch starts with an empty one."
        ),
    ),
)

#: Named volumes a branch must NEVER inherit. Not host paths, so nothing here
#: is copyable in the first place — recorded so the report, and therefore
#: `BRANCH-ACCESS.md`, states the consequence rather than leaving the user to
#: discover it from a TLS error.
NEVER_SEEDED_VOLUMES: Mapping[str, str] = {
    "caddy_data": (
        "project-scoped volume. The branch's own tailscaled issues its own "
        "certificate (spec 6.4); a copy would carry production's."
    ),
    "caddy_config": "project-scoped volume, regenerated on first start.",
}


# ---------------------------------------------------------------------------
# read-only access to a live database
# ---------------------------------------------------------------------------


def readonly_uri(path: Path | str) -> str:
    """The ``file:…?mode=ro`` URI for `path`.

    `Path.as_uri()` percent-encodes, and SQLite decodes percent escapes in URI
    filenames, so this is safe for paths containing `?` or `#` — which a
    hand-built f-string is not.
    """
    return Path(path).resolve().as_uri() + "?mode=ro"


def connect_readonly(path: Path | str) -> sqlite3.Connection:
    """Open `path` such that SQLite REFUSES writes.

    The one place this module opens a database. `mode=ro` is the whole safety
    property of §6.6: with it, a stray `INSERT` anywhere downstream raises
    ``attempt to write a readonly database`` instead of modifying production.
    Pinned by `test_the_source_connection_refuses_writes`.
    """
    uri = readonly_uri(path)
    try:
        return sqlite3.connect(uri, uri=True)
    except sqlite3.Error as exc:
        raise SeedError(
            f"cannot open {path} read-only as {uri!r}: {exc}. A read-only "
            "connection to a WAL database needs a readable `-shm`; falling "
            "back to a writable connection is NOT an option here."
        ) from exc


def snapshot_sqlite(src: Path | str, dst: Path | str) -> int:
    """`VACUUM INTO` a consistent snapshot of the live database `src` at `dst`.

    Returns the snapshot's size in bytes.

    `VACUUM INTO` runs inside a read transaction, so the snapshot is a single
    consistent point in time even while a writer commits throughout — which
    `shutil.copy2` is not, and which additionally loses everything still in an
    uncheckpointed WAL.
    """
    src = Path(src)
    dst = Path(dst)
    if dst.exists():
        raise SeedError(
            f"refusing to snapshot {src} onto existing file {dst}: `VACUUM "
            "INTO` requires a destination that does not exist, and silently "
            "overwriting a snapshot would hide a path collision."
        )
    dst.parent.mkdir(parents=True, exist_ok=True)
    con = connect_readonly(src)
    try:
        con.execute("VACUUM INTO ?", (str(dst),))
    except sqlite3.Error as exc:
        raise SeedError(f"VACUUM INTO {dst} from {src} failed: {exc}") from exc
    finally:
        con.close()
    return dst.stat().st_size


def enumerate_sqlite(root: Path | str) -> list[Path]:
    """Every SQLite database beneath `root`, recursively, sorted.

    Enumerated and never listed: see the module docstring. Symlinks are not
    followed and are not returned — 120 of them under `.hermes` are broken by
    design, and a symlink named `*.db` is not a database this seeder owns.
    """
    root = Path(root)
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames.sort()
        here = Path(dirpath)
        for name in sorted(filenames):
            if not any(name.endswith(suffix) for suffix in SQLITE_SUFFIXES):
                continue
            candidate = here / name
            if candidate.is_symlink() or not candidate.is_file():
                continue
            found.append(candidate)
    return sorted(found)


# ---------------------------------------------------------------------------
# guards
# ---------------------------------------------------------------------------


def production_root() -> Path:
    """Production's checkout, via Task 1.

    Wrapped so this module has exactly one call site, and so a test can point
    it somewhere harmless while proving the guard below fires.
    """
    return identity.production_root()


def assert_seedable(
    src_root: Path,
    dst_root: Path,
    plan: Sequence[SeedRule] = HOST_PATH_PLAN,
) -> None:
    """Refuse a destination that seeding must never write to.

    Three independent checks, each with its own wording, because the input
    space overlaps: production's checkout is also the source root on every real
    call, and a destination inside production is *usually* legitimate —
    decision D-F puts branch worktrees at `<production>/.worktrees/<name>`, so
    "inside production" cannot be the rule. The rule is "not production itself,
    not an ancestor of it, and not inside anything being copied".
    """
    src_root = Path(src_root).resolve()
    dst_root = Path(dst_root).resolve()

    if dst_root == src_root:
        raise SeedError(
            f"refusing to seed {src_root} onto itself: source and destination "
            "root are the same directory."
        )

    try:
        prod = production_root()
    except Exception as exc:            # noqa: BLE001 - fail closed
        raise SeedError(
            f"cannot determine production's checkout, so cannot prove the "
            f"destination {dst_root} is not production: {exc}"
        ) from exc

    # `prod in dst_root.parents` -- "the destination is inside production" --
    # was a third clause here until 2026-07-31, and it contradicted this
    # function's own docstring two paragraphs up: decision D-F puts branch
    # worktrees at `<production>/.worktrees/<name>`, so EVERY legitimate seed
    # has a destination inside production. It made `aurora branch up <name>`
    # refuse at its documented default location, i.e. the whole feature, and
    # it survived because both the acceptance tiers and the control test below
    # put their destinations somewhere `production_root()` does not resolve to.
    # "Inside anything being copied" is the real risk, and the plan loop below
    # is what checks it.
    if dst_root == prod or dst_root in prod.parents:
        raise SeedError(
            f"refusing to seed INTO production: destination {dst_root} is "
            f"production's checkout {prod}, or contains it. Seeding reads "
            "production and writes a branch; a swapped argument here would "
            "overwrite the live stack's state with a copy of itself."
        )

    for rule in plan:
        if not rule.copy:
            continue
        source = (src_root / rule.path).resolve()
        if dst_root == source or source in dst_root.parents:
            raise SeedError(
                f"refusing to seed with destination {dst_root} inside the "
                f"source subtree {source} (plan entry {rule.path!r}): the copy "
                "would be reading what it is writing."
            )


# ---------------------------------------------------------------------------
# the copy
# ---------------------------------------------------------------------------


def _cp(sources: Sequence[Path], dest_dir: Path) -> None:
    """`cp -a --reflink=auto <sources…> <dest_dir>/`, raising on failure.

    Never `check=False`. `cp` failing is how an unreadable file that SHOULD
    have been excluded announces itself; swallowing it is how a branch comes up
    missing state that nobody notices.
    """
    if not sources:
        return
    proc = subprocess.run(
        [*CP, *(str(s) for s in sources), str(dest_dir)],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise SeedError(
            f"cp into {dest_dir} failed (exit {proc.returncode}) for "
            f"{len(sources)} source(s), first {sources[0]}: "
            f"{proc.stderr.strip()}"
        )


def _excluded(rel: PurePosixPath, is_dir: bool, rule: SeedRule) -> bool:
    """Is `rel` -- a path relative to the RULE ROOT, not to `src_root` -- pruned?

    Relative to the rule root because that is what `exclude_dirs` is relative
    to. Getting those two frames of reference confused is not a subtle bug: the
    first version of this compared `forgejo/ssh` against `{"ssh"}`, matched
    nothing, and cloned production's host keys. `test_ssh_host_keys_are_not_
    cloned` caught it on the first run, which is the entire argument for the
    mutation discipline in this chunk.
    """
    if is_dir:
        return str(rel) in rule.exclude_dir_set
    return any(rel.name.endswith(suffix) for suffix in rule.bulk_exclude_suffixes)


def _scandir(path: Path) -> list[os.DirEntry]:
    try:
        with os.scandir(path) as it:
            return sorted(it, key=lambda e: e.name)
    except OSError as exc:
        raise SeedError(
            f"cannot list {path} while seeding: {exc}. An unreadable directory "
            "is either a plan entry that should be excluded or a real problem; "
            "it is never something to skip quietly."
        ) from exc


def _subtree_state(
    src: Path,
    rel: PurePosixPath,
    rule: SeedRule,
    cache: dict[str, tuple[bool, int]],
) -> tuple[bool, int]:
    """`(subtree contains something excluded, bytes of what is included)`.

    One walk answers both questions. The first decides whether the directory
    can be copied whole in a single `cp`; only 22 of `.hermes`' 4314
    directories directly contain an excluded entry, so almost everything takes
    the bulk path.
    """
    key = str(rel)
    cached = cache.get(key)
    if cached is not None:
        return cached
    dirty = False
    total = 0
    for entry in _scandir(src):
        child = rel / entry.name
        is_dir = entry.is_dir(follow_symlinks=False)
        if _excluded(child, is_dir, rule):
            dirty = True
            continue
        if is_dir:
            sub_dirty, sub_bytes = _subtree_state(
                Path(entry.path), child, rule, cache
            )
            dirty = dirty or sub_dirty
            total += sub_bytes
        else:
            total += entry.stat(follow_symlinks=False).st_size
    cache[key] = (dirty, total)
    return cache[key]


def _make_dst_root(dst_root: Path) -> None:
    """Create a destination directory. A WRITE, and therefore its own seam.

    Extracted from `FileCopySeeder.seed_paths` so that a guard test can
    tripwire it, which is the standing rule of this chunk: **tripwire the
    function that touches the DESTINATION, not only the one that moves the
    bytes.** Task 5 learned it the expensive way -- a tripwire over `_cp` and
    `snapshot_sqlite` missed `_copy_pruned`'s `mkdir` + `copystat`, and
    production's real `forgejo/` directory had its mtime moved by a test whose
    entire purpose was to prove that could not happen. Task 6 found the same
    shape one noun over: its first write was `docker volume create`, not
    `docker run`.

    Inline, this call was benign -- it runs after `assert_seedable` and is a
    no-op on an existing directory -- and benign is not the property being
    protected. `mkdir`, `copystat`, `chmod`, `utime` and `open(…, "w")` are all
    writes, and a guard test that cannot see one of them is a guard test with a
    hole in it. Named by the Tasks 5-7 review as MANDATE A -- which named ONE
    call site; `test_seed_paths_delegates_every_write_so_one_tripwire_covers_
    them_all` immediately found a second, the `dst.parent.mkdir` on the
    single-file copy path. Both go through here now, and that gate is what
    keeps the next one from being written inline.
    """
    dst_root.mkdir(parents=True, exist_ok=True)


def _copy_pruned(
    src: Path,
    dst: Path,
    rel: PurePosixPath,
    rule: SeedRule,
    cache: dict[str, tuple[bool, int]],
    skipped: dict[str, list[str]],
    excluded_dirs: list[str],
) -> int:
    """Copy `src` to `dst`, pruning excluded entries. Returns bytes copied."""
    dirty, size = _subtree_state(src, rel, rule, cache)
    if not dirty:
        dst.parent.mkdir(parents=True, exist_ok=True)
        _cp([src], dst.parent)
        return size

    dst.mkdir(parents=True, exist_ok=True)
    shutil.copystat(src, dst, follow_symlinks=False)

    batch: list[Path] = []
    subdirs: list[tuple[Path, Path, PurePosixPath]] = []
    for entry in _scandir(src):
        child = rel / entry.name
        is_dir = entry.is_dir(follow_symlinks=False)
        if _excluded(child, is_dir, rule):
            if is_dir:
                excluded_dirs.append(str(child))
            else:
                suffix = next(
                    s for s in rule.bulk_exclude_suffixes
                    if entry.name.endswith(s)
                )
                skipped.setdefault(suffix, []).append(str(child))
            continue
        if is_dir:
            subdirs.append((Path(entry.path), dst / entry.name, child))
        else:
            batch.append(Path(entry.path))

    for start in range(0, len(batch), _CP_BATCH):
        _cp(batch[start:start + _CP_BATCH], dst)
    for sub_src, sub_dst, sub_rel in subdirs:
        _copy_pruned(sub_src, sub_dst, sub_rel, rule, cache, skipped,
                     excluded_dirs)
    # `cp` into an existing directory updates its mtime; restore it last.
    shutil.copystat(src, dst, follow_symlinks=False)
    return size


# ---------------------------------------------------------------------------
# the seam
# ---------------------------------------------------------------------------


@runtime_checkable
class SeedStrategy(Protocol):
    """How a branch's copy of production's host-path state gets made (D10).

    A seam, not ceremony: `cp -a --reflink=auto` is right for btrfs and merely
    adequate elsewhere, and the volume/Postgres paths in Task 6 are a different
    mechanism again. A replacement supplies `name` and `seed_paths` with this
    exact signature and `get_seeder()` hands it to every caller unchanged.
    """

    name: str

    def seed_paths(
        self,
        src_root: Path,
        dst_root: Path,
        *,
        report: SeedReport | None = None,
    ) -> SeedReport:
        ...


class FileCopySeeder:
    """`cp -a --reflink=auto` for bulk state, `VACUUM INTO` for databases."""

    name = DEFAULT_STRATEGY

    def __init__(
        self,
        plan: Sequence[SeedRule] = HOST_PATH_PLAN,
        never_seeded_volumes: Mapping[str, str] = NEVER_SEEDED_VOLUMES,
    ) -> None:
        self.plan = tuple(plan)
        self.never_seeded_volumes = dict(never_seeded_volumes)

    def seed_paths(
        self,
        src_root: Path,
        dst_root: Path,
        *,
        report: SeedReport | None = None,
    ) -> SeedReport:
        src_root = Path(src_root).resolve()
        dst_root = Path(dst_root).resolve()
        assert_seedable(src_root, dst_root, self.plan)
        report = report if report is not None else SeedReport()
        _make_dst_root(dst_root)

        for rule in self.plan:
            src = src_root / rule.path
            dst = dst_root / rule.path

            if not rule.copy:
                report.add(rule.path, SKIP, detail=rule.why)
                continue

            if not src.exists():
                if rule.required:
                    raise SeedError(
                        f"plan entry {rule.path!r} is missing from {src_root}. "
                        "A required source that is absent is a hard error: "
                        "seeding it as a no-op would produce a branch that is "
                        "silently missing state and a report that says it "
                        "succeeded."
                    )
                report.add(
                    rule.path, SKIP,
                    detail=f"absent from {src_root}; nothing to seed",
                )
                continue

            skipped: dict[str, list[str]] = {}
            excluded_dirs: list[str] = []
            started = time.monotonic()
            if src.is_dir():
                # `PurePosixPath()` and not `PurePosixPath(rule.path)`: every
                # relative path below is relative to the RULE ROOT, which is
                # the frame `exclude_dirs` is written in.
                copied = _copy_pruned(
                    src, dst, PurePosixPath(), rule, {}, skipped,
                    excluded_dirs,
                )
            else:
                # Through the seam, like the root mkdir above: this is a
                # write to the destination, it precedes the tripwired `_cp`,
                # and it was the SECOND instance of MANDATE A -- the review
                # named only the root one, and the write-delegation gate found
                # this one.
                _make_dst_root(dst.parent)
                _cp([src], dst.parent)
                copied = src.stat().st_size
            report.add(
                rule.path, COPY, bytes=copied,
                seconds=time.monotonic() - started, detail=rule.why,
            )

            for name in excluded_dirs:
                report.add(f"{rule.path}/{name}", SKIP, detail=rule.why)
            for suffix, names in sorted(skipped.items()):
                if suffix in rule.exclude_suffixes:
                    detail = (
                        "runtime artefact of a running stack, not state"
                    )
                else:
                    detail = (
                        "database file: content arrives through the VACUUM "
                        "INTO snapshot below, never as a byte copy"
                    )
                report.add(
                    f"{rule.path}/**/*{suffix}", SKIP,
                    detail=f"{len(names)} file(s); {detail}",
                )

            if rule.snapshot_databases:
                self._snapshot_databases(src_root, dst_root, rule, report)

        for volume, why in sorted(self.never_seeded_volumes.items()):
            report.add(volume, SKIP, detail=why)

        return report

    def _snapshot_databases(
        self,
        src_root: Path,
        dst_root: Path,
        rule: SeedRule,
        report: SeedReport,
    ) -> None:
        root = src_root / rule.path
        for database in enumerate_sqlite(root):
            rel = database.relative_to(src_root)
            pruned = PurePosixPath(rel.relative_to(rule.path).as_posix())
            if any(
                str(PurePosixPath(*pruned.parts[:n + 1])) in rule.exclude_dir_set
                for n in range(len(pruned.parts))
            ):
                continue
            started = time.monotonic()
            size = snapshot_sqlite(database, dst_root / rel)
            report.add(
                str(rel), SNAPSHOT, bytes=size,
                seconds=time.monotonic() - started,
                detail=(
                    "read-only VACUUM INTO: consistent even under a concurrent "
                    "writer, and it carries the uncheckpointed WAL a byte copy "
                    "would lose"
                ),
            )


_STRATEGIES: dict[str, object] = {}


def register_seeder(name: str, factory) -> None:
    """Make `name` available to `get_seeder`. Used by tests and by Task 6."""
    _STRATEGIES[name] = factory


def get_seeder(name: str = DEFAULT_STRATEGY) -> SeedStrategy:
    """The seeding strategy called `name`.

    The indirection callers use, so swapping `FileCopySeeder` for a CoW-native
    implementation is one registration and no call-site change (D10).
    """
    try:
        factory = _STRATEGIES[name]
    except KeyError:
        raise SeedError(
            f"unknown seed strategy {name!r}; registered: "
            f"{sorted(_STRATEGIES)}"
        ) from None
    return factory()


register_seeder(DEFAULT_STRATEGY, FileCopySeeder)


# ===========================================================================
# Seeding, part 2 (plan Task 6): the state a host-side `cp` cannot reach
# ===========================================================================
#
# Two kinds of production state live outside the repository tree.
#
# AGENT HOMES ARE NAMED VOLUMES. `/var/lib/docker/volumes/*/_data` is
# root-owned and this user has no `sudo`, so the copy goes through a container
# that mounts both volumes. The source is mounted READ-ONLY: that is the
# volume-level equivalent of `mode=ro`, and it is what makes "seeding only ever
# reads production" a property of the mount rather than of the copy script's
# good intentions.
#
# The source volume NAME is derived from a project name that is never typed.
# There are three generations of agent volume on this host (the pre-migration
# unprefixed set, and one prefixed set per project name), and typing a prefix
# picks the wrong generation in one of the two worlds the rename produces.
#
# COMPOSE ADOPTS A PRE-EXISTING VOLUME, which is what makes pre-`up` seeding
# possible (trap 6). Measured on Compose v5.3.1, 2026-07-29, four ways —
# and the plan's description of the failure mode is WRONG, which matters
# because it is the reason a label test could pass while testing nothing:
#
#   labels on the pre-created volume          `docker compose create` behaviour
#   ---------------------------------------   --------------------------------
#   project + volume                          adopted silently, marker intact
#   project only                              adopted silently, marker intact
#   none at all                               adopted, marker intact, WARNS
#                                             "already exists but was not
#                                             created by Docker Compose"
#   project + volume + version + a config-
#   hash that does not match the resolved
#   config                                    PROMPTS, ON STDIN:
#                                             'Volume "x" exists but doesn't
#                                             match configuration in compose
#                                             file. Recreate (data will be
#                                             lost)?'
#
# That last row was measured three ways, because the precise behaviour is what
# makes it dangerous rather than merely rude:
#
#   * stdin CLOSED (`DEVNULL`, or an empty pipe): Compose reads EOF, takes it
#     as "no", keeps the volume and exits 0. Safe, and noisy.
#   * stdin an OPEN pipe or a terminal with nobody answering: it HANGS
#     INDEFINITELY. Verified — a probe left `docker compose create` blocked
#     until it was killed.
#   * a terminal with a human who answers the obvious way: the seed this whole
#     task exists to produce is DELETED.
#
# So `branch up` must both refrain from writing a config-hash label (this
# module's job, below) and invoke Compose with stdin closed (Task 8's).
#
# So Compose never "creates a second, empty volume": it adopts, or it asks to
# destroy. Two consequences for this module:
#
#   * the labels written here are exactly `project` and `volume`, and NEVER a
#     `config-hash`. A stale hash is the one input that turns `branch up` into
#     a hang, or into data loss;
#   * "adoption happened" cannot be the test of correct labelling, because
#     adoption happens with no labels at all. The labels are asserted
#     directly, against the label names Compose itself writes.
#
# The `project` label is the dangerous one. Point it at production and the
# branch writes into production's agent state, which is why the destination
# project is checked against the branch namespace before anything runs.
#
# AFFiNE POSTGRES cannot be file-copied at all: its data directory is mode 700
# and owned by a user this account is not, so the permission wall arrives
# before the consistency argument does. `pg_dump -Fc` against the live
# instance is read-only and measured at ~256 KB. The restore happens AFTER the
# branch's Postgres is up and healthy (decision D-E), through
# `pg_restore --clean --if-exists`, which is what makes it idempotent against
# a schema the migration job may already have created.
#
# `pg_restore --clean` is the single most destructive operation in this
# package: pointed at the wrong container it DROPS a live schema. The plan's
# required surface contains no guard for it and `ops/docker-guard` does not
# cover `docker exec`, so there are two independent gates here, the first of
# which reaches no daemon at all.

#: The image the volume copy runs in. NOT `alpine`: busybox `cp` has no
#: `--reflink`, and the image carries no SQLite, so neither half of the copy
#: this module performs would work there.
VOLUME_SEED_IMAGE = "python:3.13-slim@sha256:6771159cd4fa5d9bba1258caf0b82e6b73458c694d178ad97c5e925c2d0e1a91"

#: How a per-developer agent home volume is named in the compose file. The
#: compose VOLUME KEY, not the daemon-visible name -- Compose prefixes the
#: project onto it, which is what `compose_volume_name` does.
#: `test_the_agent_volume_key_matches_the_resolved_compose_config` derives the
#: real key set from the resolved configuration and fails if this drifts.
AGENT_VOLUME_TEMPLATE = "hermes-{username}-home"

#: The plan entry an agent home volume takes its treatment from. An agent home
#: IS a Hermes home -- the same live SQLite, the same pid/lock/socket
#: artefacts of a running agent -- so the rule is DERIVED from that entry
#: rather than written a second time. Two copies would drift in the dangerous
#: direction: a `.db` grabbed byte-wise arrives without its uncheckpointed WAL
#: and looks fine.
AGENT_HOME_PLAN_ENTRY = ".hermes"

#: Marker the in-container copy prints its report line behind, so incidental
#: output on stdout cannot be mistaken for the report.
VOLUME_REPORT_MARKER = "AURORA-SEED-REPORT "

#: The first five bytes of a `pg_dump -Fc` archive. A dump that does not start
#: with these is not a custom-format archive, and an EMPTY dump is the exact
#: shape "I dumped the wrong container" takes.
PG_DUMP_MAGIC = b"PGDMP"

#: `pg_restore` continues past errors by default and reports them in a summary
#: line on stderr, exiting 0. Without matching that line, restoring a dump
#: twice WITHOUT `--clean --if-exists` looks like a success.
PG_RESTORE_ERROR_MARKER = "errors ignored on restore"

VOLUME = "volume"
DUMP = "dump"
RESTORE = "restore"

_POSTGRES_USER_VAR = "POSTGRES_USER"
_POSTGRES_DB_VAR = "POSTGRES_DB"


# ---------------------------------------------------------------------------
# the one docker seam
# ---------------------------------------------------------------------------


def _docker(
    args: Sequence[str],
    *,
    stdin: bytes | str | None = None,
    binary: bool = False,
    check: bool = True,
) -> subprocess.CompletedProcess:
    """Every docker invocation this module makes, through one function.

    A single choke point so a test can tripwire EVERY call that could touch a
    destination, not only the one that moves the bytes. Task 5 learned the
    difference the expensive way: its tripwire covered `_cp` and
    `snapshot_sqlite` and not `_copy_pruned`, whose only writes were `mkdir`
    and `copystat` -- and production lost a directory's mtime.

    The equivalents here are `docker volume create` (which can plant a volume
    carrying PRODUCTION's project label, for production's next `up` to adopt)
    and `docker exec … pg_restore` (which can drop a live schema). Neither
    moves a byte through this process. Both go through here.
    """
    proc = subprocess.run(
        [DOCKER, *args],
        input=stdin,
        capture_output=True,
        check=False,
        **({} if binary else {"text": True}),
    )
    if check and proc.returncode != 0:
        stderr = proc.stderr
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", "replace")
        raise SeedError(
            f"`docker {' '.join(args)}` failed with exit {proc.returncode}: "
            f"{(stderr or '').strip() or '(no stderr)'}"
        )
    return proc


# ---------------------------------------------------------------------------
# names
# ---------------------------------------------------------------------------


def agent_volume_key(username: str) -> str:
    """The compose volume key for one developer's agent home."""
    if not isinstance(username, str) or not username.strip():
        raise SeedError(
            f"an agent volume needs a developer username, got {username!r}"
        )
    return AGENT_VOLUME_TEMPLATE.format(username=username)


def compose_volume_name(project: str, key: str) -> str:
    """The daemon-visible name Compose gives volume `key` in `project`.

    `<project>_<key>`. Not asserted from documentation: the adoption test
    pre-creates a volume under this exact name and then proves Compose ADOPTS
    it, which is the only evidence that matters -- if this rule were wrong,
    Compose would create its own volume alongside and the seeded marker file
    would be missing from the mount.
    """
    if not project or not key:
        raise SeedError(
            f"cannot name a compose volume from project {project!r} and key "
            f"{key!r}"
        )
    return f"{project}_{key}"


def agent_volume_name(project: str, username: str) -> str:
    """`<project>_hermes-<username>-home`, with the project never typed."""
    return compose_volume_name(project, agent_volume_key(username))


def compose_volume_labels(project: str, key: str) -> dict[str, str]:
    """The labels a pre-seeded volume needs for Compose to adopt it cleanly.

    Exactly two, and the omission is as deliberate as the inclusions: writing
    a `com.docker.compose.config-hash` label whose value does not match the
    resolved configuration makes `docker compose up` PROMPT on stdin, offering
    to recreate the volume and lose the data. Closed stdin turns that into a
    "no" and merely prints noise; an open pipe with nobody answering hangs
    forever, and a human at a terminal deletes the seed. Measured all three
    ways; see the table at the top of this section.
    """
    return {
        identity.PROJECT_LABEL: project,
        identity.VOLUME_LABEL: key,
    }


# ---------------------------------------------------------------------------
# guards
# ---------------------------------------------------------------------------


def assert_branch_project(project: str, what: str) -> None:
    """Refuse a compose project outside the branch namespace.

    A PREFIX WHITELIST, not a comparison against production's name, for the
    two reasons the harness gives: production carries one label today and
    another after the rename, so a blacklist is wrong in one of the two
    worlds; and this must keep working when production is DOWN, which is when
    `production_project()` raises and when a guard is most needed.

    Pure: it reaches no daemon, reads no file and cannot fail open. That is
    what lets the tests assert "it refused before doing ANYTHING", rather than
    the much weaker "it refused eventually".
    """
    prefix = identity.BRANCH_PROJECT_PREFIX
    if not isinstance(project, str) or not project.startswith(prefix) \
            or len(project) <= len(prefix):
        raise SeedError(
            f"refusing to use {project!r} as the {what}: every project this "
            f"seeder may WRITE to must be in the {prefix!r} namespace. A name "
            "outside it is production under one of its two names, or a stack "
            "that does not belong to this operation. Seeding reads production "
            "and writes a branch; there is no case in which the destination "
            "is not a branch."
        )


def assert_agent_volume_seedable(
    username: str, src_project: str, dst_project: str
) -> None:
    """Refuse an agent-volume copy that could touch production's state.

    Three checks with three distinct wordings, because a bare
    `pytest.raises(SeedError)` would not tell which one held (Task 1's
    finding, and Task 5's `assert_seedable` has the same shape). Nothing here
    talks to the daemon, so a refusal provably precedes every side effect.
    """
    agent_volume_key(username)

    if not isinstance(src_project, str) or not src_project.strip():
        raise SeedError(
            f"the source project must be a non-empty name, got "
            f"{src_project!r}; it is derived from production's identity and "
            "never typed."
        )

    assert_branch_project(dst_project, "destination project")

    if src_project == dst_project:
        raise SeedError(
            f"refusing to seed agent volume for {username!r} from project "
            f"{src_project!r} into itself: the copy would be reading the "
            "volume it is writing."
        )


def assert_branch_container(container: str, what: str) -> None:
    """Refuse a container name outside the branch namespace. Pure.

    The first of two independent gates in front of `pg_restore`. It is a name
    check and not a label check precisely so that it needs no daemon: the
    label check below is the second gate, and no single edit opens the path.

    This works because the branch overlay resets `container_name` (Task 3), so
    every branch container is named `<project>-<service>-<n>` and inherits the
    `br-` prefix, while production's Postgres carries an explicit
    `container_name` that does not.
    """
    prefix = identity.BRANCH_PROJECT_PREFIX
    if not isinstance(container, str) or not container.startswith(prefix) \
            or len(container) <= len(prefix):
        raise SeedError(
            f"refusing {container!r} as the {what}: `pg_restore --clean` DROPS "
            "every object it is about to restore, so it may only ever target "
            f"a container in the {prefix!r} namespace. Pointed at a live "
            "instance this destroys a schema, and `ops/docker-guard` does not "
            "see `docker exec`."
        )


def _assert_container_labelled_branch(container: str) -> None:
    """Second, INDEPENDENT gate: the container's own compose label.

    Deliberate duplication of the namespace rule, for the reason the harness'
    `_hard_branch_guard` gives: the guard above is one line away from being
    weakened, and what is behind it is irreversible. This one asks the daemon,
    so it also catches a container that merely happens to be NAMED like a
    branch container.
    """
    prefix = identity.BRANCH_PROJECT_PREFIX
    proc = _docker([
        "inspect", "--format",
        '{{index .Config.Labels "' + identity.PROJECT_LABEL + '"}}',
        container,
    ])
    project = (proc.stdout or "").strip()
    if not project.startswith(prefix) or len(project) <= len(prefix):
        raise SeedError(
            f"HARD GUARD: container {container!r} carries "
            f"{identity.PROJECT_LABEL}={project!r}, which is not in the "
            f"{prefix!r} namespace. Refusing to run `pg_restore --clean` "
            "against it. This gate is independent of the name check on "
            "purpose."
        )


# ---------------------------------------------------------------------------
# volume plumbing
# ---------------------------------------------------------------------------


def volume_exists(name: str) -> bool:
    return _docker(["volume", "inspect", name], check=False).returncode == 0


def volume_labels(name: str) -> dict[str, str]:
    """The compose labels on volume `name`, as a dict."""
    proc = _docker(["volume", "inspect", name, "--format", "{{json .Labels}}"])
    labels = json.loads(proc.stdout or "null")
    return dict(labels) if labels else {}


def create_labelled_volume(name: str, labels: Mapping[str, str]) -> None:
    args = ["volume", "create"]
    for key, value in labels.items():
        args += ["--label", f"{key}={value}"]
    _docker([*args, name])


# ---------------------------------------------------------------------------
# the rule an agent home is copied under, and the snapshot fallback
# ---------------------------------------------------------------------------


def plan_entry(path: str, plan: Sequence[SeedRule] = HOST_PATH_PLAN) -> SeedRule:
    for rule in plan:
        if rule.path == path:
            return rule
    raise SeedError(
        f"no seeding plan entry for {path!r}; the agent-volume rule is derived "
        f"from it. Known entries: {[r.path for r in plan]}"
    )


#: An agent home volume, copied under the SAME rule as the host-side Hermes
#: tree. Every field is derived; only `path` differs, because a volume's root
#: is the mount point rather than a subdirectory of the checkout. Adding an
#: exclusion to the host rule therefore applies to agent volumes with no
#: second edit -- which is the whole point, since the failure mode of the two
#: lists disagreeing is a byte-copied database with no WAL.
AGENT_VOLUME_RULE = dataclasses.replace(plan_entry(AGENT_HOME_PLAN_ENTRY),
                                       path=".")


def snapshot_sqlite_via_copy(
    src: Path | str, dst: Path | str, scratch_root: Path | str
) -> int:
    """`VACUUM INTO` a database that cannot be opened where it lies.

    Needed because of a hard measured limit, 2026-07-29, on this host:

        source volume mounted `:ro`, `-shm` PRESENT  -> mode=ro VACUUM INTO ok
        source volume mounted `:ro`, `-shm` ABSENT   -> "unable to open
                                                        database file"

    `mode=ro` forbids writes to the DATABASE, not to the `-shm`: SQLite still
    has to mmap a WAL index to register a read mark, and on a read-only mount
    it cannot create one. So a WAL database with no `-shm` is unreadable in
    place, and the plan's own volume test specifies exactly that shape.

    The two paths pair up rather than compromise, and this is the argument for
    doing it this way instead of dropping `:ro`:

    * an `-shm` exists precisely while some connection has the database open,
      i.e. exactly when a writer might be committing -- and that is the case
      the direct read-only `VACUUM INTO` handles, consistently, with no copy;
    * no `-shm` means no open connection, i.e. nothing is writing -- and that
      is the only case this fallback runs in, so copying the database beside
      its `-wal` cannot tear.

    The triple is copied into `scratch_root`, which is on the DESTINATION, so
    the fallback writes nothing to the source either.
    """
    src = Path(src)
    dst = Path(dst)
    scratch = Path(tempfile.mkdtemp(dir=str(scratch_root), prefix=".aurora-seed-"))
    try:
        local = scratch / src.name
        present = []
        for suffix in ("",) + SQLITE_SIDECAR_SUFFIXES:
            beside = Path(str(src) + suffix)
            if beside.is_file():
                shutil.copy2(beside, str(local) + suffix)
                present.append(suffix or "(main)")
        if "(main)" not in present:
            raise SeedError(
                f"cannot snapshot {src}: it is not a readable file, so there "
                "is nothing to copy into scratch."
            )
        return snapshot_sqlite(local, dst)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def _copy_tree_pruned(
    src_root: Path,
    dst_root: Path,
    rule: SeedRule,
    skipped: dict[str, list[str]],
    excluded_dirs: list[str],
) -> int:
    """Copy the CONTENTS of `src_root` into `dst_root`, pruning per `rule`.

    `_copy_pruned` copies a directory to a destination with the same basename
    -- its fast path is `cp -a <src> <dst.parent>` -- which is true for every
    host-path plan entry and false for a volume, whose source and destination
    are two mount points with different names. Copying entry by entry keeps
    `_copy_pruned`'s frame of reference (paths relative to the rule root)
    exactly as it is, so the exclusion semantics are shared rather than
    re-derived.
    """
    dst_root.mkdir(parents=True, exist_ok=True)
    cache: dict[str, tuple[bool, int]] = {}
    total = 0
    batch: list[Path] = []
    for entry in _scandir(src_root):
        rel = PurePosixPath(entry.name)
        is_dir = entry.is_dir(follow_symlinks=False)
        if _excluded(rel, is_dir, rule):
            if is_dir:
                excluded_dirs.append(str(rel))
            else:
                suffix = next(
                    s for s in rule.bulk_exclude_suffixes
                    if entry.name.endswith(s)
                )
                skipped.setdefault(suffix, []).append(str(rel))
            continue
        if is_dir:
            total += _copy_pruned(
                Path(entry.path), dst_root / entry.name, rel, rule, cache,
                skipped, excluded_dirs,
            )
        else:
            batch.append(Path(entry.path))
            total += entry.stat(follow_symlinks=False).st_size
    for start in range(0, len(batch), _CP_BATCH):
        _cp(batch[start:start + _CP_BATCH], dst_root)
    return total


def seed_volume_tree(
    src_root: Path | str,
    dst_root: Path | str,
    rule: SeedRule = AGENT_VOLUME_RULE,
) -> dict:
    """Copy one volume's contents, snapshotting every database. Returns a summary.

    Runs on the host in tests and INSIDE the copy container in production use
    -- the container gets this function's own source, so there is no second
    implementation to drift.
    """
    src_root = Path(src_root)
    dst_root = Path(dst_root)
    skipped: dict[str, list[str]] = {}
    excluded_dirs: list[str] = []

    started = time.monotonic()
    copied = _copy_tree_pruned(src_root, dst_root, rule, skipped, excluded_dirs)
    bulk_seconds = time.monotonic() - started

    databases = []
    for database in enumerate_sqlite(src_root):
        rel = database.relative_to(src_root)
        pruned = PurePosixPath(rel.as_posix())
        if any(
            str(PurePosixPath(*pruned.parts[:n + 1])) in rule.exclude_dir_set
            for n in range(len(pruned.parts))
        ):
            continue
        target = dst_root / rel
        began = time.monotonic()
        try:
            size = snapshot_sqlite(database, target)
            how = "direct"
        except SeedError:
            size = snapshot_sqlite_via_copy(database, target, dst_root)
            how = "via-copy"
        databases.append({
            "path": rel.as_posix(),
            "bytes": size,
            "seconds": round(time.monotonic() - began, 4),
            "how": how,
        })

    return {
        "bulk_bytes": copied,
        "bulk_seconds": round(bulk_seconds, 4),
        "databases": databases,
        "excluded_dirs": sorted(excluded_dirs),
        "skipped": {k: sorted(v) for k, v in sorted(skipped.items())},
    }


# ---------------------------------------------------------------------------
# the payload the copy container runs
# ---------------------------------------------------------------------------

#: The module members the in-container script is ASSEMBLED FROM. Listed in
#: dependency order and shipped as their own source text, so "the container
#: runs the same snapshot logic" is a fact about this module rather than a
#: claim about a second copy of it. `test_the_volume_payload_ships_this_
#: modules_own_source` pins it, and mutation M4 pins it behaviourally.
_PAYLOAD_MEMBERS = (
    "SeedError",
    "SeedRule",
    "readonly_uri",
    "connect_readonly",
    "snapshot_sqlite",
    "snapshot_sqlite_via_copy",
    "enumerate_sqlite",
    "_cp",
    "_excluded",
    "_scandir",
    "_subtree_state",
    "_copy_pruned",
    "_copy_tree_pruned",
    "seed_volume_tree",
)

_PAYLOAD_PREAMBLE = """\
# GENERATED by aurora_cli.seed.volume_seed_payload() -- do not edit.
# Assembled from that module's OWN source so the copy inside the container and
# the copy on the host cannot diverge.
from __future__ import annotations

import dataclasses
import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
"""

_PAYLOAD_MAIN = """\

if __name__ == "__main__":
    _summary = seed_volume_tree(Path({src!r}), Path({dst!r}), AGENT_VOLUME_RULE)
    print({marker!r} + json.dumps(_summary))
"""


def volume_seed_payload(
    rule: SeedRule = AGENT_VOLUME_RULE,
    *,
    src: str = "/src",
    dst: str = "/dst",
) -> str:
    """The Python program the copy container reads on stdin."""
    parts = [_PAYLOAD_PREAMBLE]
    for name in ("SQLITE_SUFFIXES", "SQLITE_SIDECAR_SUFFIXES", "CP",
                 "_CP_BATCH"):
        parts.append(f"{name} = {globals()[name]!r}\n")
    for name in _PAYLOAD_MEMBERS:
        parts.append("\n\n" + inspect.getsource(globals()[name]))
        if name == "SeedRule":
            # Emitted HERE and not at the end: `seed_volume_tree`'s default
            # argument is evaluated when the payload defines the function, so a
            # rule appended after it is a NameError at import time inside the
            # container -- measured, not theorised.
            parts.append(f"\n\nAGENT_VOLUME_RULE = {rule!r}\n")
    parts.append(_PAYLOAD_MAIN.format(src=src, dst=dst,
                                      marker=VOLUME_REPORT_MARKER))
    return "".join(parts)


def _parse_volume_report(stdout: str) -> dict:
    for line in reversed(stdout.splitlines()):
        if line.startswith(VOLUME_REPORT_MARKER):
            return json.loads(line[len(VOLUME_REPORT_MARKER):])
    raise SeedError(
        "the volume copy container printed no report line "
        f"({VOLUME_REPORT_MARKER!r}); its output was:\n{stdout}"
    )


# ---------------------------------------------------------------------------
# seeding one agent home volume
# ---------------------------------------------------------------------------


def seed_agent_volume(
    username: str,
    src_project: str,
    dst_project: str,
    *,
    report: SeedReport | None = None,
    rule: SeedRule = AGENT_VOLUME_RULE,
) -> SeedReport:
    """Copy one developer's agent home from `src_project` into `dst_project`.

    Every guard is pure and runs FIRST, so a refusal provably precedes every
    daemon call -- not merely every call that moves bytes. `docker volume
    create` is a write: with production's project label on it, production's
    next `up` adopts whatever this leaves behind.

    The destination volume must not already exist. `VACUUM INTO` refuses an
    existing file for the same reason: filling a volume that is already there
    means adopting an unknown previous generation, and the previous generation
    of a branch volume is the state of a branch that was supposed to be gone.
    """
    assert_agent_volume_seedable(username, src_project, dst_project)

    key = agent_volume_key(username)
    source = compose_volume_name(src_project, key)
    destination = compose_volume_name(dst_project, key)
    report = report if report is not None else SeedReport()

    if not volume_exists(source):
        raise SeedError(
            f"production has no agent home volume {source!r} to seed from. "
            "That name is derived from the running stack's compose project, so "
            "either the agents have never been started under this project name "
            f"(the daemon may still hold an earlier generation called {key!r}, "
            "which is a ROLLBACK copy and not this stack's state), or the "
            "volume was destroyed. Refusing to create an empty agent home: an "
            "empty one is adopted silently and surfaces later as 'my login "
            "does not work in the branch'."
        )
    if volume_exists(destination):
        raise SeedError(
            f"the destination volume {destination!r} already exists. Filling "
            "it would merge this seed into an unknown previous generation of "
            f"the same branch. Tear the branch down first."
        )

    labels = compose_volume_labels(dst_project, key)
    create_labelled_volume(destination, labels)

    started = time.monotonic()
    proc = _docker(
        [
            "run", "--rm", "-i", "--network=none",
            # Labelled for the same reason the reclaim container is: THIS is
            # the container that survived a kill between `create` and `start`
            # and could then be neither swept nor removed
            # (docs/issues/2026-08-01-wedged-seed-container.md).
            "--label", f"{identity.PROJECT_LABEL}={dst_project}",
            "-v", f"{source}:/src:ro",
            "-v", f"{destination}:/dst",
            VOLUME_SEED_IMAGE, "python", "-",
        ],
        stdin=volume_seed_payload(rule),
    )
    summary = _parse_volume_report(proc.stdout)
    elapsed = time.monotonic() - started

    report.add(
        destination, VOLUME,
        bytes=summary["bulk_bytes"] + sum(d["bytes"] for d in
                                         summary["databases"]),
        seconds=elapsed,
        detail=(
            f"agent home for {username!r}, copied from {source} with the "
            f"source mounted read-only; labels "
            f"{', '.join(f'{k}={v}' for k, v in sorted(labels.items()))} so "
            "Compose adopts it instead of creating an empty one"
        ),
    )
    for entry in summary["databases"]:
        report.add(
            f"{destination}:{entry['path']}", SNAPSHOT,
            bytes=entry["bytes"], seconds=entry["seconds"],
            detail=(
                "read-only VACUUM INTO"
                + ("" if entry["how"] == "direct" else
                   " of a scratch copy, because the database has no `-shm` "
                   "and so cannot be opened on a read-only mount")
            ),
        )
    for suffix, names in sorted(summary["skipped"].items()):
        report.add(
            f"{destination}:**/*{suffix}", SKIP,
            detail=f"{len(names)} file(s); runtime artefact or database sidecar",
        )
    return report


# ---------------------------------------------------------------------------
# AFFiNE Postgres
# ---------------------------------------------------------------------------


def postgres_service(root: Path | None = None) -> str:
    """The compose SERVICE key of the Postgres instance, derived.

    Found by asking the resolved configuration which service declares the
    Postgres image's own initialisation variables. Neither the service name
    nor the database name is typed: both belong to a vendored compose file
    this repository includes rather than owns, and one of them is also the
    account name, which the branch renderer is free to change.

    Exactly one service must qualify. Two is not something to disambiguate by
    picking the first.
    """
    config = overlay.resolve_config(root)
    services = config.get("services") or {}
    if not services:
        raise SeedError(
            "the resolved compose configuration declares no services, so the "
            "Postgres service cannot be derived from it."
        )
    candidates = sorted(
        name for name, spec in services.items()
        if _POSTGRES_DB_VAR in (spec.get("environment") or {})
        and _POSTGRES_USER_VAR in (spec.get("environment") or {})
    )
    if len(candidates) != 1:
        raise SeedError(
            f"expected exactly one service declaring both "
            f"{_POSTGRES_USER_VAR} and {_POSTGRES_DB_VAR}, found "
            f"{candidates}. Refusing to guess which one holds AFFiNE's data."
        )
    return candidates[0]


def postgres_container(project: str, root: Path | None = None) -> str:
    """The container name of `project`'s Postgres, from the daemon's labels.

    By label and not by name: production names its Postgres container
    explicitly while a branch's is named by Compose (Task 3 resets
    `container_name`), so the label is the only form that answers the question
    in both worlds.
    """
    service = postgres_service(root)
    proc = _docker([
        "ps", "-a",
        "--filter", f"label={identity.PROJECT_LABEL}={project}",
        "--filter", f"label={identity.SERVICE_LABEL}={service}",
        "--format", "{{.Names}}",
    ])
    names = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    if len(names) != 1:
        raise SeedError(
            f"expected exactly one container for service {service!r} in "
            f"compose project {project!r}, found {names}. An empty result is "
            "the vacuous case the harness refuses everywhere else: it would "
            "make every later question about this container answer 'no'."
        )
    return names[0]


def production_postgres_container() -> str:
    return postgres_container(identity.production_project())


def container_credentials(container: str) -> tuple[str, str]:
    """`(POSTGRES_USER, POSTGRES_DB)` from the env file of `container`'s stack.

    Derived from the container's own `working_dir` label, so the credentials
    for a branch's Postgres come from the BRANCH's `.env` and production's
    from production's, through one code path with nothing typed. Task 2
    renders the branch file from production's, so the values agree today --
    and this does not depend on their agreeing, which is the point: a branch
    that is given its own database credentials keeps working.
    """
    proc = _docker([
        "inspect", "--format",
        '{{index .Config.Labels "' + identity.WORKING_DIR_LABEL + '"}}',
        container,
    ])
    working_dir = (proc.stdout or "").strip()
    if not working_dir:
        raise SeedError(
            f"container {container!r} carries no "
            f"{identity.WORKING_DIR_LABEL} label, so its stack's env file "
            "cannot be located and its database credentials cannot be derived."
        )
    env_path = Path(working_dir).resolve() / envfile.ENV_FILE_NAME
    if not env_path.is_file():
        raise SeedError(
            f"container {container!r} was deployed from {working_dir}, which "
            f"holds no {envfile.ENV_FILE_NAME}; database credentials come from "
            "there and are never typed."
        )
    values = envfile.parse_env(env_path.read_text(encoding="utf-8"))
    missing = [v for v in (_POSTGRES_USER_VAR, _POSTGRES_DB_VAR)
               if not values.get(v)]
    if missing:
        raise SeedError(
            f"{env_path} declares no {', '.join(missing)}; the Postgres "
            "credentials for this stack cannot be derived."
        )
    return values[_POSTGRES_USER_VAR], values[_POSTGRES_DB_VAR]


def dump_postgres(
    container: str | None = None,
    *,
    user: str | None = None,
    database: str | None = None,
) -> bytes:
    """`pg_dump -Fc` of a live Postgres. Read-only against the instance.

    Defaults to PRODUCTION's Postgres, derived, because that is the only
    instance a branch is ever seeded from. Passing a container explicitly is
    how a test dumps its own throwaway instance.

    The result is checked for the custom-format magic and for content. That is
    not paranoia about pg_dump: a dump taken from the WRONG instance -- an
    empty branch database, or one that is not running -- is the failure this
    whole function exists to avoid, and it is silent. `--clean --if-exists`
    then makes a later restore of that empty dump DELETE the branch's data
    rather than merely fail to add any.
    """
    container = container if container is not None \
        else production_postgres_container()
    if user is None or database is None:
        derived_user, derived_db = container_credentials(container)
        user = user if user is not None else derived_user
        database = database if database is not None else derived_db

    proc = _docker(
        ["exec", container, "pg_dump", "-U", user, "-Fc", database],
        binary=True,
    )
    dump = proc.stdout
    if not dump:
        raise SeedError(
            f"`pg_dump` of database {database!r} in {container!r} returned no "
            "bytes. An empty dump restores as a deletion."
        )
    if not dump.startswith(PG_DUMP_MAGIC):
        raise SeedError(
            f"the dump of {database!r} in {container!r} does not begin with "
            f"the custom-format magic {PG_DUMP_MAGIC!r}: first bytes "
            f"{dump[:16]!r}."
        )
    return dump


def restore_postgres(
    container: str,
    dump: bytes,
    *,
    user: str | None = None,
    database: str | None = None,
    report: SeedReport | None = None,
) -> SeedReport:
    """`pg_restore --clean --if-exists` a dump into a BRANCH's Postgres.

    The most destructive call in this package. `--clean` drops every object it
    is about to restore, so a wrong container argument destroys a live schema
    -- and `ops/docker-guard` cannot help, because it does not treat
    `docker exec` as destructive. Hence two independent gates, the first pure
    (see `assert_branch_container`).

    `--clean --if-exists` is what makes this idempotent: the branch's own
    migration job may already have created the schema (decision D-E restores
    AFTER the stack is up, precisely so that it does), and re-seeding must be
    a no-op rather than a pile of "already exists" errors.

    `pg_restore` reports errors and EXITS 0 by default, so a non-zero exit is
    not the only failure to look for; the summary line on stderr is checked
    too. Without that, dropping `--clean --if-exists` looks like success.
    """
    assert_branch_container(container, "pg_restore target")
    _assert_container_labelled_branch(container)

    if not isinstance(dump, bytes) or not dump.startswith(PG_DUMP_MAGIC):
        raise SeedError(
            "refusing to restore something that is not a custom-format "
            f"`pg_dump` archive: {type(dump).__name__}, first bytes "
            f"{dump[:16]!r}."
        )

    if user is None or database is None:
        derived_user, derived_db = container_credentials(container)
        user = user if user is not None else derived_user
        database = database if database is not None else derived_db

    report = report if report is not None else SeedReport()
    started = time.monotonic()
    proc = _docker(
        [
            "exec", "-i", container,
            "pg_restore", "-U", user, "-d", database,
            "--clean", "--if-exists", "--no-owner",
        ],
        stdin=dump,
        binary=True,
        check=False,
    )
    stderr = (proc.stderr or b"").decode("utf-8", "replace")
    if proc.returncode != 0 or PG_RESTORE_ERROR_MARKER in stderr:
        raise SeedError(
            f"`pg_restore` into database {database!r} of {container!r} failed "
            f"(exit {proc.returncode}): {stderr.strip() or '(no stderr)'}"
        )

    report.add(
        f"{container}:{database}", RESTORE,
        bytes=len(dump), seconds=time.monotonic() - started,
        detail=(
            "pg_restore --clean --if-exists, so a re-seed replaces the schema "
            "the migration job created instead of colliding with it"
        ),
    )
    return report
