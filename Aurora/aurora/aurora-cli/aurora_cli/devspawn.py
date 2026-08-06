"""Who may spawn an ephemeral stack, what they may call it, and how many.

`branch.py` answers "how do I build a stack". This module answers "may THIS
caller build THIS stack", and it is the only thing between a developer's agent
container and the branch lifecycle. It is deliberately pure -- it reads
`developers.yaml` and does arithmetic on names -- so a refusal here happens
before anything has been created.

The threat model the design only makes sense against: a developer lives inside
a Hermes agent container, with no host shell and no Docker socket, because the
socket is root on the host. The question is not "how do we expose branches" but
"how do we expose them to a caller who is not trusted with the host".

FOUR PROPERTIES, each a construction rather than a check:

1. **Identity is not on the wire.** No developer tool takes a `developer`
   argument; the identity is fixed when the server process is started, by the
   privileged parent that started it. A caller cannot claim to be someone else
   because there is no field in which to make the claim.

2. **A name is constructed, never accepted.** `spawn` takes a LABEL and the
   branch name is `<developer slug>-<label>`, so "cannot tear down another
   developer's stack" is a property of the input space rather than of a check
   that could be deleted.

3. **The prefix test is only sound while namespaces are unambiguous.** Two
   roster entries that sanitise to one slug share a namespace outright, and
   `a` + label `b-x` collides with `a-b` + label `x`.
   `assert_namespaces_are_unambiguous` makes either a startup failure rather
   than a cross-tenant teardown, pinned by synthetic rosters because the live
   one has a single developer and would make the check vacuous.

4. **Quota and lifetime are enforced against the DAEMON, not a file.** A stack
   whose worktree someone deleted still runs and still costs memory.

The roster is read from PRODUCTION's checkout, never from `package_root()`:
`developers.yaml` is a symlink into the gitignored `dev-administration/`, so a
branch worktree may not have one -- and a developer who could add a line to a
file in their own worktree could otherwise mint a second identity.
"""

from __future__ import annotations

import dataclasses
import itertools
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from aurora_cli import access_doc, branch, guards, identity

#: `br-<slug>` and `<label>` are joined by this. It must survive
#: `identity.sanitise_branch_name` unchanged, or the composite name would not
#: be idempotent under the sanitiser `branch_project` applies.
NAMESPACE_SEPARATOR = "-"

LEASE_FILE_NAME = ".spawn-lease.json"

SECONDS_PER_MINUTE = 60
SECONDS_PER_HOUR = 60 * SECONDS_PER_MINUTE

#: Four hours: long enough not to interrupt a developer working through a
#: problem, short enough that a forgotten stack is gone before the next working
#: day. The reaper is what makes this real; without it the number is a comment.
DEFAULT_TTL_SECONDS = 4 * SECONDS_PER_HOUR

MAX_TTL_SECONDS = 24 * SECONDS_PER_HOUR

#: Ceilings on COUNT only; the size of each stack is governed by
#: `branch.check_resources`, which the developer surface may not override
#: (`force` is in no developer schema).
DEFAULT_MAX_PER_DEVELOPER = 1
DEFAULT_MAX_TOTAL = 3

MAX_PER_DEVELOPER_VAR = "AURORA_SPAWN_MAX_PER_DEV"
MAX_TOTAL_VAR = "AURORA_SPAWN_MAX_TOTAL"
TTL_VAR = "AURORA_SPAWN_TTL_SECONDS"

#: The environment variable the privileged broker sets to fix the server's
#: identity. Read once, at start-up, by `__main__`; never consulted per-call.
DEVELOPER_VAR = "AURORA_MCP_DEVELOPER"


class SpawnDenied(RuntimeError):
    """A developer-facing request that policy refused. Never a crash."""


# ---------------------------------------------------------------------------
# identity
# ---------------------------------------------------------------------------


def roster(root: Path | None = None) -> tuple[str, ...]:
    """Every developer this host knows, from production's checkout."""
    return branch.known_developers(root or identity.production_root())


def assert_known_developer(developer: object, root: Path | None = None) -> str:
    """Prove this identity is on the roster. Returns the ROSTER's spelling.

    Positive membership of `developers.yaml`, matched on SLUGS because the slug
    is what names the stacks. What is RETURNED is the roster entry that
    matched, because `branch.resolve_devs` matches roster names exactly: a
    broker started as `alice-two` against a roster listing `alice two` would
    otherwise pass every check here and fail every spawn.
    """
    if not isinstance(developer, str) or not developer.strip():
        raise SpawnDenied(
            "No developer identity. This server is started with one fixed "
            f"identity (${DEVELOPER_VAR} or `--as-developer`); it cannot be "
            "supplied per call."
        )
    slug = identity.sanitise_branch_name(developer)
    known = roster(root)
    matched = [n for n in known if identity.sanitise_branch_name(n) == slug]
    if not matched:
        raise SpawnDenied(
            f"{developer!r} is not a developer on this host. "
            f"developers.yaml lists {sorted(known)}. A stack is spawned as a "
            "developer or not at all."
        )
    assert_namespaces_are_unambiguous(known)
    return matched[0]


def slug_of(developer: str, root: Path | None = None) -> str:
    """The DNS label a known developer's stacks are named for."""
    return identity.sanitise_branch_name(assert_known_developer(developer, root))


def assert_namespaces_are_unambiguous(developers: Iterable[str]) -> None:
    """Refuse a roster the prefix test cannot tell apart.

    Two entries can sanitise to the SAME slug (`alice two` / `alice-two`),
    sharing one namespace entirely, or one slug can be a prefix of another at
    the separator (`a` / `a-b`), making `br-a-b-x` ambiguous. Either way
    `assert_developer_owns` proves ownership for the wrong developer and
    `destroy` honours it. No repair is not a rename, so this raises.

    Checked on every identity resolution rather than once at deploy time:
    `developers.yaml` is edited by `dev-admin`, and a rule enforced only where
    it was introduced is a rule that widens.
    """
    names = list(developers)
    slugs = [identity.sanitise_branch_name(name) for name in names]

    seen: dict[str, str] = {}
    for name, slug in zip(names, slugs):
        if slug in seen:
            raise SpawnDenied(
                f"developers.yaml is unsafe for namespaced spawning: "
                f"{seen[slug]!r} and {name!r} both name the namespace "
                f"{slug!r}, so each could inspect and destroy the other's "
                "stacks. Rename one of them."
            )
        seen[slug] = name

    for outer, inner in itertools.permutations(slugs, 2):
        if inner.startswith(outer + NAMESPACE_SEPARATOR):
            raise SpawnDenied(
                f"developers.yaml is unsafe for namespaced spawning: "
                f"{outer!r} and {inner!r} share a namespace boundary, so a "
                f"stack named by {outer!r} can be indistinguishable from one "
                f"owned by {inner!r}. Rename one of them."
            )


def namespace_prefix(developer: str, root: Path | None = None) -> str:
    """The compose-project prefix every one of this developer's stacks has."""
    prefix = guards.BRANCH_PROJECT_PREFIX
    return f"{prefix}{slug_of(developer, root)}{NAMESPACE_SEPARATOR}"


# ---------------------------------------------------------------------------
# naming
# ---------------------------------------------------------------------------


def branch_name_for(developer: str, label: object, root: Path | None = None) -> str:
    """The branch name a developer's LABEL resolves to. The only way in.

    Raises rather than truncating: `sanitise_branch_name` truncates to the
    tailnet hostname budget, and a truncation landing on the namespace
    separator produces a name outside the developer's namespace, which
    `assert_developer_owns` would refuse while naming a string nobody typed.
    """
    slug = slug_of(developer, root)
    if not isinstance(label, str) or not label.strip():
        raise SpawnDenied(
            "`label` must be a non-empty string. Your stack is named "
            f"{slug}{NAMESPACE_SEPARATOR}<label>; you choose the label and "
            "nothing else."
        )
    composite = f"{slug}{NAMESPACE_SEPARATOR}{identity.sanitise_branch_name(label)}"
    budget = identity.DNS_LABEL_MAX - len(identity.branch_hostname_prefix())
    if len(composite) > budget:
        raise SpawnDenied(
            f"{composite!r} is {len(composite)} characters; the tailnet "
            f"hostname budget is {budget}, of which "
            f"{len(slug) + len(NAMESPACE_SEPARATOR)} is your namespace. Use a "
            f"label of at most {budget - len(slug) - len(NAMESPACE_SEPARATOR)} "
            "characters."
        )
    return composite


def assert_developer_owns(
    developer: str, project: object, root: Path | None = None,
) -> str:
    """Prove `project` is a stack in this developer's namespace. Returns it.

    Three positive clauses: it is in the `br-` namespace and is not production
    (`guards.assert_branch_project`); it begins with THIS developer's prefix,
    recomputed from the roster rather than passed in; and something follows the
    prefix, so the bare namespace is not a stack in it.

    Belt and braces over `branch_name_for`: the construction is what makes the
    hostile case unreachable, this is what refuses it if a future caller
    reaches it anyway.
    """
    guards.assert_branch_project(project)
    assert isinstance(project, str)  # narrowed by the guard above
    prefix = namespace_prefix(developer, root)
    if not project.startswith(prefix):
        raise SpawnDenied(
            f"{project!r} is not yours. Your stacks are named {prefix}<label>. "
            "A developer may only inspect and destroy stacks in their own "
            "namespace."
        )
    if not project[len(prefix):]:
        raise SpawnDenied(
            f"{project!r} is your namespace prefix, not a stack in it."
        )
    return project


# ---------------------------------------------------------------------------
# quota
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Quota:
    per_developer: int = DEFAULT_MAX_PER_DEVELOPER
    total: int = DEFAULT_MAX_TOTAL

    @classmethod
    def from_environ(cls, environ: Mapping[str, str] | None = None) -> "Quota":
        env = os.environ if environ is None else environ
        return cls(
            per_developer=_positive_int(
                env.get(MAX_PER_DEVELOPER_VAR), DEFAULT_MAX_PER_DEVELOPER,
                MAX_PER_DEVELOPER_VAR,
            ),
            total=_positive_int(
                env.get(MAX_TOTAL_VAR), DEFAULT_MAX_TOTAL, MAX_TOTAL_VAR,
            ),
        )


def _positive_int(raw: str | None, default: int, name: str) -> int:
    """A ceiling that fails to parse must not silently become "no ceiling"."""
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        raise SpawnDenied(f"${name}={raw!r} is not an integer.") from None
    if value < 1:
        raise SpawnDenied(
            f"${name}={value} would disable spawning entirely; set it to 1 or "
            "more, or stop the broker."
        )
    return value


def mine(developer: str, projects: Sequence[str], root: Path | None = None) -> list[str]:
    """This developer's live projects, from a list the DAEMON produced.

    The one ownership predicate over project names: `mcp.list_mine` filters
    through this rather than re-deriving `startswith`, because the two
    spellings had already disagreed about the bare prefix.
    """
    prefix = namespace_prefix(developer, root)
    return sorted(p for p in projects if p.startswith(prefix) and p != prefix)


def assert_within_quota(
    developer: str,
    live_projects: Sequence[str],
    quota: Quota | None = None,
    root: Path | None = None,
) -> None:
    """Refuse a spawn that would exceed either ceiling.

    `live_projects` is passed in, not fetched, so this has no side effects and
    the tests need no daemon. The caller fetches it from
    `branch.live_branch_projects()` -- a cached index would let a stack whose
    worktree was deleted vanish from the count while still holding 1.3 GB.
    """
    quota = quota or Quota.from_environ()
    owned = mine(developer, live_projects, root)
    if len(owned) >= quota.per_developer:
        raise SpawnDenied(
            f"quota: you already have {len(owned)} stack(s) up "
            f"({', '.join(owned)}) and your limit is {quota.per_developer}. "
            f"Destroy one first, or wait for its lease to expire."
        )
    if len(live_projects) >= quota.total:
        raise SpawnDenied(
            f"quota: this host is running {len(live_projects)} branch stacks "
            f"and the limit is {quota.total}. This is a shared host; try "
            "again later."
        )


# ---------------------------------------------------------------------------
# leases
# ---------------------------------------------------------------------------


def humanise(seconds: float) -> str:
    """A duration in the largest unit that keeps it readable."""
    if abs(seconds) >= SECONDS_PER_HOUR:
        return f"{seconds / SECONDS_PER_HOUR:.1f}h"
    return f"{seconds / SECONDS_PER_MINUTE:.0f} min"


@dataclass(frozen=True)
class Lease:
    developer: str
    project: str
    name: str
    created: float
    ttl_seconds: int

    @property
    def expires_at(self) -> float:
        return self.created + self.ttl_seconds

    def is_expired(self, now: float) -> bool:
        return now >= self.expires_at

    def remaining(self, now: float | None = None) -> float:
        """Seconds left; negative once it has expired."""
        return self.expires_at - (time.time() if now is None else now)

    def describe(self, now: float | None = None) -> str:
        """The ONE rendering of a lease. Epoch seconds are not a rendering."""
        left = self.remaining(now)
        if left <= 0:
            return f"expired {humanise(-left)} ago"
        return f"expires in {humanise(left)}"

    def as_json(self) -> str:
        return json.dumps(
            dataclasses.asdict(self), indent=2, sort_keys=True,
        ) + "\n"


def lease_ttl(environ: Mapping[str, str] | None = None) -> int:
    """The configured lifetime, refusing rather than clamping a value above
    the ceiling: a misconfigured lifetime silently repaired is a lifetime
    nobody knows is not the one they set (`_positive_int`'s reason)."""
    env = os.environ if environ is None else environ
    ttl = _positive_int(env.get(TTL_VAR), DEFAULT_TTL_SECONDS, TTL_VAR)
    if ttl > MAX_TTL_SECONDS:
        raise SpawnDenied(
            f"${TTL_VAR}={ttl} exceeds the {MAX_TTL_SECONDS}s ceiling on a "
            "lease. Lower it, or raise MAX_TTL_SECONDS deliberately."
        )
    return ttl


def lease_path(worktree: Path | str) -> Path:
    """`<worktree>/.spawn-lease.json`. The guard is on the path BUILDER, so
    every reader and writer of a lease inherits it."""
    return guards.assert_not_production_path(worktree) / LEASE_FILE_NAME


def write_lease(
    worktree: Path | str,
    developer: str,
    project: str,
    *,
    name: str,
    ttl_seconds: int | None = None,
    now: float | None = None,
) -> Lease:
    lease = Lease(
        developer=developer,
        project=project,
        name=name,
        created=time.time() if now is None else now,
        ttl_seconds=lease_ttl() if ttl_seconds is None else ttl_seconds,
    )
    lease_path(worktree).write_text(lease.as_json(), encoding="utf-8")
    return lease


def read_lease(worktree: Path | str) -> Lease | None:
    """The lease on a worktree, or `None` if it has none or it is unreadable.

    Unreadable is `None` rather than an exception because a lease feeds a
    DESTRUCTIVE sweep: a corrupt file must mean "I do not know when this
    expires, so leave it alone", never "treat it as expired".
    """
    try:
        path = lease_path(worktree)
    except guards.GuardViolation:
        return None
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, Mapping):
        return None
    try:
        return Lease(
            developer=str(payload["developer"]),
            project=str(payload["project"]),
            name=str(payload["name"]),
            created=float(payload["created"]),
            ttl_seconds=int(payload["ttl_seconds"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


@dataclass(frozen=True)
class ReapCandidate:
    name: str
    project: str
    developer: str
    worktree: Path
    expired_for: float

    def describe(self) -> str:
        return (
            f"{self.project} (owner {self.developer}, expired "
            f"{humanise(self.expired_for)} ago)"
        )


def expired_candidates(
    summaries: Sequence[access_doc.BranchSummary], now: float | None = None,
) -> list[ReapCandidate]:
    """Which live branch stacks have outlived their lease.

    Two things a destructive sweep must not do. A stack with NO lease is not a
    candidate: `aurora branch up` run by a human writes none, and reaping the
    unleased would delete an operator's work for want of a file. And the NAME
    and PROJECT come from the daemon's summary, never from the lease -- a file
    inside a worktree is not evidence about what is running, so a lease that
    disagrees is skipped rather than reconciled.
    """
    moment = time.time() if now is None else now
    out: list[ReapCandidate] = []
    for summary in summaries:
        lease = read_lease(summary.worktree)
        if lease is None or not lease.is_expired(moment):
            continue
        if lease.project != summary.project:
            continue
        out.append(ReapCandidate(
            name=summary.name,
            project=summary.project,
            developer=lease.developer,
            worktree=Path(summary.worktree),
            expired_for=moment - lease.expires_at,
        ))
    return out


def reap(now: float | None = None, *, force: bool = True) -> list[ReapCandidate]:
    """Destroy every stack whose lease has expired. Returns what it destroyed.

    `branch_ls`/`branch_down` are resolved on the module at call time, for the
    reason `mcp.py` gives: a test patching `branch.branch_down` must observe
    the patch here too, or this is the path that reaches a real daemon.

    Ownership is re-proved per candidate and a refusal SKIPS it rather than
    aborting the sweep. This runs from cron, so one lease naming a developer
    since removed from the roster would otherwise leave every later expired
    stack running forever.
    """
    destroyed: list[ReapCandidate] = []
    for candidate in expired_candidates(branch.branch_ls(), now):
        try:
            assert_developer_owns(candidate.developer, candidate.project)
        except (SpawnDenied, guards.GuardViolation):
            continue
        branch.branch_down(candidate.name, force=force)
        destroyed.append(candidate)
    return destroyed
