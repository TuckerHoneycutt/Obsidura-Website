from __future__ import annotations

import os

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, urlunparse

# The module-level BASE_PORT constant was deleted in Chunk 2 (M4). Port
# allocation belongs to agents_compose, which is what actually writes the
# `ports:` mapping now; a second constant here could disagree with the
# rendered file and nothing would catch it.
from dev_administration.agents_compose import (
    HERMES_IMAGE, agent_specs, render_agents_compose,
)

#: The scratch container these helpers run one-off shell in. Pinned like every
#: other image: it was `"alpine"` -- no tag at all, so `docker run` took
#: whatever `latest` meant that minute, and no `repo:tag` matcher could see it.
ALPINE_IMAGE = (
    "alpine:latest@sha256:28bd5fe8b56d1bd048e5babf5b10710ebe0bae67db86916198a6eec434943f8b"
)
from dev_administration.models import DeveloperConfig, OrchestratorEvent
from dev_administration.notifier import Notifier
from dev_administration.project import (
    agent_volume, current_project, find_service_container, network_name,
    project_services,
)
from dev_administration.docker_utils import (
    volume_exists, create_volume, container_exists, container_status,
    run_temp_container, stop_and_remove_container,
)
from dev_administration.forgejo_utils import (
    create_oauth2_app, delete_oauth2_app, get_oauth2_app,
)
from dev_administration.forgejo_org import (
    user_exists, create_user, ensure_org, ensure_team,
    add_team_repo, add_team_member, ensure_branch_protection,
    generate_temp_password, get_user,
)
from dev_administration.forgejo_access import (
    deauthorize_repo, reason, resolve_shared_repos, token_name,
)
# All of these are imported at MODULE level on purpose. write_via_caddy and
# write_agent_chooser used to be imported inside reconcile(), which meant
# @patch("dev_administration.provision.write_via_caddy") bound nothing at all
# and the real function ran during unit tests -- that is how running this
# suite once wrote an empty agents.conf into PRODUCTION's Caddy container and
# returned 502 for every /agent/<user>/ route. A function-local import of a
# side-effecting function is an unpatchable escape hatch; keep them here.
from dev_administration.caddy_utils import (
    generate_caddy_agents_conf, generate_agents_json, reload_caddy,
    write_owners_map, write_denied_page, write_via_caddy, write_agent_chooser,
)
from dev_administration.ssh_utils import remove_ssh_key

#: Where the roster is mounted in the dev-admin container. `DEVELOPERS_YAML`
#: overrides it, as it does everywhere else in this package (see cli.py).
DEVELOPERS_YAML_DEFAULT = "/app/developers.yaml"


@dataclass
class ProvisionConfig:
    forgejo_url: str
    forgejo_token: str
    aurora_profile_url: str
    domain: str
    caddy_container: str
    authorized_keys_path: str
    # Which Compose project this run is allowed to touch. Empty means "ask
    # project.current_project()", which reads our own container's compose
    # LABEL first and only falls back to COMPOSE_PROJECT_NAME on the host.
    # Tests pass it explicitly so they never consult a live daemon.
    project: str = ""
    # NOTE: there is deliberately no `base_port` here. Ports come from
    # agents_compose.DEFAULT_BASE_PORT via agent_specs, which is also what
    # renders the committed fragment and what the drift test compares
    # against. A base_port field would be a second port constant in this
    # module -- exactly what the comment above the imports forbids -- and it
    # was silently ignored by every caller that set it.
    upstream_mode: str = "published"
    agent_env_dir: str = "/agent-env"
    # Read-only path to the committed compose.agents.yml, when it is mounted.
    # Empty disables the staleness check rather than failing it.
    agents_compose_path: str = ""
    org_name: str = os.environ.get("FORGEJO_ORG", "obsidura")
    dev_team: str = os.environ.get("FORGEJO_DEV_TEAM", "developers")
    shared_repos: list = None

    def __post_init__(self):
        if self.shared_repos is None:
            self.shared_repos = ["aurora", "aurora-agent", "dev-administration", "superpowers"]
        if not self.project:
            self.project = current_project()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _emit(
    notifier: Notifier,
    event_type: str,
    severity: str,
    developer: str | None,
    message: str,
    **metadata,
) -> OrchestratorEvent:
    event = OrchestratorEvent(
        timestamp=_now(),
        event_type=event_type,
        severity=severity,
        developer=developer,
        message=message,
        metadata=metadata,
    )
    notifier.notify(event)
    return event


def _check_agents_compose_fresh(
    devs: list[DeveloperConfig],
    config: ProvisionConfig,
    notifier: Notifier,
) -> list[OrchestratorEvent]:
    """Warn when compose.agents.yml no longer matches developers.yaml.

    reconcile cannot regenerate it: the file is tracked and lives at the repo
    root, while reconcile normally runs inside the dev-admin container. So it
    reports instead. Silent otherwise -- including when the path is not
    configured, since a caller that never mounted the file has not thereby
    declared it stale.
    """
    if not config.agents_compose_path:
        return []
    try:
        # Path.read_text, not bare open(): provision.open is patched by the
        # unit tests, so an open() here is captured by their mock -- it broke
        # `mock_open.assert_called_once_with(...)` and produced a spurious
        # compose.stale the moment any test set this path. It also closes the
        # fd, which `open(...).read()` did not.
        on_disk = Path(config.agents_compose_path).read_text()
    except OSError as exc:
        return [_emit(
            notifier, "compose.unreadable", "warning", None,
            f"Could not read {config.agents_compose_path}: {exc}. Cannot tell "
            "whether the committed agent fragment matches developers.yaml.",
            path=config.agents_compose_path,
        )]

    expected = render_agents_compose(agent_specs(devs))
    if on_disk == expected:
        return []
    return [_emit(
        notifier, "compose.stale", "warning", None,
        f"{config.agents_compose_path} does not match developers.yaml. "
        "Run, from the repo root on the HOST: dev-admin render-agents, then "
        "commit it. Until then `docker compose up -d` cannot start any agent "
        "added or removed since it was last rendered.",
        path=config.agents_compose_path,
    )]


def _host_port_for(specs, dev, events, notifier) -> int | None:
    """The published port agent_specs allocated for this developer.

    A dict lookup here would raise KeyError AFTER provisioning has created
    the Forgejo account, the OAuth2 app and the volume, and BEFORE Caddy is
    written -- reintroducing the crash-after-irreversible-work class two
    lines below the comment explaining it. The very scenario the comment
    cites (agent_specs learning to skip a developer) is the one that would
    trigger it, so it degrades to a warning instead.
    """
    spec = specs.get(dev.username)
    if spec is not None and spec.host_port is not None:
        return spec.host_port
    events.append(_emit(
        notifier, "agent.unaddressable", "warning", dev.username,
        f"agent_specs allocated no published port for {dev.username!r}; "
        "Caddy cannot be given an upstream for this agent.",
    ))
    return None


def _host_owner(config) -> tuple[int, int] | None:
    """The uid/gid that owns this repository on the HOST, or None.

    dev-admin runs as root in a container, so what it writes into a bind mount
    lands root-owned, and Compose reads `env_file:` as the INVOKING user -- a
    root-owned 0600 agent env file then fails every later `docker compose` in
    that checkout with `permission denied`, naming neither dev-admin nor
    provisioning. Anchored on a git-tracked, host-mounted file; `agent_env_dir`
    is NOT a valid anchor, because Docker creates it root-owned.
    """
    roster = os.environ.get("DEVELOPERS_YAML", DEVELOPERS_YAML_DEFAULT)
    for candidate in (config.agents_compose_path, roster):
        if not candidate:
            continue
        try:
            info = os.stat(candidate)
        except OSError:
            continue
        return info.st_uid, info.st_gid
    return None


def _set_host_owner(target: int | str, owner: tuple[int, int] | None) -> None:
    """Best-effort chown of a path or an open fd to `owner`.

    Warns rather than raising, because this is a hardening step and not the
    point of the caller -- but warns rather than passing, because a silent
    failure here IS the permission-denied bug `_host_owner` exists to prevent.
    """
    if owner is None:
        return
    try:
        (os.fchown if isinstance(target, int) else os.chown)(target, *owner)
    except OSError as exc:
        print(f"  ⚠ could not chown {target} to {owner[0]}:{owner[1]}: {exc}")
        print("  ⚠ `docker compose` run as the host user may fail to read it.")


def provision_developer(
    dev: DeveloperConfig,
    config: ProvisionConfig,
    notifier: Notifier,
    services_now: dict[str, str] | None = None,
) -> list[OrchestratorEvent]:
    """Provision a single developer's Forgejo account, OAuth2 app and volume.

    It does NOT start a container. Since M4 the agent is a Compose service in
    compose.agents.yml; this function prepares everything that service needs
    and then reports whether Compose has actually brought it up.

    `services_now` is the caller's already-fetched service->container map.
    Passed in rather than re-queried, because re-querying happens AFTER this
    function has created a Forgejo user, recreated an OAuth2 app, written the
    volume's .env and installed the Aurora profile — and project_services()
    is fail-closed, so one transient `docker ps` failure at that moment would
    abort reconcile with every side effect already applied and Caddy never
    updated. That is the same "raise after irreversible work" hazard the
    Task 4 stub was written to avoid.
    """
    events: list[OrchestratorEvent] = []
    name = dev.username
    # Project-scoped. An unprefixed `hermes-<u>-home` is reachable from every
    # project on the daemon, which is precisely how a branch would end up
    # writing into production's agent state.
    vol = agent_volume(name, config.project)

    # 1. Volume
    if not volume_exists(vol):
        create_volume(vol)
        events.append(_emit(notifier, "volume.created", "info", name, f"Created volume {vol}"))

    # 2. OAuth2 app
    redirect_uri = f"https://{config.domain}/agent/{name}/auth/callback"
    # One fetch, not two: the app object and its id come from the same scan of
    # the same endpoint, and asking twice cost a second retrying round trip
    # per developer per reconcile.
    app_obj = get_oauth2_app(config.forgejo_url, config.forgejo_token, f"hermes-{name}")
    app_id = app_obj["id"] if app_obj else None
    client_id = ""
    client_secret = ""
    if app_id is not None:
        # App exists — try to read creds from .env on the volume
        try:
            existing_env = run_temp_container(
                image=ALPINE_IMAGE,
                command=["cat", "/opt/data/.env"],
                volumes={vol: "/opt/data"},
            )
        except Exception:
            existing_env = ""
        for line in existing_env.split("\n"):
            if line.startswith("HERMES_DASHBOARD_OIDC_CLIENT_ID="):
                client_id = line.split("=", 1)[1]
            elif line.startswith("HERMES_DASHBOARD_OIDC_CLIENT_SECRET="):
                client_secret = line.split("=", 1)[1]
        # An app registered as a PUBLIC client can't use our client_secret;
        # Forgejo then never returns an id_token and the dashboard reports
        # "provider unreachable". Treat that as stale and rebuild.
        is_public = not app_obj.get("confidential_client", False)
        if is_public:
            print(f"  ↻ OAuth2 app hermes-{name} is a public client — recreating as confidential")

        # If we couldn't recover the secret, or the app is public, recreate it
        if not client_secret or is_public:
            delete_oauth2_app(config.forgejo_url, config.forgejo_token, app_id)
            app_id = None
    if app_id is None:
        client_id, client_secret = create_oauth2_app(
            config.forgejo_url, config.forgejo_token, f"hermes-{name}", redirect_uri,
        )
        events.append(_emit(notifier, "oauth2.created", "info", name, f"Created OAuth2 app hermes-{name}"))

    # 2b. Create Forgejo account if it doesn't exist (requires admin-scoped token)
    temp_password = None
    user_create_failed = False
    try:
        if not user_exists(config.forgejo_url, config.forgejo_token, dev.forgejo_user):
            candidate_password = generate_temp_password()
            email = dev.email or f"{dev.forgejo_user}@obsidura.local"
            create_user(config.forgejo_url, config.forgejo_token, dev.forgejo_user, email, candidate_password)
            # Only surface the password AFTER create_user returns cleanly.
            # Reporting it on the failure path hands the admin credentials
            # that were never actually set on the account.
            temp_password = candidate_password
            events.append(_emit(notifier, "user.created", "info", name, f"Created Forgejo user {dev.forgejo_user}"))
            add_team_member(config.forgejo_url, config.forgejo_token, config.org_name, config.dev_team, dev.forgejo_user)
    except Exception as e:
        user_create_failed = True
        # reason(), not `e`: create_user's POST body carries the temp password
        # in argv, and CalledProcessError stringifies the whole argv.
        print(f"  ⚠ Could not create Forgejo user {dev.forgejo_user}: {reason(e)}")
        print("  ⚠ Create the user manually in Forgejo, or use an admin-scoped token.")

    # 3. Write .env (via temp container with the volume)
    env_content = f"""FORGEJO_URL={config.forgejo_url}
HERMES_HOME=/opt/data
HERMES_DASHBOARD=1
HERMES_DASHBOARD_HOST=0.0.0.0
HERMES_DASHBOARD_OIDC_ISSUER={config.forgejo_url}
HERMES_DASHBOARD_OIDC_CLIENT_ID={client_id}
HERMES_DASHBOARD_OIDC_CLIENT_SECRET={client_secret}
"""
    run_temp_container(
        image=ALPINE_IMAGE,
        command=["sh", "-c", f'cat > /opt/data/.env << "ENVEOF"\n{env_content}ENVEOF'],
        volumes={vol: "/opt/data"},
    )

    # 4. Install Aurora profile (temp Hermes container)
    parsed = urlparse(config.aurora_profile_url)
    authed_url = urlunparse(parsed._replace(
        netloc=f"supergoodname77:{config.forgejo_token}@{parsed.netloc}"
    ))
    run_temp_container(
        image=HERMES_IMAGE,
        command=["hermes", "profile", "install", authed_url,
                  "--name", "aurora", "--force", "-y"],
        volumes={vol: "/opt/data"},
        env={"HERMES_HOME": "/opt/data"},
        network=network_name(config.project),
    )

    # 5. Hand the credentials to Compose.
    #
    # Before M4 this called `docker run` directly, producing a container with
    # NO compose project label: `docker compose down` could not see it,
    # `--remove-orphans` could not remove it, and a branch stack had no agents
    # at all. The container is now declared in compose.agents.yml. All this
    # step does is write the per-agent secrets Compose reads via `env_file:`
    # and confirm Compose has actually started it.
    #
    # Everything the old dev_env dict carried that is NOT a secret now lives
    # in compose.agents.yml — including FORWARDED_ALLOW_IPS, without which
    # uvicorn ignores X-Forwarded-Proto and login loops.
    os.makedirs(config.agent_env_dir, exist_ok=True)
    owner = _host_owner(config)
    _set_host_owner(config.agent_env_dir, owner)
    env_path = os.path.join(config.agent_env_dir, f"{name}.env")
    agent_env_lines = []
    if client_id:
        agent_env_lines.append(f"HERMES_DASHBOARD_OIDC_CLIENT_ID={client_id}")
    if client_secret:
        agent_env_lines.append(f"HERMES_DASHBOARD_OIDC_CLIENT_SECRET={client_secret}")
    tmp_path = f"{env_path}.tmp"
    with open(tmp_path, "w") as fh:
        fh.write("\n".join(agent_env_lines) + ("\n" if agent_env_lines else ""))
        # Tightened on the TEMP file, before it is visible under its real
        # name. Chmod-ing after os.replace would leave a window in which the
        # OIDC client secret is readable at the default umask. .gitignore
        # keeps this file out of the repo; this keeps it off other local
        # accounts' read path.
        os.fchmod(fh.fileno(), 0o600)
        # Ownership on the same temp fd, so the file is never visible under
        # its real name with the wrong owner. 0600 is KEPT -- the secret stays
        # unreadable to other accounts; it just belongs to the human who runs
        # compose.
        _set_host_owner(fh.fileno(), owner)
    os.replace(tmp_path, env_path)  # atomic: Compose never reads a partial file

    service = f"hermes-{name}"

    # Two distinct facts, so two events. `developer.provisioned` means the
    # durable artifacts exist -- volume, OAuth2 app, agent env file. That is
    # what this function is now responsible for, and it has just succeeded.
    #
    # Whether a CONTAINER exists is a separate question with a different
    # owner: Compose. Collapsing the two would make `developer.provisioned`
    # unreachable, because reconcile only calls this function when the
    # container is missing, and starting one is no longer something this code
    # is allowed to do.
    events.append(_emit(
        notifier, "developer.provisioned", "info", name,
        f"Provisioned {service}: volume, OAuth2 app and agent env are ready.",
        service=service, volume=vol,
    ))

    container = (services_now or {}).get(service)
    if container is None:
        events.append(_emit(
            notifier, "container.missing", "warning", name,
            f"No container for service {service} in project {config.project}. "
            f"Run, from the repo root on the HOST: "
            f"docker compose up -d {service}",
            service=service, volume=vol,
        ))

    # Human-facing summary. The events above are for machines (cron / master
    # orchestrator); this block is what an admin actually needs to act on:
    # where to send the developer and what they still have to do themselves.
    setup_url = f"https://{config.domain}/agent/{name}/setup"
    agent_url = f"https://{config.domain}/agent/{name}/"
    print()
    print(f"  ✓ User '{name}' ready — Forgejo account + Hermes agent provisioned.")
    print(f"      Forgejo login : {dev.forgejo_user}")
    if temp_password:
        print(f"      Temp password : {temp_password}   (must be changed on first login)")
    elif user_create_failed:
        print("      Password      : ⚠ ACCOUNT NOT CREATED — see warning above")
    else:
        print("      Password      : unchanged (account already existed)")
    print(f"      Setup form    : {setup_url}")
    print(f"      Agent         : {agent_url}")
    print()
    print("    Send the developer to the SETUP FORM first — they supply their own")
    print("    OpenRouter API key and SSH public key there. Nothing else is required;")
    print("    the agent is usable as soon as that form is submitted.")
    print()
    return events


def deprovision_developer(
    username: str,
    config: ProvisionConfig,
    notifier: Notifier,
) -> list[OrchestratorEvent]:
    """Stop a developer's container and take their repository access away.

    The volume is preserved. The managed TOKEN is not deleted: Forgejo answers
    401 to an admin token on DELETE /users/{u}/tokens/{id}, so only the
    developer can, and `access suspend` is the admin's lever until they do.
    """
    events: list[OrchestratorEvent] = []
    # Resolved by compose label rather than by assuming the name. A guessed
    # name gives the §5.3 guard nothing real to check -- and if some other
    # project on this daemon happens to own a container by that name, the
    # guard would (correctly) refuse, which reads as a crash rather than as
    # "not ours". Looking it up in our own project makes the distinction
    # explicit.
    container = project_services(config.project).get(f"hermes-{username}")
    vol = agent_volume(username, config.project)

    if container:
        stop_and_remove_container(container)  # guarded: asserts our project
    remove_ssh_key(username, config.authorized_keys_path)

    events.append(_emit(
        notifier, "volume.orphaned", "warning", username,
        f"Container {container or f'hermes-{username}'} stopped. "
        f"Volume {vol} preserved.",
        container=container or f"hermes-{username}", volume=vol,
    ))

    # This developer has by definition just left developers.yaml, so the roster
    # the managed-check consults is the one name being deprovisioned.
    roster = [username]
    try:
        repos = resolve_shared_repos(
            config.forgejo_url, config.forgejo_token, config.shared_repos)
    except Exception as exc:  # noqa: BLE001
        repos = []
        events.append(_emit(
            notifier, "repo.deauthorize_failed", "warning", username,
            f"Could not list the shared repos ({reason(exc)}), so {username}'s "
            f"repository access was NOT removed.",
        ))
    for repo in repos:
        try:
            if deauthorize_repo(config.forgejo_url, config.forgejo_token,
                                username, repo, roster):
                events.append(_emit(
                    notifier, "repo.deauthorized", "info", username,
                    f"Removed {username} as a collaborator on {repo}.", repo=repo,
                ))
        except Exception as exc:  # noqa: BLE001
            events.append(_emit(
                notifier, "repo.deauthorize_failed", "warning", username,
                f"Could NOT remove {username} from {repo} ({reason(exc)}) — "
                f"their access may remain. Check `dev-admin access ls {username}`.",
                repo=repo,
            ))

    events.append(_emit(
        notifier, "token.orphaned", "warning", username,
        f"{token_name(username)} is NOT revoked by this command: Forgejo "
        f"refuses that DELETE to an admin token. Run "
        f"`dev-admin access suspend {username}` to kill it now.",
    ))
    return events


def reconcile(
    devs: list[DeveloperConfig],
    notifier: Notifier,
    config: ProvisionConfig,
) -> list[OrchestratorEvent]:
    """Sync Docker state with developers.yaml."""
    events: list[OrchestratorEvent] = []
    desired = {dev.username for dev in devs}

    # Ensure org + team exist (requires admin-scoped token)
    try:
        ensure_org(config.forgejo_url, config.forgejo_token, config.org_name, "supergoodname77")
        ensure_team(config.forgejo_url, config.forgejo_token, config.org_name, config.dev_team, "read")
        for repo in config.shared_repos:
            add_team_repo(config.forgejo_url, config.forgejo_token, config.org_name, config.dev_team, repo)
            ensure_branch_protection(config.forgejo_url, config.forgejo_token, config.org_name, repo)
    except Exception as e:
        print(f"  ⚠ Skipping org/team setup: {reason(e)}")
        print(f"  ⚠ Create org '{config.org_name}' manually, or use an admin-scoped token.")

    # Agents scoped to THIS project's labels. A name-prefix scan (`hermes-`)
    # would also match another project's agents on the same daemon, which is
    # exactly the cross-project bleed §5.3 forbids. Note the admin agent's
    # service is `hermes`, not `hermes-`, so it is excluded by construction.
    services_now = project_services(config.project)
    actual = {
        svc[len("hermes-"):] for svc in services_now if svc.startswith("hermes-")
    }

    # Ports come from agent_specs -- the same function that rendered
    # compose.agents.yml -- rather than being recomputed here. Recomputing
    # `base_port + i` in two places agreed only by accident of both
    # enumerating developers.yaml in the same order; the moment agent_specs
    # sorts, skips, or returns host_port=None (the publish_ports=False branch
    # that already exists), Caddy's reverse_proxy would silently point at
    # another developer's agent, or at nothing.
    # agent_specs with its DEFAULT base port -- the same call the renderer and
    # the drift test make. An AGENT_BASE_PORT knob used to feed this while the
    # drift test used the default, so `AGENT_BASE_PORT=9200 render-agents`
    # wrote a file the drift test rejected, and reconcile then emitted a
    # permanent spurious compose.stale whose own remediation made it worse.
    # One constant, three readers, no environment.
    specs = {spec.username: spec for spec in agent_specs(devs)}

    # Warn if the committed fragment no longer matches developers.yaml.
    # Without this, adding a developer and running reconcile creates the
    # account, the OAuth app, the volume and the env file, then tells the
    # operator to run `docker compose up -d hermes-<new>` -- which fails with
    # `no such service`, because nothing re-rendered the file.
    events.extend(_check_agents_compose_fresh(devs, config, notifier))

    # Provision new developers
    for dev in devs:
        if dev.username not in actual:
            events.extend(provision_developer(
                dev, config, notifier, services_now=services_now,
            ))
        else:
            # Verify existing
            status = container_status(services_now[f"hermes-{dev.username}"])
            if status != "running":
                events.append(_emit(
                    notifier, "container.unhealthy", "warning", dev.username,
                    f"Container hermes-{dev.username} status: {status}",
                ))

    # Deprovision removed developers
    for username in actual - desired:
        events.extend(deprovision_developer(username, config, notifier))

    # Regenerate Caddy config + agents.json
    # Assign host ports for Caddy (host network mode, needs 127.0.0.1:port)
    dev_dicts = []
    for dev in devs:
        # Resolve the Forgejo numeric user id and the agent's OAuth2 client_id
        # so the authz gate can pin this agent to one identity. Both are
        # best-effort: a missing sub falls back to username matching, and a
        # missing client_id skips the aud check. Never fatal — reconcile must
        # stay usable when Forgejo is briefly unreachable.
        forgejo_sub = ""
        client_id = ""
        try:
            info = get_user(config.forgejo_url, config.forgejo_token,
                            dev.forgejo_user)
            forgejo_sub = str((info or {}).get("id") or "")
        except Exception:  # noqa: BLE001
            pass
        try:
            app = get_oauth2_app(config.forgejo_url, config.forgejo_token,
                                 f"hermes-{dev.username}")
            client_id = str((app or {}).get("client_id") or "")
        except Exception:  # noqa: BLE001
            pass
        host_port = _host_port_for(specs, dev, events, notifier)
        if host_port is None:
            # SKIP, do not emit a route with a null upstream. caddy_utils
            # reads `dev.get("host_port", 9119)`, and the key is PRESENT with
            # value None, so the default never applies -- the generator would
            # render `reverse_proxy 127.0.0.1:None` three times over. That
            # config is then written into Caddyfile.d/agents.conf, which the
            # main Caddyfile imports, and reload_caddy runs `caddy reload`
            # with check=False and discards the failure. Caddy keeps serving
            # the old config from memory and reconcile reports success, so
            # the breakage only appears at the NEXT Caddy start -- a reboot,
            # an unrelated `up -d` -- where it takes down EVERY route in the
            # file: AFFiNE, Forgejo, fjell, the setup form. Losing one
            # agent's route is strictly better than losing the whole site.
            continue
        dev_dicts.append({
            "username": dev.username,
            "display_name": dev.display_name,
            "host_port": host_port,
            "forgejo_user": dev.forgejo_user,
            "forgejo_sub": forgejo_sub,
            "client_id": client_id,
        })
    conf = generate_caddy_agents_conf(dev_dicts, config.domain, mode=config.upstream_mode)
    agents_json = generate_agents_json(devs)

    # Write Caddy config files by docker-exec'ing into the Caddy container.
    # Bazzite's read-only overlay prevents bind-mount writes from dev-admin.
    # Resolved from THIS project's compose labels. The old code defaulted to
    # the literal production Caddy container name, which would have made a
    # branch's reconcile rewrite PRODUCTION's Caddy configuration — spec
    # §5.3's headline failure. CADDY_CONTAINER survives as an override, and
    # every write below is guarded and will refuse a foreign container.
    caddy_container = (
        os.environ.get("CADDY_CONTAINER")
        or getattr(config, "caddy_container", "")
        or find_service_container("caddy", config.project)
    )
    write_via_caddy(caddy_container, "agents.conf", conf)
    write_via_caddy(caddy_container, "agents.json", agents_json)
    # The generated conf references the chooser page only when there are 2+
    # developers, but write it unconditionally so the file is never missing
    # if a second developer is added later.
    write_agent_chooser(caddy_container, dev_dicts)
    write_denied_page(caddy_container)

    # Ownership map for the agent-authz gate. Written under /output rather
    # than /app: the repo is mounted read-only, and Bazzite's read-only
    # rootfs refuses to create a new mountpoint inside it.
    owners_path = os.environ.get(
        "OWNERS_MAP_PATH", "/output/agent-authz-data/owners.json"
    )
    try:
        write_owners_map(owners_path, dev_dicts)
    except OSError as exc:
        print(f"  ⚠ could not write owners map to {owners_path}: {exc}")
        print("  ⚠ per-agent authorization will DENY until this is fixed.")

    reload_caddy(caddy_container)

    return events
