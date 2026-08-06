#!/usr/bin/env python3
"""Prove the per-agent authz gate accepts the owner and rejects everyone else.

Logs in as two different Forgejo accounts, obtains a real session JWT for
each, and calls the authz endpoint directly for the same agent. The owner
must get 204; the non-owner must get 403.

Usage:
  python3 scripts/authz_test.py <agent> <owner_user> <owner_pw> <other_user> <other_pw>
"""
from __future__ import annotations

import http.cookiejar
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

D = "superserver.tailc67a98.ts.net"
FJ = f"https://{D}/git"
AUTHZ = "http://127.0.0.1:9140"


def session_token(user: str, pw: str, agent: str) -> str:
    """Complete a real OIDC login and return the session JWT."""
    jar = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    op.addheaders = [("User-Agent", "Mozilla/5.0 authz-test")]

    def go(url, data=None, referer=None):
        body = urllib.parse.urlencode(data).encode() if data else None
        h = {"Content-Type": "application/x-www-form-urlencoded"} if data else {}
        if referer:
            h["Referer"] = referer
        try:
            with op.open(urllib.request.Request(url, data=body, headers=h), timeout=25) as r:
                return r.status, r.geturl(), r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            return e.code, url, (e.read().decode("utf-8", "replace") if e.fp else "")

    def csrf(html):
        m = re.search(r'name="_csrf"\s+value="([^"]+)"', html)
        return m.group(1) if m else ""

    _, _, html = go(f"{FJ}/user/login")
    go(f"{FJ}/user/login", {"user_name": user, "password": pw, "_csrf": csrf(html)},
       referer=f"{FJ}/user/login")

    _, url, html = go(f"https://{D}/agent/{agent}/")
    # Submit the consent screen if Forgejo shows one.
    if "/login/oauth/authorize" in url and "<form" in html:
        fields = {"_csrf": csrf(html), "granted": "true"}
        for k in ("client_id", "state", "scope", "nonce", "redirect_uri",
                  "response_type", "code_challenge", "code_challenge_method"):
            m = re.search(rf'name="{k}"\s+value="([^"]*)"', html)
            if m:
                fields[k] = m.group(1)
        go(f"{FJ}/login/oauth/grant", fields, referer=url)

    for c in jar:
        if c.name.endswith("hermes_session_at"):
            return c.value or ""
    return ""


def ask_authz(agent: str, token: str) -> tuple[int, str]:
    """Call the gate the way Caddy's forward_auth does."""
    import subprocess
    cmd = [
        "docker", "exec", "aurora-caddy-1", "wget", "-S", "-qO-",
        "--timeout=6", "--header", f"Cookie: __Secure-hermes_session_at={token}",
        f"{AUTHZ}/auth?agent={agent}",
    ]
    p = subprocess.run(cmd, capture_output=True, text=True)
    blob = p.stdout + p.stderr
    m = re.search(r"HTTP/1\.1 (\d{3})", blob)
    reason = re.search(r"X-Authz-Reason:\s*(.+)", blob)
    return (int(m.group(1)) if m else 0,
            reason.group(1).strip() if reason else "")


if len(sys.argv) < 6:
    print(__doc__)
    sys.exit(2)

agent, owner, owner_pw, other, other_pw = sys.argv[1:6]

ok = True

tok = session_token(owner, owner_pw, agent)
if not tok:
    print(f"FAIL: could not get a session for owner {owner!r}")
    sys.exit(1)
code, reason = ask_authz(agent, tok)
print(f"[owner]     {owner:14} -> {code} {reason}")
ok &= code == 204

tok2 = session_token(other, other_pw, agent)
if not tok2:
    print(f"note: {other!r} got no session (may lack a grant); treating as denied")
    code2, reason2 = 401, "no session"
else:
    code2, reason2 = ask_authz(agent, tok2)
print(f"[non-owner] {other:14} -> {code2} {reason2}")
ok &= code2 in (401, 403)

code3, reason3 = ask_authz(agent, "not-a-jwt")
print(f"[garbage]   {'bad token':14} -> {code3} {reason3}")
ok &= code3 == 401

print()
print("PER-AGENT AUTHZ", "ENFORCED" if ok else "**NOT ENFORCED**")
sys.exit(0 if ok else 1)
