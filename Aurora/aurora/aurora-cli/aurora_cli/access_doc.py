"""`BRANCH-ACCESS.md` and `.worktrees/INDEX.md` (Task 10).

**These documents are the product, not documentation about the product.**
Spec 7.4 returns `BRANCH-ACCESS.md` verbatim as CLI stdout and as the MCP tool
result, so a developer -- or an agent -- acts on it directly. Anything wrong
in it is a broken feature, not a documentation bug.

Three properties are load-bearing, and each one is a defect this project has
already paid for once:

* **No secret reaches a document.** `branch-env.yaml` marks `TS_AUTHKEY`
  `secret: true`; that flag, and never a name heuristic, is what this module
  keys off. Decision D-F puts branch worktrees inside the tree production's
  Hermes bind-mounts, so a leak here is readable by production's agent
  containers -- strictly worse than the same value in the branch `.env`, which
  is 0600.
* **No URL that 502s.** Finding N5: the Caddyfile redirects `/agent` -- the
  ADMIN Hermes dashboard -- to `https://{$DOMAIN_NAME}:{$HERMES_SERVE_PORT}/`,
  which is a `tailscale serve` mapping that exists only on the host, for
  production. A branch's sidecar runs no `serve`. The per-developer
  `/agent/<user>/` routes are unaffected: they are generated into
  `Caddyfile.d/agents.conf` and proxied inside the sidecar's netns.
* **No container name this module invented.** `compose.branch.yml` resets
  `container_name` to null precisely so Compose owns the names, and Compose
  will pick a `-2` suffix the first time a container is recreated while the
  old one still exists. A table built by string concatenation is wrong on that
  day and every day after it.

Rendering only. Nothing here runs a subprocess or reads the daemon: the rows
are handed in by `branch.compose_ps()`, which is the one implementation of
"what is running in this project". That split is deliberate -- it is what lets
the renderer be tested against a deliberately SURPRISING container name
without a live stack, and it keeps `branch.py` the only module that issues
commands.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from aurora_cli import envfile, exclusions, identity

#: The document `up` writes into the branch worktree. Pinned against
#: `identity.branch_paths(...).access_doc` by a drift test -- two spellings of
#: one filename is how a reader is told to open a file that is not there.
ACCESS_DOC_NAME = "BRANCH-ACCESS.md"

#: The index beside the branch worktrees, regenerated on every up and down.
INDEX_NAME = "INDEX.md"

#: How the admin dashboard is marked. A literal, because the test that pins
#: N5 asserts on it and a renderer free to reword it could quietly downgrade
#: "UNAVAILABLE" to "may not work".
UNAVAILABLE = "UNAVAILABLE"

#: The admin dashboard's path in production's Caddyfile.
ADMIN_DASHBOARD_PATH = "/agent"

#: The ONE line of a branch access document that may name production's
#: domain, formatted with it. Anything else naming production is a branch
#: document advertising production's stack, which is the direction spec 5.4
#: exists to prevent.
#:
#: The wording is deliberately about the git REMOTE, not about safety in
#: general: plan defect 33 established that the pre-push hook cannot prevent
#: CONTACT with a branch forge (git discovers remote refs before hooks run, so
#: a credential reaches the forge before the refusal). It stops the push, not
#: the handshake, and this document does not claim otherwise.
PRODUCTION_FORGE_LINE = (
    "- Commits from this worktree still go to production's Forgejo at "
    "https://{domain}/git/ -- that is this repository's `origin`, it is the "
    "normal case, and the pre-push hook allows it."
)

#: Order the URL table is rendered in. Keys absent from `urls()` are skipped;
#: `agent-*` keys follow, sorted. A fixed order so two branches' documents can
#: be diffed against each other.
_URL_ORDER = ("fjell", "forgejo", "affine")

_URL_NOTES = {
    "fjell": "the portfolio at the site root; no Caddy auth in front of it "
             "-- the tailnet is the boundary, and each service behind it "
             "carries its own login",
    "forgejo": "this branch's own git forge, seeded from production's "
               "database -- same users, same tokens",
    "affine": "this branch's own AFFiNE, restored from a `pg_dump` of "
              "production's",
}


class AccessDocError(RuntimeError):
    """A document could not be rendered, or would have leaked something.

    Raised from several distinct checks, so every test asserts on the MESSAGE
    and never on the type alone (Task 1's sequential-guard finding).
    """


# ---------------------------------------------------------------------------
# the rows the renderer is fed
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ContainerRow:
    """One line of `docker compose -p <project> ps --format json`.

    `name` is COMPOSE's, never constructed. See the module docstring.
    """

    service: str
    name: str
    state: str = ""
    status: str = ""
    health: str = ""

    @property
    def condition(self) -> str:
        parts = [p for p in (self.state, self.health) if p]
        return " / ".join(parts) or "unknown"


@dataclass(frozen=True)
class BranchSummary:
    """One branch, as `INDEX.md` and `aurora branch ls` report it.

    Everything here is derived from the daemon except `worktree_exists`, which
    is the point of the pairing: a branch whose worktree someone deleted by
    hand is still running and still costs RAM, and an index built from the
    filesystem would not list it at all.
    """

    name: str
    project: str
    domain: str
    worktree: Path
    worktree_exists: bool
    containers: tuple[ContainerRow, ...] = ()

    @property
    def running(self) -> int:
        return sum(1 for c in self.containers if c.state == "running")

    @property
    def access_doc(self) -> Path:
        return self.worktree / ACCESS_DOC_NAME


# ---------------------------------------------------------------------------
# secrets
# ---------------------------------------------------------------------------


def secret_variables(manifest: Sequence[envfile.Requirement] | None = None) -> tuple[str, ...]:
    """Every variable `branch-env.yaml` marks `secret: true`.

    Driven by the FLAG, never by a name heuristic. A heuristic ("anything
    containing KEY or TOKEN") is a guess about the next variable somebody
    adds; the manifest is a statement about the ones that exist.

    Refuses an empty result. A scrubber that iterates an empty set passes over
    every document it is ever shown -- trap 2, wearing a redaction costume --
    and deleting `secret: true` from the manifest would otherwise silently
    disarm both this and every test that exercises it.
    """
    requirements = envfile.load_manifest() if manifest is None else manifest
    names = tuple(r.name for r in requirements if r.secret)
    if not names:
        raise AccessDocError(
            f"{envfile.MANIFEST_NAME} marks no variable `secret: true`, so the "
            "access document's leak check would pass over every document it "
            "was shown. Refusing to render one. If a secret really stopped "
            "being a secret, delete this check deliberately rather than by "
            "editing the manifest."
        )
    return names


def _assert_no_secret_leaked(text: str, env_file: Path | None) -> None:
    """Refuse a document carrying a secret's NAME or its VALUE.

    Two legs, because they fail differently:

    * the NAME, which is available even when the branch `.env` is not, and
      which catches the obvious `TS_AUTHKEY=...` line;
    * the VALUE read out of the branch `.env`, which is the one that matters --
      it catches a key printed under some other label, or inside a note, or in
      a seed report detail. Nothing in this package puts it there today; that
      is exactly the property that has to keep being true.
    """
    names = secret_variables()
    for name in names:
        if name in text:
            raise AccessDocError(
                f"refusing to render an access document naming {name}: "
                f"{envfile.MANIFEST_NAME} marks it `secret: true`. Decision "
                "D-F puts this document inside the tree production's Hermes "
                "bind-mounts, so it is readable by production's agent "
                "containers -- a secret is worse here than in the branch "
                "`.env`, which is mode 0600."
            )
    if env_file is None:
        return
    try:
        values = envfile.parse_env(Path(env_file).read_text(encoding="utf-8"))
    except (OSError, envfile.EnvFileError):
        # No branch `.env`, or one this repository refuses to read. The NAME
        # leg above still ran. Not an error: `branch access` is expected to
        # work on a branch whose worktree was removed by hand.
        return
    for name in names:
        value = values.get(name, "")
        if value and value in text:
            raise AccessDocError(
                f"refusing to render an access document containing the VALUE "
                f"of {name}, read from {env_file}. It is marked `secret: true` "
                f"in {envfile.MANIFEST_NAME}, and this document is world-"
                "readable inside production's agent workspace."
            )


def _assert_production_is_named_once(text: str, production_domain: str) -> None:
    """Production's domain may appear on exactly one, known line.

    Not a substring allowance ("some production references are fine") -- that
    is how the next one gets through. The permitted line is the module
    constant, formatted, compared whole.

    This is a RUNTIME check as well as a test, deliberately: the test feeds
    fabricated results, and the values that actually reach a real document --
    seed report details, `notes`, a hook's advice -- are ones no test has
    seen. The independent pressure on the constant itself is the test's own
    copy of the sentence, which is duplicated there on purpose.
    """
    if not production_domain:
        raise AccessDocError(
            "production's domain resolved empty, so 'this document does not "
            "name production' would be true of every document. Refusing to "
            "render."
        )
    permitted = PRODUCTION_FORGE_LINE.format(domain=production_domain)
    offenders = [
        line for line in text.splitlines()
        if production_domain in line and line.strip() != permitted.strip()
    ]
    if offenders:
        raise AccessDocError(
            "refusing to render an access document that names production's "
            f"domain outside the one permitted line: {offenders!r}. A branch's "
            "document advertising production's URLs is how a developer ends up "
            "working in the stack the branch exists to keep away from."
        )


# ---------------------------------------------------------------------------
# BRANCH-ACCESS.md
# ---------------------------------------------------------------------------


def _url_rows(result: Any) -> list[tuple[str, str, str]]:
    urls = result.urls()
    if not urls:
        raise AccessDocError(
            "the branch result carries no URLs, so a URL table rendered from "
            "it would be empty and every assertion over it vacuous."
        )
    rows: list[tuple[str, str, str]] = []
    for key in _URL_ORDER:
        if key in urls:
            rows.append((key, urls[key], _URL_NOTES.get(key, "")))
    for key in sorted(k for k in urls if k.startswith("agent-")):
        dev = key[len("agent-"):]
        rows.append((
            f"agent ({dev})",
            urls[key],
            f"{dev}'s Hermes dashboard, proxied in the sidecar's network "
            "namespace",
        ))
    # Anything else `urls()` grows later. Rendered rather than dropped: a URL
    # a branch serves and its access document omits is the same defect as a
    # URL it prints and does not serve, one direction over.
    for key in sorted(urls):
        if key not in _URL_ORDER and not key.startswith("agent-"):
            rows.append((key, urls[key], ""))
    return rows


def _admin_dashboard_section(domain: str) -> list[str]:
    """N5, spelled out. No URL is printed here on purpose."""
    return [
        f"### `{ADMIN_DASHBOARD_PATH}` (the admin Hermes dashboard) is "
        f"{UNAVAILABLE} in a branch",
        "",
        f"No URL is printed for it, deliberately. The Caddyfile handles "
        f"`{ADMIN_DASHBOARD_PATH}` with "
        "`redir https://{$DOMAIN_NAME}:{$HERMES_SERVE_PORT}/`, and that port "
        "is a `tailscale serve` mapping which exists **only on the host, for "
        "production**. A branch's sidecar runs no `serve`, so the redirect "
        f"leads nowhere: `https://{domain}{ADMIN_DASHBOARD_PATH}` would answer "
        "with a redirect to a port that is not listening. A URL that fails is "
        "worse than no URL.",
        "",
        "The per-developer `/agent/<user>/` routes in the table above are "
        "**not** affected. They are generated into "
        "`Caddyfile.d/agents.conf` by `dev-admin reconcile` and proxied "
        "inside the sidecar's network namespace, which is where this branch's "
        "containers actually are.",
    ]


def _exclusion_rows(
    excluded: Sequence[str],
    manifest: Mapping[str, exclusions.ServiceRule] | None = None,
) -> list[tuple[str, str, str]]:
    """Each excluded service, and WHY it is missing.

    The requested/transitively-added split is derived from the manifest rather
    than carried along from the command line, so it is available to
    `aurora branch access` on a branch created weeks ago. "I asked to drop
    `forgejo` and `forgejo-mcp` vanished too" is the question this answers.
    """
    rules = exclusions.load_manifest() if manifest is None else manifest
    rows: list[tuple[str, str, str]] = []
    for name in sorted(excluded):
        pulled_by = sorted(
            other for other in excluded
            if other != name and name in (
                rules[other].also_exclude if other in rules else ()
            )
        )
        rule = rules.get(name)
        if pulled_by:
            how = "pulled in by " + ", ".join(f"`{p}`" for p in pulled_by)
        else:
            how = "requested with `--without`"
        rows.append((name, how, (rule.why if rule and rule.why else "-")))
    return rows


def _hook_lines(result: Any) -> list[str]:
    """What the pre-push hook does, and whether git will run it.

    Honest about two things at once (plan defect 33 and Task 7's open item 1):
    the hook stops the ref update, not the connection; and until a human runs
    the arming command, git does not run it at all.
    """
    hook = getattr(result, "hook", None)
    lines = [
        "- The `pre-push` hook in this worktree refuses a push aimed at a "
        "BRANCH forge. It does not prevent CONTACT with one: git discovers the "
        "remote's refs before any hook runs, so a credential is presented to "
        "the branch's Forgejo and only then is the push refused. The hook "
        "stops the push, not the handshake.",
    ]
    if hook is None:
        lines.append(
            "- The hook's installation state is not recorded for this branch. "
            f"Check it with `git -C {getattr(result.paths, 'worktree', '?')} "
            "hook run --to-stdin=/dev/null pre-push -- origin <url>`."
        )
        return lines
    if hook.effective:
        lines.append(
            f"- It is ARMED: git resolves hooks to `{hook.hooks_dir}` and the "
            "file is executable, so it runs."
        )
        return lines
    lines += [
        "- **IT IS INERT. Nothing below is protecting you yet.** The hook is "
        f"installed at `{hook.path}`, but git resolves hooks to "
        f"`{hook.hooks_dir}` and looks in this worktree not at all. It is one "
        "write to the SHARED git config, which for every worktree of this "
        "repository is production's checkout, so nothing in this package may "
        "make it -- a human runs this once, ever:",
        "",
        "```",
        hook.activation_command,
        "```",
        "",
        "  Until then, a push aimed at a branch forge is not refused.",
    ]
    return lines


def render_access_doc(
    result: Any,
    containers: Sequence[ContainerRow] = (),
    *,
    production_domain: str | None = None,
) -> str:
    """`BRANCH-ACCESS.md` for one branch. Returned verbatim to humans and MCP.

    `result` is a `branch.BranchResult`, taken structurally rather than by
    import so that this module stays free of `branch.py` (which imports it).
    `containers` comes from `branch.compose_ps()` and is never derived here.

    `production_domain` exists for tests that fabricate an identity; it
    defaults to the derivation, so the real path has no branch of its own.
    """
    paths = result.paths
    domain = result.domain
    prod = (
        identity.production_domain() if production_domain is None
        else production_domain
    )

    out: list[str] = []
    add = out.append

    add(f"# Branch `{result.name}`")
    add("")
    add(f"- compose project: `{result.project}`")
    add(f"- tailnet node: `{paths.hostname}`")
    add(f"- worktree: `{paths.worktree}`")
    add(f"- generated by: `aurora branch up` / `aurora branch access "
        f"{result.name}`, regenerated on every up and down")
    if getattr(result, "sanitised", False):
        add(f"- NOTE: the requested name `{result.requested_name}` was "
            f"sanitised to `{result.name}` (spec 7.1: one DNS label).")
    add("")

    add("## URLs")
    add("")
    add("| what | URL | note |")
    add("|---|---|---|")
    for label, url, note in _url_rows(result):
        add(f"| {label} | {url} | {note} |")
    add("")
    if not result.devs:
        add("No developer agent was requested for this branch (`--devs none`), "
            "so there are no `/agent/<user>/` routes.")
        add("")
    out.extend(_admin_dashboard_section(domain))
    add("")

    add("## Containers")
    add("")
    if containers:
        add("Names are read from `docker compose -p " + result.project
            + " ps`, never constructed: `compose.branch.yml` resets "
              "`container_name` to null so that Compose owns them, and "
              "Compose appends `-2` the moment a container is recreated "
              "beside an older one.")
        add("")
        add("| service | container | state |")
        add("|---|---|---|")
        for row in containers:
            add(f"| {row.service} | `{row.name}` | {row.condition} |")
        add("")
        add("Paste-ready shells (spec D6 -- these run on the host you already "
            "reach over Tailscale SSH, no new infrastructure):")
        add("")
        add("```")
        for row in containers:
            add(f"docker exec -it {row.name} bash")
        add("```")
        add("")
        add("Some images ship `sh` and no `bash`; "
            f"`aurora branch shell {result.name} <service>` resolves the "
            "container from this branch's labels for you.")
    else:
        add("**Nothing is running under this project.** Either the branch was "
            "torn down, or `up` did not get far enough to create a container. "
            f"`aurora branch down {result.name}` reclaims whatever is left.")
    add("")

    add("## Commands")
    add("")
    add("```")
    add(f"aurora branch access {result.name}            # this document, "
        "regenerated from live state")
    add(f"aurora branch shell {result.name} <service>   # exec into one of "
        "the containers above")
    add(f"aurora branch rebuild {result.name} <service> # rebuild and restart "
        "ONE service, in this project only")
    add(f"aurora branch down {result.name}              # destroy the stack, "
        "its volumes and this worktree")
    add("```")
    add("")

    add("## What was excluded")
    add("")
    rows = _exclusion_rows(result.excluded) if result.excluded else []
    if rows:
        add("| service | why it is missing | manifest note |")
        add("|---|---|---|")
        for name, how, why in rows:
            add(f"| `{name}` | {how} | {why} |")
    else:
        add("Nothing. This branch runs the full stack.")
    add("")

    add("## What was seeded")
    add("")
    # THREE states, not two. `None` means "this document was regenerated and
    # cannot know", and it must not render as "nothing was seeded": whether a
    # branch shares production's users is the last thing a document should
    # guess about. Seeding is an event, not a state, so it is the one thing
    # `aurora branch access` cannot re-derive.
    seeded = getattr(result, "seeded", None)
    if getattr(result, "seed_report", None) is not None:
        add(result.seed_report.render())
    elif seeded is None:
        add("Not recorded here. Seeding happens once, at `up`, and leaves no "
            "state that can be read back -- see the copy of this document "
            "written when the branch was created.")
    elif seeded:
        add("Seeded, but no report was recorded.")
    else:
        add("**Nothing** (`--no-seed`). This branch's Forgejo, Hermes and "
            "AFFiNE start empty: no users, no repositories, no agent "
            "identities.")
    add("")

    resources = getattr(result, "resources", None)
    if resources is not None and resources.forced:
        add("## Resource guard OVERRIDDEN")
        add("")
        add("This branch was created with `--force`, over the resource "
            "guard's refusal:")
        add("")
        for shortfall in resources.shortfalls():
            add(f"- {shortfall}")
        add("")
        add("It may be killed by the kernel, or fill the disk.")
        add("")

    add("## Pushing from this worktree")
    add("")
    out.extend(_hook_lines(result))
    add(PRODUCTION_FORGE_LINE.format(domain=prod))
    add("")

    notes = list(getattr(result, "notes", ()) or ())
    if notes:
        add("## Notes")
        add("")
        for note in notes:
            add(f"- {' '.join(str(note).split())}")
        add("")

    text = "\n".join(out).rstrip("\n") + "\n"
    _assert_no_secret_leaked(text, getattr(paths, "env_file", None))
    _assert_production_is_named_once(text, prod)
    return text


# ---------------------------------------------------------------------------
# INDEX.md
# ---------------------------------------------------------------------------


def render_index(
    branches: Iterable[BranchSummary], runtime: str | None = None,
) -> str:
    """`.worktrees/INDEX.md`, from a list DERIVED FROM THE DAEMON.

    Never from a cached file, and the difference is not academic: a branch
    whose worktree was deleted by hand is still running and still costs RAM,
    and an index that read itself would keep listing a branch that was torn
    down an hour ago. `branch.live_branch_projects()` is the one query, and
    `branch_down_all` uses the same one for the same reason.

    Because `.worktrees/` sits inside the tree production's Hermes mounts
    (decision D-F), production's agent reads this file, and every branch's
    access document through it, with no extra wiring.

    `runtime` names WHICH daemon the rows came from, and it is stated in the
    document rather than left implicit. `branch_ls` asks one daemon per call
    (its docstring says why), so an index regenerated from docker cannot see a
    podman branch -- and an index that silently omitted one would be the exact
    thing this file is written against: a branch nobody knows is running.
    """
    branches = list(branches)
    out: list[str] = []
    add = out.append
    add("# Branch stacks on this host")
    add("")
    add("Regenerated by `aurora branch up` and `aurora branch down`. Every row "
        "is derived from the Docker daemon, never from this file: a branch "
        "whose worktree was removed by hand is still running and still costs "
        "memory, and only the daemon knows about it.")
    add("")
    if runtime is not None:
        add(f"**Generated from the `{runtime}` runtime only.** One daemon is "
            "asked per regeneration, so a branch built on the other runtime "
            "is not listed here even though it is running. "
            "`aurora branch ls --runtime <other>` asks it.")
        add("")
    if not branches:
        add("No branch stack is running.")
        add("")
        return "\n".join(out)
    add("| branch | project | URL | containers | worktree | access document |")
    add("|---|---|---|---|---:|---|")
    for b in sorted(branches, key=lambda x: x.name):
        worktree = (
            f"`{b.worktree}`" if b.worktree_exists
            else f"`{b.worktree}` **MISSING**"
        )
        doc = f"`{b.access_doc}`" if b.worktree_exists else "-"
        add(
            f"| {b.name} | `{b.project}` | https://{b.domain}/ | "
            f"{b.running} running / {len(b.containers)} | {worktree} | {doc} |"
        )
    add("")
    return "\n".join(out)
