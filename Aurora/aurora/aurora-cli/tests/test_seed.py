"""Seeding, part 1: the seam and host-path state (spec §6, plan Task 5).

Why the primary tests are built on a fixture and not on production
------------------------------------------------------------------
Production is written to *while this test runs*. A "seeding did not mutate
production" assertion built on it is flaky in one direction (Forgejo commits a
session row on its own and the test goes red for nothing) and blind in the
other (a real mutation is indistinguishable from ambient noise). So the shapes
that matter are reproduced in `tmp_path`: a WAL-mode database with an
uncheckpointed WAL and a writer committing *during* the snapshot, a database at
depth 4, a broken symlink, a unix socket, a file the test user cannot read, and
bulk directories.

Exactly one test touches production, `test_production_gitea_db_snapshots_read_
only`, and it is read-only by construction plus tripwired — see its docstring.

The four trap shapes, and where each is answered
-----------------------------------------------
* **vacuous pass** — production's real `.env` happens to contain no quoted
  values, and a Chunk 2 agreement test therefore passed over an empty set.
  Every assertion here over a set of files or databases first asserts the set is
  non-empty, and where the point is coverage (`.db` *and* `-wal` both compared)
  the coverage itself is a separate, named test.
* **sequential-guard `raises`** — `assert_seedable` raises `SeedError` from
  three checks whose inputs overlap. Every `pytest.raises` below asserts on the
  message and asserts the *other* guards' wording is absent.
* **self-blinding artefact** — the list of databases the fixture creates is
  written out here, and `enumerate_sqlite` discovers them by walking; the
  seventh database is added by the test at a depth and name the fixture never
  mentions, so a generator and its checker cannot be blinded together.
* **artifact-vs-generator** — the no-mutation invariant is checked in both
  directions: that a correct seed leaves the tree byte-identical, and (the
  separate coverage test) that the comparison set actually contains the file
  kinds the invariant is about.
"""

from __future__ import annotations

import dataclasses
import hashlib
import inspect
import json
import os
import re
import shutil
import socket
import sqlite3
import stat
import subprocess
import sys
import textwrap
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

import pytest

from aurora_cli import identity, overlay, seed

# `dev-administration` is on sys.path via pytest.ini's `pythonpath`, which
# is what makes `tests` resolve to the dev-administration package and gives
# this file the ONE implementation of the docstring-stripping scan.
from tests.test_guard_coverage import _strip_docstrings

# `tests/` is on sys.path for any run that collects it, and `testpaths` puts it
# first -- but an `aurora-cli/tests/test_seed.py`-only invocation collects it
# never. PROD_VOLATILE_SUFFIXES has exactly one definition (Task 0) and this
# module must not grow a second, so make the import work either way.
_HARNESS_DIR = identity.package_root() / "tests"
if str(_HARNESS_DIR) not in sys.path:
    sys.path.insert(0, str(_HARNESS_DIR))

import conftest  # noqa: E402

# The harness fixtures are imported BY NAME because pytest resolves
# fixtures from the requesting module's namespace, and `throwaway_branches`
# -- the factory `throwaway_branch` is one call of -- must come with it or
# the wrapper is unresolvable.
from branch_harness import (  # noqa: E402,F401
    PROD_VOLATILE_SUFFIXES,
    assert_production_unchanged,
    production_snapshot,
    throwaway_branch,
    throwaway_branches,
)

#: Where the fixture's broken symlink points. A container-side path, exactly as
#: production's 120 real ones do.
BROKEN_LINK_TARGET = "/opt/data/home/.cache/uv/archive-v0/deadbeefcafe"

#: The databases the fixture creates, mirroring production's real shape: one
#: under `forgejo/`, six under `.hermes/` at depths 1, 2 and 3. Written out
#: here on purpose -- `enumerate_sqlite` must DISCOVER them, so the expectation
#: cannot come from the same walk the implementation does.
FIXTURE_DATABASES = (
    "forgejo/gitea/gitea.db",
    ".hermes/state.db",
    ".hermes/kanban.db",
    ".hermes/projects.db",
    ".hermes/verification_evidence.db",
    ".hermes/cron/executions.db",
    ".hermes/mnemosyne/data/mnemosyne.db",
)

HERMES_DATABASES = tuple(p for p in FIXTURE_DATABASES if p.startswith(".hermes/"))

#: Bulk, write-once-ish content: the part a plain `cp` is the right tool for.
FIXTURE_BULK = {
    "forgejo/gitea/conf/app.ini": "[server]\nDOMAIN = example.invalid\n",
    "forgejo/gitea/attachments/a1/b2/attachment-blob": "attachment payload\n",
    "forgejo/git/repositories/org/repo.git/HEAD": "ref: refs/heads/main\n",
    "forgejo/ssh/ssh_host_ed25519_key.pub": "ssh-ed25519 AAAAC3Nz fixture\n",
    ".hermes/memories/MEMORY.md": "# memory\n- a fact\n",
    ".hermes/skills/some-skill/SKILL.md": "# skill\n",
    ".hermes/mnemosyne/data/notes/note.md": "a note\n",
    "affine/config/config.json": '{"server": {}}\n',
    "affine/config/private.key": "-----BEGIN PRIVATE KEY-----\nfixture\n",
    "Caddyfile.d/agents.conf": "handle /agent/someone/* {\n}\n",
    "agent-authz/data/owners.json": '{"someone": "someone"}\n',
    ".agent-env/oidc-someone.env": "OIDC_CLIENT_SECRET=production-secret\n",
    "affine/data/postgres/PG_VERSION": "16\n",
    "arcadedb/databases/graph/manifest": "arcade\n",
    # NOT in HOST_PATH_PLAN. Present so "the seed is an allowlist" is a claim
    # about an entry that really exists in the source rather than about
    # nothing.
    "caddy_data/pki/authorities/local/root.crt": "a certificate\n",
}

#: Runtime artefacts of a *running* stack. Excluded, and the exclusion is
#: load-bearing for the socket: `cp` cannot faithfully reproduce one.
FIXTURE_ARTEFACTS = (
    ".hermes/hermes.pid",
    ".hermes/cron/.tick.lock",
    ".hermes/home/.cache/uv/.lock",
)

#: Paths spec §6 says a branch must not inherit. Written out here INDEPENDENTLY
#: of `HOST_PATH_PLAN`, because a checker that read the plan is blinded by the
#: same edit that breaks it: delete an entry and both the declaration and its
#: test vanish together. Mutation M20 is that edit. Safety survives it either
#: way -- seeding is an allowlist, so an undeclared path is never copied -- but
#: the SeedReport stops saying "your OIDC secrets were not copied and must be
#: regenerated", and that sentence is the only warning the branch's user gets.
MUST_NOT_BE_SEEDED = (
    "Caddyfile.d",
    "agent-authz/data/owners.json",
    ".agent-env",
    "affine/data",
    "arcadedb",
)

UNREADABLE_KEY = "forgejo/ssh/ssh_host_ed25519_key"
BROKEN_LINK = ".hermes/home/.cache/uv/wheels-v6/pypi/edge-tts/7.2.7-py3-none-any"
FIXTURE_SOCKET = ".hermes/hermes.sock"


# --------------------------------------------------------------- fixture


@dataclass
class ProdShaped:
    """A throwaway tree with production's awkward shapes, and nothing else."""

    root: Path
    holders: list[sqlite3.Connection] = field(default_factory=list)
    initial_rows: int = 0
    wal_only_rows: int = 0

    @property
    def total_rows(self) -> int:
        return self.initial_rows + self.wal_only_rows


def _make_wal_db(path: Path, *, initial: int, wal_only: int,
                 payload: int = 64) -> sqlite3.Connection:
    """A WAL database whose most recent rows exist ONLY in the `-wal`.

    The checkpoint-then-disable-autocheckpoint sequence is what makes that
    true, and it is what makes mutation M1 (`snapshot_sqlite` -> `shutil.copy2`)
    deterministic rather than a race: a byte copy of the main database file
    cannot contain rows that were never written to it. Production's
    `forgejo/gitea/gitea.db` is in exactly this state today -- 2.4 MB main file
    beside a 4.1 MB uncheckpointed WAL.

    The connection is RETURNED and must stay open: closing the last connection
    checkpoints the WAL and deletes both sidecars, and then there is no `-wal`
    for the no-mutation invariant to compare.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, payload TEXT)")
    pad = "x" * payload
    con.executemany(
        "INSERT INTO t (payload) VALUES (?)",
        [(f"initial-{i}-{pad}",) for i in range(initial)],
    )
    con.commit()
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    con.execute("PRAGMA wal_autocheckpoint=0")
    con.executemany(
        "INSERT INTO t (payload) VALUES (?)",
        [(f"wal-only-{i}-{pad}",) for i in range(wal_only)],
    )
    con.commit()
    return con


@pytest.fixture
def prod_shaped(tmp_path: Path):
    """Production's shape, reproduced: see the module docstring."""
    root = tmp_path / "production"
    fixture = ProdShaped(root=root, initial_rows=120, wal_only_rows=40)

    for rel, text in FIXTURE_BULK.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)

    for rel in FIXTURE_ARTEFACTS:
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("runtime\n")

    for rel in FIXTURE_DATABASES:
        fixture.holders.append(
            _make_wal_db(root / rel, initial=fixture.initial_rows,
                         wal_only=fixture.wal_only_rows)
        )

    link = root / BROKEN_LINK
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(BROKEN_LINK_TARGET)

    sock_path = root / FIXTURE_SOCKET
    sock_path.parent.mkdir(parents=True, exist_ok=True)
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.bind(str(sock_path))

    key = root / UNREADABLE_KEY
    key.write_text("PRIVATE\n")
    key.chmod(0o000)

    try:
        yield fixture
    finally:
        sock.close()
        for con in fixture.holders:
            con.close()
        key.chmod(0o600)


@pytest.fixture
def seeder():
    return seed.get_seeder()


# --------------------------------------------------------------- helpers


def _fingerprint(root: Path) -> tuple[dict[str, str], list[str]]:
    """`({relative path: content digest}, [unreadable paths])`.

    Excludes `PROD_VOLATILE_SUFFIXES` -- Task 0's single definition of "changes
    on its own while a read-only seed runs" (finding N6). `-shm` is the mmap'd
    WAL index and a read-only `VACUUM INTO` may legitimately rewrite it;
    including it makes the invariant red against a CORRECT seeder, which is the
    same defect shape as Chunk 2's `PRODUCTION_PROJECT` comparison.

    Symlinks are fingerprinted by their target, never followed, and sockets by
    the fact that they are sockets. Unreadable files are returned separately so
    a caller can assert *which* ones were unreadable, rather than silently
    comparing a smaller set than it thinks.
    """
    prints: dict[str, str] = {}
    unreadable: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames.sort()
        here = Path(dirpath)
        for name in sorted(filenames):
            path = here / name
            rel = path.relative_to(root).as_posix()
            if rel.endswith(PROD_VOLATILE_SUFFIXES):
                continue
            if path.is_symlink():
                prints[rel] = "link:" + os.readlink(path)
                continue
            if stat.S_ISSOCK(path.lstat().st_mode):
                prints[rel] = "socket"
                continue
            try:
                prints[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
            except PermissionError:
                unreadable.append(rel)
    return prints, sorted(unreadable)


def _row_count(database: Path) -> int | None:
    """Rows in `t`, or None if the table is not even there."""
    con = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    try:
        return con.execute("SELECT count(*) FROM t").fetchone()[0]
    except sqlite3.Error:
        return None
    finally:
        con.close()


def _integrity(database: Path) -> str:
    con = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    try:
        return con.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        con.close()


def _sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --------------------------------------------------------------- enumeration


def test_enumerate_finds_databases_at_every_depth(prod_shaped):
    """Recursive discovery, at depths the spec's own list did not reach.

    Spec §6.3 named four databases and hedged with "at least five"; production
    has seven, at depths 1 to 3. So the count here is checked exactly, and then
    an EIGHTH is added at a depth and under a name that appears nowhere in this
    module's fixture data. A hardcoded implementation cannot find it.
    """
    found = seed.enumerate_sqlite(prod_shaped.root / ".hermes")
    relative = sorted(
        p.relative_to(prod_shaped.root).as_posix() for p in found
    )
    assert relative == sorted(HERMES_DATABASES)
    assert len(relative) == 6, "the fixture must reproduce all six, or this test proves nothing"
    depths = {rel.count("/") for rel in relative}
    assert depths == {1, 2, 3}, f"depth coverage lost: {depths}"

    newcomer = prod_shaped.root / ".hermes/agents/someone/store/inbox.db"
    prod_shaped.holders.append(_make_wal_db(newcomer, initial=3, wal_only=1))

    again = seed.enumerate_sqlite(prod_shaped.root / ".hermes")
    assert len(again) == 7
    assert newcomer in again, (
        "a database added at a new depth under a new name was not discovered; "
        "the enumeration is not an enumeration"
    )


def test_enumerate_ignores_symlinks_and_non_databases(prod_shaped):
    """A symlink named like a database is not one, and is never followed.

    120 of production's `.hermes` symlinks are broken by design. A walk that
    treated one as a database would try to `VACUUM INTO` from a path that does
    not exist and fail the whole seed.
    """
    hermes = prod_shaped.root / ".hermes"
    (hermes / "decoy.db").symlink_to(BROKEN_LINK_TARGET)
    (hermes / "notes.txt").write_text("not a database\n")

    found = seed.enumerate_sqlite(hermes)
    assert found, "vacuous: nothing was enumerated at all"
    assert hermes / "decoy.db" not in found
    assert all(p.suffix in seed.SQLITE_SUFFIXES for p in found)


def test_the_bulk_exclusions_are_derived_from_one_suffix_list():
    """`SQLITE_SUFFIXES` is the only place database suffixes are written.

    Two lists -- one for "enumerate these" and one for "do not bulk-copy
    these" -- is two sources of truth, and the drift is silent in the dangerous
    direction: a `.db` the bulk copy grabs byte-wise arrives without its
    uncheckpointed WAL and looks perfectly fine.
    """
    snapshotting = [r for r in seed.HOST_PATH_PLAN if r.snapshot_databases]
    assert snapshotting, "vacuous: no plan entry snapshots databases"
    for rule in snapshotting:
        for base in seed.SQLITE_SUFFIXES:
            for side in ("",) + seed.SQLITE_SIDECAR_SUFFIXES:
                assert base + side in rule.bulk_exclude_suffixes, (
                    f"{rule.path}: {base + side} is not pruned from the bulk "
                    "copy, so it would be copied AND snapshotted"
                )

    plain = [r for r in seed.HOST_PATH_PLAN if r.copy and not r.snapshot_databases]
    assert plain, "vacuous: no plan entry copies without snapshotting"
    for rule in plain:
        assert ".db" not in rule.bulk_exclude_suffixes


# --------------------------------------------------------------- read-only


def test_the_source_connection_refuses_writes(prod_shaped):
    """`mode=ro` is the safety property, not a comment about intent.

    §6.6 says seeding only ever reads production. `connect_readonly` makes that
    a property of the CONNECTION: SQLite refuses the write instead of
    performing it, so no amount of wrong code downstream can modify the source.
    """
    database = prod_shaped.root / ".hermes/state.db"
    uri = seed.readonly_uri(database)
    assert "mode=ro" in uri, uri

    con = seed.connect_readonly(database)
    try:
        with pytest.raises(sqlite3.OperationalError) as raised:
            con.execute("INSERT INTO t (payload) VALUES ('written')")
        assert "readonly" in str(raised.value).lower(), raised.value
    finally:
        con.close()

    assert _row_count(database) == prod_shaped.total_rows


def test_snapshot_of_a_database_written_during_the_copy_is_consistent(tmp_path):
    """A snapshot taken while a writer commits is a single point in time.

    Three things are asserted, and all three are needed:

    * the snapshot opens and `PRAGMA integrity_check` says `ok` -- it is not a
      torn file;
    * its row count is one of the values the writer actually COMMITTED, never
      an intermediate one;
    * the writer committed at least twice *inside* the snapshot's own time
      window. Without that last assertion the test would pass against a
      snapshot taken while nothing was happening, and mutation M1 would survive
      -- which the brief says means the fixture, not the mutation table, is
      wrong.
    """
    database = tmp_path / "state.db"
    con = _make_wal_db(database, initial=20_000, wal_only=4_000, payload=200)
    assert database.stat().st_size > 1_000_000, "too small to overlap a writer"

    committed: list[tuple[float, int]] = []
    stop = threading.Event()
    failure: list[BaseException] = []

    def writer() -> None:
        try:
            writer_con = sqlite3.connect(database, isolation_level=None)
            writer_con.execute("PRAGMA wal_autocheckpoint=0")
            n = 24_000
            while not stop.is_set():
                writer_con.execute("BEGIN")
                writer_con.execute(
                    "INSERT INTO t (payload) VALUES (?)", (f"live-{n}",)
                )
                writer_con.execute("COMMIT")
                n += 1
                committed.append((time.monotonic(), n))
            writer_con.close()
        except BaseException as exc:            # noqa: BLE001 - reported below
            failure.append(exc)

    thread = threading.Thread(target=writer, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not committed and not failure and time.monotonic() < deadline:
            time.sleep(0.001)
        started = time.monotonic()
        size = seed.snapshot_sqlite(database, tmp_path / "snapshot.db")
        finished = time.monotonic()
    finally:
        stop.set()
        thread.join(timeout=10)
        con.close()

    assert not failure, failure
    assert committed, "the writer never committed anything"
    assert size > 0

    during = [n for when, n in committed if started <= when <= finished]
    assert len(during) >= 2, (
        f"the writer committed {len(during)} time(s) inside the snapshot "
        f"window ({finished - started:.3f}s). The fixture is not exercising a "
        "concurrent writer, so this test cannot catch a torn copy."
    )

    snapshot = tmp_path / "snapshot.db"
    assert _integrity(snapshot) == "ok"
    count = _row_count(snapshot)
    assert count is not None, (
        f"the snapshot has no table `t` at all: {snapshot} is not a usable "
        "database"
    )
    assert count in {n for _, n in committed} | {24_000}, (
        f"the snapshot holds {count} rows, which is not any value the writer "
        f"committed (committed: {sorted({n for _, n in committed})[:5]}… "
        f"{sorted({n for _, n in committed})[-5:]}). Either it is torn, or it "
        "lost the uncheckpointed WAL."
    )


def test_the_snapshot_carries_rows_that_live_only_in_the_wal(tmp_path):
    """Why `VACUUM INTO` and not `cp` -- stated as a test, in both directions.

    Production's `gitea.db` has a 4.1 MB uncheckpointed WAL. The generator
    (`snapshot_sqlite`) must carry it; the control shows a byte copy of the
    main file does not. One direction alone would be satisfiable by an
    implementation that is right for the wrong reason.
    """
    database = tmp_path / "gitea.db"
    con = _make_wal_db(database, initial=50, wal_only=25)
    try:
        assert (tmp_path / "gitea.db-wal").stat().st_size > 0

        seed.snapshot_sqlite(database, tmp_path / "vacuumed.db")
        assert _row_count(tmp_path / "vacuumed.db") == 75

        shutil.copy2(database, tmp_path / "bytewise.db")
        assert _row_count(tmp_path / "bytewise.db") == 50, (
            "control failed: a byte copy of the main file was expected to lose "
            "the 25 WAL-only rows. If it did not, the fixture has already "
            "checkpointed and no test here proves anything about WALs."
        )
    finally:
        con.close()


# --------------------------------------------------------------- no mutation


def test_seed_does_not_mutate_the_source(prod_shaped, seeder, tmp_path):
    """Finding N6, as an assertion: a correct seed changes nothing it reads.

    Compared: every file under the source, symlinks by target and sockets by
    kind, MINUS Task 0's `PROD_VOLATILE_SUFFIXES`. The precision is the point
    -- `-shm` is excluded because a read-only `VACUUM INTO` legitimately
    rewrites it, and `-wal` is emphatically NOT excluded because that is the
    file a seeder opening the source read-write would damage. See
    `test_the_no_mutation_invariant_compares_databases_and_wals` for the
    coverage half.
    """
    before, unreadable_before = _fingerprint(prod_shaped.root)
    assert before, "vacuous: nothing was fingerprinted"

    seeder.seed_paths(prod_shaped.root, tmp_path / "branch")

    after, unreadable_after = _fingerprint(prod_shaped.root)

    assert unreadable_before == unreadable_after == [UNREADABLE_KEY], (
        "the set of unreadable source files changed, or is not the one file "
        f"expected: {unreadable_before} -> {unreadable_after}"
    )

    differing = sorted(
        rel for rel in set(before) | set(after)
        if before.get(rel) != after.get(rel)
    )
    assert differing == [], (
        "seeding MUTATED the source tree. Changed: "
        + ", ".join(differing)
        + ". Seeding reads production; a write here is a write to a live stack."
    )


def test_the_no_mutation_invariant_compares_databases_and_wals(prod_shaped):
    """The invariant is not allowed to be hollowed out into a tautology.

    An exclusion list is the cheapest way to make a comparison test pass, and
    `-wal` is the entry that would do it: exclude it and a seeder that opens
    the source read-write and checkpoints it goes undetected in the file that
    shows the damage most directly. So this test pins what the comparison set
    must CONTAIN, separately from the comparison itself, and pins the two
    suffix decisions N6 rests on.
    """
    prints, unreadable = _fingerprint(prod_shaped.root)
    assert prints, "vacuous: nothing was fingerprinted"

    databases = sorted(p for p in prints if p.endswith(".db"))
    wals = sorted(p for p in prints if p.endswith(".db-wal"))
    shms = sorted(p for p in prints if p.endswith("-shm"))

    assert len(databases) == len(FIXTURE_DATABASES), databases
    assert wals, (
        "the compared set contains no `-wal` file. Either the fixture has no "
        "WAL databases, or `-wal` has been added to PROD_VOLATILE_SUFFIXES -- "
        "and then a seeder that checkpoints the source is invisible in exactly "
        "the file that would show it."
    )
    assert any(
        (prod_shaped.root / rel).stat().st_size > 0 for rel in wals
    ), "every compared `-wal` is empty, so comparing them proves nothing"
    assert shms == [], (
        f"`-shm` files are being compared ({shms}); a read-only VACUUM INTO "
        "may rewrite one, so this makes the invariant red against a CORRECT "
        "seeder"
    )

    assert "-shm" in PROD_VOLATILE_SUFFIXES
    assert "-wal" not in PROD_VOLATILE_SUFFIXES, (
        "`-wal` must never be treated as volatile: finding N6 excludes `-shm`, "
        "`.lock`, `.pid` and `.log` on measured evidence and deliberately "
        "stops there."
    )
    assert unreadable == [UNREADABLE_KEY]


# --------------------------------------------------------------- what is not cloned


def test_ssh_host_keys_are_not_cloned(prod_shaped, seeder, tmp_path):
    """Spec §6.4, and a mechanical reason on top of it.

    A branch presenting production's host key under a different hostname trips
    an SSH host-key warning on every developer machine. Independently, the keys
    are root-owned mode 600 and `cp` cannot read them, so a seeder without this
    exclusion does not merely leak -- it fails. Both are asserted, because
    either alone could be satisfied for the wrong reason: the readable `.pub`
    proves the directory had something clonable in it.
    """
    branch = tmp_path / "branch"
    report = seeder.seed_paths(prod_shaped.root, branch)

    assert (prod_shaped.root / "forgejo/ssh/ssh_host_ed25519_key.pub").is_file(), (
        "vacuous: the source has no host key material to leak"
    )
    assert not (branch / "forgejo/ssh").exists()
    leaked = sorted(str(p.relative_to(branch)) for p in branch.rglob("ssh_host_*"))
    assert leaked == [], f"host key material reached the branch: {leaked}"

    assert (branch / "forgejo/gitea/conf/app.ini").is_file(), (
        "vacuous the other way: forgejo was not seeded at all"
    )
    assert "forgejo/ssh" in report.paths()


def test_caddy_data_is_not_cloned(prod_shaped, seeder, tmp_path):
    """`caddy_data`/`caddy_config` are project-scoped volumes (spec §6.4).

    The branch's own tailscaled issues its own certificate. Copying
    production's would hand a branch a certificate for production's hostname,
    which is both wrong and, per §5.4, the cross-wiring direction that matters.
    Recorded in the report as well as absent from the tree, because "your
    certificate will be re-issued on first start" is something
    `BRANCH-ACCESS.md` has to say out loud.

    Which volumes must be declared is DERIVED from the resolved compose
    configuration, not read out of `NEVER_SEEDED_VOLUMES`. The first version of
    this test iterated the constant it was checking, and mutation M13b -- delete
    one entry -- proved that blinds the declaration and its checker in the same
    stroke: green suite, branch serving production's certificate. Deriving also
    catches the opposite drift, a new named volume added to Caddy in compose.yml
    that nobody thought about here.
    """
    config = overlay.resolve_config()
    caddy = (config.get("services") or {})[overlay.CADDY_SERVICE]
    named = sorted(
        entry["source"] for entry in (caddy.get("volumes") or [])
        if entry.get("type") == "volume"
    )
    assert named, (
        "vacuous: the resolved config shows caddy mounting no named volume, so "
        "this test has no expectation to check"
    )
    for volume in named:
        assert volume in seed.NEVER_SEEDED_VOLUMES, (
            f"caddy mounts the named volume {volume!r}, which is where its "
            "certificate and configuration state live, but seed.py does not "
            "declare it never-seeded. A branch that inherited it would present "
            "production's certificate (spec 6.4)."
        )

    branch = tmp_path / "branch"
    report = seeder.seed_paths(prod_shaped.root, branch)

    assert seed.NEVER_SEEDED_VOLUMES, "vacuous: nothing declared never-seeded"
    for volume, why in seed.NEVER_SEEDED_VOLUMES.items():
        assert why.strip(), f"{volume} is declared never-seeded with no reason"
        assert volume in report.paths(), (
            f"{volume} is never seeded but the report does not say so"
        )
        assert not (branch / volume).exists()

    assert (prod_shaped.root / "caddy_data").is_dir(), (
        "vacuous: the source has no caddy_data to copy"
    )


def test_the_seed_is_an_allowlist(prod_shaped, seeder, tmp_path):
    """Nothing outside `HOST_PATH_PLAN` is copied, ever.

    This is what makes the two tests above claims rather than coincidences: a
    copy-everything-then-delete seeder would put production's OIDC secrets and
    Caddy state into a branch for as long as it took to remove them, and would
    clone whatever production grew since this plan was written.
    """
    branch = tmp_path / "branch"
    report = seeder.seed_paths(prod_shaped.root, branch)

    not_copied = {rule.path for rule in seed.HOST_PATH_PLAN if not rule.copy}
    for rel in MUST_NOT_BE_SEEDED:
        assert (prod_shaped.root / rel).exists(), f"vacuous: no source {rel}"
        assert not (branch / rel).exists(), f"{rel} reached the branch"
        assert rel in not_copied, (
            f"spec 6 says {rel} must not be inherited, but no plan entry "
            "declares it. The allowlist means it is not copied either way -- "
            "what is lost is the report line telling the branch's user it has "
            "to be regenerated."
        )
        assert rel in report.paths(), (
            f"{rel} is not seeded and the report does not say so, so "
            "BRANCH-ACCESS.md will not either"
        )

    declared = {rule.path for rule in seed.HOST_PATH_PLAN}
    source_top = {p.name for p in prod_shaped.root.iterdir()}
    undeclared = sorted(
        name for name in source_top
        if not any(rule == name or rule.startswith(name + "/") for rule in declared)
    )
    assert undeclared, (
        "vacuous: every top-level entry in the source is declared, so this "
        "test cannot observe an allowlist at all"
    )
    for name in undeclared:
        assert not (branch / name).exists(), (
            f"{name} is not in HOST_PATH_PLAN but was copied anyway"
        )

    for rule in seed.HOST_PATH_PLAN:
        if rule.copy:
            continue
        assert not (branch / rule.path).exists(), (
            f"{rule.path} is declared copy=False but is present in the branch"
        )
        assert (prod_shaped.root / rule.path).exists(), (
            f"vacuous for {rule.path}: it is not in the source either"
        )


def test_broken_symlinks_survive(prod_shaped, seeder, tmp_path):
    """`cp -a` preserves them; anything that dereferences fails outright.

    Production has 120 of these under `.hermes/home/.cache/uv`, pointing at
    container-side paths. `find -not -readable` lists them and they look like
    permission failures.
    """
    branch = tmp_path / "branch"
    seeder.seed_paths(prod_shaped.root, branch)

    link = branch / BROKEN_LINK
    assert link.is_symlink(), f"{link} is not a symlink"
    assert os.readlink(link) == BROKEN_LINK_TARGET
    assert not link.exists(), "the link resolved, so the fixture is not broken"


def test_runtime_artefacts_are_not_copied(prod_shaped, seeder, tmp_path):
    """`.pid`, `.lock` and `.sock` belong to the process that made them.

    The socket is the load-bearing case: it cannot be reproduced by copying,
    and a `cp` that met one would either fail or create something that is not a
    socket.
    """
    branch = tmp_path / "branch"
    seeder.seed_paths(prod_shaped.root, branch)

    for rel in FIXTURE_ARTEFACTS + (FIXTURE_SOCKET,):
        assert (prod_shaped.root / rel).exists(), f"vacuous: no source {rel}"
        assert not (branch / rel).exists(), f"{rel} was copied into the branch"

    assert (branch / ".hermes/memories/MEMORY.md").is_file(), (
        "vacuous the other way: .hermes was not seeded at all"
    )


def test_an_unreadable_file_outside_the_exclusions_fails_the_seed(
    prod_shaped, seeder, tmp_path,
):
    """A failing `cp` is a finding, never noise to be swallowed.

    This is the test that lets `forgejo/ssh` be an EXPLICIT exclusion instead of
    an "ignore errors" flag. The six host keys are excluded by name, so the
    seeder never meets them; anything else it cannot read is a real problem, and
    a `cp` wrapper running with `check=False` would produce a branch missing
    state and a report claiming success.
    """
    blocked = prod_shaped.root / ".hermes/memories/PRIVATE.md"
    blocked.write_text("unreadable\n")
    blocked.chmod(0o000)
    try:
        with pytest.raises(seed.SeedError) as raised:
            seeder.seed_paths(prod_shaped.root, tmp_path / "branch")
        message = str(raised.value)
        assert "cp into" in message, message
        assert "Permission denied" in message, message
        assert "PRIVATE.md" in message, message
    finally:
        blocked.chmod(0o600)


def test_databases_are_snapshotted_not_byte_copied(prod_shaped, seeder, tmp_path):
    """Every database arrives as a `VACUUM INTO` snapshot, sidecars excluded.

    The row count is the assertion that matters: it can only be right if the
    uncheckpointed WAL came across, and a byte copy of the main file cannot
    produce it.
    """
    branch = tmp_path / "branch"
    report = seeder.seed_paths(prod_shaped.root, branch)

    snapshotted = sorted(a.path for a in report.of(seed.SNAPSHOT))
    assert snapshotted == sorted(FIXTURE_DATABASES), snapshotted

    for rel in FIXTURE_DATABASES:
        copied = branch / rel
        assert copied.is_file(), f"{rel} was not seeded"
        assert _integrity(copied) == "ok", rel
        assert _row_count(copied) == prod_shaped.total_rows, (
            f"{rel} lost its uncheckpointed WAL: "
            f"{_row_count(copied)} rows, expected {prod_shaped.total_rows}"
        )
        for side in seed.SQLITE_SIDECAR_SUFFIXES:
            sidecar = Path(str(copied) + side)
            assert not sidecar.exists(), (
                f"{sidecar.name} was copied; a stale sidecar beside a fresh "
                "snapshot is worse than none"
            )


def test_seed_report_lists_every_action(prod_shaped, seeder, tmp_path):
    """`SeedReport` is the document Task 10 prints as "what was seeded"."""
    branch = tmp_path / "branch"
    report = seeder.seed_paths(prod_shaped.root, branch)

    assert len(report) > 0
    paths = report.paths()

    for rule in seed.HOST_PATH_PLAN:
        assert rule.path in paths, f"{rule.path} is not in the report"
        assert rule.why.strip(), f"{rule.path} carries no reason"

    copied = {a.path for a in report.of(seed.COPY)}
    skipped = {a.path for a in report.of(seed.SKIP)}
    assert copied == {r.path for r in seed.HOST_PATH_PLAN if r.copy}
    assert {r.path for r in seed.HOST_PATH_PLAN if not r.copy} <= skipped
    assert "forgejo/ssh" in skipped
    assert {a.path for a in report.of(seed.SNAPSHOT)} == set(FIXTURE_DATABASES)
    assert set(seed.NEVER_SEEDED_VOLUMES) <= skipped

    assert report.total_bytes() > 0
    assert report.total_seconds() > 0
    for action in report.of(seed.COPY) + report.of(seed.SNAPSHOT):
        assert action.bytes > 0, f"{action.path} recorded zero bytes"
        assert action.detail.strip(), f"{action.path} recorded no reason"

    rendered = report.render()
    assert "| copy |" in rendered and "| snapshot |" in rendered
    for rule in seed.HOST_PATH_PLAN:
        assert f"`{rule.path}`" in rendered


# --------------------------------------------------------------- guards


def test_seeding_refuses_a_destination_that_is_the_source(prod_shaped, seeder):
    with pytest.raises(seed.SeedError) as raised:
        seeder.seed_paths(prod_shaped.root, prod_shaped.root)
    message = str(raised.value)
    assert "onto itself" in message, message
    assert "INTO production" not in message, message
    assert "inside the source subtree" not in message, message


def test_seeding_refuses_to_write_into_production(prod_shaped, seeder,
                                                 monkeypatch):
    """The destination guard, proved against production's REAL path.

    This test names production's checkout as a destination, so before it does
    anything it makes every writing primitive unreachable: `_cp`,
    `snapshot_sqlite` and `_copy_pruned` are replaced by tripwires and asserted
    never to have fired. That is the direct lesson of the 2026-07-29 incident,
    in which a test proved a guard worked by making the dangerous call and
    relying on the guard it was testing. A guard test must be safe when the
    guard is broken, because that is the only situation in which it matters.

    `_copy_pruned` is on that list because leaving it off was not hypothetical.
    With the guard disabled, an earlier version of this test let `_copy_pruned`
    run: it never reached the tripwired `_cp`, but it had already called
    `dst.mkdir(exist_ok=True)` and `shutil.copystat(src, dst)` and so set the
    mtime of production's real `forgejo/` directory from the fixture's. No
    content, no ownership, no children -- but a write to production all the
    same, from a test whose entire purpose is to prove that cannot happen. The
    lesson generalises: tripwire the function that TOUCHES the destination, not
    only the one that moves the bytes.

    `_make_dst_root` was added to that list by Task 8 (MANDATE A of the Tasks
    5-7 review). It is `seed_paths`' own `mkdir` on the destination root, and
    it was the one remaining write this tripwire could not see -- benign in
    practice, because it runs after the guard and is a no-op on an existing
    directory, and exactly the shape above one function up.
    """
    fired: list[tuple] = []

    def tripwire(*args, **kwargs):
        fired.append((args, kwargs))
        raise AssertionError(
            "TRIPWIRE: production was named as the seeding destination and a "
            f"write was attempted anyway: {args!r}"
        )

    monkeypatch.setattr(seed, "_cp", tripwire)
    monkeypatch.setattr(seed, "snapshot_sqlite", tripwire)
    monkeypatch.setattr(seed, "_copy_pruned", tripwire)
    monkeypatch.setattr(seed, "_make_dst_root", tripwire)

    production = identity.production_root()
    with pytest.raises(seed.SeedError) as raised:
        seeder.seed_paths(prod_shaped.root, production)
    message = str(raised.value)
    assert "INTO production" in message, message
    assert "onto itself" not in message, message
    assert not fired, f"the tripwire fired: {fired}"

    with pytest.raises(seed.SeedError) as raised:
        seeder.seed_paths(prod_shaped.root, production.parent)
    assert "INTO production" in str(raised.value), raised.value
    assert not fired, f"the tripwire fired: {fired}"


def test_seed_paths_delegates_every_write_so_one_tripwire_covers_them_all():
    """Deletion pressure on the tripwire above (MANDATE A).

    The tripwire is only total while every write in `seed_paths` goes through a
    NAMED function it can replace. A future `chmod` or `open(..., "w")` written
    inline would re-open exactly the hole that moved production's `forgejo/`
    mtime in Task 5, and no existing test would notice -- the guard test would
    keep passing while covering less.

    Docstrings are stripped before scanning, because this project already
    shipped an `inspect.getsource()` check that was satisfied by prose. The
    named seams are asserted to exist as well, so the scan cannot pass by
    finding nothing at all.
    """
    for seam in ("_make_dst_root", "_copy_pruned", "_cp", "snapshot_sqlite"):
        assert callable(getattr(seed, seam)), seam
    # Dedented before parsing: `_strip_docstrings` compiles the text, and a
    # method's source arrives indented.
    source = _strip_docstrings(textwrap.dedent(
        inspect.getsource(seed.FileCopySeeder.seed_paths)))
    assert "_make_dst_root" in source, (
        "seed_paths no longer delegates its destination mkdir; the guard "
        "tripwire cannot see an inline one"
    )
    for forbidden in (".mkdir(", "copystat", ".chmod(", "os.utime",
                      "shutil.copy"):
        assert forbidden not in source, (
            f"seed_paths writes to the destination directly via {forbidden!r}. "
            "Every write must go through a named seam or "
            "test_seeding_refuses_to_write_into_production cannot tripwire it."
        )


def test_seeding_refuses_a_destination_inside_a_source_subtree(prod_shaped,
                                                              seeder):
    """The copy must not be reading what it is writing.

    Decision D-F puts branch worktrees at `<production>/.worktrees/<name>`, so
    "inside production" is legitimate and cannot be the rule; "inside something
    being copied" is.
    """
    with pytest.raises(seed.SeedError) as raised:
        seeder.seed_paths(prod_shaped.root, prod_shaped.root / ".hermes/branch")
    message = str(raised.value)
    assert "inside the source subtree" in message, message
    assert ".hermes" in message, message
    assert "onto itself" not in message, message
    assert "INTO production" not in message, message


def test_a_destination_under_worktrees_is_allowed(prod_shaped, seeder, tmp_path,
                                                  monkeypatch):
    """The control case for the three guards above.

    Without it, an `assert_seedable` that raised unconditionally would satisfy
    every `raises` test in this file.

    `production_root` is bound to the FIXTURE root, and that is the whole
    point of this test rather than a detail of it. Unbound, `assert_seedable`
    resolves the real checkout while the destination is under `tmp_path`, so
    every clause phrased in terms of production compares two unrelated trees
    and cannot fire. This test passed for that reason while a clause reading
    `prod in dst_root.parents` refused every branch `aurora branch up` has
    ever tried to create at its documented location -- the wrong-identity
    shape: green because it measured the wrong production, not because the
    property held.
    """
    monkeypatch.setattr(seed, "production_root", lambda: prod_shaped.root)
    branch = prod_shaped.root / ".worktrees/somebranch"
    report = seeder.seed_paths(prod_shaped.root, branch)
    assert (branch / "forgejo/gitea/gitea.db").is_file()
    assert report.of(seed.COPY)


def test_a_required_source_that_is_missing_is_a_hard_error(prod_shaped, seeder,
                                                          tmp_path):
    """An absent source is not a quiet no-op.

    Seeding a missing `forgejo/` as zero bytes produces a branch with no
    Forgejo data and a report that says it succeeded -- the silent-inheritance
    shape finding N1 is about, one layer down.
    """
    shutil.rmtree(prod_shaped.root / "affine/config")
    with pytest.raises(seed.SeedError) as raised:
        seeder.seed_paths(prod_shaped.root, tmp_path / "branch")
    message = str(raised.value)
    assert "affine/config" in message, message
    assert "hard error" in message, message


def test_seed_does_not_redefine_the_volatile_suffix_list():
    """One definition of "volatile", in Task 0's harness.

    Chunk 2 shipped two functions that each ran their own "identical" docker
    query and they drifted apart twice. A second copy of this list would drift
    the same way, and the direction that matters is the silent one: a local copy
    that grows `-wal` hollows out the no-mutation invariant with nothing to
    notice.
    """
    source = Path(seed.__file__).read_text()
    assert "PROD_VOLATILE_SUFFIXES" not in source, (
        "seed.py refers to PROD_VOLATILE_SUFFIXES; it must be imported from "
        "tests/branch_harness.py by the TEST, not restated in the module"
    )
    harness = (identity.package_root() / "tests/branch_harness.py").read_text()
    assert "PROD_VOLATILE_SUFFIXES = " in harness, (
        "vacuous: the harness does not define it either"
    )


# --------------------------------------------------------------- the seam


def _parameters(function) -> list[tuple[str, object]]:
    return [
        (p.name, p.kind)
        for p in inspect.signature(function).parameters.values()
    ]


def test_the_seam_is_swappable(monkeypatch, tmp_path):
    """D10: a CoW-native seeder can replace `FileCopySeeder` untouched.

    `cp -a --reflink=auto` is right for btrfs and merely adequate elsewhere, so
    the indirection is real rather than ceremonial. The signature comparison is
    the load-bearing assertion: `runtime_checkable` `isinstance` only checks
    that a method exists by name, which a strategy taking different arguments
    would also satisfy.
    """
    class RecordingSeeder:
        name = "recording"

        def __init__(self) -> None:
            self.calls: list[tuple[Path, Path]] = []

        def seed_paths(self, src_root, dst_root, *, report=None):
            self.calls.append((Path(src_root), Path(dst_root)))
            report = report if report is not None else seed.SeedReport()
            report.add("everything", seed.COPY, bytes=1, detail="reflinked")
            return report

    monkeypatch.setitem(seed._STRATEGIES, "recording", RecordingSeeder)

    strategy = seed.get_seeder("recording")
    assert isinstance(strategy, seed.SeedStrategy)
    assert _parameters(RecordingSeeder.seed_paths) == _parameters(
        seed.FileCopySeeder.seed_paths
    )
    assert _parameters(seed.SeedStrategy.seed_paths) == _parameters(
        seed.FileCopySeeder.seed_paths
    ), (
        "the Protocol and the implementation disagree about `seed_paths`, so "
        "the seam does not describe what callers actually call"
    )

    report = strategy.seed_paths(tmp_path / "src", tmp_path / "dst")
    assert strategy.calls == [(tmp_path / "src", tmp_path / "dst")]
    assert report.of(seed.COPY)

    default = seed.get_seeder()
    assert isinstance(default, seed.FileCopySeeder)
    assert default.name == seed.DEFAULT_STRATEGY


def test_get_seeder_rejects_an_unknown_strategy():
    with pytest.raises(seed.SeedError) as raised:
        seed.get_seeder("cowmagic")
    message = str(raised.value)
    assert "cowmagic" in message
    assert seed.DEFAULT_STRATEGY in message, (
        "the refusal does not say what IS registered"
    )


# --------------------------------------------------------------- live, read-only


def test_production_gitea_db_snapshots_read_only(tmp_path):
    """The one test that touches production. Read-only by construction.

    It snapshots production's real, live `gitea.db` -- 2.4 MB beside a 4.1 MB
    uncheckpointed WAL -- and asserts the snapshot carries real identity and
    that production's own files are byte-identical afterwards.

    A TRIPWIRE is installed over `sqlite3.connect` before the snapshot runs and
    asserts every connection is a `file:…?mode=ro` URI. That is not belt and
    braces: mutation M2 (open the source `mode=rwc` and
    `PRAGMA wal_checkpoint(TRUNCATE)`) would, without it, CHECKPOINT
    PRODUCTION'S LIVE FORGEJO DATABASE when this test ran. The plan's mutation
    table does not warn about that, and the rule from the 2026-07-29 incident
    is that a mutation which disables a safety property must be unable to reach
    the live thing it protects.

    The `-wal` of a live database can change on its own, so the measurement is
    retried: a `-wal` that differs on every attempt is a mutating seeder, while
    one that differs on some is Forgejo doing its job.
    """
    production = identity.production_root()
    databases = seed.enumerate_sqlite(production / "forgejo")
    assert len(databases) == 1, (
        f"expected exactly one database under production's forgejo tree, "
        f"found {databases}"
    )
    source = databases[0]
    sidecars = [source, Path(str(source) + "-wal")]
    assert source.stat().st_size > 0
    assert Path(str(source) + "-wal").exists(), (
        "vacuous: production's Forgejo database has no WAL, so this test says "
        "nothing about seeding one"
    )

    real_connect = sqlite3.connect
    connections: list[str] = []

    def tripwire(database, *args, **kwargs):
        connections.append(str(database))
        if not (
            isinstance(database, str)
            and database.startswith("file:")
            and "mode=ro" in database
            and kwargs.get("uri") is True
        ):
            raise AssertionError(
                "TRIPWIRE: seeding opened a connection that is not read-only "
                f"while pointed at production: {database!r} kwargs={kwargs!r}. "
                "Production's live Forgejo database was one statement away "
                "from being written to."
            )
        return real_connect(database, *args, **kwargs)

    unchanged = None
    attempts = []
    for attempt in range(3):
        before = {str(p): _sha256(p) for p in sidecars}
        sqlite3.connect = tripwire
        try:
            size = seed.snapshot_sqlite(source, tmp_path / f"snap-{attempt}.db")
        finally:
            sqlite3.connect = real_connect
        after = {str(p): _sha256(p) for p in sidecars}
        changed = sorted(k for k in before if before[k] != after[k])
        attempts.append(changed)
        if not changed:
            unchanged = tmp_path / f"snap-{attempt}.db"
            break

    assert connections, "vacuous: the tripwire never saw a connection"
    assert all("mode=ro" in c for c in connections), connections
    assert unchanged is not None, (
        "production's Forgejo database and/or its `-wal` changed on all three "
        f"attempts: {attempts}. A file that changes every single time a "
        "read-only snapshot is taken is a mutating seeder, not ambient write "
        "load."
    )
    assert size > 0

    assert _integrity(unchanged) == "ok"
    con = sqlite3.connect(f"file:{unchanged}?mode=ro", uri=True)
    try:
        users = {row[0] for row in con.execute("SELECT lower_name FROM user")}
        repos = {row[0] for row in con.execute(
            "SELECT lower_name FROM repository"
        )}
    finally:
        con.close()

    assert users, "the snapshot has no users; it did not capture real identity"
    assert repos, "the snapshot has no repositories"
    assert "obsidura" in users, sorted(users)
    assert identity.declared_project() in repos, sorted(repos)


# ===========================================================================
# Seeding, part 2 (plan Task 6): agent volumes and AFFiNE Postgres
# ===========================================================================
#
# Two classes of test, and the split is deliberate.
#
# The FAST ones replace `seed._docker` -- the module's single docker seam --
# with a double, and assert on the command line that would have been run. That
# is the only way to answer "did it refuse BEFORE doing anything", which is a
# different question from "did it refuse". Task 5 wrote to production while
# proving a guard worked, because its tripwire covered the functions that moved
# bytes and not the one that touched the destination; here EVERY docker call
# goes through one function, so a tripwire over it is total.
#
# The SLOW ones use real volumes and real containers under throwaway `br-`
# projects, because three of this task's claims are claims about Docker and
# Compose rather than about this code: that a `:ro` volume mount really does
# stop the copy writing to its source, that Compose really does ADOPT a
# pre-seeded volume, and that `pg_restore --clean --if-exists` really is
# idempotent. None of those can be established with a double.
#
# What the probes measured, because two of the plan's premises are wrong
# ----------------------------------------------------------------------
# Compose v5.3.1 adopts a pre-existing volume with the right labels, with only
# the project label, and with NO labels at all (warning, then adopts). It never
# "creates a second, empty volume". So `test_seeded_volume_carries_the_labels_
# compose_expects` cannot rest on adoption alone -- adoption is what happens
# anyway -- and it asserts the labels directly, against the label NAMES Compose
# itself writes on a volume it created.
#
# A pre-seeded volume carrying a `config-hash` label that does not match the
# resolved config makes Compose PROMPT ON STDIN, offering to recreate the
# volume and lose the data; with no TTY it hangs indefinitely. That is why
# `compose_volume_labels` writes two labels and not four, and why there is a
# test that says so.


_VOLUME_KEY_PATTERN = re.compile(r"^hermes-(?P<username>.+)-home$")

#: A minimal compose project that declares one named volume, for the adoption
#: probe. Nothing in it matters except the volume declaration.
_ADOPTION_COMPOSE = """\
services:
  holder:
    image: {image}
    command: ["python", "-c", "print('holder')"]
    volumes:
      - {key}:/data
volumes:
  {key}:
"""

#: A throwaway Postgres. The credentials are read from a `.env` beside it, and
#: they are deliberately NOT production's: `container_credentials` derives them
#: from the container's own `working_dir` label, and a fixture that reused
#: production's values would pass whether the derivation worked or not. That is
#: the mistake Chunk 2 shipped in the other direction -- a conformance test
#: that compared against production's identity and went red when a branch was
#: correct.
_POSTGRES_COMPOSE = """\
services:
  postgres:
    image: {image}
    environment:
      POSTGRES_USER: ${{POSTGRES_USER}}
      POSTGRES_PASSWORD: ${{POSTGRES_PASSWORD}}
      POSTGRES_DB: ${{POSTGRES_DB}}
      POSTGRES_HOST_AUTH_METHOD: trust
    healthcheck:
      test: ['CMD', 'pg_isready', '-U', '${{POSTGRES_USER}}', '-d', '${{POSTGRES_DB}}']
      interval: 2s
      timeout: 5s
      retries: 20
"""

BRANCH_PG_USER = "branchuser"
BRANCH_PG_DB = "branchdb"

_VOLUME_REPORT_STUB = {
    "bulk_bytes": 4096,
    "bulk_seconds": 0.01,
    "databases": [{"path": "state.db", "bytes": 8192, "seconds": 0.01,
                   "how": "direct"}],
    "excluded_dirs": [],
    "skipped": {".pid": ["hermes.pid"]},
}


# ------------------------------------------------------- the docker double


class DockerDouble:
    """Stands in for `seed._docker`, recording every invocation.

    Answers only the reads the code under test performs, and answers them from
    data the test supplies. It never reaches a daemon, which is the point: the
    guard tests need to assert that NOTHING happened, and "nothing happened"
    is only checkable if every possible something goes through here.
    """

    def __init__(self, *, volumes=(), labels=None, working_dir=None,
                 container_project=None, container_names=(), explode=False):
        self.calls: list[dict] = []
        self.volumes = set(volumes)
        self.labels = dict(labels or {})
        self.working_dir = working_dir
        self.container_project = container_project
        self.container_names = list(container_names)
        self.explode = explode

    def __call__(self, args, *, stdin=None, binary=False, check=True):
        args = list(args)
        self.calls.append({"args": args, "stdin": stdin, "binary": binary})
        if self.explode:
            raise AssertionError(
                "TRIPWIRE: a docker command was reached even though this call "
                f"must have been refused before any side effect: {args}"
            )
        return self._answer(args, check=check)

    def _answer(self, args, *, check):
        def done(stdout="", code=0):
            return subprocess.CompletedProcess(args, code, stdout, "")

        if args[:2] == ["volume", "inspect"]:
            name = args[2]
            if "--format" in args:
                return done(json.dumps(self.labels.get(name, {})))
            return done("[]" if name in self.volumes else "",
                        0 if name in self.volumes else 1)
        if args[:2] == ["volume", "create"]:
            name = args[-1]
            self.volumes.add(name)
            labels = {}
            for i, token in enumerate(args):
                if token == "--label":
                    key, _, value = args[i + 1].partition("=")
                    labels[key] = value
            self.labels[name] = labels
            return done(name)
        if args[0] == "run":
            return done(seed.VOLUME_REPORT_MARKER
                        + json.dumps(_VOLUME_REPORT_STUB))
        if args[0] == "inspect":
            fmt = args[args.index("--format") + 1]
            if identity.WORKING_DIR_LABEL in fmt:
                return done(f"{self.working_dir}\n")
            if identity.PROJECT_LABEL in fmt:
                return done(f"{self.container_project}\n")
            return done("")
        if args[0] == "ps":
            return done("".join(f"{n}\n" for n in self.container_names))
        if args[0] == "exec":
            return done(b"PGDMP-stub" if binary else "PGDMP-stub")
        raise AssertionError(f"the double does not know how to answer {args}")


@pytest.fixture
def branch_project() -> str:
    """A `br-` project name that needs no daemon.

    The docker-free tests must not pay for `throwaway_branch`, which snapshots
    production and runs a teardown; they never create anything.
    """
    return f"{identity.BRANCH_PROJECT_PREFIX}unit-{os.getpid()}"


# ------------------------------------------------------- naming and derivation


def test_agent_volume_seed_is_project_scoped(monkeypatch, branch_project):
    """Both volume names are derived; neither project prefix is typed.

    The source is `<production project>_hermes-<u>-home`. There are three
    generations of that volume on this daemon -- one per project name the stack
    has carried, plus the unprefixed pre-migration originals -- so a typed
    prefix does not merely look wrong, it copies a DIFFERENT GENERATION of the
    user's identity, and the branch then behaves like an old backup.

    Mutation M1 hardcodes the post-rename prefix. It must fail TODAY, while
    production still carries the other name; that is the whole reason the
    "derive, never type" rule is enforced by a test and not by review.
    """
    production = identity.production_project()
    username = "testuser"
    source = seed.agent_volume_name(production, username)
    destination = seed.agent_volume_name(branch_project, username)

    assert production not in (branch_project, ""), (
        "vacuous: production's project name and the branch's coincide"
    )
    assert source != destination

    double = DockerDouble(volumes={source})
    monkeypatch.setattr(seed, "_docker", double)
    seed.seed_agent_volume(username, production, branch_project)

    runs = [c for c in double.calls if c["args"][0] == "run"]
    assert len(runs) == 1, [c["args"] for c in double.calls]
    mounts = [a for a in runs[0]["args"] if ":/src" in a or ":/dst" in a]
    assert mounts == [f"{source}:/src:ro", f"{destination}:/dst"], mounts

    creates = [c["args"] for c in double.calls
               if c["args"][:2] == ["volume", "create"]]
    assert len(creates) == 1 and creates[0][-1] == destination, creates
    assert production not in " ".join(creates[0]), (
        f"the destination volume was created carrying production's project "
        f"name: {creates[0]}"
    )


def test_the_source_volume_is_mounted_read_only(monkeypatch, branch_project):
    """`:ro` on the source mount is the volume-level `mode=ro`.

    Task 5 made "seeding only ever reads production" a property of the SQLite
    connection. A container that mounts production's agent home read-write has
    no such property: the copy script inside it is one typo from writing to
    production's state, and nothing outside the container can see it happen.

    Kept as its own test rather than folded into the naming one, so that the
    mutation which drops `:ro` reddens something whose name says what was lost.
    """
    production = identity.production_project()
    source = seed.agent_volume_name(production, "testuser")
    double = DockerDouble(volumes={source})
    monkeypatch.setattr(seed, "_docker", double)
    seed.seed_agent_volume("testuser", production, branch_project)

    run = next(c["args"] for c in double.calls if c["args"][0] == "run")
    src_mounts = [a for a in run if a.startswith(f"{source}:")]
    assert src_mounts == [f"{source}:/src:ro"], (
        f"the source volume is not mounted read-only: {src_mounts}"
    )
    assert "--network=none" in run, (
        "the copy container is given a network; it needs none, and a copy of "
        f"production's agent state should not be able to reach one: {run}"
    )


def test_the_seeded_volume_labels_carry_no_config_hash(branch_project):
    """Two labels, and the omission is measured rather than tasteful.

    Compose v5.3.1 writes four labels on a volume it creates: project, volume,
    version and `config-hash`. Replicating the hash is worse than omitting it,
    and this is the one place in the task where getting it wrong does not fail
    loudly. Measured 2026-07-29 with a deliberately wrong hash:

        Volume "x" exists but doesn't match configuration in compose file.
        Recreate (data will be lost)?

    On stdin, and what happens next depends on what stdin is: closed stdin
    reads EOF and is taken as "no" (safe, noisy), an open pipe with nobody
    answering hangs indefinitely, and a human at a terminal who answers the
    obvious way deletes the seed. All three measured 2026-07-29.

    This test is the cheap half of the defence and it runs without a daemon.
    The expensive half belongs to Task 8: invoke Compose with stdin closed, so
    that a hash label arriving from somewhere else cannot stall `branch up`.
    """
    labels = seed.compose_volume_labels(branch_project, "hermes-testuser-home")
    assert set(labels) == {identity.PROJECT_LABEL, identity.VOLUME_LABEL}, (
        f"unexpected label set {sorted(labels)}: a `config-hash` label whose "
        "value does not match the resolved config turns `compose up` into an "
        "interactive prompt offering to delete the volume"
    )
    assert not any("hash" in key for key in labels), sorted(labels)


def test_the_agent_volume_rule_is_derived_from_the_hermes_plan_entry():
    """An agent home IS a Hermes home, so its rule is not written twice.

    Derived with `dataclasses.replace`, so every field except `path` comes from
    the host-side entry. Adding an exclusion there applies to volumes with no
    second edit -- and the failure mode of the two lists disagreeing is silent
    and dangerous: a `.db` grabbed byte-wise arrives without its uncheckpointed
    WAL and looks fine.

    The expectation is asserted twice, from both sides. The derivation
    equality alone would be satisfied by two rules that are both wrong, so the
    fields that matter are also pinned against literals written out here.
    """
    host = seed.plan_entry(seed.AGENT_HOME_PLAN_ENTRY)
    rebuilt = dataclasses.replace(seed.AGENT_VOLUME_RULE,
                                  path=seed.AGENT_HOME_PLAN_ENTRY)
    assert rebuilt == host, (
        "the agent volume rule is no longer the host Hermes rule with a "
        f"different root: {seed.AGENT_VOLUME_RULE} vs {host}"
    )
    assert seed.AGENT_VOLUME_RULE.snapshot_databases is True
    assert seed.AGENT_VOLUME_RULE.exclude_suffixes == (".pid", ".lock", ".sock")
    assert ".db" in seed.AGENT_VOLUME_RULE.bulk_exclude_suffixes
    assert ".db-wal" in seed.AGENT_VOLUME_RULE.bulk_exclude_suffixes


def test_the_agent_volume_key_matches_the_resolved_compose_config():
    """The volume key is checked against what compose actually declares.

    `AGENT_VOLUME_TEMPLATE` is a format string, and a format string that agrees
    with nothing is how a seeded volume ends up beside the one Compose creates
    rather than being adopted as it. The per-developer agent services are
    THEMSELVES generated from `developers.yaml`, so the expectation is derived
    from the resolved configuration -- both directions, so neither a renamed
    template nor a renamed volume can pass.
    """
    from dev_administration.models import parse_developers_yaml

    config = overlay.resolve_config()
    services = config.get("services") or {}
    assert services, "vacuous: the resolved config declares no services"

    developers = parse_developers_yaml(identity.package_root()
                                       / "developers.yaml")
    usernames = sorted(d.username for d in developers)
    assert usernames, "vacuous: developers.yaml declares no developer"

    declared = {
        name: sorted(
            entry["source"] for entry in (spec.get("volumes") or [])
            if entry.get("type") == "volume"
        )
        for name, spec in services.items()
    }

    for username in usernames:
        key = seed.agent_volume_key(username)
        owners = [name for name, sources in declared.items() if key in sources]
        assert len(owners) == 1, (
            f"{key!r} -- the volume this seeder would create for {username!r} "
            f"-- is mounted by {owners}, not by exactly one service. Either "
            "the template drifted from compose.agents.yml or a volume is "
            "shared between agents."
        )

    every_key = sorted({k for sources in declared.values() for k in sources})
    agent_keys = [k for k in every_key if _VOLUME_KEY_PATTERN.match(k)]
    assert agent_keys, (
        f"vacuous: the resolved config declares no volume shaped like an agent "
        f"home; declared volumes are {every_key}"
    )
    for key in agent_keys:
        username = _VOLUME_KEY_PATTERN.match(key)["username"]
        assert username in usernames, (
            f"the resolved config declares agent volume {key!r} for a "
            f"developer who is not in developers.yaml: {username!r}"
        )
        assert seed.agent_volume_key(username) == key


def test_the_volume_payload_ships_this_modules_own_source():
    """The container runs THIS module's snapshot logic, not a copy of it.

    Assembled with `inspect.getsource`, so a change to `snapshot_sqlite`
    reaches the container with no second edit. Asserted on the source text of
    every shipped member and, separately, by compiling the result -- an
    assembled program that does not compile is a payload that fails inside a
    container, where the traceback is much harder to read.

    Note what this test deliberately does NOT claim. "The payload mentions
    VACUUM INTO" would be satisfied by a docstring; Chunk 2 shipped exactly
    that mistake. The behavioural claim is mutation M4's: seeding a volume with
    a plain `cp` for `*.db` must lose the WAL-only rows, and
    `test_agent_volume_databases_are_snapshotted_not_copied` is where that is
    checked, against a real container.
    """
    payload = seed.volume_seed_payload()
    assert seed._PAYLOAD_MEMBERS, "vacuous: the payload ships nothing"
    assert "snapshot_sqlite" in seed._PAYLOAD_MEMBERS
    assert "seed_volume_tree" in seed._PAYLOAD_MEMBERS

    for name in seed._PAYLOAD_MEMBERS:
        source = inspect.getsource(getattr(seed, name))
        assert source in payload, (
            f"the payload does not carry {name}'s own source; it has been "
            "reimplemented or paraphrased, which is the drift this assembly "
            "exists to prevent"
        )

    compile(payload, "<payload>", "exec")
    assert repr(seed.AGENT_VOLUME_RULE) in payload, (
        "the payload does not carry the rule, so the container would prune "
        "different things from the host"
    )
    assert seed.VOLUME_REPORT_MARKER in payload


def _stripped_seed_source() -> str:
    return _strip_docstrings(inspect.getsource(seed))



def _scannable(literals: dict[str, str]) -> dict[str, str]:
    """Drop identities this package's own name makes unscannable.

    Production's Compose project became `aurora` in Chunk 2 -- and this
    package is `aurora_cli`, the host entry point is `aurora`, and the images
    are `aurora-*`. A substring scan for the project name now matches the
    product's own vocabulary (`from aurora_cli import ...`) and can no longer
    tell a hardcoded identity from an import. Both this module and
    `test_crosswire` already recorded that exemption in prose for the PRODUCT
    name; the rename collapsed product and project into one token, so the
    code has to honour what the prose already said.

    The exemption is CONDITIONAL, and that is the point: it cancels itself.
    Rename production to anything that is not a prefix of this package's
    import name and the literal is scanned again, with no edit here. A blanket
    exemption would still be exempting a token nobody remembered in a year.
    """
    package = seed.__name__.split(".")[0]
    return {
        label: value for label, value in literals.items()
        if not package.startswith(value)
    }

def test_the_seed_module_does_not_type_productions_project_name():
    """The scan Task 1 introduced, applied to this module.

    Docstrings are stripped; comments are not, because a comment carrying a
    live identity is the copy-paste source for the next person who wants a
    quick default.

    `declared_project()` is NOT in the banned set here, and the reason is worth
    recording rather than quietly working around: this package's own import
    path contains it, so a scan for it would fire on `from aurora_cli import
    identity` and would be deleted by the first person it annoyed. The
    hardcoded-prefix mutation is caught behaviourally instead, by
    `test_agent_volume_seed_is_project_scoped`.
    """
    banned = _scannable({
        "production's project name": identity.production_project(),
        "the tailnet suffix": identity.tailnet_suffix(),
    })
    for value in banned.values():
        assert isinstance(value, str) and len(value) >= 4, (
            f"derived a degenerate literal {value!r}; the scan would be vacuous"
        )
    assert banned, (
        "every identity was exempted, so this scan checks nothing at all"
    )
    banned = list(banned.values())

    source = _stripped_seed_source()
    assert "seed_agent_volume" in source, (
        "vacuous: the stripped source no longer contains the code under scan"
    )
    offenders = [value for value in banned if value in source]
    assert offenders == [], (
        f"seed.py types production's identity instead of deriving it: "
        f"{offenders}"
    )


def test_the_postgres_functions_do_not_type_the_database_credentials():
    """"Do not type the account name" -- as a gate, scoped to where it applies.

    The bare string is a legitimate REPOSITORY PATH elsewhere in this module
    (two host-path plan entries begin with it), so a module-wide scan would be
    wrong. Scoped to the three functions that handle credentials, it is exact.
    """
    values = identity.production_env()
    secrets = sorted({values.get("POSTGRES_USER", ""),
                      values.get("POSTGRES_DB", "")} - {""})
    assert secrets, "vacuous: production's env declares no Postgres credentials"

    for function in (seed.dump_postgres, seed.restore_postgres,
                     seed.container_credentials):
        source = _strip_docstrings(inspect.getsource(function))
        offenders = [s for s in secrets if s in source]
        assert offenders == [], (
            f"{function.__name__} types {offenders}; the credentials come from "
            "the stack's own env file so that a branch given its own remains "
            "correct"
        )


# ------------------------------------------------------- the guards


def test_agent_volume_seed_refuses_to_write_into_productions_volume(
    monkeypatch
):
    """Production as the destination: refused BEFORE anything happens.

    "It raised eventually" is not the property. `docker volume create` is a
    WRITE: a volume carrying production's project label is adopted by
    production's next `up`, and the branch's copy of an agent home becomes
    production's. Task 5 lost a directory mtime on production for precisely
    this reason -- its tripwire covered the functions that moved bytes and not
    the one that touched the destination.

    So the double raises on ANY docker call, and the test asserts the recorded
    call list is EMPTY. Mutation M2 (drop the destination guard) then fails
    with the tripwire's message instead of reaching the daemon.
    """
    production = identity.production_project()
    double = DockerDouble(explode=True)
    monkeypatch.setattr(seed, "_docker", double)

    with pytest.raises(seed.SeedError) as raised:
        seed.seed_agent_volume("testuser", production, production)

    assert double.calls == [], (
        f"the refusal came AFTER {len(double.calls)} docker invocation(s): "
        f"{[c['args'] for c in double.calls]}"
    )
    message = str(raised.value)
    assert identity.BRANCH_PROJECT_PREFIX in message
    assert "destination project" in message
    assert "reading the volume it is writing" not in message, (
        "the same-project guard answered a question about production; the two "
        "conditions overlap here and the wordings must discriminate"
    )


def test_the_agent_volume_guards_each_refuse_on_their_own(monkeypatch,
                                                          branch_project):
    """Three guards, three wordings, and a control that they are not blanket.

    `assert_agent_volume_seedable` raises one exception type from several
    checks whose inputs overlap -- production's name is BOTH "not a branch" and
    (on a real call) "the source". A bare `pytest.raises(SeedError)` therefore
    proves nothing about which guard held, which is Task 1's finding and the
    reason each case below asserts the other wordings are ABSENT.

    The control matters as much: without it, a function that raised
    unconditionally would satisfy every `raises` case in this test.
    """
    production = identity.production_project()
    double = DockerDouble(explode=True)
    monkeypatch.setattr(seed, "_docker", double)

    cases = {
        "destination project": (("testuser", production, production),),
        "reading the volume it is writing": (
            ("testuser", branch_project, branch_project),
        ),
        "developer username": (("", production, branch_project),),
        "source project must be": (("testuser", "", branch_project),),
    }
    for expected, (args,) in cases.items():
        with pytest.raises(seed.SeedError) as raised:
            seed.assert_agent_volume_seedable(*args)
        message = str(raised.value)
        assert expected in message, (
            f"{args} raised the wrong guard: {message}"
        )
        for other in cases:
            if other != expected:
                assert other not in message, (
                    f"{args} raised a message matching two guards ({expected} "
                    f"and {other}): {message}"
                )

    # Control: a legitimate triple passes, so the cases above are about their
    # own conditions and not about the function refusing everything.
    seed.assert_agent_volume_seedable("testuser", production, branch_project)
    assert double.calls == [], "a pure guard reached the daemon"


def test_the_pg_restore_guard_refuses_everything_outside_the_branch_namespace(
    monkeypatch
):
    """`pg_restore --clean` DROPS. Its guard is pure and it is checked as such.

    This is the most destructive call in the package and the plan's required
    surface contains no guard for it at all. `ops/docker-guard` does not help:
    it treats `compose down`, `rm`, `volume rm` and friends as destructive and
    `docker exec` as harmless, which for `pg_restore --clean` it is not.

    Production's own Postgres container name is derived, not typed, so this
    keeps meaning the same thing after the rename.
    """
    production_container = seed.production_postgres_container()
    assert not production_container.startswith(
        identity.BRANCH_PROJECT_PREFIX
    ), (
        f"vacuous: production's Postgres container {production_container!r} is "
        "already in the branch namespace, so refusing it proves nothing"
    )

    double = DockerDouble(explode=True)
    monkeypatch.setattr(seed, "_docker", double)
    dump = seed.PG_DUMP_MAGIC + b"-stub"

    for container in (production_container, "", "br-", "postgres", None):
        with pytest.raises(seed.SeedError) as raised:
            seed.restore_postgres(container, dump)
        assert "pg_restore target" in str(raised.value), str(raised.value)

    assert double.calls == [], (
        "the restore guard let a docker command through: "
        f"{[c['args'] for c in double.calls]}"
    )


def test_the_second_pg_restore_gate_holds_with_the_first_one_disabled(
    monkeypatch
):
    """The label gate, proven independent -- without running `pg_restore`.

    Two gates exist because one of them is a single line away from being
    weakened and what is behind it is irreversible. Proving the second one
    holds means disabling the first, which is exactly the shape that destroyed
    production on 2026-07-29: a test that verifies a guard by making the
    dangerous call.

    So the double answers the `docker inspect` the label gate needs and RAISES
    on `exec`, which is the only verb that can restore anything. The dangerous
    call is unreachable by construction, not by the guard under test.
    """
    class InspectOnly(DockerDouble):
        def __call__(self, args, *, stdin=None, binary=False, check=True):
            if list(args)[:1] == ["exec"]:
                raise AssertionError(
                    "TRIPWIRE: `docker exec` was reached with the first "
                    f"pg_restore gate disabled: {list(args)}"
                )
            return super().__call__(args, stdin=stdin, binary=binary,
                                    check=check)

    double = InspectOnly(container_project=identity.production_project())
    monkeypatch.setattr(seed, "_docker", double)
    monkeypatch.setattr(seed, "assert_branch_container",
                        lambda container, what: None)

    with pytest.raises(seed.SeedError) as raised:
        seed.restore_postgres("looks-like-anything",
                              seed.PG_DUMP_MAGIC + b"-stub")
    message = str(raised.value)
    assert "HARD GUARD" in message, message
    assert identity.PROJECT_LABEL in message
    assert not any(c["args"][0] == "exec" for c in double.calls), (
        f"{[c['args'] for c in double.calls]}"
    )
    assert any(c["args"][0] == "inspect" for c in double.calls), (
        "vacuous: the label gate never asked the daemon anything, so it cannot "
        "have been what refused"
    )


def test_restore_refuses_something_that_is_not_a_dump(monkeypatch):
    """A restore of the wrong bytes is a `--clean` with nothing to put back."""
    double = DockerDouble(container_project="br-somewhere")
    monkeypatch.setattr(seed, "_docker", double)
    for payload in (b"", b"not a dump", "PGDMP as text"):
        with pytest.raises(seed.SeedError) as raised:
            seed.restore_postgres("br-x-postgres-1", payload)
        assert "custom-format" in str(raised.value)
    assert not any(c["args"][0] == "exec" for c in double.calls)


# ------------------------------------------------------- missing source volume


def test_a_missing_source_volume_is_a_hard_error(monkeypatch, branch_project):
    """No source volume means no seed -- not an empty one.

    Not hypothetical on this host: the agent home volumes for production's
    CURRENT project name do not exist. The three per-developer volumes were
    destroyed in the 2026-07-29 incident and never recreated, because the
    unprefixed pre-migration generation survived and made the loss recoverable.
    An earlier generation is a ROLLBACK COPY, not this stack's state, so
    falling back to it would silently seed a branch from a backup.

    Creating the destination volume anyway is the worst option available:
    Compose adopts an empty volume in silence, the branch's agent starts with
    no identity, and the symptom arrives days later as "my login does not work
    in the branch" -- the failure spec 6.3 exists to prevent.
    """
    production = identity.production_project()
    source = seed.agent_volume_name(production, "testuser")
    destination = seed.agent_volume_name(branch_project, "testuser")

    double = DockerDouble(volumes=set())
    monkeypatch.setattr(seed, "_docker", double)
    with pytest.raises(seed.SeedError) as raised:
        seed.seed_agent_volume("testuser", production, branch_project)

    message = str(raised.value)
    assert source in message
    assert "ROLLBACK" in message.upper()
    assert not any(c["args"][:2] == ["volume", "create"] for c in double.calls), (
        "a destination volume was created for a seed that cannot happen; "
        "Compose would adopt it empty"
    )
    assert destination not in double.volumes


def test_an_existing_destination_volume_is_a_hard_error(monkeypatch,
                                                       branch_project):
    """Filling a volume that is already there merges two generations."""
    production = identity.production_project()
    source = seed.agent_volume_name(production, "testuser")
    destination = seed.agent_volume_name(branch_project, "testuser")
    double = DockerDouble(volumes={source, destination})
    monkeypatch.setattr(seed, "_docker", double)

    with pytest.raises(seed.SeedError) as raised:
        seed.seed_agent_volume("testuser", production, branch_project)
    assert destination in str(raised.value)
    assert "already exists" in str(raised.value)
    assert not any(c["args"][0] == "run" for c in double.calls)


# ------------------------------------------------------- credentials


def test_container_credentials_come_from_that_stacks_own_env_file(monkeypatch,
                                                                 tmp_path):
    """The branch's Postgres credentials come from the BRANCH's `.env`.

    Derived from the container's own `working_dir` label, so one code path
    serves production and every branch. The fixture's values are deliberately
    not production's: if this read production's file instead, the values would
    still match today (Task 2 renders one from the other) and the test would
    pass while the derivation was broken.
    """
    (tmp_path / ".env").write_text(
        f"POSTGRES_USER={BRANCH_PG_USER}\n"
        f"POSTGRES_PASSWORD={BRANCH_PG_USER}\n"
        f"POSTGRES_DB={BRANCH_PG_DB}\n"
    )
    production_values = identity.production_env()
    assert production_values.get("POSTGRES_USER") != BRANCH_PG_USER, (
        "vacuous: the fixture reuses production's credentials, so reading the "
        "wrong file would look correct"
    )

    double = DockerDouble(working_dir=str(tmp_path))
    monkeypatch.setattr(seed, "_docker", double)
    assert seed.container_credentials("br-x-postgres-1") == (
        BRANCH_PG_USER, BRANCH_PG_DB
    )

    (tmp_path / ".env").write_text("POSTGRES_USER=only-the-user\n")
    with pytest.raises(seed.SeedError) as raised:
        seed.container_credentials("br-x-postgres-1")
    assert "POSTGRES_DB" in str(raised.value)


def test_postgres_service_is_derived_and_unique():
    """The Postgres service comes from the resolved config, not from a name.

    It lives in a vendored compose file this repository includes rather than
    owns, so its service key, its container name and its database name are all
    somebody else's to change.
    """
    config = overlay.resolve_config()
    services = config.get("services") or {}
    assert len(services) > 1, "vacuous: too few services to choose between"

    service = seed.postgres_service()
    assert service in services
    environment = services[service].get("environment") or {}
    assert "POSTGRES_DB" in environment and "POSTGRES_USER" in environment

    others = [
        name for name, spec in services.items()
        if name != service and "POSTGRES_DB" in (spec.get("environment") or {})
    ]
    assert others == [], (
        f"more than one service declares POSTGRES_DB ({[service, *others]}); "
        "the derivation would be a guess"
    )


def test_dump_postgres_defaults_to_productions_container(monkeypatch):
    """With no argument, the dump comes from production. Nothing else.

    Mutation M6 points it at a branch instead. That must fail, and the reason
    it fails matters: an empty or absent instance yields no bytes, and an empty
    dump restored with `--clean --if-exists` DELETES the branch's data rather
    than merely failing to add any.
    """
    production_container = seed.production_postgres_container()
    values = identity.production_env()

    double = DockerDouble(working_dir=str(identity.production_root()))
    real = seed._docker

    def recording(args, **kwargs):
        double.calls.append({"args": list(args), **kwargs})
        if list(args)[0] == "exec":
            return subprocess.CompletedProcess(
                list(args), 0, seed.PG_DUMP_MAGIC + b"-stub", b"")
        return real(args, **kwargs)

    monkeypatch.setattr(seed, "_docker", recording)
    seed.dump_postgres()

    execs = [c["args"] for c in double.calls if c["args"][0] == "exec"]
    assert len(execs) == 1, execs
    assert execs[0][1] == production_container, execs
    assert "pg_dump" in execs[0]
    assert values["POSTGRES_USER"] in execs[0]
    assert values["POSTGRES_DB"] in execs[0]
    assert "-Fc" in execs[0], (
        "the dump is not in custom format, so `pg_restore --clean --if-exists` "
        f"cannot read it: {execs[0]}"
    )


def test_dump_postgres_refuses_a_dump_with_no_content(monkeypatch):
    """The silent failure this whole function exists to avoid.

    Two conditions and two DISTINCT messages, asserted separately. The magic
    check alone would reject an empty dump as well -- `b""` does not start with
    `PGDMP` -- so a test that only asserted `SeedError` would let the emptiness
    check be deleted without noticing. Found exactly that way, by a mutation
    that survived. The two cases also mean different things to whoever reads
    the failure: "nothing came back at all" is the wrong-container shape
    mutation M6 produces, while "the wrong bytes came back" is a corrupt or
    non-custom-format archive.
    """
    expectations = {
        b"": "restores as a deletion",
        b"not an archive": "custom-format magic",
    }
    for stdout, expected in expectations.items():
        def recording(args, __stdout=stdout, **kwargs):
            if list(args)[0] == "exec":
                return subprocess.CompletedProcess(list(args), 0, __stdout, b"")
            return subprocess.CompletedProcess(list(args), 0, "x", "")
        monkeypatch.setattr(seed, "_docker", recording)
        with pytest.raises(seed.SeedError) as raised:
            seed.dump_postgres("br-x-postgres-1", user="u", database="d")
        message = str(raised.value)
        assert expected in message, (stdout, message)
        for other in expectations.values():
            if other != expected:
                assert other not in message, (stdout, message)


# ------------------------------------------------------- the snapshot fallback


def test_snapshot_via_copy_carries_the_wal_only_rows(tmp_path):
    """The fallback for a database that cannot be opened where it lies.

    Measured on this host, and it is why the fallback exists at all:

        source volume mounted `:ro`, `-shm` PRESENT -> mode=ro VACUUM INTO ok
        source volume mounted `:ro`, `-shm` ABSENT  -> "unable to open
                                                        database file"

    `mode=ro` forbids writes to the DATABASE, not to the `-shm`: SQLite still
    mmaps a WAL index to register a read mark, and on a read-only mount it
    cannot create one. The plan's own volume test specifies a database with an
    uncheckpointed WAL and no `-shm`, i.e. exactly the shape that cannot be
    read in place -- so without this path, the read-only source mount and the
    plan's test are mutually exclusive.

    A 0o500 directory does NOT reproduce the failure (EACCES and EROFS are not
    handled alike), which is recorded so nobody "simplifies" the real container
    test into a chmod.
    """
    source = tmp_path / "src" / "state.db"
    holder = _make_wal_db(source, initial=30, wal_only=12)
    try:
        Path(str(source) + "-shm").unlink()
        assert Path(str(source) + "-wal").stat().st_size > 0, (
            "vacuous: there is no WAL, so a byte copy would be correct"
        )
        out = tmp_path / "out"
        out.mkdir()
        size = seed.snapshot_sqlite_via_copy(source, out / "state.db", out)
        assert size > 0
        assert _integrity(out / "state.db") == "ok"
        assert _row_count(out / "state.db") == 42, (
            "the fallback lost the rows that live only in the WAL"
        )
        assert sorted(p.name for p in out.iterdir()) == ["state.db"], (
            "the fallback left its scratch copy inside the branch's volume"
        )
    finally:
        holder.close()


def test_snapshot_via_copy_does_not_mutate_the_source(tmp_path):
    """The fallback copies OUT of the source and writes only to the destination."""
    source = tmp_path / "src" / "state.db"
    holder = _make_wal_db(source, initial=20, wal_only=8)
    try:
        Path(str(source) + "-shm").unlink()
        watched = [source, Path(str(source) + "-wal")]
        before = {str(p): _sha256(p) for p in watched}
        assert all(before.values()), before
        out = tmp_path / "out"
        out.mkdir()
        seed.snapshot_sqlite_via_copy(source, out / "state.db", out)
        after = {str(p): _sha256(p) for p in watched}
        assert before == after, (
            f"the fallback mutated its source: "
            f"{[k for k in before if before[k] != after[k]]}"
        )
    finally:
        holder.close()


def test_seed_volume_tree_snapshots_and_prunes(tmp_path):
    """The whole volume copy, on the host, with no container in the way.

    The container test below is the one that proves the mount semantics; this
    one is fast enough to run on every change and pins the pruning and the
    snapshotting together. `_copy_tree_pruned` exists because `_copy_pruned`'s
    fast path is `cp -a <src> <dst.parent>`, which requires source and
    destination to share a basename -- true for every host-path plan entry and
    false for two volume mount points.
    """
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    holders = [
        _make_wal_db(src / "state.db", initial=15, wal_only=5),
        _make_wal_db(src / "cron" / "executions.db", initial=4, wal_only=3),
    ]
    try:
        (src / "memories").mkdir(parents=True, exist_ok=True)
        (src / "memories" / "MEMORY.md").write_text("# memory\n")
        (src / "hermes.pid").write_text("1\n")
        (src / "cron" / ".tick.lock").write_text("")
        (src / "broken").symlink_to(BROKEN_LINK_TARGET)

        summary = seed.seed_volume_tree(src, dst)

        assert sorted(d["path"] for d in summary["databases"]) == [
            "cron/executions.db", "state.db",
        ]
        assert _row_count(dst / "state.db") == 20
        assert _row_count(dst / "cron" / "executions.db") == 7
        assert _integrity(dst / "state.db") == "ok"
        assert (dst / "memories" / "MEMORY.md").is_file()
        assert (dst / "broken").is_symlink()
        assert os.readlink(dst / "broken") == BROKEN_LINK_TARGET
        for pruned in ("hermes.pid", "cron/.tick.lock", "state.db-wal",
                       "state.db-shm"):
            assert not (dst / pruned).exists(), f"{pruned} was copied"
        assert summary["skipped"], "vacuous: nothing was pruned"
    finally:
        for holder in holders:
            holder.close()


# ------------------------------------------------------- real docker


def _volume_script(volume: str, script: str, *, readonly: bool = False) -> str:
    mount = f"{volume}:/dst" + (":ro" if readonly else "")
    proc = subprocess.run(
        ["docker", "run", "--rm", "-i", "--network=none", "-v", mount,
         seed.VOLUME_SEED_IMAGE, "python", "-"],
        input=script, capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, (
        f"helper container failed: {proc.returncode}\n{proc.stderr}"
    )
    return proc.stdout


_BUILD_AGENT_HOME = r'''
import os, pathlib, sqlite3
p = pathlib.Path("/dst")
(p / "memories").mkdir(parents=True, exist_ok=True)
(p / "memories" / "MEMORY.md").write_text("# memory\n- a fact\n")
(p / "hermes.pid").write_text("999\n")
(p / "broken").symlink_to("/opt/data/home/.cache/uv/archive-v0/deadbeef")
(p / "cron").mkdir(exist_ok=True)

def wal(path, initial, wal_only):
    con = sqlite3.connect(path)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, payload TEXT)")
    con.executemany("INSERT INTO t (payload) VALUES (?)",
                    [("initial-%d" % i,) for i in range(initial)])
    con.commit()
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    con.execute("PRAGMA wal_autocheckpoint=0")
    con.executemany("INSERT INTO t (payload) VALUES (?)",
                    [("wal-only-%d" % i,) for i in range(wal_only)])
    con.commit()

wal(p / "state.db", 100, 40)
wal(p / "cron" / "executions.db", 5, 3)
# Leave state.db with NO -shm: the shape the plan's test specifies, and the one
# that cannot be opened on a read-only mount. cron/executions.db keeps its -shm,
# so a single fixture exercises BOTH snapshot paths.
os._exit(0)
'''

_DROP_SHM = r'''
import pathlib
pathlib.Path("/dst/state.db-shm").unlink()
print(sorted(p.name for p in pathlib.Path("/dst").iterdir()))
'''

_FINGERPRINT = r'''
import hashlib, json, os, pathlib
d = pathlib.Path("/dst")
out = {}
for p in sorted(d.rglob("*")):
    rel = str(p.relative_to(d))
    if p.is_symlink():
        out[rel] = "link:" + os.readlink(p)
    elif p.is_file():
        out[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    else:
        out[rel] = "dir"
print("FP " + json.dumps(out))
'''

_READ_DATABASES = r'''
import json, os, pathlib, sqlite3
d = pathlib.Path("/dst")
out = {"files": sorted(str(p.relative_to(d)) for p in d.rglob("*"))}
for name in ("state.db", "cron/executions.db"):
    path = d / name
    if not path.exists():
        out[name] = None
        continue
    con = sqlite3.connect("file:%s?mode=ro" % path, uri=True)
    out[name] = {
        "rows": con.execute("SELECT count(*) FROM t").fetchone()[0],
        "wal_only": con.execute(
            "SELECT count(*) FROM t WHERE payload LIKE 'wal-only-%'"
        ).fetchone()[0],
        "integrity": con.execute("PRAGMA integrity_check").fetchone()[0],
    }
    con.close()
out["marker"] = (d / "MARKER").read_text() if (d / "MARKER").exists() else None
print("DB " + json.dumps(out))
'''

_WRITE_MARKER = r'''
import pathlib
pathlib.Path("/dst/MARKER").write_text("seeded")
print("marker written")
'''


# The DESTINATION is read through a WRITABLE mount, and that is not laziness.
# A vacuumed snapshot has no WAL and opens read-only anywhere; a BYTE COPY of a
# WAL database whose sidecars were pruned cannot be opened on a read-only mount
# at all. Reading the destination :ro therefore turns mutation M4 into
# "the helper container crashed" instead of "the WAL-only rows are missing",
# which is a red for the right cause reported as the wrong one -- and a test
# whose failure message does not name the property is a test nobody trusts.


def _tagged(stdout: str, tag: str) -> dict:
    for line in stdout.splitlines():
        if line.startswith(tag + " "):
            return json.loads(line[len(tag) + 1:])
    raise AssertionError(f"no {tag!r} line in helper output:\n{stdout}")


def _seeded_agent_home(source_project: str, destination_project: str,
                       username: str = "testuser"):
    """A source agent volume filled with production's awkward shapes, seeded."""
    source = seed.agent_volume_name(source_project, username)
    subprocess.run(
        ["docker", "volume", "create", "--label",
         f"{identity.PROJECT_LABEL}={source_project}", source],
        capture_output=True, text=True, check=True,
    )
    _volume_script(source, _BUILD_AGENT_HOME)
    _volume_script(source, _DROP_SHM)
    before = _tagged(_volume_script(source, _FINGERPRINT, readonly=True), "FP")
    report = seed.seed_agent_volume(username, source_project,
                                   destination_project)
    after = _tagged(_volume_script(source, _FINGERPRINT, readonly=True), "FP")
    return source, report, before, after


def test_agent_volume_databases_are_snapshotted_not_copied(throwaway_branches):
    """A real copy, through a real container, with the source mounted `:ro`.

    Mutation M4 replaces the snapshot with a plain `cp` for `*.db`. `state.db`
    here has 40 rows that exist ONLY in its uncheckpointed WAL and no `-shm`,
    exactly as production's Forgejo database does today, so a byte copy of the
    main file cannot contain them -- deterministically, not as a race.

    The same fixture exercises both snapshot paths, which is what stops the
    fallback from being an untested branch: `state.db` has no `-shm` and must
    go via a scratch copy, `cron/executions.db` has one and must be read
    directly off the read-only mount.

    It also asserts the SOURCE volume is unchanged, which is the volume-level
    form of Task 5's no-mutation invariant. `-shm` is excluded for finding N6's
    reason -- a read-only `VACUUM INTO` may legitimately rewrite it.
    """
    source_project = throwaway_branches()
    destination_project = throwaway_branches()
    source, report, before, after = _seeded_agent_home(source_project,
                                                       destination_project)
    destination = seed.agent_volume_name(destination_project, "testuser")

    data = _tagged(_volume_script(destination, _READ_DATABASES),
                   "DB")
    assert data["state.db"] is not None, data["files"]
    assert data["state.db"]["integrity"] == "ok"
    assert data["state.db"]["rows"] == 140, data["state.db"]
    assert data["state.db"]["wal_only"] == 40, (
        "the destination lost the rows that live only in the source's WAL: "
        f"{data['state.db']}"
    )
    assert data["cron/executions.db"]["rows"] == 8
    assert data["cron/executions.db"]["wal_only"] == 3

    paths = {a.path.split(":", 1)[-1]: a for a in report.of(seed.SNAPSHOT)}
    assert set(paths) == {"state.db", "cron/executions.db"}, sorted(paths)
    assert "scratch copy" in paths["state.db"].detail, (
        "state.db has no `-shm` and cannot be opened on a read-only mount, so "
        f"it must have been snapshotted via a copy: {paths['state.db'].detail}"
    )
    assert "scratch copy" not in paths["cron/executions.db"].detail, (
        "cron/executions.db has an `-shm` and must be read directly off the "
        "read-only mount; if this went via a copy, the direct path is dead "
        "code and nothing tests it"
    )

    assert not any(f in data["files"] for f in
                   ("hermes.pid", "state.db-wal", "state.db-shm",
                    "cron/.tick.lock")), data["files"]
    assert "memories/MEMORY.md" in data["files"]
    assert data["files"], "vacuous: the destination volume is empty"

    volatile = tuple(PROD_VOLATILE_SUFFIXES)
    compared = {k: v for k, v in before.items() if not k.endswith(volatile)}
    assert any(k.endswith(".db") for k in compared), (
        "vacuous: the compared set contains no database"
    )
    assert any(k.endswith("-wal") for k in compared), (
        "vacuous: the compared set contains no WAL, so a seeder that "
        "checkpointed its source would go unnoticed"
    )
    changed = sorted(
        k for k in compared
        if compared[k] != after.get(k)
    )
    assert changed == [], (
        f"seeding mutated its SOURCE volume, which on a real call is "
        f"production's agent home: {changed}"
    )


def test_seeded_volume_carries_the_labels_compose_expects(throwaway_branches,
                                                          tmp_path):
    """The labels, and then adoption -- because adoption alone proves nothing.

    Measured on Compose v5.3.1, 2026-07-29: a pre-existing volume is adopted
    with the right labels, with only the project label, and with NO labels at
    all (it warns and adopts). Compose never creates a second, empty volume, so
    "the marker file survived" is true however the volume was labelled, and
    mutation M3 -- omit `com.docker.compose.volume` -- would SURVIVE a test
    that checked adoption alone. The plan describes the failure mode
    incorrectly, and this is where that costs something.

    So the labels are asserted directly, and the two label NAMES are derived
    from a volume COMPOSE ITSELF created rather than from this package's
    constants: that is what makes them facts about Compose. Adoption is then
    checked as its own property, along with the absence of the warning that
    marks an unlabelled volume and the absence of a second volume.
    """
    seeded_project = throwaway_branches()
    source_project = throwaway_branches()
    compose_project = throwaway_branches()
    key = seed.agent_volume_key("testuser")

    # What Compose writes on a volume it creates itself.
    workdir = tmp_path / "adopt"
    workdir.mkdir()
    (workdir / "compose.yml").write_text(
        _ADOPTION_COMPOSE.format(image=seed.VOLUME_SEED_IMAGE, key=key)
    )
    subprocess.run(
        ["docker", "compose", "-p", compose_project, "create"],
        cwd=workdir, capture_output=True, text=True, check=True,
        # DEVNULL and a timeout, together, because a volume carrying a stale
        # config-hash label makes Compose PROMPT on stdin and a prompt with no
        # answer is an indefinite hang -- a suite that hangs is worse than one
        # that fails.
        stdin=subprocess.DEVNULL, timeout=180,
    )
    compose_own = seed.volume_labels(
        seed.compose_volume_name(compose_project, key)
    )
    assert identity.PROJECT_LABEL in compose_own, compose_own
    assert identity.VOLUME_LABEL in compose_own, (
        f"Compose no longer labels its own volumes with "
        f"{identity.VOLUME_LABEL!r}; the adoption contract has changed: "
        f"{compose_own}"
    )
    assert compose_own[identity.VOLUME_LABEL] == key

    _seeded_agent_home(source_project, seeded_project)
    destination = seed.compose_volume_name(seeded_project, key)
    labels = seed.volume_labels(destination)
    assert labels.get(identity.PROJECT_LABEL) == seeded_project, labels
    assert labels.get(identity.VOLUME_LABEL) == key, (
        f"the seeded volume is missing the label Compose writes to recognise "
        f"its own: {labels}"
    )
    assert not any("hash" in name for name in labels), (
        f"a config-hash label makes `compose up` prompt to delete the volume: "
        f"{labels}"
    )

    _volume_script(destination, _WRITE_MARKER)
    proc = subprocess.run(
        ["docker", "compose", "-p", seeded_project, "create"],
        cwd=workdir, capture_output=True, text=True, check=True,
        # DEVNULL and a timeout, together, because a volume carrying a stale
        # config-hash label makes Compose PROMPT on stdin and a prompt with no
        # answer is an indefinite hang -- a suite that hangs is worse than one
        # that fails.
        stdin=subprocess.DEVNULL, timeout=180,
    )
    combined = proc.stdout + proc.stderr
    assert "was not created by Docker Compose" not in combined, combined
    assert "Recreate" not in combined, (
        f"Compose asked whether to recreate the volume: {combined}"
    )

    named = [
        line.strip() for line in subprocess.run(
            ["docker", "volume", "ls", "-q", "--filter",
             f"label={identity.PROJECT_LABEL}={seeded_project}"],
            capture_output=True, text=True, check=True,
        ).stdout.splitlines() if line.strip()
    ]
    assert named == [destination], (
        f"Compose did not adopt the seeded volume; volumes for "
        f"{seeded_project} are {named}"
    )
    data = _tagged(_volume_script(destination, _READ_DATABASES),
                   "DB")
    assert data["marker"] == "seeded", (
        "the marker written before `compose create` is gone, so the volume was "
        "replaced rather than adopted"
    )
    assert data["state.db"]["rows"] == 140, (
        "the seeded data did not survive adoption"
    )


@pytest.fixture
def branch_postgres(throwaway_branch, tmp_path):
    """A running, healthy Postgres under a throwaway `br-` project.

    Its credentials are deliberately NOT production's, so every derivation that
    claims to read the BRANCH's `.env` is actually exercised.
    """
    workdir = tmp_path / "postgres"
    workdir.mkdir()
    config = overlay.resolve_config()
    image = (config["services"][seed.postgres_service()])["image"]
    (workdir / "compose.yml").write_text(_POSTGRES_COMPOSE.format(image=image))
    (workdir / ".env").write_text(
        f"POSTGRES_USER={BRANCH_PG_USER}\n"
        f"POSTGRES_PASSWORD={BRANCH_PG_USER}\n"
        f"POSTGRES_DB={BRANCH_PG_DB}\n"
    )
    proc = subprocess.run(
        ["docker", "compose", "-p", throwaway_branch, "up", "-d", "--wait"],
        cwd=workdir, capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, (
        f"the throwaway Postgres did not become healthy: {proc.stderr}"
    )
    try:
        yield seed.postgres_container(throwaway_branch)
    finally:
        subprocess.run(
            ["docker", "compose", "-p", throwaway_branch, "down", "-v",
             "--remove-orphans"],
            cwd=workdir, capture_output=True, text=True, check=False,
        )


def _psql(container: str, sql: str, *, user=BRANCH_PG_USER,
          database=BRANCH_PG_DB) -> str:
    proc = subprocess.run(
        ["docker", "exec", container, "psql", "-U", user, "-d", database,
         "-tAc", sql],
        capture_output=True, text=True, check=True,
    )
    return proc.stdout.strip()


def test_postgres_restore_is_idempotent(branch_postgres):
    """Restore twice; the second time is a no-op, not a pile of collisions.

    `--clean --if-exists` is what makes that true, and it is not decoration:
    decision D-E restores AFTER the branch's stack is up, precisely so the
    restore runs against whatever schema the migration job has already created.

    Mutation M5 removes those flags. Measured on this host, that makes
    `pg_restore` exit 1 AND print `errors ignored on restore` -- so the check
    in `restore_postgres` looks for both, because `pg_restore` continues past
    errors and exits 0 in other configurations, and "it did not crash" is how
    M5 would survive.
    """
    _psql(branch_postgres,
          "CREATE TABLE thing (id serial primary key, name text); "
          "INSERT INTO thing (name) SELECT 'row-' || g "
          "FROM generate_series(1, 37) g;")
    assert _psql(branch_postgres, "SELECT count(*) FROM thing") == "37"

    dump = seed.dump_postgres(branch_postgres)
    assert dump.startswith(seed.PG_DUMP_MAGIC)

    counts = []
    for _ in range(2):
        report = seed.restore_postgres(branch_postgres, dump)
        counts.append(_psql(branch_postgres, "SELECT count(*) FROM thing"))
    assert counts == ["37", "37"], counts
    assert report.of(seed.RESTORE), "the restore recorded no action"

    derived = seed.container_credentials(branch_postgres)
    assert derived == (BRANCH_PG_USER, BRANCH_PG_DB), (
        f"the credentials did not come from the branch's own .env: {derived}"
    )


def test_the_restore_does_not_depend_on_the_role_names_matching(
    branch_postgres
):
    """Production's real dump, restored into a branch with a different role.

    Measured, 2026-07-29: without `--no-owner` this produces
    `role "<production's user>" does not exist` 101 times, `pg_restore` exits 1
    and the restore is reported as failed -- with 84 tables nonetheless
    created, i.e. a half-restored database and an error.

    Task 2 renders the branch's `.env` from production's, so the roles match
    today and the flag is inert. It is here so that they are not REQUIRED to
    match: giving a branch its own database password is an obvious future
    hardening, and this is the coupling that would break silently when
    somebody does it.

    Doubles as the only end-to-end proof that production's AFFiNE dump
    restores at all.
    """
    dump = seed.dump_postgres()
    assert len(dump) > 50_000, (
        f"production's AFFiNE dump is only {len(dump)} bytes; that is not a "
        "real schema and this test would prove nothing"
    )
    production_user = identity.production_env()["POSTGRES_USER"]
    assert production_user != BRANCH_PG_USER, (
        "vacuous: the branch fixture reuses production's role name, so a "
        "restore that depended on them matching would still pass"
    )

    seed.restore_postgres(branch_postgres, dump)
    tables = _psql(
        branch_postgres,
        "SELECT count(*) FROM information_schema.tables "
        "WHERE table_schema='public'",
    )
    assert int(tables) > 10, (
        f"production's dump restored only {tables} public tables"
    )
    seed.restore_postgres(branch_postgres, dump)
    assert _psql(
        branch_postgres,
        "SELECT count(*) FROM information_schema.tables "
        "WHERE table_schema='public'",
    ) == tables


def test_postgres_dump_is_read_only():
    """The second test that touches production, and it only reads.

    `pg_dump` takes no exclusive lock and writes nothing; the assertion is that
    production's Postgres container is the SAME container, still started at the
    same instant, and that the whole production stack is untouched.

    The content assertions are what make mutation M6 -- dump the branch's
    Postgres instead of production's -- fail rather than pass quietly. An
    absent container yields an error, but an EMPTY one yields a valid, tiny
    archive with the right magic bytes, which is why the size floor is here
    too. An empty dump restored with `--clean --if-exists` deletes rather than
    fails.
    """
    container = seed.production_postgres_container()
    before = production_snapshot()
    detail = conftest.inspect_container(container)
    identifier, started = detail["Id"], detail["State"]["StartedAt"]
    assert identifier and started

    dump = seed.dump_postgres()

    after = conftest.inspect_container(container)
    assert after["Id"] == identifier, "production's Postgres was RECREATED"
    assert after["State"]["StartedAt"] == started, (
        "production's Postgres was RESTARTED by a read-only dump"
    )
    assert after["State"]["Running"] is True
    assert_production_unchanged(before)

    assert dump, "the dump is empty"
    assert dump.startswith(seed.PG_DUMP_MAGIC), (
        f"the dump does not begin with the custom-format magic: {dump[:16]!r}"
    )
    assert len(dump) > 50_000, (
        f"the dump is {len(dump)} bytes. Production's AFFiNE schema measured "
        "256182 bytes on 2026-07-29; an archive this small is an empty "
        "database, i.e. the wrong instance was dumped"
    )


def test_a_restore_that_reports_errors_and_exits_zero_is_a_failure(monkeypatch):
    """`pg_restore` continues past errors, and does not always exit non-zero.

    Measured on this host, restoring a dump twice WITHOUT `--clean --if-exists`
    exits 1 *and* prints the summary line, so a plain returncode check happens
    to be sufficient today. That is exactly the shape this project keeps
    getting caught by: a rule that is correct today with nothing stopping
    somebody deleting it. `pg_restore`'s documented behaviour is to continue
    unless `--exit-on-error` is given, so the summary line is the reliable
    signal and this test is the pressure that keeps it.
    """
    def reports_errors(args, *, stdin=None, binary=False, check=True):
        args = list(args)
        if args[0] == "exec":
            return subprocess.CompletedProcess(
                args, 0, b"",
                b"pg_restore: warning: " + seed.PG_RESTORE_ERROR_MARKER.encode()
                + b": 17\n",
            )
        if args[0] == "inspect":
            return subprocess.CompletedProcess(args, 0, "br-somewhere\n", "")
        raise AssertionError(args)

    monkeypatch.setattr(seed, "_docker", reports_errors)
    with pytest.raises(seed.SeedError) as raised:
        seed.restore_postgres("br-x-postgres-1", seed.PG_DUMP_MAGIC + b"-stub",
                              user="u", database="d")
    assert seed.PG_RESTORE_ERROR_MARKER in str(raised.value)


def test_postgres_service_refuses_to_guess_between_two_candidates(monkeypatch):
    """Two services declaring the credentials is not a tie to break.

    Production has exactly one, so the refusal has no live example to fire on
    -- which is why it is driven with a fabricated configuration instead of
    left as an unexercised branch. Without this, replacing the uniqueness check
    with "take the first" survives the whole suite.
    """
    fabricated = {
        "services": {
            "postgres": {"environment": {"POSTGRES_USER": "u",
                                         "POSTGRES_DB": "d"}},
            "postgres-replica": {"environment": {"POSTGRES_USER": "u",
                                                 "POSTGRES_DB": "d"}},
            "web": {"environment": {"PORT": "80"}},
        }
    }
    monkeypatch.setattr(overlay, "resolve_config", lambda *a, **k: fabricated)
    with pytest.raises(seed.SeedError) as raised:
        seed.postgres_service()
    message = str(raised.value)
    assert "postgres-replica" in message and "postgres" in message
    assert "guess" in message

    monkeypatch.setattr(overlay, "resolve_config",
                        lambda *a, **k: {"services": {"web": {}}})
    with pytest.raises(seed.SeedError):
        seed.postgres_service()


def test_seed_volume_tree_copies_a_volume_with_no_exclusions_at_all(tmp_path):
    """The case `_copy_tree_pruned` exists for, and the one the other tests miss.

    `_copy_pruned` has two paths. When a subtree contains something excluded it
    walks child by child, and that path does not care what the destination is
    called. When the subtree is CLEAN it takes the fast path -- a single
    `cp -a <src> <dst.parent>` -- which silently assumes source and destination
    share a basename. Every host-path plan entry does; two volume mount points
    (`/src` and `/dst`) do not, and the result inside the container is a `cp`
    into the wrong place.

    A source with no exclusions is not a contrived shape: a freshly created
    agent home has no databases, no pid file, no lock and no socket, so it is
    exactly what the first `branch up` after a new developer is added copies.

    Found by mutation: replacing `_copy_tree_pruned` with a direct
    `_copy_pruned` call SURVIVED the whole suite, because every other fixture
    here contains a `.pid` or a `.db` and is therefore always on the slow path.
    """
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    (src / "skills" / "some-skill").mkdir(parents=True)
    (src / "skills" / "some-skill" / "SKILL.md").write_text("# skill\n")
    (src / "MEMORY.md").write_text("# memory\n")

    rule = seed.AGENT_VOLUME_RULE
    assert seed._subtree_state(src, PurePosixPath(), rule, {})[0] is False, (
        "vacuous: this fixture contains something excluded, so the clean-subtree "
        "fast path is not the one under test"
    )

    summary = seed.seed_volume_tree(src, dst, rule)

    assert summary["databases"] == []
    assert summary["skipped"] == {}
    assert (dst / "MEMORY.md").read_text() == "# memory\n"
    assert (dst / "skills" / "some-skill" / "SKILL.md").is_file()
    assert not (tmp_path / "src" / "src").exists()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["dst", "src"], (
        "the copy landed somewhere other than the destination: "
        f"{sorted(p.name for p in tmp_path.iterdir())}"
    )
