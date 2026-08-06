"""Per-agent authorization gate.

Hermes' OIDC plugin authenticates (proves *who* you are) but does not
authorize (decide *which* agent you may reach) — its own docstring says
"the IDP's own allowlist is authoritative". Forgejo, in turn, has no
per-OAuth2-app user restriction. So any valid Forgejo account could reach
any developer's agent.

This service closes that gap. Caddy calls it via ``forward_auth`` before
proxying to an agent; it verifies the session JWT properly (signature via
the issuer's JWKS, plus iss/aud/exp) and then checks the identity actually
owns the agent named in the path.

Deliberately fail-closed: any error — unverifiable token, unreachable
JWKS, unknown agent — denies access.

Endpoint:
    GET /auth?agent=<username>
        Cookie: __Secure-hermes_session_at=<jwt>

    204  authorized
    401  no/invalid session        (Caddy sends the user to log in)
    403  valid session, wrong user (Caddy shows "not your agent")
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import jwt
from jwt import PyJWKClient

ISSUER = os.environ.get("OIDC_ISSUER", "").rstrip("/")
OWNERS_PATH = os.environ.get("OWNERS_PATH", "/etc/agent-authz/owners.json")
LISTEN_PORT = int(os.environ.get("LISTEN_PORT", "9140"))

# Cookie names: Hermes prefixes with __Secure- when it sees an HTTPS scheme.
# Accept both so the gate keeps working if the forwarded scheme changes.
COOKIE_NAMES = ("__Secure-hermes_session_at", "hermes_session_at")

_jwks_client: PyJWKClient | None = None
_jwks_lock = threading.Lock()

_owners: dict[str, dict] = {}
_owners_mtime = 0.0
_owners_lock = threading.Lock()


def get_jwks() -> PyJWKClient:
    """Cache the JWKS client; PyJWKClient caches keys internally."""
    global _jwks_client
    with _jwks_lock:
        if _jwks_client is None:
            with urllib.request.urlopen(
                f"{ISSUER}/.well-known/openid-configuration", timeout=10
            ) as r:
                disco = json.load(r)
            _jwks_client = PyJWKClient(disco["jwks_uri"], cache_keys=True)
        return _jwks_client


def load_owners() -> dict[str, dict]:
    """Reload the agent->owner map when the file changes.

    Written by ``dev-admin reconcile``; picked up without a restart so
    provisioning a developer takes effect immediately.
    """
    global _owners, _owners_mtime
    with _owners_lock:
        try:
            mtime = os.path.getmtime(OWNERS_PATH)
        except OSError:
            return _owners
        if mtime != _owners_mtime:
            try:
                with open(OWNERS_PATH) as fh:
                    _owners = json.load(fh)
                _owners_mtime = mtime
            except (OSError, ValueError):
                pass  # keep the last good map rather than failing open
        return _owners


def read_cookie(header: str, names: tuple[str, ...]) -> str:
    for part in (header or "").split(";"):
        name, _, value = part.strip().partition("=")
        if name in names:
            return value
    return ""


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):  # noqa: A002,D102 - quiet by default
        pass

    def _reply(self, code: int, reason: str = "") -> None:
        body = reason.encode()
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        if reason:
            self.send_header("X-Authz-Reason", reason[:120])
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/healthz":
            self._reply(200, "ok")
            return

        agent = (parse_qs(parsed.query).get("agent") or [""])[0].strip()
        if not agent:
            self._reply(403, "no agent in request")
            return

        owners = load_owners()
        entry = owners.get(agent)
        if not entry:
            # Unknown agent: fail closed rather than allowing through.
            self._reply(403, f"agent {agent!r} has no registered owner")
            return

        token = read_cookie(self.headers.get("Cookie", ""), COOKIE_NAMES)
        if not token:
            self._reply(401, "no session cookie")
            return

        try:
            signing_key = get_jwks().get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256", "ES256", "RS384", "RS512"],
                issuer=ISSUER,
                audience=entry.get("client_id"),
                options={"require": ["exp", "iss", "sub"]},
            )
        except Exception as exc:  # noqa: BLE001 - any failure denies
            self._reply(401, f"invalid session: {type(exc).__name__}")
            return

        sub = str(claims.get("sub", ""))
        username = str(claims.get("preferred_username") or claims.get("name") or "")

        # Match on Forgejo's numeric user id when we have it — usernames can
        # be changed, ids cannot. Fall back to the username for entries
        # provisioned before the id was recorded.
        want_sub = str(entry.get("owner_sub") or "")
        want_user = str(entry.get("owner_username") or "")
        if want_sub:
            ok = sub == want_sub
        else:
            ok = bool(want_user) and username.lower() == want_user.lower()

        if not ok:
            self._reply(
                403,
                f"{username or sub} is not the owner of agent {agent}",
            )
            return
        self._reply(204)


def main() -> None:
    if not ISSUER:
        raise SystemExit("OIDC_ISSUER is required")
    ThreadingHTTPServer(("0.0.0.0", LISTEN_PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
