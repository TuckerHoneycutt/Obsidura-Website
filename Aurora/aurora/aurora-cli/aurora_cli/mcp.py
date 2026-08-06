"""The stdio MCP facade: line-delimited JSON-RPC 2.0, hand-written (Task 11).

Spec D5 and 7.3: one package, two surfaces. `aurora branch ...` is the human
surface and `aurora mcp` is the agent surface, and **they call the same
functions**. Not "equivalent" functions -- the same objects, looked up on
`aurora_cli.branch` at call time, so a test that patches `branch.branch_up`
observes the patch through both. Two implementations of "create a branch" is
the drift this project's ledger keeps recording, one noun at a time.

Per decision D-B the transport is hand-written. MCP's stdio transport is
line-delimited JSON-RPC 2.0 and `initialize`, `notifications/initialized`,
`tools/list` and `tools/call` are the whole surface 7.3 needs. Four methods do
not justify a dependency that would then have to exist in the host venv, in a
fresh worktree AND in the `aurora-cli:local` image (decision D-A) -- and a
hand-written server is testable by writing bytes to a pipe, with no network
and no version drift. `tests` therefore pin this against a RECORDED
TRANSCRIPT of the bytes, not against a library's behaviour.

THREE THINGS THIS FILE IS RESPONSIBLE FOR, each of which is a real hazard
rather than a hypothetical one:

1. **An MCP server exposes destructive operations to a caller nobody in this
   repository controls.** `branch_down` reaches Docker. A tool that took a
   project name out of a JSON-RPC frame and handed it to Compose would be the
   2026-07-29 incident again with a pipe in front of it. So every tool that
   can destroy resolves its target through `identity.branch_paths` -- which
   sanitises and forces the `br-` namespace -- and then proves it with
   `guards.assert_branch_project` / `assert_not_production_path` BEFORE
   dispatching. `aurora-cli/tests/test_guards.py` asserts that structurally,
   over this module as well as over `branch.py`.

2. **No secret crosses the wire.** `TS_AUTHKEY` is marked `secret: true` in
   `branch-env.yaml`, and Task 10 built the mechanism that keys off that flag
   and refuses an empty set. This module calls THAT function rather than
   growing a second one: `access_doc._assert_no_secret_leaked`, applied to the
   SERIALISED response -- so it sees the whole payload regardless of which
   field a value was accidentally put in -- and again, name-leg only, over
   every outgoing line, which catches a key that reached an error message.

3. **The server stays alive.** A malformed line is `-32700` and the next
   message is still served; an unknown method is `-32601`; a tool that raises
   becomes a tool RESULT with `isError`, not a traceback and not a dead
   process. An MCP server that dies on the first bad byte is one an agent
   cannot use, and an agent cannot see stderr.

Documents are the product (spec 7.4): `branch_up` and `branch_access` return
`BRANCH-ACCESS.md` verbatim -- the same string the CLI prints and the same
string the file on disk carries -- and `branch_list` returns `INDEX.md`.

TWO TOOL TABLES, ONE TRANSPORT (2026-07-31). The table above is the ADMIN
surface: on the host, as a human, able to name any branch. The DEVELOPER
surface (`developer_server`) is the same transport with a different table,
scoped to one developer's namespace by `devspawn`. The dispatch, the error
model and the secret check are shared deliberately -- a second server would be
a second place for `_emit`'s leak check to be forgotten -- and `Server` exists
only to make the table a parameter instead of a global.
"""

from __future__ import annotations

import functools
import json
import re
import subprocess
import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, BinaryIO, Callable, Mapping, Sequence

from aurora_cli import access_doc, branch, devspawn, envfile, guards, identity

# ---------------------------------------------------------------------------
# the wire
# ---------------------------------------------------------------------------

JSONRPC_VERSION = "2.0"

#: JSON-RPC 2.0 reserved codes. Spelled out rather than inlined so the tests
#: assert on the same constants the server emits and a typo cannot be
#: "correct" on both sides.
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

#: The protocol revision this server prefers. `initialize` ECHOES the version
#: the client asked for when it is one we speak, and answers with this one
#: otherwise -- that is the negotiation MCP specifies, and it is also what
#: keeps this file from going stale the day a client is upgraded.
PROTOCOL_VERSION = "2025-06-18"
SUPPORTED_PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")

#: This server's own name and version -- not production's identity, which is
#: derived and never typed (see `identity`'s docstring). `aurora_cli` is this
#: package's own name; naming yourself is not hardcoding production.
SERVER_NAME = "aurora-branch"
SERVER_VERSION = "0.3.0"

INSTRUCTIONS = (
    "Branch lifecycle for this stack. `branch_up` mints a complete isolated "
    "copy of production -- its own Compose project, tailnet node, certificate "
    "and seeded state -- and returns its BRANCH-ACCESS.md verbatim; that "
    "document is the product, act on it directly. `branch_down` destroys one. "
    "Both are scoped to the `br-` namespace by construction and cannot reach "
    "production. `branch_list` returns the index of live branches; "
    "`branch_access` regenerates one branch's document from live state. "
    "`rebuild` rebuilds production's from-source images and recreates their "
    "containers -- merging a pull request does NOT do this, and a stack "
    "serving a stale binary answers 200 on every route. Call it with "
    "`check: true` first; that reports staleness and changes nothing."
)


class ProtocolError(RuntimeError):
    """A JSON-RPC frame this server will not act on. Carries its own code."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


# ---------------------------------------------------------------------------
# secrets: the same mechanism the access document uses, never a second one
# ---------------------------------------------------------------------------


def _assert_no_secret_in(text: str, env_files: Sequence[Path | None] = ()) -> None:
    """Refuse to emit anything carrying a secret's NAME or its VALUE.

    Deliberately delegates to `access_doc._assert_no_secret_leaked`, which is
    driven by `access_doc.secret_variables()` -- the `branch-env.yaml`
    `secret: true` flag, never a name heuristic, and it REFUSES an empty set
    so that deleting the flag raises instead of silently disarming every
    check that depends on it.

    Reaching for a module-private name inside the same package is deliberate.
    The alternative is a second implementation of "is a secret in this
    string", and two implementations of one measurement is precisely how this
    project's earlier drifts happened. A leak here is worse than a leak into
    the branch `.env` (mode 0600): this text goes down a pipe to a caller
    nobody in this repository controls.

    The check runs over the SERIALISED payload, so it does not care which
    field a value ended up in. Called with no env files it still runs the NAME
    leg, which is why the empty case is a call rather than a `return`.
    """
    files = [f for f in env_files if f is not None]
    if not files:
        access_doc._assert_no_secret_leaked(text, None)
        return
    for env_file in files:
        access_doc._assert_no_secret_leaked(text, env_file)


# ---------------------------------------------------------------------------
# tools
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ToolResult:
    """What a tool produced, and where its secrets would have come from.

    `env_files` is not decoration: the VALUE leg of the leak check reads the
    branch `.env`, and a tool that returned a key under some other label is
    only caught if the file that holds the key is named here.
    """

    text: str
    env_files: tuple[Path, ...] = ()


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[[Mapping[str, Any]], ToolResult]

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }


def _require_name(arguments: Mapping[str, Any]) -> str:
    value = arguments.get("name")
    if not isinstance(value, str) or not value.strip():
        raise ProtocolError(
            INVALID_PARAMS,
            "`name` must be a non-empty string naming the branch.",
        )
    return value


def _guarded_paths(name: str) -> identity.BranchPaths:
    """Resolve a branch name from the wire into paths that PROVE they are one.

    `identity.branch_paths` sanitises the name to a single DNS label and
    forces the `br-` project prefix, so a hostile string cannot become a
    production project here. That is a construction argument, and a
    construction argument is not a guard -- so the two guards run anyway, on
    the values actually about to be used. The order matters: nothing has been
    issued at this point, so a refusal leaves the host untouched.
    """
    paths = identity.branch_paths(name)
    guards.assert_branch_project(paths.project)
    guards.assert_not_production_path(paths.worktree)
    return paths


def _bool(arguments: Mapping[str, Any], key: str, default: bool = False) -> bool:
    value = arguments.get(key, default)
    if not isinstance(value, bool):
        raise ProtocolError(INVALID_PARAMS, f"`{key}` must be a boolean.")
    return value


def _string_list(arguments: Mapping[str, Any], key: str) -> tuple[str, ...]:
    value = arguments.get(key) or []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ProtocolError(
            INVALID_PARAMS, f"`{key}` must be a string or a list of strings."
        )
    return tuple(value)


def _optional_string(arguments: Mapping[str, Any], key: str) -> str | None:
    value = arguments.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ProtocolError(INVALID_PARAMS, f"`{key}` must be a string.")
    return value


def _tool_branch_up(arguments: Mapping[str, Any]) -> ToolResult:
    """Create a branch stack, then refresh its documents. Returns the document.

    `branch.branch_up` and `branch.refresh_branch_docs` are looked up on the
    module at call time, which is what makes "the MCP path runs the same code
    the CLI runs" a testable claim rather than an assertion.

    `refresh_branch_docs` is called HERE, exactly as `__main__._cmd_branch_up`
    calls it, because Task 10 hoisted it out of `branch_up` deliberately: it
    regenerates `<production>/.worktrees/INDEX.md`, and the lifecycle
    functions are exercised against real Docker objects by the test suite.
    Without this call a branch created over MCP would have no access document
    and the index would go stale (Task 10 open item 2).
    """
    name = _require_name(arguments)
    _guarded_paths(name)
    result = branch.branch_up(
        name,
        from_ref=_optional_string(arguments, "from_ref"),
        no_seed=_bool(arguments, "no_seed"),
        seed_strategy=arguments.get("seed") or "filecopy",
        without=_string_list(arguments, "without"),
        devs=_optional_string(arguments, "devs"),
        force=_bool(arguments, "force"),
        build=_bool(arguments, "build", True),
    )
    doc_path, _index = branch.refresh_branch_docs(result)
    return ToolResult(
        text=Path(doc_path).read_text(encoding="utf-8"),
        env_files=(result.paths.env_file,),
    )


def _tool_branch_down(arguments: Mapping[str, Any]) -> ToolResult:
    """Destroy one branch stack, or every one, then regenerate the index.

    Mirrors `__main__._cmd_branch_down` exactly, including the fact that it
    calls `write_index` rather than `refresh_branch_docs`: after a teardown
    the worktree is gone, and `refresh_branch_docs` would write a
    BRANCH-ACCESS.md into it -- `_write_document` creates parents -- which
    RESURRECTS the directory the teardown just removed. See the ledger's Task
    11 entry: that is a defect in the instruction, not a shortcut here, and
    `test_the_teardown_tool_does_not_resurrect_the_worktree` pins it.
    """
    everything = _bool(arguments, "all")
    force = _bool(arguments, "force")
    env_files: list[Path] = []

    if everything:
        results = branch.branch_down_all(force=force)
    else:
        name = _require_name(arguments)
        paths = _guarded_paths(name)
        env_files.append(paths.env_file)
        results = [branch.branch_down(name, force=force)]

    index = branch.write_index()
    return ToolResult(
        text=branch.render_teardown(results, index),
        env_files=tuple(env_files),
    )


def _tool_branch_list(arguments: Mapping[str, Any]) -> ToolResult:
    """Every branch stack on this host, as `.worktrees/INDEX.md`.

    Derived from the daemon by `branch.branch_ls`, never from a cached file:
    a branch whose worktree was deleted by hand is still running, still costs
    memory, and is invisible to anything that walks the filesystem.
    """
    summaries = branch.branch_ls()
    return ToolResult(
        text=access_doc.render_index(summaries),
        env_files=tuple(
            summary.worktree / envfile.ENV_FILE_NAME for summary in summaries
        ),
    )


def _tool_branch_access(arguments: Mapping[str, Any]) -> ToolResult:
    """One branch's `BRANCH-ACCESS.md`, regenerated from live state."""
    name = _require_name(arguments)
    paths = identity.branch_paths(name)
    return ToolResult(
        text=branch.branch_access(name),
        env_files=(paths.env_file,),
    )


# ---------------------------------------------------------------------------
# rebuild: the one tool that is POINTED AT PRODUCTION on purpose
# ---------------------------------------------------------------------------
#
# Every other tool here proves it is branch-scoped before it acts, because
# reaching production would be the 2026-07-29 incident with a pipe in front of
# it. This one reaches production by design, so it cannot use that argument and
# needs its own, which is: IT ISSUES NO DESTRUCTIVE VERB. `ops/rebuild.sh` runs
# `compose config`, `image inspect` and `compose up -d --build` -- and
# `compose up` is deliberately absent from ops/docker-guard's destructive set
# ("it is how production is restored, so it must never be blocked"). Nothing
# here is stopped, removed, restarted or destroyed, so there is nothing for a
# `br-` guard to protect and no AURORA_ALLOW_PROD to reach for.
#
# What IS hostile input is the service list: it arrives in a JSON-RPC frame
# from a caller nobody in this repository controls, and it becomes argv. A
# service name of `--profile`, or one naming production's own project followed
# by a destructive verb, is the 2026-07-29 incident again by another route. So `_safe_service_names` refuses anything
# that is not a plain compose service name BEFORE `_rebuild_argv` builds a
# single word, and `_rebuild_argv` puts `--` in front of the names so even an
# accepted name cannot be read as a flag. Belt and braces, in that order.

#: The script IS the implementation. This module does not reimplement
#: staleness, image fingerprinting or the buildable-service derivation -- two
#: implementations of one measurement is the drift this project's ledger keeps
#: recording, and the CLI/MCP split above exists precisely to avoid it.
REBUILD_SCRIPT = "ops/rebuild.sh"

#: A compose service name, as Compose itself spells them. Deliberately
#: restrictive: this is an allowlist over a value that becomes argv, so a
#: spelling nobody anticipated is refused rather than passed along.
SERVICE_NAME = re.compile(r"[a-z0-9][a-z0-9._-]*")


def _safe_service_names(arguments: Mapping[str, Any]) -> tuple[str, ...]:
    """The `services` argument, or a refusal, before anything is built.

    `fullmatch`, not `match`: `match` accepts `fjell; rm -rf /` because the
    prefix is fine, which is the whole failure mode this exists to stop. The
    leading-character class refuses `-` and `--` specifically, so a flag
    cannot arrive disguised as a service.
    """
    names = _string_list(arguments, "services")
    rejected = [name for name in names if not SERVICE_NAME.fullmatch(name)]
    if rejected:
        raise ProtocolError(
            INVALID_PARAMS,
            f"not compose service names: {rejected}. `services` takes plain "
            "service names as declared in compose.yml; nothing was built.",
        )
    return names


def _rebuild_argv(check: bool, services: Sequence[str]) -> list[str]:
    """The whole command this tool can ever issue.

    Split out so it is testable without running anything, and so a test can
    assert over every argument combination that no destructive verb appears in
    it. `--` separates flags from operands: after it, `--check` would be a
    service name and would be refused by the script rather than honoured.
    """
    argv = ["bash", REBUILD_SCRIPT]
    if check:
        argv.append("--check")
    if services:
        argv.append("--")
        argv.extend(services)
    return argv


def _tool_rebuild(arguments: Mapping[str, Any]) -> ToolResult:
    """Rebuild production's from-source images, or just report staleness.

    Exit 1 under `check` is not a failure -- it is the ANSWER, and it is the
    answer an agent most needs to read, so it comes back as an ordinary result
    carrying the report. Any OTHER non-zero exit means the script could not be
    run at all, and a non-zero exit from a real build is a build failure; both
    are raised, which `_method_tools_call` turns into `isError` with the
    script's own transcript attached.

    Runs on the host as the user, in the production checkout, with no new
    container and no Docker-socket routing: `ops/rebuild.sh` needs git and
    docker, and this process already has both.
    """
    services = _safe_service_names(arguments)
    check = _bool(arguments, "check")
    root = identity.production_root()

    # `env=` and not the ambient environment. `branch.stripped_environ()` exists
    # because an exported COMPOSE_PROJECT_NAME / COMPOSE_PROFILES / COMPOSE_FILE
    # silently redirects a Compose command, and `DOCKER_HOST` -- added to that
    # tuple by this same branch -- redirects the DAEMON. The one command in this
    # repository pointed at production ON PURPOSE was the one not using it: with
    # a podman session's DOCKER_HOST exported, `rebuild` reported every image
    # NEVER-BUILT, built them into the rootless store, brought a SECOND copy of
    # production's stack up there, and returned a transcript saying it deployed
    # while production went on serving the stale images this tool exists to catch.
    completed = subprocess.run(
        _rebuild_argv(check, services),
        cwd=root,
        capture_output=True,
        text=True,
        env=branch.stripped_environ(),
    )
    transcript = (completed.stdout or "") + (completed.stderr or "")

    if check:
        # 0 and 1 are the only VERDICTS. Anything else means the script could
        # not be asked -- and `bash` exits 127 on a missing file, which is the
        # normal state of a production checkout that has not yet merged this
        # branch. Treating "could not run" as "STALE" is not a safe default in
        # the harmless direction: it is a confident wrong answer, and the whole
        # point of this tool is that the wrong answer is the one nobody caught
        # for thirteen hours.
        if completed.returncode not in (0, 1):
            raise RuntimeError(
                f"{REBUILD_SCRIPT} could not be run in {root} (exit "
                f"{completed.returncode}), so nothing is known about "
                f"staleness:\n{transcript}"
            )
        verdict = (
            "STALE - production is serving code older than the checkout."
            if completed.returncode == 1
            else "FRESH - every image is at least as new as its build context."
        )
        return ToolResult(
            text=f"{verdict}\n\n{transcript}",
            env_files=(root / envfile.ENV_FILE_NAME,),
        )

    if completed.returncode != 0:
        raise RuntimeError(
            f"ops/rebuild.sh exited {completed.returncode}; production was "
            f"left as the transcript describes:\n{transcript}"
        )
    return ToolResult(
        text=transcript,
        env_files=(root / envfile.ENV_FILE_NAME,),
    )


TOOLS: tuple[Tool, ...] = (
    Tool(
        name="branch_up",
        description=(
            "Create an ephemeral branch stack: a git worktree, its own Compose "
            "project in the `br-` namespace, its own tailnet node and "
            "certificate, and state seeded from production read-only. Returns "
            "the branch's BRANCH-ACCESS.md verbatim -- URLs, container names, "
            "paste-ready shells. Production keeps serving throughout and "
            "cannot be reconfigured or taken down by this."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Branch name; sanitised to one DNS label.",
                },
                "from_ref": {
                    "type": "string",
                    "description": "Create the git branch from this ref. Omit "
                                   "to reuse an existing branch.",
                },
                "devs": {
                    "type": "string",
                    "description": "Which developers get an agent: a "
                                   "comma-separated list, `all`, or `none`.",
                },
                "without": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Services to exclude; see "
                                   "branch-services.yaml. Exclusions close "
                                   "transitively.",
                },
                "no_seed": {
                    "type": "boolean",
                    "description": "Start empty instead of copying "
                                   "production's state.",
                },
                "seed": {
                    "type": "string",
                    "description": "Seeding strategy (default `filecopy`).",
                },
                "force": {
                    "type": "boolean",
                    "description": "Override the memory/disk guard. Recorded "
                                   "in the access document.",
                },
                "build": {
                    "type": "boolean",
                    "description": "Build images on the first up (default "
                                   "true).",
                },
            },
            "required": ["name"],
            "additionalProperties": False,
        },
        handler=_tool_branch_up,
    ),
    Tool(
        name="branch_down",
        description=(
            "Destroy a branch stack: its containers, its volumes, its network "
            "and its worktree, then regenerate the branch index. Refuses any "
            "project outside the `br-` namespace and any path outside "
            "`.worktrees/`, before issuing a single command."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "The branch to destroy. Required unless "
                                   "`all` is true.",
                },
                "all": {
                    "type": "boolean",
                    "description": "Destroy every branch stack the daemon "
                                   "knows about.",
                },
                "force": {
                    "type": "boolean",
                    "description": "Remove the worktree even with uncommitted "
                                   "changes.",
                },
            },
            "additionalProperties": False,
        },
        handler=_tool_branch_down,
    ),
    Tool(
        name="branch_list",
        description=(
            "Every branch stack running on this host, as the "
            "`.worktrees/INDEX.md` document: name, project, URL, container "
            "count and whether its worktree still exists. Derived from the "
            "Docker daemon, so a branch whose worktree was deleted by hand -- "
            "the one nobody knows is still consuming memory -- is listed."
        ),
        input_schema={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        handler=_tool_branch_list,
    ),
    Tool(
        name="branch_access",
        description=(
            "One branch's BRANCH-ACCESS.md, regenerated from live state: "
            "URLs, the service-to-container table read from Compose, "
            "paste-ready `docker exec` lines, what was excluded and what was "
            "seeded. Read-only."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "The branch."},
            },
            "required": ["name"],
            "additionalProperties": False,
        },
        handler=_tool_branch_access,
    ),
    Tool(
        name="rebuild",
        description=(
            "Rebuild PRODUCTION's from-source images and recreate their "
            "containers. Merging a pull request updates the checkout and "
            "rebuilds nothing, and `docker compose restart` reuses the image "
            "it already has -- so a merged change can sit unserved while every "
            "route answers 200 and every healthcheck stays green. Pass "
            "`check: true` first: that reports which images are older than the "
            "last commit touching their build context and changes nothing. "
            "The service list is derived from `docker compose config`, never "
            "hardcoded. Issues no destructive verb -- nothing is stopped, "
            "removed or torn down."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "services": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Services to rebuild. Omit for every "
                                   "service declaring a build context.",
                },
                "check": {
                    "type": "boolean",
                    "description": "Report staleness and change nothing. Do "
                                   "this before rebuilding.",
                },
            },
            "additionalProperties": False,
        },
        handler=_tool_rebuild,
    ),
)

TOOLS_BY_NAME: dict[str, Tool] = {tool.name: tool for tool in TOOLS}


# ---------------------------------------------------------------------------
# the developer surface
# ---------------------------------------------------------------------------

DEVELOPER_INSTRUCTIONS = (
    "Ephemeral stacks you own. `spawn` mints a complete isolated copy of "
    "production as compose project `br-{prefix}<label>` -- its own Forgejo, "
    "its own agent, its own tailnet name, seeded from production read-only -- "
    "and returns its BRANCH-ACCESS.md verbatim; that document is the product, "
    "act on it directly. You choose the LABEL; the rest of the name is yours "
    "and is not negotiable, which is what stops two developers colliding. "
    "`list_mine` shows yours and when each lease expires, `destroy` removes "
    "one, `access` re-reads one's document. You cannot see, reach or destroy "
    "another developer's stack, and you cannot reach production."
)


def _developer_tools(developer: str) -> tuple[Tool, ...]:
    """The tool table for ONE developer. The identity is closed over, not passed.

    The whole access-control design in one signature: the handlers capture
    `developer` from this scope and no schema has a `developer` key, so there
    is no byte a caller can put on the wire that changes whose namespace they
    are in. An authorisation bug here would have to be a bug in this
    function's arguments, not a check someone forgot to run.

    `assert_known_developer` runs here as well as inside every resolver, so a
    broker started for an unknown name fails at start-up rather than at the
    first destructive call.
    """
    # The ROSTER's spelling, not the caller's: `branch.resolve_devs` matches
    # roster entries exactly, so a broker started as `alice-two` against a
    # roster listing `alice two` would otherwise resolve here and fail every
    # spawn at `--devs`.
    roster_name = devspawn.assert_known_developer(developer)

    def _resolve(arguments: Mapping[str, Any]) -> identity.BranchPaths:
        """The caller's LABEL as paths for a stack this developer owns.

        Four proofs, in the order that leaves the host untouched on refusal:
        the roster, the namespace construction, the two `br-` guards, and the
        ownership test. Nothing has been issued when any of them refuses.
        """
        paths = _guarded_paths(
            devspawn.branch_name_for(developer, arguments.get("label"))
        )
        devspawn.assert_developer_owns(developer, paths.project)
        return paths

    def spawn(arguments: Mapping[str, Any]) -> ToolResult:
        name = _resolve(arguments).name
        devspawn.assert_within_quota(developer, branch.live_branch_projects())
        result = branch.branch_up(
            name,
            from_ref=_optional_string(arguments, "from_ref"),
            no_seed=_bool(arguments, "no_seed"),
            seed_strategy="filecopy",
            without=_string_list(arguments, "without"),
            # Forced, never read from the wire. `--devs all` starts every
            # developer's agent in every branch; a developer asking for
            # someone else's agent in their own stack is a request to run
            # another identity's Hermes, which is the thing `agent-authz`
            # exists to prevent.
            devs=roster_name,
            # Absent from the schema on purpose: `force` overrides
            # `check_resources`, i.e. the memory and disk floor that protects
            # every other tenant of this host. A ceiling a caller can raise is
            # not a ceiling.
            force=False,
            build=_bool(arguments, "build", True),
        )
        lease = devspawn.write_lease(
            result.paths.worktree, roster_name, result.project,
            name=result.name,
        )
        doc_path, _index = branch.refresh_branch_docs(result)
        document = Path(doc_path).read_text(encoding="utf-8")
        return ToolResult(
            text=document + _lease_footer(lease),
            env_files=(result.paths.env_file,),
        )

    # Delegation, not a second implementation: these two were byte-for-byte
    # the admin handlers with the name resolved differently, and they had
    # already drifted over which of them re-proved the `br-` guards. The
    # resolver above is the whole difference between the two surfaces.
    def destroy(arguments: Mapping[str, Any]) -> ToolResult:
        return _tool_branch_down({
            "name": _resolve(arguments).name,
            "force": _bool(arguments, "force"),
        })

    def list_mine(arguments: Mapping[str, Any]) -> ToolResult:
        live = branch.branch_ls()
        owned = set(devspawn.mine(developer, [s.project for s in live]))
        summaries = [s for s in live if s.project in owned]
        body = access_doc.render_index(summaries)
        leases = [
            _lease_line(s, devspawn.read_lease(s.worktree)) for s in summaries
        ]
        return ToolResult(
            text=body + ("\n" + "\n".join(leases) + "\n" if leases else ""),
            env_files=tuple(
                s.worktree / envfile.ENV_FILE_NAME for s in summaries
            ),
        )

    def access(arguments: Mapping[str, Any]) -> ToolResult:
        return _tool_branch_access({"name": _resolve(arguments).name})

    label_schema = {
        "type": "string",
        "description": "The part of the name you choose. Your stack is "
                       f"`{devspawn.namespace_prefix(developer)}<label>`.",
    }
    return (
        Tool(
            name="spawn",
            description=(
                "Create an ephemeral copy of this stack that belongs to you: "
                "its own Compose project in your namespace, its own tailnet "
                "node and certificate, your agent and nobody else's, and "
                "state seeded from production read-only. Returns its "
                "BRANCH-ACCESS.md. It carries a lease and is destroyed "
                "automatically when the lease expires."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "label": label_schema,
                    "from_ref": {
                        "type": "string",
                        "description": "Git ref to branch from. A ref, not a "
                                       "stack: this cannot name a project.",
                    },
                    "without": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Services to leave out; see "
                                       "branch-services.yaml.",
                    },
                    "no_seed": {
                        "type": "boolean",
                        "description": "Start empty instead of copying "
                                       "production's state.",
                    },
                    "build": {
                        "type": "boolean",
                        "description": "Build images on first up (default "
                                       "true).",
                    },
                },
                "required": ["label"],
                "additionalProperties": False,
            },
            handler=spawn,
        ),
        Tool(
            name="destroy",
            description=(
                "Destroy one of YOUR stacks: containers, volumes, network and "
                "worktree. A label outside your namespace is refused before "
                "any command is issued."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "label": label_schema,
                    "force": {
                        "type": "boolean",
                        "description": "Remove the worktree even with "
                                       "uncommitted changes.",
                    },
                },
                "required": ["label"],
                "additionalProperties": False,
            },
            handler=destroy,
        ),
        Tool(
            name="list_mine",
            description=(
                "Your stacks and nobody else's, derived from the Docker "
                "daemon, with the lease expiry of each."
            ),
            input_schema={
                "type": "object", "properties": {},
                "additionalProperties": False,
            },
            handler=list_mine,
        ),
        Tool(
            name="access",
            description=(
                "One of your stacks' BRANCH-ACCESS.md, regenerated from live "
                "state. Read-only."
            ),
            input_schema={
                "type": "object",
                "properties": {"label": label_schema},
                "required": ["label"],
                "additionalProperties": False,
            },
            handler=access,
        ),
    )


def _lease_footer(lease: devspawn.Lease) -> str:
    return (
        f"\n## Lease\n\n"
        f"This stack is leased to `{lease.developer}` and {lease.describe()}; "
        f"it is destroyed automatically then. Destroy it yourself with the "
        f"`destroy` tool when you are done -- the quota is per developer, so a "
        f"stack you have forgotten is a stack you cannot replace.\n"
    )


def _lease_line(
    summary: access_doc.BranchSummary, lease: devspawn.Lease | None,
) -> str:
    if lease is None:
        return f"- `{summary.project}` — no lease (created outside the facade)"
    return f"- `{summary.project}` — {lease.describe()}"


# ---------------------------------------------------------------------------
# methods
# ---------------------------------------------------------------------------


def _method_initialize(
    server: "Server", params: Mapping[str, Any],
) -> dict[str, Any]:
    requested = params.get("protocolVersion")
    version = (
        requested if isinstance(requested, str)
        and requested in SUPPORTED_PROTOCOL_VERSIONS
        else PROTOCOL_VERSION
    )
    return {
        "protocolVersion": version,
        "capabilities": {"tools": {"listChanged": False}},
        "serverInfo": {"name": server.name, "version": SERVER_VERSION},
        "instructions": server.instructions,
    }


def _method_tools_list(
    server: "Server", params: Mapping[str, Any],
) -> dict[str, Any]:
    return {"tools": [tool.describe() for tool in server.tools]}


def _method_tools_call(
    server: "Server", params: Mapping[str, Any],
) -> dict[str, Any]:
    """Dispatch one tool. A tool that RAISES is a result, not a crash.

    The distinction is the whole of MCP's error model and it is load-bearing
    here: a JSON-RPC error means "this frame was wrong", and an agent should
    stop and re-read the schema. A tool result with `isError` means "the frame
    was fine and the operation failed", and the text is the diagnostic the
    agent needs -- for `branch_up` that text carries the `aurora branch down`
    command for the half-built branch that is now on the host.

    `ProtocolError` is deliberately NOT caught here: a missing `name` or an
    unknown tool is a malformed call, and reporting it as a successful call
    that failed would tell an agent to retry something that cannot work.
    """
    name = params.get("name")
    if not isinstance(name, str):
        raise ProtocolError(INVALID_PARAMS, "`name` must name a tool.")
    # THIS server's table, not the module's. A developer session that could
    # reach `TOOLS_BY_NAME` would reach `branch_down`, which takes an
    # arbitrary name -- the whole namespacing design would be a decoration on
    # a table that was still there.
    tool = server.tools_by_name.get(name)
    if tool is None:
        raise ProtocolError(
            INVALID_PARAMS,
            f"unknown tool {name!r}; this server offers "
            f"{sorted(server.tools_by_name)}.",
        )
    arguments = params.get("arguments") or {}
    if not isinstance(arguments, Mapping):
        raise ProtocolError(INVALID_PARAMS, "`arguments` must be an object.")

    try:
        outcome = tool.handler(arguments)
    except ProtocolError:
        raise
    except Exception as exc:                      # noqa: BLE001 - deliberate
        # Every failure this package raises is already a sentence written for
        # a human: a guard refusal names the value it could not prove, and
        # BranchUpFailed carries the teardown command. Those are what the
        # agent needs; a traceback is not, and a dead server is worse.
        # Production's `.env`, so the VALUE leg of the leak check runs here
        # too. This text is an exception message, and `BranchError` embeds the
        # failed argv and the subprocess stderr verbatim -- the likeliest way
        # a secret reaches a developer is a command that failed while carrying
        # one.
        return _tool_payload(
            f"{type(exc).__name__}: {exc}",
            (_production_env_file(),),
            is_error=True,
        )
    return _tool_payload(outcome.text, outcome.env_files, is_error=False)


def _production_env_file() -> Path | None:
    """Production's `.env`, or `None` when this checkout cannot locate it."""
    try:
        return envfile.production_env_path()
    except (identity.IdentityError, OSError):
        return None


def _tool_payload(
    text: str, env_files: Sequence[Path | None], *, is_error: bool
) -> dict[str, Any]:
    """Build a `tools/call` result, and prove it carries no secret.

    The check runs over the SERIALISED payload rather than over `text`, so it
    does not depend on which field a value ended up in -- a key that leaked
    into a structured field would be just as readable to the caller.
    """
    payload = {
        "content": [{"type": "text", "text": text}],
        "isError": is_error,
    }
    _assert_no_secret_in(json.dumps(payload, ensure_ascii=False), env_files)
    return payload


METHODS: dict[str, Callable[["Server", Mapping[str, Any]], dict[str, Any]]] = {
    "initialize": _method_initialize,
    "tools/list": _method_tools_list,
    "tools/call": _method_tools_call,
}

#: Notifications this server understands. A notification never gets a
#: response -- that is JSON-RPC, not a shortcut -- and an UNKNOWN notification
#: is also silent, because replying to one with an error is how a client that
#: sends a harmless extra notification gets an unpaired frame it cannot match.
NOTIFICATIONS = frozenset({"notifications/initialized", "notifications/cancelled"})


# ---------------------------------------------------------------------------
# the loop
# ---------------------------------------------------------------------------


def _error(rpc_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": JSONRPC_VERSION,
        "id": rpc_id,
        "error": {"code": code, "message": message},
    }


def _result(rpc_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": JSONRPC_VERSION, "id": rpc_id, "result": result}


@dataclass(frozen=True)
class Server:
    """One session's tool table. The transport below is shared by every one.

    A dataclass rather than a module global because there are now two tables
    and the developer's one closes over an identity. Making the table an
    attribute is what stops `_method_tools_call` reaching a table that was not
    the caller's -- see the comment there.
    """

    tools: tuple[Tool, ...]
    instructions: str = INSTRUCTIONS
    name: str = SERVER_NAME

    #: Cached: `_method_tools_call` reads it twice per call and the table is
    #: fixed at construction. `cached_property` writes through `__dict__`, so
    #: it works on a frozen dataclass.
    @functools.cached_property
    def tools_by_name(self) -> dict[str, Tool]:
        return {tool.name: tool for tool in self.tools}

    def handle_line(self, line: str) -> dict[str, Any] | None:
        """One inbound frame in, at most one outbound frame out.

        `None` means "write nothing", which is the correct answer to a
        notification and to a blank line. Everything else is a complete
        JSON-RPC response object.
        """
        text = line.strip()
        if not text:
            return None
        try:
            message = json.loads(text)
        except ValueError as exc:
            # id is null: JSON-RPC requires it when the id could not be read,
            # and a client matching responses by id needs the frame anyway.
            return _error(None, PARSE_ERROR, f"Parse error: {exc}")

        if not isinstance(message, Mapping):
            return _error(
                None, INVALID_REQUEST,
                "Invalid Request: a JSON-RPC message must be an object. "
                "Batches are not supported by this server.",
            )

        rpc_id = message.get("id")
        method = message.get("method")
        is_request = "id" in message and rpc_id is not None

        if not isinstance(method, str):
            if not is_request:
                return None
            return _error(
                rpc_id, INVALID_REQUEST, "Invalid Request: no `method`."
            )

        params = message.get("params") or {}
        if not isinstance(params, Mapping):
            if not is_request:
                return None
            return _error(rpc_id, INVALID_PARAMS, "`params` must be an object.")

        if not is_request:
            # A notification. Nothing this server offers changes state on one,
            # so unknown notifications are ignored rather than answered.
            return None

        handler = METHODS.get(method)
        if handler is None:
            if method in NOTIFICATIONS:
                return _error(
                    rpc_id, INVALID_REQUEST,
                    f"{method!r} is a notification and must not carry an `id`.",
                )
            return _error(
                rpc_id, METHOD_NOT_FOUND,
                f"Method not found: {method!r}. This server implements "
                f"{sorted(METHODS)} and the `notifications/initialized` "
                "notification, and nothing else.",
            )

        try:
            return _result(rpc_id, handler(self, params))
        except ProtocolError as exc:
            return _error(rpc_id, exc.code, str(exc))
        except Exception as exc:                  # noqa: BLE001 - deliberate
            # The last net. Reaching it means a bug in this module rather than
            # in a tool (tools are caught in `_method_tools_call`), so the
            # traceback goes to stderr where a human debugging the server can
            # find it, and the caller gets a frame instead of a closed pipe.
            traceback.print_exc(file=sys.stderr)
            return _error(rpc_id, INTERNAL_ERROR, f"{type(exc).__name__}: {exc}")

    def serve(
        self, stdin: BinaryIO | None = None, stdout: BinaryIO | None = None,
    ) -> int:
        """Read frames until EOF. Returns 0; it does not raise on a bad frame.

        Binary streams, deliberately: the tests write BYTES to a pipe, which is
        what the transport actually is. Reading text would let a decoding
        difference between the test and the real entry point hide here.
        """
        stdin = sys.stdin.buffer if stdin is None else stdin
        stdout = sys.stdout.buffer if stdout is None else stdout

        for raw in stdin:
            response = self.handle_line(raw.decode("utf-8", "replace"))
            if response is not None:
                _emit(stdout, response)
        return 0


ADMIN_SERVER = Server(tools=TOOLS)


def developer_server(developer: str) -> Server:
    """The server a developer's agent talks to. One identity, fixed at birth.

    The identity is a CONSTRUCTOR ARGUMENT, supplied by the privileged process
    that started this server -- in practice `ops/aurora-spawn-broker`, one
    socket per developer. Which socket a container can open is a bind-mount
    decision made by the operator, so the identity is carried by the
    filesystem and never by anything the developer can write.
    """
    slug = devspawn.slug_of(developer)
    return Server(
        tools=_developer_tools(developer),
        instructions=DEVELOPER_INSTRUCTIONS.replace("{prefix}", f"{slug}-"),
        name=f"{SERVER_NAME}-{slug}",
    )


def encode(message: Mapping[str, Any]) -> bytes:
    """One response, one line, UTF-8, newline-terminated.

    `sort_keys` and compact `separators` so the transcript the tests pin is
    deterministic byte for byte; a wire format whose whitespace depends on a
    default cannot be pinned against a recording at all.

    `ensure_ascii=False` deliberately: with the default, a non-ASCII byte in a
    secret would be emitted as `\\uXXXX` escapes and the substring check in
    `_assert_no_secret_in` would not find it. JSON escapes newlines inside
    strings, so a document with newlines in it still occupies exactly one
    line -- which is the framing this transport has.
    """
    return json.dumps(
        message, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8") + b"\n"


def _emit(stream: BinaryIO, message: Mapping[str, Any]) -> bytes:
    """Write one frame, refusing to write one that carries a secret.

    Belt and braces over `_tool_payload`'s check, and not redundant with it:
    this one also covers ERROR frames, which are built from exception text
    that no tool composed and no test has seen. Name leg only -- this layer
    has no branch in hand and so no `.env` to read.

    A refusal here cannot re-raise: the caller is a loop whose job is to keep
    answering. It substitutes a frame that names neither the variable nor the
    value, because a message saying "I refused to leak TS_AUTHKEY" has put the
    variable's name on the wire to say so.

    THE ONE DEGRADATION, and why it is provably not a hole. When the manifest
    itself is unreadable -- an `aurora-cli:local` container started with no
    repository mounted -- this check cannot run at all. It passes the frame
    through, and that is safe by a coupling rather than by optimism:
    `_tool_payload` calls the SAME function, so an unreadable manifest means
    no `tools/call` ever produced a result. Every frame that can reach here in
    that state is built from this module's own constants. The alternative --
    refusing everything -- is an image that cannot complete a handshake and
    therefore cannot tell its caller what is wrong.
    `test_an_unreadable_manifest_stops_tool_results_and_not_the_handshake`
    pins both halves of that coupling, because the degradation is only sound
    while both hold.
    """
    line = encode(message)
    try:
        _assert_no_secret_in(line.decode("utf-8"))
    except access_doc.AccessDocError:
        line = encode(_error(
            message.get("id"), INTERNAL_ERROR,
            "the server refused to emit a response that would have carried a "
            "value marked secret in the branch environment manifest.",
        ))
    except (envfile.ManifestError, OSError):
        pass
    stream.write(line)
    stream.flush()
    return line


#: The admin surface as module functions. `aurora-cli/tests/test_mcp.py` pins
#: the wire against a recorded transcript through these two names, so they are
#: bindings to `ADMIN_SERVER`'s methods rather than a second spelling.
handle_line = ADMIN_SERVER.handle_line
serve = ADMIN_SERVER.serve
