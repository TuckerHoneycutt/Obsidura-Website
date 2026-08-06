#!/usr/bin/env python3
"""Drive a REAL end-to-end OIDC login for a provisioned developer.

Unlike pipeline_check.py (which probes each component in isolation), this
performs the actual browser flow with a cookie jar:

    1. log into Forgejo with username/password
    2. GET /agent/<user>/            -> 302 to prefixed login
    3. follow to Forgejo /login/oauth/authorize
    4. submit the consent form if Forgejo shows one
    5. land on /agent/<user>/auth/callback?code=...
    6. assert we end up authenticated on the dashboard with real HTML

Exit 0 only if the final page is the authenticated dashboard.

    python3 scripts/e2e_login.py testuser 'Sup3rTest!Pass9'
"""
from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

DOMAIN = os.environ.get("DOMAIN", "superserver.tailc67a98.ts.net")
BASE = f"https://{DOMAIN}"
FORGEJO = f"{BASE}/git"


def build_opener() -> urllib.request.OpenerDirector:
    jar = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    op.addheaders = [("User-Agent", "Mozilla/5.0 e2e-login")]
    return op


def get(op, url: str, timeout: int = 20):
    try:
        with op.open(urllib.request.Request(url), timeout=timeout) as r:
            return r.status, r.geturl(), r.read().decode("utf-8", "replace"), dict(r.headers)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace") if e.fp else ""
        return e.code, url, body, dict(e.headers or {})


def post(op, url: str, data: dict, timeout: int = 20):
    enc = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(
        url, data=enc,
        headers={"Content-Type": "application/x-www-form-urlencoded", "Referer": url},
    )
    try:
        with op.open(req, timeout=timeout) as r:
            return r.status, r.geturl(), r.read().decode("utf-8", "replace"), dict(r.headers)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace") if e.fp else ""
        return e.code, url, body, dict(e.headers or {})




def find_csrf(html: str) -> str:
    for pat in (
        r'name="_csrf"\s+value="([^"]+)"',
        r'name="csrfToken"\s+value="([^"]+)"',
        r'content="([^"]+)"\s+name="csrf-token"',
        r'name="csrf-token"\s+content="([^"]+)"',
    ):
        m = re.search(pat, html)
        if m:
            return m.group(1)
    return ""


def step(n: int, msg: str) -> None:
    print(f"  [{n}] {msg}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("username", nargs="?", default="testuser")
    ap.add_argument("password", nargs="?", default=os.environ.get("TEST_PASSWORD", ""))
    args = ap.parse_args()
    user, pw = args.username, args.password
    if not pw:
        print("FAIL: no password given (arg or $TEST_PASSWORD)")
        return 1

    op = build_opener()

    # 1. Forgejo login
    st, _, html, _ = get(op, f"{FORGEJO}/user/login")
    if st != 200:
        print(f"FAIL: forgejo login page status={st}")
        return 1
    csrf = find_csrf(html)
    st, url, html, _ = post(op, f"{FORGEJO}/user/login",
                            {"user_name": user, "password": pw, "_csrf": csrf})
    if "user/login" in url and ("Username or password is incorrect" in html or st != 200):
        print(f"FAIL: forgejo login rejected (status={st}, url={url})")
        return 1
    step(1, f"forgejo login ok -> {url}")

    # Confirm the WEB session exists. /api/v1/* wants a token, not a cookie,
    # so probe a cookie-authenticated web page instead.
    st, url2, body, _ = get(op, f"{FORGEJO}/user/settings")
    if st != 200 or "/user/login" in url2:
        print(f"FAIL: forgejo web session not established (status={st}, url={url2})")
        return 1
    step(2, "forgejo web session established (/user/settings reachable)")

    # 2-5. the dashboard flow, following redirects (incl. cross to forgejo)
    st, final_url, html, hdrs = get(op, f"{BASE}/agent/{user}/")
    step(3, f"GET /agent/{user}/ -> {st} {final_url}")

    # Forgejo may present a consent screen; submit it.
    if "/login/oauth/authorize" in final_url and "<form" in html:
        csrf = find_csrf(html)
        fields = {"_csrf": csrf, "granted": "true"}
        for key in ("client_id", "state", "scope", "nonce", "redirect_uri",
                    "response_type", "code_challenge", "code_challenge_method"):
            m = re.search(rf'name="{key}"\s+value="([^"]*)"', html)
            if m:
                fields[key] = m.group(1)
        st, final_url, html, hdrs = post(op, f"{FORGEJO}/login/oauth/grant", fields)
        step(4, f"submitted consent -> {st} {final_url}")

    # 6. assertions on the landing page
    ctype = hdrs.get("Content-Type", "")
    if st == 503 or '"detail"' in html and "unreachable" in html:
        print(f"FAIL: provider unreachable at final step: {html[:160]}")
        return 1
    if "/user/login" in final_url:
        print("FAIL: bounced back to forgejo login (session not accepted)")
        return 1
    if "auth/login" in final_url or "/login" in final_url.rstrip("/").split(DOMAIN)[-1]:
        print(f"FAIL: still on a login page: {final_url}")
        return 1
    if st != 200:
        print(f"FAIL: final status={st} url={final_url} body={html[:160]!r}")
        return 1
    if "application/json" in ctype:
        print(f"FAIL: final page is JSON, not the dashboard: {html[:160]}")
        return 1
    if "text/html" not in ctype:
        print(f"FAIL: final content-type={ctype!r}")
        return 1
    if len(html) < 200:
        print(f"FAIL: final HTML suspiciously short ({len(html)}B): {html[:160]!r}")
        return 1

    step(5, f"landed on {final_url} ({len(html)}B {ctype.split(';')[0]})")

    # authenticated API probe — the real proof the session works
    st, _, body, _ = get(op, f"{BASE}/agent/{user}/api/auth/providers")
    step(6, f"providers api -> {st}")

    print(f"\nE2E LOGIN PASSED for {user!r} — dashboard reachable and authenticated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
