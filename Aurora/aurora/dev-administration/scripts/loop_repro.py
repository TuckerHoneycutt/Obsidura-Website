#!/usr/bin/env python3
"""Reproduce the login->verify loop the way a real browser hits it.

The e2e test logs in as `testuser` and passes. The user hits the loop while
authenticated to Forgejo as the ADMIN (supergoodname77, user_id 1) with the
OAuth app already authorized, so Forgejo skips the consent screen and the
callback returns immediately.

This script:
  1. logs into Forgejo as the given account (default: the admin),
  2. walks /agent/<user>/ hop by hop WITHOUT auto-following,
  3. prints every Set-Cookie and Location,
  4. then re-requests the dashboard with the resulting jar to see whether
     the freshly-minted session actually verifies.

Usage: python3 scripts/loop_repro.py <agent_user> <forgejo_user> <password>
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

AGENT = sys.argv[1] if len(sys.argv) > 1 else "testuser"
FUSER = sys.argv[2] if len(sys.argv) > 2 else "supergoodname77"
FPASS = sys.argv[3] if len(sys.argv) > 3 else ""

jar = http.cookiejar.CookieJar()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **kw):
        return None


follow = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
nofollow = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(jar), NoRedirect
)
for o in (follow, nofollow):
    o.addheaders = [("User-Agent", "Mozilla/5.0 loop-repro")]


def req(url, data=None, opener=None, referer=None):
    body = urllib.parse.urlencode(data).encode() if data else None
    headers = {}
    if data:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    if referer:
        headers["Referer"] = referer
    r = urllib.request.Request(url, data=body, headers=headers)
    op = opener or nofollow
    try:
        with op.open(r, timeout=25) as resp:
            return resp.status, dict(resp.headers), resp.read().decode("utf-8", "replace"), resp.geturl()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers or {}), (e.read().decode("utf-8", "replace") if e.fp else ""), url


def csrf(h):
    for p in (r'name="_csrf"\s+value="([^"]+)"',
              r'content="([^"]+)"\s+name="csrf-token"',
              r'name="csrf-token"\s+content="([^"]+)"'):
        m = re.search(p, h)
        if m:
            return m.group(1)
    return ""


if not FPASS:
    print("usage: loop_repro.py <agent_user> <forgejo_user> <password>")
    sys.exit(2)

_, _, html, _ = req(f"{FJ}/user/login", opener=follow)
req(f"{FJ}/user/login", {"user_name": FUSER, "password": FPASS, "_csrf": csrf(html)},
    opener=follow, referer=f"{FJ}/user/login")
st, _, _, url = req(f"{FJ}/user/settings", opener=follow)
print(f"forgejo session as {FUSER!r}: {st} {url}")
if "/user/login" in url:
    print("  -> login FAILED, wrong password?")
    sys.exit(2)

print(f"\nwalking /agent/{AGENT}/ …")
url = f"https://{D}/agent/{AGENT}/"
for hop in range(1, 12):
    st, hdr, body, _ = req(url)
    loc = hdr.get("Location", "")
    ctype = hdr.get("Content-Type", "").split(";")[0]
    print(f"\nhop {hop}: {st} {ctype} {url[:100]}")
    for k, v in hdr.items():
        if k.lower() == "set-cookie":
            name = v.split("=")[0]
            path = re.search(r"[Pp]ath=([^;]*)", v)
            cleared = "Max-Age=0" in v or "max-age=0" in v
            print(f"   set-cookie: {name} path={path.group(1) if path else '?'}"
                  f"{'  [CLEARED]' if cleared else ''}")
    if loc:
        print(f"   -> {loc[:130]}")
    if st in (301, 302, 303, 307, 308) and loc:
        url = urllib.parse.urljoin(url, loc)
        continue
    # Forgejo consent screen: submit it, the way a user clicking
    # "Authorize" does. Without this the walk stops here and never
    # exercises the callback, which is where the loop actually shows up.
    if st == 200 and "/login/oauth/authorize" in url and "<form" in body:
        fields = {"_csrf": csrf(body), "granted": "true"}
        for key in ("client_id", "state", "scope", "nonce", "redirect_uri",
                    "response_type", "code_challenge", "code_challenge_method"):
            m = re.search(rf'name="{key}"\s+value="([^"]*)"', body)
            if m:
                fields[key] = m.group(1)
        print("   [consent screen] submitting Authorize…")
        st, hdr, body, _ = req(f"{FJ}/login/oauth/grant", fields, referer=url)
        loc = hdr.get("Location", "")
        print(f"   grant -> {st} {loc[:120]}")
        for k, v in hdr.items():
            if k.lower() == "set-cookie":
                print(f"   set-cookie: {v.split('=')[0]}")
        if st in (301, 302, 303) and loc:
            url = urllib.parse.urljoin(url, loc)
            continue
    print(f"   body[:120]={body[:120]!r}")
    break

print("\njar now holds:")
for c in jar:
    if "hermes" in c.name:
        print(f"   {c.name} path={c.path} len={len(c.value or '')} dots={(c.value or '').count('.')}")

st, hdr, body, u = req(f"https://{D}/agent/{AGENT}/")
print(f"\nre-request dashboard: {st} {hdr.get('Location','')[:80]}")
print("VERDICT:", "LOOP (bounced back to login)"
      if st in (301, 302) and "login" in hdr.get("Location", "")
      else f"OK ({st})")
