#!/usr/bin/env python3
"""End-to-end pipeline verification for a provisioned developer agent.

Imported by the `dev-admin verify` CLI command; also runnable directly as
scripts/pipeline_check.py for use outside the container.

Runs an ordered series of independent checks against the live stack and
prints a PASS/FAIL table. Exit code 0 only when every check passes, so it
can be used as a loop condition:

    until python3 scripts/pipeline_check.py testuser; do sleep 5; done

Each check is deliberately narrow so a failure names the broken component
rather than "the site is down". Checks that cannot run because an earlier
dependency failed are reported as SKIP (and still fail the run).

Usage:
    python3 scripts/pipeline_check.py [username] [--json] [--verbose]

Environment:
    DOMAIN            public host (default superserver.tailc67a98.ts.net)
    FORGEJO_BASE      forgejo base URL (default https://$DOMAIN/git)
    CADDY_CONTAINER   caddy container name
                      (default: resolved from this project's compose labels)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

DOMAIN = os.environ.get("DOMAIN", "superserver.tailc67a98.ts.net")
FORGEJO_BASE = os.environ.get("FORGEJO_BASE", f"https://{DOMAIN}/git")
_CADDY_CACHE = None
_AGENT_CACHE: dict[str, str] = {}


def _caddy_container() -> str:
    """Resolve the caddy container from THIS project's compose labels rather
    than a fixed name, so `dev-admin verify` inside a branch checks the
    branch's Caddy. CADDY_CONTAINER remains an escape hatch, and every use
    site is read-only (cat, caddy validate, wget).

    Resolved lazily and cached: current_project() raises rather than guessing
    when no project is resolvable, so evaluating this at module scope would
    make `import verify` fail outright.
    """
    global _CADDY_CACHE
    if _CADDY_CACHE is None:
        override = os.environ.get("CADDY_CONTAINER")
        if override:
            _CADDY_CACHE = override
        else:
            from dev_administration.project import find_service_container
            _CADDY_CACHE = find_service_container("caddy")
    return _CADDY_CACHE


def _agent_container(user: str) -> str:
    """The developer's agent container in THIS project, or "" if there is none.

    NOT the daemon-global `hermes-<user>`: compose.branch.yml resets
    container_name, so in a branch the container is `br-<x>-hermes-<u>-1` and
    that literal resolves to PRODUCTION's agent -- verify would exec into
    production and report PASS for a broken branch. Label-resolved, like
    _caddy_container(). "" rather than a raise: every call site already treats
    a failed docker command as a FAIL.
    """
    if user not in _AGENT_CACHE:
        from dev_administration.project import ProjectMismatch, find_service_container
        try:
            _AGENT_CACHE[user] = find_service_container(f"hermes-{user}")
        except ProjectMismatch:
            _AGENT_CACHE[user] = ""
    return _AGENT_CACHE[user]


PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"


class Results:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    def add(self, name: str, status: str, detail: str = "") -> None:
        self.rows.append({"check": name, "status": status, "detail": detail})

    def ok(self) -> bool:
        return all(r["status"] == PASS for r in self.rows)

    def failed_names(self) -> list[str]:
        return [r["check"] for r in self.rows if r["status"] != PASS]


def sh(cmd: list[str], timeout: int = 20) -> tuple[int, str, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"
    except FileNotFoundError as exc:
        return 127, "", str(exc)


def http(url: str, timeout: int = 15) -> tuple[int, dict, str]:
    """GET without following redirects. Returns (status, headers, body)."""

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **kw):  # noqa: D401,ANN002,ANN003
            return None

    opener = urllib.request.build_opener(NoRedirect)
    req = urllib.request.Request(url, headers={"User-Agent": "pipeline-check/1"})
    try:
        with opener.open(req, timeout=timeout) as resp:
            return resp.status, dict(resp.headers), resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace") if exc.fp else ""
        return exc.code, dict(exc.headers or {}), body
    except Exception as exc:  # noqa: BLE001
        return 0, {}, f"{type(exc).__name__}: {exc}"


def container_env(container: str, key: str) -> str:
    rc, out, _ = sh(["docker", "exec", container, "printenv", key])
    return out if rc == 0 else ""


# --------------------------------------------------------------------------
# checks
# --------------------------------------------------------------------------


def check_container(r: Results, user: str) -> bool:
    name = _agent_container(user)
    if not name:
        r.add("container.exists", FAIL, f"no hermes-{user} service in this project")
        return False
    rc, out, _ = sh(["docker", "inspect", "-f", "{{.State.Running}}", name])
    if rc != 0:
        r.add("container.exists", FAIL, f"{name} not found")
        return False
    if out != "true":
        r.add("container.exists", FAIL, f"{name} state={out}")
        return False
    r.add("container.exists", PASS, name)
    return True


def check_port(r: Results, user: str) -> int | None:
    name = _agent_container(user)
    rc, out, _ = sh(["docker", "port", name, "9119"])
    if rc != 0 or not out:
        r.add("container.port", FAIL, "9119 not published")
        return None
    m = re.search(r":(\d+)\s*$", out.splitlines()[0])
    if not m:
        r.add("container.port", FAIL, f"unparsable: {out}")
        return None
    port = int(m.group(1))
    r.add("container.port", PASS, f"9119 -> 127.0.0.1:{port}")
    return port


def check_dashboard_process(r: Results, user: str) -> bool:
    name = _agent_container(user)
    rc, out, _ = sh(["docker", "exec", name, "ps", "-eo", "args"])
    if rc != 0:
        r.add("dashboard.process", FAIL, "ps failed")
        return False
    if "hermes dashboard" not in out:
        r.add("dashboard.process", FAIL, "no `hermes dashboard` process")
        return False
    r.add("dashboard.process", PASS, "running")
    return True


def check_dashboard_bound(r: Results, user: str) -> bool:
    """The auth gate refuses to bind 0.0.0.0 without a provider; catch that."""
    name = _agent_container(user)
    rc, out, _ = sh(["docker", "logs", "--tail", "80", name])
    blob = out
    if "Refusing to bind dashboard" in blob.split("HERMES_DASHBOARD_READY")[-1]:
        r.add("dashboard.bound", FAIL, "refusing to bind (no auth provider)")
        return False
    if "HERMES_DASHBOARD_READY" not in blob:
        r.add("dashboard.bound", FAIL, "no READY marker in recent logs")
        return False
    r.add("dashboard.bound", PASS, "READY")
    return True


def check_oidc_env(r: Results, user: str) -> dict:
    name = _agent_container(user)
    env = {
        k: container_env(name, k)
        for k in (
            "HERMES_DASHBOARD_OIDC_CLIENT_ID",
            "HERMES_DASHBOARD_OIDC_CLIENT_SECRET",
            "HERMES_DASHBOARD_OIDC_ISSUER",
            "HERMES_DASHBOARD_PUBLIC_URL",
        )
    }
    missing = [k.split("OIDC_")[-1] for k, v in env.items() if not v]
    if missing:
        r.add("oidc.env", FAIL, f"empty: {', '.join(missing)}")
    else:
        r.add("oidc.env", PASS, f"client_id={env['HERMES_DASHBOARD_OIDC_CLIENT_ID'][:8]}…")
    expect_pub = f"https://{DOMAIN}/agent/{user}"
    if env["HERMES_DASHBOARD_PUBLIC_URL"] != expect_pub:
        r.add("oidc.public_url", FAIL, f"got {env['HERMES_DASHBOARD_PUBLIC_URL']!r} want {expect_pub!r}")
    else:
        r.add("oidc.public_url", PASS, expect_pub)
    return env


def check_oidc_app_live(r: Results, user: str, env: dict, token: str) -> None:
    """The client_id in the container must still exist in Forgejo (not stale)."""
    cid = env.get("HERMES_DASHBOARD_OIDC_CLIENT_ID", "")
    if not cid:
        r.add("oidc.app_live", SKIP, "no client_id")
        return
    if not token:
        r.add("oidc.app_live", SKIP, "no FORGEJO_ADMIN_TOKEN")
        return
    rc, out, _ = sh([
        "curl", "-fsS", f"{FORGEJO_BASE}/api/v1/user/applications/oauth2",
        "-H", f"Authorization: token {token}",
    ])
    if rc != 0:
        r.add("oidc.app_live", FAIL, "forgejo app list failed")
        return
    try:
        apps = json.loads(out)
    except json.JSONDecodeError:
        r.add("oidc.app_live", FAIL, "app list not JSON")
        return
    ids = {a.get("client_id") for a in apps}
    if cid not in ids:
        r.add("oidc.app_live", FAIL, f"client_id {cid[:8]}… STALE (not in Forgejo)")
        return
    app = next(a for a in apps if a.get("client_id") == cid)
    want_redirect = f"https://{DOMAIN}/agent/{user}/auth/callback"
    if want_redirect not in (app.get("redirect_uris") or []):
        r.add("oidc.app_live", FAIL, f"redirect_uri mismatch: {app.get('redirect_uris')}")
        return
    r.add("oidc.app_live", PASS, f"app id={app.get('id')} redirect ok")

    # confidential_client must be true when we send a client_secret, else
    # Forgejo may omit the id_token / reject client auth on the token endpoint.
    if env.get("HERMES_DASHBOARD_OIDC_CLIENT_SECRET") and not app.get("confidential_client"):
        r.add("oidc.confidential", FAIL, "secret configured but app is public (confidential_client=false)")
    else:
        r.add("oidc.confidential", PASS, f"confidential={app.get('confidential_client')}")


def check_discovery(r: Results, user: str) -> dict:
    name = _agent_container(user)
    url = f"{FORGEJO_BASE}/.well-known/openid-configuration"
    rc, out, err = sh(["docker", "exec", name, "curl", "-fsS", "--max-time", "8", url])
    if rc != 0:
        r.add("oidc.discovery", FAIL, f"unreachable from container: {err[:80]}")
        return {}
    try:
        disco = json.loads(out)
    except json.JSONDecodeError:
        r.add("oidc.discovery", FAIL, "discovery not JSON")
        return {}
    for key in ("issuer", "authorization_endpoint", "token_endpoint", "jwks_uri"):
        if not disco.get(key):
            r.add("oidc.discovery", FAIL, f"missing {key}")
            return disco
    r.add("oidc.discovery", PASS, f"issuer={disco['issuer']}")
    return disco


def check_jwks(r: Results, user: str, disco: dict) -> None:
    if not disco.get("jwks_uri"):
        r.add("oidc.jwks", SKIP, "no jwks_uri")
        return
    name = _agent_container(user)
    rc, out, err = sh(["docker", "exec", name, "curl", "-fsS", "--max-time", "8", disco["jwks_uri"]])
    if rc != 0:
        r.add("oidc.jwks", FAIL, f"unreachable: {err[:80]}")
        return
    try:
        keys = json.loads(out).get("keys") or []
    except json.JSONDecodeError:
        r.add("oidc.jwks", FAIL, "jwks not JSON")
        return
    if not keys:
        r.add("oidc.jwks", FAIL, "no keys")
        return
    r.add("oidc.jwks", PASS, f"{len(keys)} key(s), alg={keys[0].get('alg')}")


def check_issuer_match(r: Results, env: dict, disco: dict) -> None:
    """Configured issuer must equal the issuer the IDP advertises, exactly."""
    if not disco:
        r.add("oidc.issuer_match", SKIP, "no discovery")
        return
    cfg = (env.get("HERMES_DASHBOARD_OIDC_ISSUER") or "").rstrip("/")
    adv = (disco.get("issuer") or "").rstrip("/")
    if cfg != adv:
        r.add("oidc.issuer_match", FAIL, f"configured {cfg!r} != advertised {adv!r}")
    else:
        r.add("oidc.issuer_match", PASS, adv)


def check_caddy_route(r: Results, user: str) -> None:
    rc, out, _ = sh(["docker", "exec", _caddy_container(), "cat", "/etc/caddy/Caddyfile.d/agents.conf"])
    if rc != 0:
        r.add("caddy.route", FAIL, "agents.conf unreadable")
        return
    need_prefix = f"header_up X-Forwarded-Prefix /agent/{user}"
    if f"handle_path /agent/{user}" not in out:
        r.add("caddy.route", FAIL, f"no handle_path block for {user}")
        return
    if need_prefix not in out:
        r.add("caddy.route", FAIL, "missing X-Forwarded-Prefix header_up")
        return
    if "}}" in out:
        r.add("caddy.route", FAIL, "malformed braces (}})")
        return
    r.add("caddy.route", PASS, "handle_path + X-Forwarded-Prefix")

    rc2, _, err2 = sh(["docker", "exec", _caddy_container(), "caddy", "validate", "--config", "/etc/caddy/Caddyfile"])
    if rc2 != 0 and "adapting config" in err2:
        r.add("caddy.config_valid", FAIL, err2.splitlines()[-1][:100])
    else:
        r.add("caddy.config_valid", PASS, "adapts cleanly")


def check_entry_redirect(r: Results, user: str) -> None:
    """GET /agent/<user>/ must 302 to the PREFIXED login path."""
    status, headers, body = http(f"https://{DOMAIN}/agent/{user}/")
    loc = headers.get("Location", "")
    if status == 502:
        r.add("http.entry", FAIL, "502 (backend unreachable from Caddy)")
        return
    if status != 302:
        r.add("http.entry", FAIL, f"status={status} body={body[:80]!r}")
        return
    if not loc.startswith(f"/agent/{user}/auth/login"):
        r.add("http.entry", FAIL, f"unprefixed redirect: {loc[:90]}")
        return
    r.add("http.entry", PASS, f"302 -> {loc[:60]}")


def check_login_redirect(r: Results, user: str, env: dict) -> None:
    """GET the login path must 302 to Forgejo /login/oauth/authorize with the
    right client_id and a prefixed redirect_uri."""
    url = f"https://{DOMAIN}/agent/{user}/auth/login?provider=self-hosted&next=%2F"
    status, headers, body = http(url)
    if status != 302:
        r.add("http.login", FAIL, f"status={status} body={body[:120]!r}")
        return
    loc = headers.get("Location", "")
    if "/login/oauth/authorize" not in loc:
        r.add("http.login", FAIL, f"not an authorize redirect: {loc[:90]}")
        return
    cid = env.get("HERMES_DASHBOARD_OIDC_CLIENT_ID", "")
    if cid and f"client_id={cid}" not in loc:
        r.add("http.login", FAIL, "client_id in redirect != container env")
        return
    want = f"%2Fagent%2F{user}%2Fauth%2Fcallback"
    if want not in loc:
        r.add("http.login", FAIL, "redirect_uri missing /agent/<user> prefix")
        return
    r.add("http.login", PASS, "authorize redirect well-formed")


def check_authorize_accepted(r: Results, user: str, env: dict) -> None:
    """Follow the authorize URL unauthenticated. Forgejo must bounce us to its
    OWN login page (303 -> /git/user/login). If it instead returns an
    oauth error, the client registration is broken."""
    cid = env.get("HERMES_DASHBOARD_OIDC_CLIENT_ID", "")
    if not cid:
        r.add("forgejo.authorize", SKIP, "no client_id")
        return
    from urllib.parse import quote
    redirect = quote(f"https://{DOMAIN}/agent/{user}/auth/callback", safe="")
    url = (
        f"{FORGEJO_BASE}/login/oauth/authorize?response_type=code"
        f"&client_id={cid}&redirect_uri={redirect}"
        f"&scope=openid+profile+email&state=probe&code_challenge=probe"
        f"&code_challenge_method=S256"
    )
    status, headers, body = http(url)
    loc = headers.get("Location", "")
    if status in (302, 303) and "user/login" in loc:
        r.add("forgejo.authorize", PASS, "bounces to Forgejo login (client accepted)")
        return
    if status in (302, 303) and "error=" in loc:
        r.add("forgejo.authorize", FAIL, f"oauth error: {loc.split('error=')[-1][:60]}")
        return
    if status == 200 and "authorize" in body.lower():
        r.add("forgejo.authorize", PASS, "consent screen (already authenticated)")
        return
    r.add("forgejo.authorize", FAIL, f"status={status} loc={loc[:70]} body={body[:70]!r}")


def check_no_json_error(r: Results, user: str) -> None:
    """A 200 that is actually a JSON error envelope is a silent failure.
    Probe the SPA root and the providers API."""
    status, headers, body = http(f"https://{DOMAIN}/agent/{user}/login")
    ctype = headers.get("Content-Type", "")
    if status == 200 and "application/json" in ctype:
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            payload = {}
        if "detail" in payload or "error" in payload:
            r.add("http.login_page", FAIL, f"JSON error body: {body[:100]}")
            return
    if status not in (200, 302):
        r.add("http.login_page", FAIL, f"status={status} body={body[:90]!r}")
        return
    if status == 200 and "text/html" not in ctype:
        r.add("http.login_page", FAIL, f"expected HTML, got {ctype!r}")
        return
    r.add("http.login_page", PASS, f"{status} {ctype.split(';')[0] or 'redirect'}")

    status2, _, body2 = http(f"https://{DOMAIN}/agent/{user}/api/auth/providers")
    if status2 != 200:
        r.add("http.providers", FAIL, f"status={status2} body={body2[:90]!r}")
        return
    try:
        provs = json.loads(body2).get("providers") or []
    except json.JSONDecodeError:
        r.add("http.providers", FAIL, "not JSON")
        return
    names = [p.get("name") for p in provs]
    if "self-hosted" not in names:
        r.add("http.providers", FAIL, f"self-hosted absent: {names}")
        return
    r.add("http.providers", PASS, f"providers={names}")


def _parse_log_ts(ts: str):
    """Parse an ISO timestamp from the auth log, tolerating >6 digit fractions."""
    from datetime import datetime, timezone

    ts = (ts or "").strip().replace("Z", "+00:00")
    if not ts:
        return None
    m = re.match(r"(.*\.\d{1,6})\d*([+-]\d{2}:\d{2})?$", ts)
    if m:
        ts = m.group(1) + (m.group(2) or "+00:00")
    try:
        d = datetime.fromisoformat(ts)
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _last_unreachable_ts(user: str):
    """Timestamp of the newest provider_unreachable entry, or None.

    Used as an exact high-water mark so a later run ignores everything an
    earlier run wrote. Wall-clock boundaries are unsafe: two runs seconds
    apart would each see the other's probe entry.
    """
    rc, out, _ = sh([
        "docker", "exec", _agent_container(user), "sh", "-c",
        "tail -n 200 /opt/data/logs/dashboard-auth.log 2>/dev/null || true",
    ])
    if rc != 0:
        return None
    newest = None
    for line in out.splitlines():
        if "provider_unreachable" not in line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        ets = _parse_log_ts(entry.get("ts", ""))
        if ets and (newest is None or ets > newest):
            newest = ets
    return newest


def _authlog_count(user: str, since=None) -> int:
    """Count provider_unreachable entries newer than ``since`` (-1 on error).

    ``since`` defaults to container start. Callers pass this run's start
    timestamp instead, so entries left by PREVIOUS runs' stale-cookie probes
    are excluded and the suite stays idempotent.
    """
    name = _agent_container(user)
    rc, started, _ = sh(["docker", "inspect", "-f", "{{.State.StartedAt}}", name])
    if rc != 0:
        return -1
    from datetime import datetime, timezone

    def parse(ts: str):
        ts = ts.strip().replace("Z", "+00:00")
        # trim fractional seconds to 6 digits for fromisoformat
        m = re.match(r"(.*\.\d{1,6})\d*([+-]\d{2}:\d{2})?$", ts)
        if m:
            ts = m.group(1) + (m.group(2) or "+00:00")
        try:
            d = datetime.fromisoformat(ts)
            return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        except ValueError:
            return None

    start = since or parse(started)
    rc, out, _ = sh([
        "docker", "exec", name, "sh", "-c",
        "tail -n 200 /opt/data/logs/dashboard-auth.log 2>/dev/null || true",
    ])
    if rc != 0:
        return -1
    n = 0
    for line in out.splitlines():
        if "provider_unreachable" not in line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        ets = parse(entry.get("ts", ""))
        if start and ets and ets <= start:
            continue  # at or before the high-water mark -> earlier run
        n += 1
    return n


def check_auth_log_clean(r: Results, user: str, baseline: int, after: int) -> None:
    """Fail if REAL traffic hit a broken session while this suite was running.

    Three classes of provider_unreachable entry exist; only one is a fault:

      1. Before this run started -> prior runs' probes or historical noise.
         Excluded by the caller, which counts from a timestamp captured at
         the start of THIS run. Without this the suite is not idempotent:
         run 2 would see run 1's probe entry and report a false failure.
      2. Caused by this suite's deliberate stale-cookie probe -> expected.
         Caddy rewrites the 503 into a clean cookie-clearing login bounce,
         but Hermes still logs the internal verify failure, so the log line
         is not evidence of a user-visible fault.
      3. Real traffic during the run window -> a genuine fault, fails.

    Class 2 cannot be separated by client IP: Caddy correctly overwrites
    X-Forwarded-For with the true client address, so a marker IP does not
    survive the proxy. The run-window boundary is used instead.
    """
    if baseline < 0 or after < 0:
        r.add("log.auth_clean", SKIP, "auth log unavailable")
        return
    if baseline > 0:
        r.add(
            "log.auth_clean",
            FAIL,
            f"{baseline} provider_unreachable from real traffic during this run",
        )
        return
    probe_caused = max(0, after - baseline)
    detail = "no real-traffic failures"
    detail += f" ({probe_caused} probe-induced)" if probe_caused else ""
    r.add("log.auth_clean", PASS, detail)


def _errlog_count(user: str, since=None) -> int:
    """Count 'unreachable during verify' lines in errors.log.

    ``errors.log`` is plain text with only second-resolution timestamps and
    no client IP, so a timestamp window cannot reliably separate two runs
    that happen within the same second. The caller therefore uses this as a
    running TOTAL and compares before/after deltas instead. ``since`` is
    accepted for symmetry with ``_authlog_count`` but only filters out lines
    predating the container start.
    """
    from datetime import datetime, timezone

    name = _agent_container(user)
    rc, started, _ = sh(["docker", "inspect", "-f", "{{.State.StartedAt}}", name])
    if rc != 0:
        return -1
    try:
        start_dt = datetime.fromisoformat(
            re.sub(r"(\.\d{6})\d*", r"\1", started.strip().replace("Z", "+00:00"))
        )
    except ValueError:
        return -1

    rc, out, _ = sh([
        "docker", "exec", name, "sh", "-c",
        "tail -n 200 /opt/data/logs/errors.log 2>/dev/null || true",
    ])
    if rc != 0:
        return -1
    n = 0
    for ln in (out or "").splitlines():
        if "unreachable during verify" not in ln:
            continue
        m = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", ln)
        if not m:
            continue
        ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone.utc
        )
        if ts < start_dt:
            continue  # pre-restart, historical
        n += 1
    return n


def check_errors_log(r: Results, user: str, baseline: int, after: int) -> None:
    """Fail if the probe caused MORE verify errors than the one it must cause.

    Unlike the auth log, errors.log can't be windowed precisely (second
    resolution, no client IP), so this works purely on the delta across the
    probe: exactly one new line is expected and anything else is suspicious.
    The absolute total is ignored because it accumulates across runs.
    """
    if baseline < 0 or after < 0:
        r.add("log.errors", SKIP, "errors log unavailable")
        return
    delta = after - baseline
    if delta > 1:
        r.add("log.errors", FAIL, f"{delta} new verify errors during probe (expected <=1)")
        return
    detail = "no unexpected verify errors"
    detail += " (1 probe-induced)" if delta == 1 else ""
    r.add("log.errors", PASS, detail)


def check_login_button_target(r: Results, user: str) -> None:
    """The sign-in button on /login must lead somewhere that works.

    Hermes renders the provider button with a hardcoded, UNPREFIXED
    ``href="/auth/login?provider=..."`` (login_page.py). That link is in the
    HTML body, so the Location-header rewrites can't touch it. Left alone it
    lands on the site root -> basic-auth fjell -> 404, which is exactly the
    failure a user hits after clicking "Sign in".

    Caddy rescues it with a Referer-matched redirect. This check follows the
    button the way a browser would: request the href WITH the login page as
    Referer, and require a redirect back under /agent/<user>/.
    """
    status, headers, body = http(f"https://{DOMAIN}/agent/{user}/login")
    if status != 200:
        r.add("http.login_button", SKIP, f"login page status={status}")
        return
    m = re.search(r'href="([^"]*auth/login[^"]*)"', body)
    if not m:
        r.add("http.login_button", FAIL, "no provider sign-in link on /login")
        return
    href = m.group(1).replace("&amp;", "&")

    from urllib.parse import urljoin

    target = urljoin(f"https://{DOMAIN}/agent/{user}/login", href)

    import urllib.request as _u

    class NoRedirect(_u.HTTPRedirectHandler):
        def redirect_request(self, *a, **kw):  # noqa: ANN002,ANN003
            return None

    req = _u.Request(
        target,
        headers={
            "Referer": f"https://{DOMAIN}/agent/{user}/login",
            "User-Agent": "pipeline-check/1",
        },
    )
    try:
        with _u.build_opener(NoRedirect).open(req, timeout=15) as resp:
            st, hdrs = resp.status, dict(resp.headers)
    except urllib.error.HTTPError as exc:
        st, hdrs = exc.code, dict(exc.headers or {})
    except Exception as exc:  # noqa: BLE001
        r.add("http.login_button", FAIL, f"{type(exc).__name__}: {exc}")
        return

    loc = hdrs.get("Location", "")
    if st in (401, 404):
        r.add("http.login_button", FAIL, f"button -> {st} (escapes the /agent/{user} prefix)")
        return
    if st == 302 and "/login/oauth/authorize" in loc:
        r.add("http.login_button", PASS, "button -> IDP authorize")
        return
    if st == 302 and loc.startswith(f"/agent/{user}/"):
        r.add("http.login_button", PASS, f"button -> {loc[:52]}")
        return
    r.add("http.login_button", FAIL, f"button -> {st} {loc[:60]!r}")


def check_secure_cookies(r: Results, user: str) -> None:
    """Session cookies must be Secure / __Secure- prefixed over HTTPS.

    Hermes derives BOTH the cookie Secure flag and the cookie NAME prefix
    from the forwarded scheme. uvicorn only honours X-Forwarded-* from peers
    in ``forwarded_allow_ips`` (default 127.0.0.1); Caddy reaches the
    published port from the Docker bridge gateway, so without
    FORWARDED_ALLOW_IPS the header is discarded, scheme resolves to http,
    and the cookie written at login is looked up under a DIFFERENT name on
    the next request. Result: login_success immediately followed by
    session_verify_failure, and the user ping-pongs between the dashboard
    and the sign-in page.

    Detect it on the very first response — the SSO-attempt cookie shows the
    same scheme derivation without needing a full login.
    """
    status, headers, _ = http(f"https://{DOMAIN}/agent/{user}/")
    cookies = [
        v for k, v in headers.items()
        if k.lower() == "set-cookie" and "hermes" in v.lower()
    ]
    if not cookies:
        r.add("http.secure_cookies", SKIP, f"no hermes cookie on first response ({status})")
        return
    insecure = [
        c.split("=")[0] for c in cookies
        if "Secure" not in c or not c.split("=")[0].startswith("__Secure-")
    ]
    if insecure:
        r.add(
            "http.secure_cookies",
            FAIL,
            f"{insecure[0]} not Secure/__Secure- "
            f"(X-Forwarded-Proto not reaching uvicorn?)",
        )
        return
    r.add("http.secure_cookies", PASS, cookies[0].split("=")[0])


def check_auth_orphan_no_basicauth(r: Results, user: str) -> None:
    """Unprefixed /auth/* must never fall through to the portfolio.

    Browsers strip Referer on cross-origin navigations, so coming back from
    the Forgejo consent screen can hit /auth/login with no referring page.
    The Referer-matched rescue then misses and the request falls through to
    the site's default handler — a bare 404 from fjell, leaving the developer
    stranded mid-sign-in. The 401 branch below is kept anyway: it costs
    nothing and still names the failure if a basic_auth is ever put back.

    TWO valid outcomes, depending on how many developers exist:
      * exactly one  -> 302 into that agent's prefix (unambiguous target)
      * two or more  -> 200 chooser page, because we cannot know which agent
                        the user meant and guessing would send them to
                        someone else's agent
    Only a basic-auth prompt (or a fall-through to the portfolio) is a
    failure. An earlier version of this check accepted only the 302 and so
    reported a false failure the moment a second developer was added.
    """
    for path in ("/auth/login?provider=self-hosted", "/auth/callback?code=x&state=y"):
        status, headers, body = http(f"https://{DOMAIN}{path}")
        if status == 401 or "www-authenticate" in {k.lower() for k in headers}:
            r.add(
                "http.auth_orphan",
                FAIL,
                f"{path.split('?')[0]} -> basic-auth prompt (falls through to portfolio)",
            )
            return
        loc = headers.get("Location", "")
        if status == 302 and loc.startswith("/agent/"):
            continue
        if status == 200 and "choose your agent" in (body or "").lower():
            continue
        r.add(
            "http.auth_orphan",
            FAIL,
            f"{path.split('?')[0]} -> {status} {loc[:40]!r} (neither prefix redirect nor chooser)",
        )
        return
    r.add("http.auth_orphan", PASS, "refererless /auth/* never reaches the portfolio")


def check_unauthenticated_api_blocked(r: Results, user: str) -> None:
    """The agent API must reject requests with no session.

    Guards the property that actually matters: the per-developer container
    is not reachable without a verified OIDC session. Checked directly
    because the sign-in UX has been confusing enough to make it look open.
    """
    for path in ("api/sessions", "api/config"):
        status, _, _ = http(f"https://{DOMAIN}/agent/{user}/{path}")
        if status not in (401, 403):
            r.add(
                "http.api_guarded",
                FAIL,
                f"/{path} returned {status} without a session (expected 401)",
            )
            return
    r.add("http.api_guarded", PASS, "api 401s without a session")


def check_authz_gate(r: Results, user: str) -> None:
    """The per-agent authorization gate must be up and failing closed.

    Hermes authenticates but does not authorize — its OIDC plugin has no
    user allowlist ("the IDP's own allowlist is authoritative") and Forgejo
    has no per-OAuth2-app user restriction. Without the agent-authz gate ANY
    valid Forgejo account can open ANY developer's agent.

    Checks the service is reachable, that it denies a request with no
    session, and that this agent has a registered owner (an unknown agent
    fails closed, which would lock the real owner out).
    """
    import urllib.error
    import urllib.request

    base = os.environ.get("AUTHZ_URL", "http://127.0.0.1:9140")
    try:
        rc, out, _ = sh([
            "docker", "exec", _caddy_container(), "wget", "-S", "-qO-", "--timeout=5",
            f"{base}/auth?agent={user}",
        ])
    except Exception as exc:  # noqa: BLE001
        r.add("authz.gate", FAIL, f"{type(exc).__name__}: {exc}")
        return
    blob = out or ""
    rc2, err, _ = sh([
        "docker", "exec", _caddy_container(), "sh", "-c",
        f"wget -S -qO- --timeout=5 '{base}/auth?agent={user}' 2>&1 | head -20",
    ])
    blob = (blob + (err or ""))
    m = re.search(r"HTTP/1\.1 (\d{3})", blob)
    if not m:
        r.add("authz.gate", FAIL, "agent-authz unreachable (agents would be unguarded)")
        return
    status = int(m.group(1))
    if status == 403 and "no registered owner" in blob:
        r.add("authz.gate", FAIL, f"no owner registered for {user} — owner locked out")
        return
    if status != 401:
        r.add("authz.gate", FAIL, f"no-session request returned {status}, expected 401")
        return
    r.add("authz.gate", PASS, "denies unauthenticated (fails closed)")


def check_stale_cookie_handling(r: Results, user: str) -> None:
    """A stale/garbage value in the ID-token cookie slot must NOT surface as
    503 'provider unreachable'. The correct behaviour is to treat the session
    as invalid and bounce to login (302). This is the exact symptom users hit
    after the OAuth2 app is rotated, so it gets its own check."""
    import urllib.request as _u

    class NoRedirect(_u.HTTPRedirectHandler):
        def redirect_request(self, *a, **kw):  # noqa: ANN002,ANN003
            return None

    req = _u.Request(
        f"https://{DOMAIN}/agent/{user}/",
        headers={
            "Cookie": "hermes_session_at=stale-not-a-jwt; hermes_session_provider=self-hosted",
            "User-Agent": "pipeline-check/1",
        },
    )
    opener = _u.build_opener(NoRedirect)
    try:
        with opener.open(req, timeout=15) as resp:
            status, body = resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        status = exc.code
        body = exc.read().decode("utf-8", "replace") if exc.fp else ""
    except Exception as exc:  # noqa: BLE001
        r.add("http.stale_cookie", FAIL, f"{type(exc).__name__}: {exc}")
        return

    if status == 503 and "unreachable" in body:
        r.add("http.stale_cookie", FAIL, "stale cookie -> 503 provider unreachable")
        return
    if status not in (302, 401):
        r.add("http.stale_cookie", FAIL, f"status={status} body={body[:90]!r}")
        return
    r.add("http.stale_cookie", PASS, f"{status} (session rejected cleanly)")


def _safe_check(r: "Results", name: str, fn, *args) -> None:
    """Run one check, converting an unexpected exception into a FAIL row.

    This module's stated contract is that "each check is deliberately narrow
    so a failure names the broken component rather than 'the site is down'".
    Resolving the caddy container now consults this project's compose labels
    and raises ProjectMismatch when no project is resolvable, so an unwrapped
    check would end the entire run with a traceback instead of reporting.
    """
    try:
        fn(r, *args)
    except Exception as exc:
        r.add(name, FAIL, f"{type(exc).__name__}: {exc}"[:120])


def run_checks(user: str, token: str = "") -> Results:
    """Run every pipeline check for ``user`` and return the Results.

    Shared by the ``dev-admin verify`` CLI command and the standalone
    scripts/pipeline_check.py entrypoint so the two can never drift.
    """
    token = token or os.environ.get("FORGEJO_ADMIN_TOKEN", "")

    # Window boundary for the log checks: the timestamp of the newest
    # provider_unreachable entry that ALREADY exists. Anything at or before it
    # belongs to a previous run (or the container's history) and is out of
    # scope. A wall-clock boundary is not safe here — two runs a couple of
    # seconds apart would each fall inside the other's window and report a
    # false failure. Anchoring to the log's own last entry is exact.
    watermark = _last_unreachable_ts(user)
    r = Results()
    alive = check_container(r, user)
    if alive:
        check_port(r, user)
        check_dashboard_process(r, user)
        check_dashboard_bound(r, user)
        env = check_oidc_env(r, user)
        disco = check_discovery(r, user)
        check_jwks(r, user, disco)
        check_issuer_match(r, env, disco)
        check_oidc_app_live(r, user, env, token)
        check_authorize_accepted(r, user, env)
    else:
        env = {}
    _safe_check(r, "caddy.route", check_caddy_route, user)
    check_entry_redirect(r, user)
    if alive:
        check_login_redirect(r, user, env)
    check_no_json_error(r, user)
    check_login_button_target(r, user)
    check_secure_cookies(r, user)
    check_auth_orphan_no_basicauth(r, user)
    check_unauthenticated_api_blocked(r, user)
    _safe_check(r, "authz.gate", check_authz_gate, user)

    # Sample the logs, fire the deliberate stale-cookie probe, then re-sample.
    # The auth-log sample is bounded by a high-water mark taken at the top of
    # this run, so entries written by earlier runs never count. Only the
    # pre-probe count reflects real traffic; the probe itself always makes
    # Hermes log one internal verify failure even though Caddy turns the
    # response into a clean login bounce.
    auth_before = _authlog_count(user, since=watermark) if alive else -1
    err_before = _errlog_count(user) if alive else -1
    check_stale_cookie_handling(r, user)
    if alive:
        import time as _time

        _time.sleep(1)  # let the async log write land
        check_auth_log_clean(
            r, user, auth_before, _authlog_count(user, since=watermark)
        )
        check_errors_log(r, user, err_before, _errlog_count(user))
    return r


def render(r: Results, user: str, as_json: bool = False) -> None:
    """Print a Results table (or JSON) exactly as the CLI/script expect."""
    if as_json:
        print(json.dumps({"ok": r.ok(), "checks": r.rows}, indent=2))
        return
    width = max(len(x["check"]) for x in r.rows) + 2
    for row in r.rows:
        mark = {PASS: "✓", FAIL: "✗", SKIP: "–"}[row["status"]]
        print(f"  {mark} {row['check']:<{width}} {row['detail']}")
    print()
    if r.ok():
        print(f"ALL {len(r.rows)} CHECKS PASSED for '{user}'")
    else:
        print(f"FAILED: {', '.join(r.failed_names())}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("username", nargs="?", default="testuser")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    user = args.username
    r = run_checks(user)
    render(r, user, as_json=args.json)
    return 0 if r.ok() else 1


if __name__ == "__main__":
    sys.exit(main())
