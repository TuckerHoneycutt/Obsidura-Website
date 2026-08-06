#!/usr/bin/env python3
"""End-to-end proof that agent isolation holds THROUGH CADDY.

authz_test.py calls the gate directly. This drives a full browser-style
login as a non-owner and then tries to open someone else's agent and read
its API — the attack that actually matters.

Usage:
  python3 scripts/isolation_test.py <agent> <owner_u> <owner_pw> <other_u> <other_pw>
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


def browser(user: str, pw: str):
    jar = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    op.addheaders = [("User-Agent", "Mozilla/5.0 isolation-test")]

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
    return go, csrf


def open_agent(go, csrf, agent: str):
    """Full sign-in attempt at /agent/<agent>/, consent included."""
    st, url, html = go(f"https://{D}/agent/{agent}/")
    if "/login/oauth/authorize" in url and "<form" in html:
        fields = {"_csrf": csrf(html), "granted": "true"}
        for k in ("client_id", "state", "scope", "nonce", "redirect_uri",
                  "response_type", "code_challenge", "code_challenge_method"):
            m = re.search(rf'name="{k}"\s+value="([^"]*)"', html)
            if m:
                fields[k] = m.group(1)
        st, url, html = go(f"{FJ}/login/oauth/grant", fields, referer=url)
    return st, url, html


if len(sys.argv) < 6:
    print(__doc__)
    sys.exit(2)

agent, owner, owner_pw, other, other_pw = sys.argv[1:6]
ok = True

go, csrf = browser(owner, owner_pw)
st, url, html = open_agent(go, csrf, agent)
owner_in = st == 200 and f"/agent/{agent}/" in url and "<!doctype html>" in html.lower()
print(f"[owner]     {owner:12} -> {st} {url}")
print(f"            reached dashboard: {owner_in}")
ok &= owner_in
st, _, _ = go(f"https://{D}/agent/{agent}/api/sessions")
print(f"            api/sessions -> {st}")
ok &= st == 200

go2, csrf2 = browser(other, other_pw)
st2, url2, html2 = open_agent(go2, csrf2, agent)
blocked = ("isn't your agent" in html2.lower()) or st2 in (401, 403)
print(f"[non-owner] {other:12} -> {st2} {url2}")
print(f"            blocked: {blocked}")
ok &= blocked
st3, _, body3 = go2(f"https://{D}/agent/{agent}/api/sessions")
api_blocked = st3 in (401, 403) or "isn't your agent" in body3.lower()
print(f"            api/sessions -> {st3} blocked={api_blocked}")
ok &= api_blocked

print()
print("AGENT ISOLATION", "ENFORCED" if ok else "**BROKEN**")
sys.exit(0 if ok else 1)
