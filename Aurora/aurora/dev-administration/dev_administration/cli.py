from __future__ import annotations

import os
from pathlib import Path

import typer
import yaml

from dev_administration.agents_compose import (
    agent_specs, render_agents_compose,
)
from dev_administration.models import DeveloperConfig, parse_developers_yaml
from dev_administration.notifier import get_notifier
from dev_administration.provision import (
    reconcile as do_reconcile,
    ProvisionConfig,
    deprovision_developer as do_deprovision,
)
from dev_administration.docker_utils import (
    container_status, list_volumes, stop_and_remove_container, volume_exists,
)
from dev_administration.forgejo_utils import find_oauth2_app, delete_oauth2_app
from dev_administration.forgejo_org import user_exists
from dev_administration.forgejo_access import (
    DEFAULT_SCOPES, AccessError, _assert_managed, authorize_repo,
    deauthorize_repo, default_branch_protection, list_tokens, mint_token,
    reason, repo_permission, resolve_shared_repos, revoke_token, set_active,
    token_name,
)
from dev_administration.project import agent_volume, current_project, project_services

app = typer.Typer(
    help="Aurora orchestrator — provision and manage per-developer Hermes containers",
    no_args_is_help=True,
)


def _load_devs() -> list[DeveloperConfig]:
    dev_path = os.environ.get("DEVELOPERS_YAML", "developers.yaml")
    return parse_developers_yaml(Path(dev_path))


def _load_config() -> ProvisionConfig:
    return ProvisionConfig(
        forgejo_url=os.environ["FORGEJO_URL"],
        forgejo_token=os.environ["FORGEJO_ADMIN_TOKEN"],
        aurora_profile_url=os.environ["AURORA_PROFILE_URL"],
        # No production default: a wrong domain writes production URLs into a
        # branch's Caddy config and its OAuth redirect URIs.
        domain=os.environ["DOMAIN_NAME"],
        # Empty, not a literal: provision.reconcile resolves Caddy from this
        # project's compose labels. CADDY_CONTAINER remains an override.
        caddy_container=os.environ.get("CADDY_CONTAINER", ""),
        authorized_keys_path=os.environ.get("AUTHORIZED_KEYS", "/app/authorized_keys"),
        # `project` is deliberately NOT passed. ProvisionConfig.__post_init__
        # fills it from project.current_project(), which reads this
        # container's own compose LABEL first and COMPOSE_PROJECT_NAME only as
        # a host-CLI fallback. Reading the env var here instead would invert
        # that precedence, and spec §4.1 renders a branch's .env FROM
        # production's -- so a branch whose COMPOSE_PROJECT_NAME override
        # failed would inherit PRODUCTION's name and act on it. The label
        # cannot lie; the env var can.
        upstream_mode=os.environ.get("AGENT_UPSTREAM_MODE", "published"),
        agent_env_dir=os.environ.get("AGENT_ENV_DIR", "/agent-env"),
        agents_compose_path=os.environ.get("AGENTS_COMPOSE_PATH", ""),
    )


def _get_notifier():
    name = os.environ.get("DEV_ADMIN_NOTIFIER", "stdout")
    kwargs = {}
    if name == "file":
        kwargs["path"] = os.environ.get("DEV_ADMIN_NOTIFIER_FILE", "/app/events.log")
    return get_notifier(name, **kwargs)


@app.command()
def reconcile():
    """Sync Docker state with developers.yaml.
    Provisions new developers, deprovisions removed ones, verifies existing ones.
    """
    devs = _load_devs()
    config = _load_config()
    notifier = _get_notifier()
    events = do_reconcile(devs, notifier, config)
    typer.echo(f"Reconciled {len(devs)} developers. {len(events)} events emitted.")


@app.command("render-agents")
def render_agents(
    output: str = typer.Option(
        "compose.agents.yml", "--output", "-o",
        help="Where to write the fragment (repo root by default)",
    ),
    check: bool = typer.Option(
        False, "--check",
        help="Exit 1 if the file on disk differs from a fresh render",
    ),
):
    """Regenerate compose.agents.yml from developers.yaml.

    Run after every developers.yaml change and commit the result: the file is
    `include:`d by compose.yml and Compose fails hard on a missing include,
    so it cannot be gitignored.
    """
    devs = _load_devs()
    # Neither the base port nor the publish mode is read from the environment.
    # This command writes a TRACKED file that three readers must agree on --
    # this renderer, tests/test_repo_conformance.py's drift check, and
    # reconcile's compose.stale check. Any env input makes them disagree:
    # `AGENT_BASE_PORT=9200 render-agents` wrote a file the drift test
    # rejected, and reconcile then emitted a permanent spurious compose.stale
    # whose own remediation rewrote the file and turned the drift test
    # permanently red. To move the ports, change DEFAULT_BASE_PORT.
    #
    # publish_ports is likewise fixed: running this in a branch with
    # AGENT_UPSTREAM_MODE=service would rewrite the committed fragment to the
    # no-ports variant. A branch drops its ports via `ports: !reset []` in
    # compose.branch.yml (spec 4.2), not by re-rendering. This
    # command writes a TRACKED file, and the drift test always renders the
    # published variant; running it in a branch with
    # AGENT_UPSTREAM_MODE=service would silently rewrite the committed
    # fragment to the no-ports form, dirty the worktree and redden the drift
    # test — the exact failure the header says profiles exist to avoid.
    # A branch drops its ports via `ports: !reset []` in compose.branch.yml
    # (spec §4.2), not by re-rendering this file.
    body = render_agents_compose(agent_specs(devs))

    path = Path(output)
    if check:
        current = path.read_text() if path.exists() else ""
        if current != body:
            typer.echo(
                f"{output} is stale — run `dev-admin render-agents` and commit it.",
                err=True,
            )
            raise typer.Exit(1)
        typer.echo(f"{output} is up to date ({len(devs)} developers).")
        return

    path.write_text(body)
    typer.echo(f"Wrote {output} for {len(devs)} developers.")


def _overlay_module():
    """`aurora_cli.overlay`, imported lazily and only for this one command.

    Deliberately NOT a module-level import. `aurora_cli` lives in a sibling
    top-level directory and is NOT inside the image this package is built into
    — the Dockerfile copies nothing but `/app` and the compose file binds only
    `./dev-administration`. A module-level import would therefore break every
    OTHER command in the container, including `reconcile`, which is what the
    container is for. It would also add a runtime dependency to a package the
    plan restricts to typer + pyyaml.

    Rendering the overlay needs the WHOLE repository resolved by `docker
    compose config`, so it is a host-side command in the first place, exactly
    like `render-agents` — which also writes a tracked file that lives on the
    host.
    """
    import sys

    # <repo>/dev-administration/dev_administration/cli.py
    repo_root = Path(__file__).resolve().parents[2]
    package_dir = str(repo_root / "aurora-cli")
    if package_dir not in sys.path:
        sys.path.insert(0, package_dir)
    try:
        from aurora_cli import overlay
    except ImportError as exc:      # pragma: no cover - environment, not logic
        raise typer.BadParameter(
            f"aurora_cli is not importable from {package_dir}: {exc}. "
            "render-branch-override resolves the whole repository with "
            "`docker compose config`, so it must be run on the HOST from a "
            "checkout, not inside the dev-admin container."
        ) from exc
    return overlay


@app.command("render-branch-override")
def render_branch_override(
    output: str = typer.Option(
        "", "--output", "-o",
        help="Where to write the overlay (repo root by default)",
    ),
    check: bool = typer.Option(
        False, "--check",
        help="Exit 1 if the file on disk differs from a fresh render",
    ),
):
    """Regenerate compose.branch.yml from the resolved compose configuration.

    The overlay is the only configuration difference between production and a
    branch: it resets every daemon-global `container_name` and every published
    `ports` entry, and adds the Tailscale sidecar Caddy is flipped into.

    Run after ANY change to compose.yml, affine/compose.yml, compose.agents.yml
    or developers.yaml, and commit the result — Compose's `-f` is a hard error
    on a missing file, the same reason compose.agents.yml is committed.

    Nothing here is read from the environment except COMPOSE_PROFILES, which is
    forced to `*`. This command writes a TRACKED file that three readers must
    agree on, and the drift test renders it with every profile active; a render
    that saw only the active profiles would silently drop every per-developer
    agent from the enumeration and produce a branch that cannot start.
    """
    overlay = _overlay_module()
    root = Path(__file__).resolve().parents[2]
    path = Path(output) if output else overlay.overlay_path(root)

    body = overlay.render_overlay(overlay.resolve_config(root), root)

    if check:
        current = path.read_text() if path.exists() else ""
        if current != body:
            typer.echo(
                f"{path.name} is stale — run "
                "`dev-admin render-branch-override` and commit it.",
                err=True,
            )
            raise typer.Exit(1)
        typer.echo(f"{path.name} is up to date.")
        return

    path.write_text(body)
    resets = overlay.overlay_resets(body)
    typer.echo(f"Wrote {path} — {len(resets)} services reset.")


@app.command()
def status():
    """Show all developers, their containers, volumes, and health status."""
    devs = _load_devs()
    project = current_project()

    # Both lookups are scoped to THIS project, and both had to change in M4.
    #
    # Volumes: the migration moved agent state to `<project>_hermes-<u>-home`.
    # A `hermes-` prefix scan matches only the stale unprefixed ROLLBACK
    # copies, so every developer rendered as "—" (or, worse, named a volume
    # reconcile will never touch again) while the live data was intact.
    #
    # Containers: `list_containers("hermes-")` was a global name scan across
    # the whole daemon, so a branch's `dev-admin status` reported PRODUCTION's
    # agents — the cross-project disclosure §5.3 exists to stop.
    services = project_services(project)
    volumes = set(list_volumes(f"{project}_hermes-"))

    typer.echo(f"\n{'Developer':<15} {'Container':<20} {'Volume':<38} {'Status':<15}")
    typer.echo(f"{'─'*15} {'─'*20} {'─'*38} {'─'*15}")

    for dev in devs:
        container = services.get(f"hermes-{dev.username}")
        vol = agent_volume(dev.username, project)
        status_str = "—"
        if container:
            status_str = container_status(container) or "unknown"
        typer.echo(
            f"{dev.username:<15} {container or '—':<20} "
            f"{vol if vol in volumes else '—':<38} {status_str:<15}"
        )

    # Orphaned volumes
    orphaned = volumes - {agent_volume(d.username, project) for d in devs}
    for vol in sorted(orphaned):
        typer.echo(f"{'(orphaned)':<15} {'—':<20} {vol:<38} {'preserved':<15}")


@app.command()
def doctor():
    """Health check: all containers reachable, volumes exist, OAuth2 apps valid."""
    typer.echo("Doctor not yet implemented — run 'dev-admin status' for now.")


@app.command()
def add(
    username: str = typer.Argument(..., help="Developer username"),
    display_name: str = typer.Option("", "--display-name", "-n", help="Display name"),
    forgejo_user: str = typer.Option("", "--forgejo-user", "-u", help="Forgejo username"),
):
    """Add a developer entry to developers.yaml. Does not provision."""
    dev_path = Path(os.environ.get("DEVELOPERS_YAML", "developers.yaml"))

    data = yaml.safe_load(dev_path.read_text()) if dev_path.exists() else {"developers": []}
    if data is None:
        data = {"developers": []}
    devs = data.get("developers", [])

    if any(d["username"] == username for d in devs):
        typer.echo(f"Developer '{username}' already exists.", err=True)
        raise typer.Exit(1)

    devs.append({
        "username": username,
        "display_name": display_name or username,
        "forgejo_user": forgejo_user or username,
    })
    data["developers"] = devs
    dev_path.write_text(yaml.dump(data, default_flow_style=False))
    typer.echo(f"Added '{username}'. Run 'dev-admin reconcile' to provision.")


@app.command()
def remove(username: str = typer.Argument(..., help="Developer username to remove")):
    """Remove a developer entry from developers.yaml. Does not deprovision."""
    dev_path = Path(os.environ.get("DEVELOPERS_YAML", "developers.yaml"))

    data = yaml.safe_load(dev_path.read_text())
    devs = data.get("developers", [])
    original_len = len(devs)
    devs = [d for d in devs if d["username"] != username]
    data["developers"] = devs
    dev_path.write_text(yaml.dump(data, default_flow_style=False))

    if len(devs) == original_len:
        typer.echo(f"Developer '{username}' not found.", err=True)
        raise typer.Exit(1)
    typer.echo(f"Removed '{username}'. Run 'dev-admin reconcile' to deprovision.")


@app.command()
def provision(
    username: str = typer.Argument(..., help="Developer username"),
    display_name: str = typer.Option("", "--display-name", "-n", help="Display name"),
    forgejo_user: str = typer.Option("", "--forgejo-user", "-u", help="Forgejo username"),
    email: str = typer.Option("", "--email", "-e", help="Email (for Forgejo account)"),
    skip_verify: bool = typer.Option(False, "--skip-verify", help="Don't run checks after"),
):
    """One-liner: add a developer to developers.yaml, provision, and verify.

    Equivalent to `add` + `reconcile` + `verify`. This is the normal way to
    onboard someone; the individual commands exist for finer control.
    """
    dev_path = Path(os.environ.get("DEVELOPERS_YAML", "developers.yaml"))
    data = yaml.safe_load(dev_path.read_text()) if dev_path.exists() else None
    if not data:
        data = {"developers": []}
    devs = data.get("developers") or []

    if not any(d.get("username") == username for d in devs):
        devs.append({
            "username": username,
            "display_name": display_name or username,
            "forgejo_user": forgejo_user or username,
            "email": email or f"{username}@obsidura.local",
        })
        data["developers"] = devs
        dev_path.write_text(yaml.dump(data, default_flow_style=False))
        typer.echo(f"Added '{username}' to developers.yaml")
    else:
        typer.echo(f"'{username}' already in developers.yaml — reconciling")

    events = do_reconcile(_load_devs(), _get_notifier(), _load_config())
    typer.echo(f"Reconcile complete ({len(events)} events).")

    if skip_verify:
        return
    import time as _time

    from dev_administration.verify import render, run_checks

    typer.echo("\nVerifying pipeline (allowing time for the container to boot)…")
    deadline = _time.time() + 60
    while True:
        results = run_checks(username)
        if results.ok() or _time.time() >= deadline:
            render(results, username)
            if not results.ok():
                raise typer.Exit(1)
            return
        _time.sleep(5)


@app.command()
def verify(
    username: str = typer.Argument(..., help="Developer username to verify"),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output"),
    wait: int = typer.Option(
        0, "--wait", "-w",
        help="Retry for up to N seconds until every check passes (0 = single run)",
    ),
):
    """Verify a developer's whole pipeline: container, OIDC, Caddy, HTTP.

    Exit code is 0 only when every check passes, so this is safe to use as a
    loop/CI condition. Use --wait to poll while a freshly-provisioned
    container finishes booting.
    """
    import time as _time

    from dev_administration.verify import render, run_checks

    deadline = _time.time() + wait
    while True:
        results = run_checks(username)
        if results.ok() or _time.time() >= deadline:
            render(results, username, as_json=json_out)
            if not results.ok():
                raise typer.Exit(1)
            return
        _time.sleep(5)


@app.command()
def deprovision(username: str = typer.Argument(..., help="Developer username")):
    """Stop a developer's container. Volume is preserved."""
    config = _load_config()
    notifier = _get_notifier()
    do_deprovision(username, config, notifier)
    typer.echo(f"Deprovisioned '{username}'. Volume preserved.")


@app.command()
def reset(username: str = typer.Argument(..., help="Developer username to reset")):
    """Tear down a developer's container + OAuth2 app. Keeps the developers.yaml entry
    and the Docker volume. Run 'reconcile' afterwards to re-provision from scratch."""
    config = _load_config()
    notifier = _get_notifier()
    # Resolved by compose label, like deprovision: a guessed name gives the
    # §5.3 guard nothing it can prove belongs to us, so it would refuse.
    container = project_services(config.project).get(f"hermes-{username}")

    # 1. Stop + remove container
    if container:
        stop_and_remove_container(container)
        typer.echo(f"  removed container {container}")
    else:
        typer.echo(f"  no container for hermes-{username} in project {config.project}")

    # 2. Delete OAuth2 app
    app_id = find_oauth2_app(config.forgejo_url, config.forgejo_token, f"hermes-{username}")
    if app_id:
        delete_oauth2_app(config.forgejo_url, config.forgejo_token, app_id)
        typer.echo(f"  deleted OAuth2 app hermes-{username}")
    else:
        typer.echo(f"  no OAuth2 app found")

    # 3. Note: volume + Forgejo user + developers.yaml entry are preserved
    vol = agent_volume(username, config.project)
    if volume_exists(vol):
        typer.echo(f"  volume {vol} preserved (run 'reconcile' to re-provision)")
    else:
        typer.echo(f"  volume {vol} does not exist")

    if user_exists(config.forgejo_url, config.forgejo_token, username):
        typer.echo(f"  Forgejo user {username} preserved")

    typer.echo(
        f"\nReset complete for '{username}'. "
        f"Run 'dev-admin reconcile' to re-provision."
    )


access_app = typer.Typer(
    help="Scoped per-developer Forgejo access tokens.",
    no_args_is_help=True,
)
app.add_typer(access_app, name="access")

# `mint` and `revoke` deliberately do NOT call _load_config(): it requires
# FORGEJO_ADMIN_TOKEN, and the whole point is that a developer runs these
# without one. They need the URL and the roster, nothing else.
def _access_url() -> str:
    url = os.environ.get("FORGEJO_URL", "")
    if not url:
        raise typer.BadParameter("FORGEJO_URL is not set.")
    return url


def _dev_names() -> list[str]:
    return [d.forgejo_user for d in _load_devs()]


def _dev_password() -> str:
    """Prompt or FORGEJO_DEV_PASSWORD only. No flag exists, so `ps` cannot show it."""
    return (os.environ.get("FORGEJO_DEV_PASSWORD")
            or typer.prompt("Forgejo password", hide_input=True))


@access_app.command("mint")
def access_mint(
    username: str = typer.Argument(..., help="Your Forgejo username (must be in developers.yaml)"),
    scope: list[str] = typer.Option(
        None, "--scope", "-s",
        help=f"Override the token scopes. Default: {', '.join(DEFAULT_SCOPES)}",
    ),
):
    """Mint YOUR scoped Forgejo token and print it once.

    Run this as the developer, not as the admin — Forgejo answers 401 to an
    admin token on this route, so the admin cannot mint it for you and never
    sees it. The secret is written to no file; Forgejo keeps only a hash.
    """
    scopes = tuple(scope) if scope else DEFAULT_SCOPES
    try:
        created = mint_token(
            _access_url(), username, _dev_password(), _dev_names(), scopes)
    except AccessError as exc:
        typer.echo(f"Refused: {exc}", err=True)
        raise typer.Exit(1)

    typer.echo(f"Minted {created['name']} for {username}")
    typer.echo(f"  scopes : {', '.join(created.get('scopes') or scopes)}")
    typer.echo("")
    typer.echo("  Token (shown once — store it in a password manager, not a file):")
    typer.echo(f"  {created['sha1']}")
    typer.echo("")
    typer.echo("  Use it as an HTTPS password. Revoke it with:")
    typer.echo(f"  dev-admin access revoke {username}")


@access_app.command("revoke")
def access_revoke(
    username: str = typer.Argument(..., help="Your Forgejo username"),
):
    """Delete YOUR managed token and confirm Forgejo no longer lists it.

    Also the developer's own act: an admin token is 401 on this route. An admin
    who needs to cut access without you is looking for `access suspend`.
    """
    try:
        deleted = revoke_token(
            _access_url(), username, _dev_password(), _dev_names())
    except AccessError as exc:
        typer.echo(f"FAILED: {exc}", err=True)
        raise typer.Exit(1)

    if deleted is None:
        typer.echo(f"No {token_name(username)} to revoke.")
        raise typer.Exit(1)
    typer.echo(
        f"Revoked {deleted['name']} (id {deleted['id']}, "
        f"...{deleted.get('token_last_eight', '?')}) — Forgejo re-checked, it is gone."
    )


@access_app.command("ls")
def access_ls(
    username: str = typer.Argument("", help="One developer, or all of them if omitted"),
):
    """Show every token and repository grant on each developer's account. Admin token.

    This is the answer to 'where does this credential live': in Forgejo, and
    nowhere else. Tokens the developer made themselves are shown too, marked
    `(personal)` — `revoke` will not touch them, but an admin asking what an
    account can do needs to see them.
    """
    config = _load_config()
    known = _dev_names()
    try:
        if username:
            _assert_managed(username, known)
    except AccessError as exc:
        typer.echo(f"Refused: {exc}", err=True)
        raise typer.Exit(1)
    try:
        # Hoisted out of the per-developer loop: neither this nor the
        # protection read below depends on the developer, and each carries a
        # six-attempt retry.
        repos = resolve_shared_repos(
            config.forgejo_url, config.forgejo_token, config.shared_repos)
    except Exception as exc:  # noqa: BLE001 - the tokens are still worth listing
        typer.echo(f"(repository access unreadable: {reason(exc)})", err=True)
        repos = []

    notes = {}
    for target in repos:
        try:
            branch, protected = default_branch_protection(
                config.forgejo_url, config.forgejo_token, target)
            notes[target] = "" if protected else f"  [{branch} UNPROTECTED]"
        except Exception as exc:  # noqa: BLE001
            notes[target] = f"  [protection unreadable: {reason(exc)}]"

    for name in [username] if username else known:
        managed = token_name(name)
        # The whole body, not just list_tokens: one bad user must not abort the
        # listing partway through with a traceback.
        try:
            tokens = list_tokens(config.forgejo_url, name, config.forgejo_token)
            typer.echo(f"{name}:")
            if not tokens:
                typer.echo("  (no access tokens)")
            for entry in tokens:
                tag = "managed" if entry.get("name") == managed else "personal"
                scopes = ", ".join(entry.get("scopes") or []) or "none"
                typer.echo(
                    f"  {entry.get('name')}  ({tag})  id={entry.get('id')}  "
                    f"...{entry.get('token_last_eight', '?')}  [{scopes}]"
                )
            for target in repos:
                perm = repo_permission(
                    config.forgejo_url, config.forgejo_token, name, target)
                typer.echo(f"  repo {target}: {perm or 'no access'}{notes[target]}")
        except Exception as exc:  # noqa: BLE001
            typer.echo(f"{name}: unreadable ({reason(exc)})")


@access_app.command("suspend")
def access_suspend(
    username: str = typer.Argument(..., help="Developer username"),
):
    """Cut off a developer's Forgejo access now, without their cooperation.

    Deactivates the account: their token stops working for the API and for git
    over HTTPS. Measured, not assumed.

    This SUSPENDS, it does not revoke. `access restore` brings the same token
    back to life. The durable fix is the developer running `access revoke` —
    Forgejo does not let an admin token delete someone else's token at all.
    """
    config = _load_config()
    try:
        set_active(config.forgejo_url, config.forgejo_token, username, False, _dev_names())
    except AccessError as exc:
        typer.echo(f"Refused: {exc}", err=True)
        raise typer.Exit(1)
    typer.echo(
        f"Suspended {username}. Their tokens and git-over-HTTPS are dead until "
        f"`dev-admin access restore {username}`.\n"
        f"This is a suspension, not a revocation — the token still exists. "
        f"See `dev-admin access ls {username}`."
    )


@access_app.command("restore")
def access_restore(
    username: str = typer.Argument(..., help="Developer username"),
):
    """Reactivate a suspended developer. Their existing token works again."""
    config = _load_config()
    try:
        set_active(config.forgejo_url, config.forgejo_token, username, True, _dev_names())
    except AccessError as exc:
        typer.echo(f"Refused: {exc}", err=True)
        raise typer.Exit(1)
    typer.echo(f"Restored {username}.")


def _repos(config, repo: list[str]) -> list[str]:
    if repo:
        return list(repo)
    found = resolve_shared_repos(config.forgejo_url, config.forgejo_token, config.shared_repos)
    if not found:
        raise typer.BadParameter(
            f"none of {config.shared_repos} exist under the admin token's account. "
            "Name them explicitly with --repo owner/name."
        )
    return found


@access_app.command("authorize")
def access_authorize(
    username: str = typer.Argument(..., help="Developer username"),
    repo: list[str] = typer.Option(
        None, "--repo", "-r",
        help="owner/name. Defaults to the shared repos under the admin's account.",
    ),
    permission: str = typer.Option(
        "write", "--permission", "-p", help="read or write. Never admin or owner.",
    ),
    allow_unprotected: bool = typer.Option(
        False, "--allow-unprotected",
        help="Grant write even where the default branch has no protection rule.",
    ),
):
    """Give a developer access to the repositories themselves. Admin token.

    A token proves identity; it grants nothing. Without this the developer
    authenticates fine and sees no repository at all.

    This uses repository collaborators, NOT the org team `reconcile` sets up:
    every shared repo is owned by the admin's user namespace, and a Gitea team
    can only hold repos owned by its own org.
    """
    config = _load_config()
    known = _dev_names()
    try:
        targets = _repos(config, repo)
        for target in targets:
            got = authorize_repo(
                config.forgejo_url, config.forgejo_token, username,
                target, permission, known, allow_unprotected,
            )
            typer.echo(f"  {target}: {username} -> {got}")
    except AccessError as exc:
        typer.echo(f"Refused: {exc}", err=True)
        raise typer.Exit(1)
    typer.echo(
        f"\n{username} can now clone and push to {len(targets)} repo(s). "
        f"They still need a token: `dev-admin access mint {username}`."
    )


@access_app.command("deauthorize")
def access_deauthorize(
    username: str = typer.Argument(..., help="Developer username"),
    repo: list[str] = typer.Option(
        None, "--repo", "-r", help="owner/name. Defaults to the shared repos.",
    ),
):
    """Remove a developer's access to the repositories. Admin token.

    Unlike `suspend`, this is durable and specific: it survives a `restore` and
    leaves the rest of their Forgejo account alone. Their token keeps working
    — it just reaches nothing.
    """
    config = _load_config()
    known = _dev_names()
    removed = 0
    try:
        for target in _repos(config, repo):
            if deauthorize_repo(config.forgejo_url, config.forgejo_token,
                                username, target, known):
                typer.echo(f"  {target}: removed {username}")
                removed += 1
            else:
                typer.echo(f"  {target}: {username} was not a collaborator")
    except AccessError as exc:
        typer.echo(f"Refused: {exc}", err=True)
        raise typer.Exit(1)
    if not removed:
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
