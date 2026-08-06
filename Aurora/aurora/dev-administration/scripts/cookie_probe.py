#!/usr/bin/env python3
"""Print the cookie names the REAL login flow sets.

Used to confirm the __Secure- / __Host- prefixing rule that
hermes_cli/dashboard_auth/cookies.py applies, because the cookie *name*
changes with (https, path-prefix) and any clearing logic must match it
exactly or it silently no-ops.
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
print(f"dashboard: {st} {url}")
print("cookies set by the real flow:")
for c in jar:
    print(f"   {c.name}   path={c.path}  secure={c.secure}")
