"""The hub's contract with the rest of the stack.

fjell renders the hub from three things it does not own: the agent roster
(`Caddyfile.d/agents.json`), the routes that roster implies
(`Caddyfile.d/agents.conf`), and Caddy's decision to mount the hub somewhere
the caller's Forgejo cookie can reach it. All three drift independently of
the Rust code, and the unit tests in `fjell/src` cannot see any of them.
"""

import json
import re
from pathlib import PurePosixPath

from conftest import REPO_ROOT, compose_config_cached, is_tracked

AGENTS_JSON = REPO_ROOT / "Caddyfile.d/agents.json"
AGENTS_CONF = REPO_ROOT / "Caddyfile.d/agents.conf"
CADDYFILE = REPO_ROOT / "Caddyfile"
FJELL_CONFIG_RS = REPO_ROOT / "fjell/src/config.rs"


def _developers() -> list[str]:
    """Usernames from developers.yaml — the source both generators read."""
    import sys

    path = str(REPO_ROOT / "dev-administration")
    if path not in sys.path:
        sys.path.insert(0, path)
    from dev_administration.models import parse_developers_yaml

    return [d.username for d in parse_developers_yaml(REPO_ROOT / "developers.yaml")]


def _roster() -> list[str]:
    return [entry["username"] for entry in json.loads(AGENTS_JSON.read_text())]


def test_the_roster_the_hub_reads_is_not_empty():
    """Guard for every assertion below that quantifies over the roster.

    An empty agents.json satisfies "every agent is routable" vacuously, and
    it is also the exact shape of the bug this feature fixed: fjell had no
    mount for this file at all, so load_agents() returned [] in production
    and the old landing page listed nobody.
    """
    assert _roster(), f"{AGENTS_JSON} lists no agents — every roster assertion below is vacuous"


def test_every_agent_the_hub_can_link_to_is_routable():
    """The hub renders `/agent/<username>/` for the roster entry matching the
    caller. If Caddy has no route for that username the link is a 404 with no
    error anywhere — agents.json and agents.conf come from two different
    generators and nothing else compares them.
    """
    conf = AGENTS_CONF.read_text()
    unroutable = [
        user for user in _roster()
        if f"handle_path /agent/{user}/*" not in conf
    ]
    assert unroutable == [], (
        f"agents.json offers {unroutable} but agents.conf routes no such path; "
        "the hub would link every one of them to a 404. Re-run "
        "`dev-admin reconcile` and commit both files."
    )


def test_the_roster_matches_developers_yaml():
    """Both generated files are committed, so both can go stale."""
    assert sorted(_roster()) == sorted(_developers()), (
        "Caddyfile.d/agents.json is stale relative to developers.yaml — run "
        "`dev-admin reconcile` and commit the result"
    )


def test_the_hub_is_mounted_where_the_forgejo_cookie_reaches_it():
    """The hub's identity signal is the Forgejo session cookie, and that
    cookie is Path=/git/ (measured). Move the hub to the site root and it
    still renders — it just silently believes every caller is anonymous,
    which is the failure this test exists to make loud.
    """
    caddyfile = CADDYFILE.read_text()
    mount = re.search(r"handle_path\s+(/git/\S+)\s*\{([^}]*)\}", caddyfile)
    assert mount, "no handle_path under /git/ — the hub is not mounted where the cookie is sent"
    assert "FJELL_UPSTREAM" in mount.group(2), (
        f"{mount.group(1)} is routed somewhere other than fjell:\n{mount.group(2)}"
    )
    assert mount.group(1).startswith("/git/."), (
        f"{mount.group(1)} does not start with a dot, so a Forgejo account "
        "could be registered with that name and shadow the hub"
    )


def test_the_front_door_redirects_to_the_hub():
    caddyfile = CADDYFILE.read_text()
    root = re.search(r"handle\s+/\s*\{([^}]*)\}", caddyfile)
    assert root, "nothing handles the exact path `/`"
    # The `*` is not decoration — see
    # test_no_redir_hides_its_destination_in_the_matcher_slot.
    assert re.search(r"redir\s+\*\s+/git/\.\S*hub\S*/?\s", root.group(1)), (
        f"`/` does not redirect to the hub:\n{root.group(1)}"
    )


def _fjell_env() -> dict:
    # `docker compose config --format json` always normalises `environment`
    # to a mapping, whichever form compose.yml wrote it in.
    return compose_config_cached()["services"]["fjell"].get("environment") or {}


def test_no_redir_hides_its_destination_in_the_matcher_slot():
    """`redir /foo/ 302` does not redirect to /foo/.

    Caddy reads the first token after `redir` as an OPTIONAL matcher, and a
    token beginning with `/` is a path matcher. So the directive parses as
    "for requests under /foo/, redirect to `302`". Inside `handle /foo` that
    matcher can never match, the block falls through, and Caddy answers an
    empty 200 with no Location header.

    Not hypothetical. Measured on production 2026-07-31:

        $ curl -sS -o /dev/null -D- https://…/affine
        HTTP/2 200
        content-length: 0

    `/affine` had been silently broken for as long as the block existed, and
    the hub's own front-door redirect landed on it the first time it ran in a
    branch. `caddy validate` accepts both spellings — only a request tells
    them apart. Write `redir * /foo/ 302`.
    """
    offenders = []
    for path in [CADDYFILE, *sorted((REPO_ROOT / "Caddyfile.d").glob("*.conf"))]:
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            tokens = line.split()
            if len(tokens) >= 2 and tokens[0] == "redir" and tokens[1].startswith("/"):
                offenders.append(f"{path.name}:{lineno}: {line.strip()}")
    assert offenders == [], (
        "these redirects put their destination where Caddy expects a matcher, "
        f"so they answer an empty 200 instead of redirecting: {offenders}"
    )


def test_affines_emailed_link_routes_reach_affine():
    """AFFiNE's password-reset, invite and sign-in links land at the SITE ROOT,
    never under /affine, whatever External URL says in the admin panel.

    URLHelper builds every link with `new URL(path, this.requestOrigin)` --
    requestOrigin, not baseUrl -- and requestOrigin is `new URL(externalUrl)
    .origin`, which drops the path. The frontend supplies a root-absolute path
    anyway (`callbackUrl: "/auth/changePassword"`, hardcoded in
    static/js/index.*.js). With no route for them these fall through to the
    basic_auth catch-all. Measured on production 2026-08-03:

        $ curl -sI 'https://.../auth/changePassword?userId=...&token=...'
        HTTP/2 401
        www-authenticate: Basic realm="restricted"

    -- a password-reset mail nobody can use, and the same for every invite and
    OAuth callback. AFFINE_SERVER_SUB_PATH does not fix it: it mounts routes
    and assets under a subpath but leaves URLHelper on the bare origin.

    These are AFFiNE's own top-level client routes (`grep 'path:"/' on
    static/js/index.*.js`), not a guess.
    """
    text = CADDYFILE.read_text()
    matched = set()
    for line in text.splitlines():
        tokens = line.split()
        if len(tokens) >= 3 and tokens[0].startswith("@affine") and tokens[1] == "path":
            matched.update(tokens[2:])

    required = {
        "/auth", "/auth/*", "/invite/*", "/magic-link", "/open-app/*",
        "/oauth/*", "/redirect-proxy", "/share/*",
    }
    missing = sorted(required - matched)
    assert missing == [], (
        f"these AFFiNE link routes are not routed to AFFiNE: {missing}. They "
        "will 401 from the basic_auth catch-all, silently breaking password "
        "reset and invitations."
    )


def test_no_named_matcher_is_defined_twice():
    """Caddy refuses to start if a matcher name is reused.

        Error: adapting config using caddyfile: matcher is defined more
               than once: @affine

    Measured 2026-08-03 while adding the link routes above. The obvious way to
    extend a matcher -- a second `@affine path ...` line -- is not additive and
    is not a warning: it is an adapt failure, so Caddy does not come up at all
    and the next reload is an outage. Give the new set its own name, or extend
    the existing `path` line in place.
    """
    seen: dict[str, int] = {}
    for path in [CADDYFILE, *sorted((REPO_ROOT / "Caddyfile.d").glob("*.conf"))]:
        for line in path.read_text().splitlines():
            tokens = line.split()
            # A definition is `@name <matcher> ...`; a *use* is `handle @name {`.
            if len(tokens) >= 2 and tokens[0].startswith("@"):
                seen[f"{path.name} {tokens[0]}"] = seen.get(f"{path.name} {tokens[0]}", 0) + 1
    dupes = sorted(k for k, n in seen.items() if n > 1)
    assert dupes == [], (
        f"named matchers defined more than once: {dupes}. Caddy will fail to "
        "adapt this config and refuse to start."
    )


def test_fjell_is_given_the_roster_it_reads():
    """Before this feature nothing mounted the roster directory at all, so
    load_agents() returned [] and the page that consumed it degraded silently
    to listing nobody. A missing bind mount is not a startup error anywhere
    in Compose, and `docker compose config` validates it happily.

    Derived from the configured path rather than a constant, so moving the
    mount and forgetting the env var (or the reverse) is what fails.
    """
    fjell = compose_config_cached()["services"]["fjell"]
    roster = PurePosixPath(_fjell_env().get("AGENTS_JSON_PATH", ""))
    assert str(roster) != ".", "AGENTS_JSON_PATH is unset in compose.yml"

    mounts = [
        v for v in fjell.get("volumes", [])
        if str(roster) == v["target"] or str(roster).startswith(v["target"] + "/")
    ]
    assert mounts, (
        f"nothing is mounted at {roster}; fjell would read an empty roster. "
        f"fjell mounts {[v['target'] for v in fjell.get('volumes', [])]}"
    )
    assert any(m["source"].endswith("/Caddyfile.d") for m in mounts), (
        f"{roster} is mounted from {[m['source'] for m in mounts]}, not from "
        "Caddyfile.d, which is the only directory reconcile writes the roster to"
    )


def test_fjells_compiled_in_default_matches_the_mount():
    """The Rust default and the compose env var are two independent copies of
    one path. If they drift, fjell keeps working in production (the env var
    wins) and breaks anywhere the env var is absent, which is every unit-test
    and every future caller — the quiet kind of drift.
    """
    default = re.search(
        r'DEFAULT_AGENTS_JSON_PATH:\s*&str\s*=\s*"([^"]+)"',
        FJELL_CONFIG_RS.read_text(),
    )
    assert default, "fjell/src/config.rs no longer declares DEFAULT_AGENTS_JSON_PATH"
    assert default.group(1) == _fjell_env().get("AGENTS_JSON_PATH"), (
        f"config.rs compiles in {default.group(1)!r} but compose.yml sets "
        f"{_fjell_env().get('AGENTS_JSON_PATH')!r}"
    )


def test_fjell_can_reach_forgejo_by_service_dns():
    """127.0.0.1 reaches nothing from inside fjell's netns, and a branch
    publishes no host ports, so a host-style upstream works in neither.
    """
    url = _fjell_env().get("FORGEJO_INTERNAL_URL", "")
    assert url, "FORGEJO_INTERNAL_URL is unset; fjell would fall back to a default nothing pins"
    assert "127.0.0.1" not in url and "localhost" not in url, (
        f"FORGEJO_INTERNAL_URL={url!r} is a loopback address, which resolves "
        "to fjell's own container"
    )


def test_hub_assets_are_vendored_into_the_repo():
    """No CDN, no npm step: the stack is tailnet-only and a hotlinked asset
    is an unstyled page on a host with no route to the internet.
    """
    for asset in ("fjell/static/hub.css", "fjell/static/hub-bg.webp"):
        path = REPO_ROOT / asset
        assert path.exists(), f"{asset} is missing"
        assert is_tracked(path), (
            f"{asset} exists but is untracked — it would not survive a fresh clone"
        )

    body = (REPO_ROOT / "fjell/static/hub.css").read_text()
    # `url("https://…")` does not contain `url(http`. The stylesheet's house
    # style is a QUOTED url(), so the naive substring could not fire — strip
    # the quotes before looking. The inline `data:` URI survives this: it still
    # reads `url(data:`, and the `http://www.w3.org/2000/svg` inside it is an
    # XML namespace name, not a fetch.
    unquoted = body.replace('"', "").replace("'", "")
    for remote in ("@import", "url(http", "url(//"):
        assert remote not in unquoted, f"hub.css pulls in a remote asset via {remote}"
