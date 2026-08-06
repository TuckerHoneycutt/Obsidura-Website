#!/usr/bin/env python3
"""Log in for real, then assert the SPA shell AND its JS/CSS assets load
through the /agent/<user> prefix. Catches 'HTTP 200 but broken page'."""
from __future__ import annotations

import http.cookiejar
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

DOMAIN = "superserver.tailc67a98.ts.net"
FORGEJO = f"https://{DOMAIN}/git"
USER = sys.argv[1] if len(sys.argv) > 1 else "testuser"
PW = sys.argv[2] if len(sys.argv) > 2 else "Sup3rTest!Pass9"

jar = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
op.addheaders = [("User-Agent", "Mozilla/5.0 asset-check")]


def go(url, data=None):
    body = urllib.parse.urlencode(data).encode() if data else None
    h = {"Content-Type": "application/x-www-form-urlencoded"} if data else {}
    try:
        with op.open(urllib.request.Request(url, data=body, headers=h), timeout=25) as r:
            return r.status, r.geturl(), r.read().decode("utf-8", "replace"), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, url, (e.read().decode("utf-8", "replace") if e.fp else ""), dict(e.headers or {})


def csrf(h):
    for p in (r'name="_csrf"\s+value="([^"]+)"',
              r'content="([^"]+)"\s+name="csrf-token"',
              r'name="csrf-token"\s+content="([^"]+)"'):
        m = re.search(p, h)
        if m:
            return m.group(1)
    return ""


fails = []

_, _, html, _ = go(f"{FORGEJO}/user/login")
go(f"{FORGEJO}/user/login", {"user_name": USER, "password": PW, "_csrf": csrf(html)})

st, url, html, hdrs = go(f"https://{DOMAIN}/agent/{USER}/")
print(f"dashboard: {st} {url}")
if st != 200:
    fails.append(f"dashboard status {st}")
if "text/html" not in hdrs.get("Content-Type", ""):
    fails.append("dashboard not HTML")
if '"detail"' in html and "unreachable" in html:
    fails.append("provider unreachable JSON")

assets = re.findall(r'(?:src|href)="(/agent/[^"]+\.(?:js|css))"', html)
assets += re.findall(r'(?:src|href)="(/[^"/][^"]*\.(?:js|css))"', html)
assets = list(dict.fromkeys(assets))
print(f"assets referenced: {len(assets)}")

if not assets:
    fails.append("no JS/CSS assets referenced in SPA shell")

for a in assets[:6]:
    if not a.startswith(f"/agent/{USER}/"):
        fails.append(f"asset not prefixed: {a}")
        print(f"  ✗ {a} (missing /agent/{USER} prefix)")
        continue
    ast_, _, _, ah = go(f"https://{DOMAIN}{a}")
    ct = ah.get("Content-Type", "").split(";")[0]
    ok = ast_ == 200 and ("javascript" in ct or "css" in ct)
    print(f"  {'✓' if ok else '✗'} {a} -> {ast_} {ct}")
    if not ok:
        fails.append(f"asset {a} -> {ast_} {ct}")

st_api, _, body_api, _ = go(f"https://{DOMAIN}/agent/{USER}/api/auth/providers")
print(f"providers api: {st_api}")
if st_api != 200:
    fails.append(f"providers api {st_api}")

print()
if fails:
    print("ASSET/SPA CHECK FAILED:")
    for f in fails:
        print(f"  - {f}")
    sys.exit(1)
print(f"SPA + ASSETS OK for {USER!r} — dashboard fully functional behind the prefix")
