#!/usr/bin/env python3
"""Dump the ACTUAL session cookie values after a real login.

'Not enough segments' means the value in the ID-token slot isn't a JWT.
This prints each cookie's path and segment count so we can tell a real JWT
(3 dot-separated parts) from an opaque Forgejo token (gto_..., 0 dots), and
spot duplicate cookies of the same name at different paths — the browser
sends all of them and the server reads whichever comes first.
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
USER = sys.argv[1] if len(sys.argv) > 1 else "testuser"
PW = sys.argv[2] if len(sys.argv) > 2 else "Sup3rTest!Pass9"

jar = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
op.addheaders = [("User-Agent", "Mozilla/5.0")]


def go(u, d=None):
    b = urllib.parse.urlencode(d).encode() if d else None
    h = {"Content-Type": "application/x-www-form-urlencoded"} if d else {}
    try:
        with op.open(urllib.request.Request(u, data=b, headers=h), timeout=25) as r:
            return r.status, r.geturl(), r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, u, (e.read().decode("utf-8", "replace") if e.fp else "")


def csrf(h):
    m = re.search(r'name="_csrf"\s+value="([^"]+)"', h)
    return m.group(1) if m else ""


_, _, h = go(f"{FJ}/user/login")
go(f"{FJ}/user/login", {"user_name": USER, "password": PW, "_csrf": csrf(h)})
st, url, _ = go(f"https://{D}/agent/{USER}/")
print(f"dashboard: {st} {url}\n")

for c in jar:
    if not c.name.startswith(("hermes_", "__Secure-hermes_", "__Host-hermes_")):
        continue
    val = c.value or ""
    dots = val.count(".")
    kind = "JWT-shaped" if dots == 2 else f"NOT a JWT ({dots} dots)"
    preview = val[:40] + ("…" if len(val) > 40 else "")
    print(f"{c.name}")
    print(f"   path={c.path}  len={len(val)}  {kind}")
    print(f"   value={preview}")
