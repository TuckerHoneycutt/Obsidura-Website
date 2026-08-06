"""`python -m aurora_cli` -- the argparse entry point behind the `aurora` shim.

Every subcommand here is a thin adapter. The work, the refusals and the
document rendering all live in `aurora_cli.branch`, because Task 11's MCP
facade must call the SAME functions -- a second rendering of a branch's access
document, or a second enumeration of live branches, is the drift this
project's ledger keeps recording.

`branch up` prints `BRANCH-ACCESS.md` verbatim (spec 4.1 step 9, 7.4). It is
the same string the file on disk carries and the same string MCP will return.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Make the package importable when this file is executed by path
# (`python aurora-cli/aurora_cli/__main__.py`) rather than as a module. The
# directory that must be on sys.path is the package's PARENT -- parents[1] --
# not the repository root; the repository root contains no importable
# `aurora_cli`. Under `python -m` this is already true and the insert is a
# no-op, which is the point: one code path, no branch on how we were started.
_PACKAGE_PARENT = str(Path(__file__).resolve().parents[1])
if _PACKAGE_PARENT not in sys.path:
    sys.path.insert(0, _PACKAGE_PARENT)

from aurora_cli import (  # noqa: E402  (after the sys.path fix)
    access_doc, branch, devspawn, forgejo_token, guards, identity, mcp,
    overlay, tailnet,
)
from aurora_cli import runtime as runtimes  # noqa: E402


def _add_runtime_flag(parser: argparse.ArgumentParser, *, upward: bool) -> None:
    """`--runtime docker|podman` on one subcommand.

    Two wordings, because the flag means two different things. On `up` it is a
    CHOICE and the default is docker. On the commands that address an existing
    branch it is at most a confirmation: `up` records the runtime in the
    worktree and that record wins, so passing a contradicting value is refused
    rather than obeyed (`branch.teardown_runtime`).

    `choices` is left to `runtime.resolve_runtime` rather than given to
    argparse, so that the flag and `$AURORA_BRANCH_RUNTIME` are validated by
    the same code and produce the same message. An argparse `choices` error
    would say nothing about why falling back to docker is not on offer.
    """
    parser.add_argument(
        "--runtime", default=None, metavar="NAME",
        help=(
            f"which container runtime to build this branch on: "
            f"{' or '.join(runtimes.RUNTIMES)} "
            f"(default {runtimes.DEFAULT_RUNTIME}, or ${runtimes.RUNTIME_ENV_VAR}). "
            "podman points this branch's compose at the user's ROOTLESS podman "
            "socket, so its containers, images and build cache are in a "
            "different daemon from production's -- not merely guarded away "
            "from them."
            if upward else
            f"the runtime this branch is on ({' or '.join(runtimes.RUNTIMES)}). "
            "Normally unnecessary: `branch up` records it in the worktree and "
            "the record wins. Refused if it contradicts that record."
        ),
    )


def _cmd_branch_up(args: argparse.Namespace) -> int:
    """`aurora branch up <name>`, then its access document, verbatim.

    `refresh_branch_docs` is called HERE rather than inside `branch_up`
    deliberately: it regenerates `<production>/.worktrees/INDEX.md`, and the
    test suite runs the lifecycle functions against real Docker objects. A
    write into production's checkout on every teardown test is not a thing to
    arrange by accident. See `branch.refresh_branch_docs`.
    """
    result = branch.branch_up(
        args.name,
        from_ref=args.from_ref,
        no_seed=args.no_seed,
        seed_strategy=args.seed,
        without=tuple(args.without or ()),
        devs=args.devs,
        force=args.force,
        build=not args.no_build,
        runtime=args.runtime,
        limits=args.limits,
    )
    doc_path, index = branch.refresh_branch_docs(result)
    document = doc_path.read_text(encoding="utf-8")

    if args.json:
        print(json.dumps({
            "name": result.name,
            "requested_name": result.requested_name,
            "project": result.project,
            "hostname": result.paths.hostname,
            "domain": result.domain,
            "worktree": str(result.paths.worktree),
            "devs": list(result.devs),
            "excluded": list(result.excluded),
            "runtime": result.runtime,
            "seeded": result.seeded,
            "urls": result.urls(),
            "notes": result.notes,
            "access_doc": str(doc_path),
            "index": str(index),
            # The document itself, so a JSON consumer is not a second-class
            # reader of the one artefact spec 7.4 calls the product.
            "document": document,
        }, indent=2, sort_keys=True))
        return 0

    # Verbatim. Spec 7.4: this string is what the CLI prints, what the file
    # holds and what MCP returns.
    print(document, end="")
    return 0


def _cmd_branch_down(args: argparse.Namespace) -> int:
    """`aurora branch down <name>` / `--all`.

    Task 9 built `branch_down` and `branch_down_all` but wired neither to the
    CLI, so the teardown command printed by `branch up`'s failure path and by
    every access document named a subcommand that did not exist. Wired here.
    """
    if args.all:
        results = branch.branch_down_all(force=args.force, runtime=args.runtime)
    elif args.name:
        results = [
            branch.branch_down(args.name, force=args.force, runtime=args.runtime)
        ]
    else:
        print("error: name a branch, or pass --all", file=sys.stderr)
        return 1

    index = branch.write_index()
    payload = [{
        "project": r.project,
        "worktree": str(r.worktree),
        "used_fallback": r.used_fallback,
        "containers_removed": list(r.containers_removed),
        "volumes_removed": list(r.volumes_removed),
        "networks_removed": list(r.networks_removed),
        "worktree_removed": r.worktree_removed,
        "notes": list(r.notes),
    } for r in results]

    if args.json:
        print(json.dumps({"index": str(index), "torn_down": payload},
                         indent=2, sort_keys=True))
        return 0

    # `branch.render_teardown`, not a local loop: Task 11's MCP facade reports
    # the same event, and an operator reading a terminal and an agent reading a
    # tool result must not be told different things about what is still on the
    # host -- particularly the RESIDUE notes.
    print(branch.render_teardown(results, index), end="")
    return 0


def _cmd_branch_ls(args: argparse.Namespace) -> int:
    """Production's derived identity, and every branch stack on the daemon.

    The identity keys stay at the top level of the JSON payload: Task 1's
    end-to-end shim tests read them from there, and this subcommand is still
    the answer to "what does this tool think production is?".
    """
    facts = identity.describe()
    branches = branch.branch_ls(runtime=args.runtime)
    if args.json:
        payload = dict(facts)
        payload["branches"] = [{
            "name": b.name,
            "project": b.project,
            "domain": b.domain,
            "worktree": str(b.worktree),
            "worktree_exists": b.worktree_exists,
            "containers": len(b.containers),
            "running": b.running,
        } for b in branches]
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    width = max(len(k) for k in facts)
    for key in sorted(facts):
        print(f"{key.replace('_', ' '):<{width}}  {facts[key]}")
    print()
    if not branches:
        print("no branch stacks are running")
        return 0
    for b in branches:
        missing = "" if b.worktree_exists else "  (WORKTREE MISSING)"
        print(f"{b.name:<20} {b.project:<24} {b.running}/{len(b.containers)} "
              f"running  https://{b.domain}/{missing}")
    return 0


def _cmd_branch_access(args: argparse.Namespace) -> int:
    """The branch's access document, regenerated from live state, verbatim."""
    print(branch.branch_access(args.name), end="")
    return 0


def _cmd_branch_shell(args: argparse.Namespace) -> int:
    """Exec into one of a branch's containers. Does not return on success."""
    branch.branch_shell(args.name, args.service, tuple(args.command or ()),
                        runtime=args.runtime)
    return 0


def _cmd_branch_rebuild(args: argparse.Namespace) -> int:
    branch.branch_rebuild(
        args.name, tuple(args.service or ()), build=not args.no_build,
        runtime=args.runtime,
    )
    print(f"rebuilt {', '.join(args.service) or 'every service'} in "
          f"{identity.branch_paths(args.name).project}")
    return 0


def _cmd_branch_overlay(args: argparse.Namespace) -> int:
    """Re-render a live branch's overlay after its service set changed."""
    path, stale = branch.branch_overlay(
        args.name, check=args.check, limits=args.limits,
    )
    if not stale:
        print(f"{path} already covers every service")
        return 0
    if args.check:
        print(
            f"{path} is STALE: the branch has services it does not reset, so "
            "they keep production's container_name and publish host ports. "
            f"Run `aurora branch overlay {args.name}`.",
            file=sys.stderr,
        )
        return 1
    print(f"re-rendered {path}")
    return 0


def _cmd_mcp(args: argparse.Namespace) -> int:
    """`aurora mcp` -- the stdio MCP facade (spec D5, 7.3).

    A one-line adapter on purpose. Everything the server does lives in
    `aurora_cli.mcp`, which dispatches to the same `aurora_cli.branch`
    functions the subcommands above call; the two surfaces are thin skins on
    one implementation, and `aurora-cli/tests/test_mcp.py` proves it by
    patching a `branch` function and observing it through both.

    `--as-developer` swaps the tool table for one scoped to that developer's
    namespace (2026-07-31). It is a START-UP argument because it is the whole
    of the authorisation model: whoever starts this process decides whose
    stacks the caller on stdin can touch, and the caller has no way to say
    otherwise. `ops/aurora-spawn-broker` is what starts it in production, one
    unix socket per developer.
    """
    developer = args.as_developer or os.environ.get(devspawn.DEVELOPER_VAR)
    if developer:
        return mcp.developer_server(developer).serve()
    return mcp.serve()


def _cmd_dev_spawn_ls(args: argparse.Namespace) -> int:
    """Every leased stack on the host, and how long each has left."""
    rows = [
        (s.project, devspawn.read_lease(s.worktree)) for s in branch.branch_ls()
    ]
    if args.json:
        print(json.dumps([{
            "project": project,
            "developer": lease.developer if lease else None,
            "expires_at": lease.expires_at if lease else None,
            "leased": lease is not None,
        } for project, lease in rows], indent=2, sort_keys=True))
        return 0
    if not rows:
        print("no branch stacks are running")
        return 0
    for project, lease in rows:
        if lease is None:
            print(f"{project:<32} (no lease — created outside the facade)")
        else:
            print(f"{project:<32} {lease.developer:<20} {lease.describe()}")
    return 0


def _cmd_dev_spawn_reap(args: argparse.Namespace) -> int:
    """Destroy every leased stack whose lease has expired.

    Intended for cron. `--dry-run` is the default-adjacent safety: this is a
    destructive sweep driven by a clock, and the first thing an operator wants
    is to see what it WOULD remove.
    """
    if args.dry_run:
        verb = "would destroy"
        candidates = devspawn.expired_candidates(branch.branch_ls())
    else:
        verb = "destroyed"
        candidates = devspawn.reap(force=args.force)
    for candidate in candidates:
        print(f"{verb} {candidate.describe()}")
    if not candidates:
        print("nothing has expired")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aurora",
        description="Branch lifecycle for this stack.",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="emit machine-readable JSON instead of aligned text",
    )
    sub = parser.add_subparsers(dest="group", required=True)

    # NOT named `branch`: that would shadow the imported `branch` module
    # inside this function, and the shadow only shows up when a help
    # string reads a module constant -- i.e. at `--help`, not at import.
    branch_group = sub.add_parser(
        "branch", help="create, inspect and destroy branch stacks")
    branch_sub = branch_group.add_subparsers(dest="action", required=True)
    ls = branch_sub.add_parser(
        "ls", help="the derived production identity, and every live branch"
    )
    _add_runtime_flag(ls, upward=False)
    ls.set_defaults(func=_cmd_branch_ls)

    access = branch_sub.add_parser(
        "access",
        help="print a branch's BRANCH-ACCESS.md, regenerated from live state",
    )
    access.add_argument("name")
    access.set_defaults(func=_cmd_branch_access)

    shell = branch_sub.add_parser(
        "shell", help="exec into a branch container, resolved from its labels",
    )
    shell.add_argument("name")
    shell.add_argument("service", help="a compose SERVICE key, not a container name")
    shell.add_argument(
        "command", nargs=argparse.REMAINDER,
        help=f"what to run (default: {' '.join(branch.DEFAULT_SHELL)})",
    )
    _add_runtime_flag(shell, upward=False)
    shell.set_defaults(func=_cmd_branch_shell)

    rebuild = branch_sub.add_parser(
        "rebuild",
        help="rebuild and restart services in this branch's project only",
    )
    rebuild.add_argument("name")
    rebuild.add_argument("service", nargs="*", help="services; default all")
    rebuild.add_argument(
        "--no-build", action="store_true",
        help="restart without rebuilding the image",
    )
    _add_runtime_flag(rebuild, upward=False)
    rebuild.set_defaults(func=_cmd_branch_rebuild)

    down = branch_sub.add_parser(
        "down", help="destroy a branch stack, its volumes and its worktree",
    )
    down.add_argument("name", nargs="?", default=None)
    down.add_argument(
        "--all", action="store_true",
        help="every branch on the daemon, derived from container labels",
    )
    down.add_argument(
        "--force", action="store_true",
        help="remove the worktree even with uncommitted changes",
    )
    _add_runtime_flag(down, upward=False)
    down.set_defaults(func=_cmd_branch_down)

    up = branch_sub.add_parser(
        "up", help="create a branch stack: worktree, .env, seed, compose, hook",
    )
    up.add_argument("name", help="the branch name; sanitised to one DNS label")
    up.add_argument(
        "--from", dest="from_ref", metavar="REF", default=None,
        help="create the branch from REF; fails if the branch already exists. "
             "Omit to reuse an existing branch.",
    )
    up.add_argument(
        "--limits", default=None,
        help="resource ceilings for this branch: a profile in "
             "branch-limits.yaml, or `none` for no ceilings at all (recorded "
             "in the access document). Unset, the committed overlay's "
             "ceilings apply.",
    )
    up.add_argument(
        "--devs", default=None,
        help="which developers get an agent: a comma-separated list, `all`, or "
             f"`none`. Unset, ${branch.DEV_ENV_VAR} is tried and then "
             "`git config user.name`; if neither resolves this fails rather "
             "than guessing.",
    )
    up.add_argument(
        "--without", action="append", metavar="SERVICE", default=[],
        help="exclude a service (repeatable). See branch-services.yaml.",
    )
    up.add_argument(
        "--no-seed", action="store_true",
        help="do not copy production's state. The branch's Forgejo, Hermes and "
             "AFFiNE start empty.",
    )
    up.add_argument(
        "--seed", default="filecopy", metavar="STRATEGY",
        help="seeding strategy (default: filecopy)",
    )
    up.add_argument(
        "--no-build", action="store_true",
        help="skip `--build` on the first full `up`",
    )
    up.add_argument(
        "--force", action="store_true",
        help="override the resource guard. The override is recorded in the "
             "branch's access document.",
    )
    _add_runtime_flag(up, upward=True)
    up.set_defaults(func=_cmd_branch_up)

    overlay_cmd = branch_sub.add_parser(
        "overlay",
        help="re-render a live branch's compose.branch.yml after its service "
             "set changed (e.g. a developer was provisioned into it)",
    )
    overlay_cmd.add_argument("name")
    overlay_cmd.add_argument(
        "--limits", default=None,
        help="resource profile from branch-limits.yaml, or `none` for no "
             "ceilings at all",
    )
    overlay_cmd.add_argument(
        "--check", action="store_true",
        help="exit 1 if the overlay is stale; write nothing",
    )
    overlay_cmd.set_defaults(func=_cmd_branch_overlay)

    mcp_parser = sub.add_parser(
        "mcp",
        help="serve the MCP facade over stdio: line-delimited JSON-RPC 2.0",
        description="Speaks MCP over stdin/stdout. No daemon, no port, no "
                    "always-on container (spec 12 option 3 was rejected as "
                    "slop). The tools are the same functions `aurora branch "
                    "...` calls.",
    )
    mcp_parser.add_argument(
        "--as-developer", metavar="USER", default=None,
        help="serve the DEVELOPER tool table for USER: spawn/destroy/"
             "list_mine/access, scoped to `br-<user>-*`. The identity is set "
             f"here or in ${devspawn.DEVELOPER_VAR}, never by the caller.",
    )
    mcp_parser.set_defaults(func=_cmd_mcp)

    spawn_group = sub.add_parser(
        "dev-spawn",
        help="operate the developer-facing spawn facade (host side)",
    )
    spawn_sub = spawn_group.add_subparsers(dest="action", required=True)

    spawn_ls = spawn_sub.add_parser(
        "ls", help="every branch stack, with the lease on each")
    spawn_ls.set_defaults(func=_cmd_dev_spawn_ls)

    spawn_reap = spawn_sub.add_parser(
        "reap", help="destroy every stack whose lease has expired")
    spawn_reap.add_argument(
        "--dry-run", action="store_true",
        help="print what would be destroyed and destroy nothing",
    )
    spawn_reap.add_argument(
        "--no-force", dest="force", action="store_false", default=True,
        help="keep a worktree that has uncommitted changes instead of "
             "discarding it; the sweep forces by default because a lease that "
             "expired four hours ago is not a session anyone is still in",
    )
    spawn_reap.set_defaults(func=_cmd_dev_spawn_reap)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    # BranchUpFailed FIRST and alone: it subclasses BranchError, and exit 2
    # is what tells a caller "something is on the host and needs `branch
    # down`" apart from "nothing was created". Its message already carries
    # the exact teardown command.
    except branch.BranchUpFailed as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    # Deliberately not a traceback. Every one of these messages names the
    # value that could not be resolved or proven, and that value is the whole
    # diagnostic; a stack trace buries it. A guard or a policy refusing is a
    # correct outcome, not a crash, so both land here.
    except (
        identity.IdentityError,
        branch.BranchError,
        guards.GuardViolation,
        devspawn.SpawnDenied,
        access_doc.AccessDocError,
        runtimes.RuntimeSelectionError,
        # Both of these were reachable and BOTH escaped as tracebacks.
        # `overlay.OverlayError`: `aurora branch overlay <name> --limits typo`
        # goes straight to `overlay.resolve_limits`, caught nowhere.
        # `tailnet.TailnetError`: `resolve_branch_authkey` -> `oauth_client()`
        # raises on half an OAuth client, and it runs BEFORE `branch_up`'s
        # `try`, so `BranchUpFailed` does not wrap it -- a typo in production's
        # `.env` printed a stack trace instead of the refusal written for it.
        overlay.OverlayError,
        tailnet.TailnetError,
        # Not relying on `branch_up`'s blanket `except Exception` to wrap this:
        # `branch_overlay` / `branch_rebuild` are reachable callers too.
        forgejo_token.ForgejoTokenError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
