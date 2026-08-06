#!/usr/bin/env python3
"""Trace the OIDC redirect chain hop-by-hop with a cookie jar, never
auto-following, so the exact failing hop is visible."""
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


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **kw):
        return None


op = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(jar), NoRedirect
)
op.addheaders = [("User-Agent", "Mozilla/5.0 trace")]


def req(url, data=None, referer=None):
    body = urllib.parse.urlencode(data).encode() if data else None
    headers = {}
    if data:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    if referer:
        headers["Referer"] = referer
    r = urllib.request.Request(url, data=body, headers=headers)
    try:
        with op.open(r, timeout=20) as resp:
            return resp.status, dict(resp.headers), resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers or {}), (e.read().decode("utf-8", "replace") if e.fp else "")


def csrf(h):
    for p in (
        r'name="_csrf"\s+value="([^"]+)"',
        r'content="([^"]+)"\s+name="csrf-token"',
        r'name="csrf-token"\s+content="([^"]+)"',
    ):
        m = re.search(p, h)
        if m:
            return m.group(1)
    return ""


_, _, html = req(f"{FORGEJO}/user/login")
st, hdr, html = req(
    f"{FORGEJO}/user/login",
    {"user_name": USER, "password": PW, "_csrf": csrf(html)},
    referer=f"{FORGEJO}/user/login",
)
print(f"login POST -> {st} loc={hdr.get('Location','')}")
print("cookies:", sorted(c.name for c in jar))

url = f"https://{DOMAIN}/agent/{USER}/"
for hop in range(1, 12):
    st, hdr, body = req(url)
    loc = hdr.get("Location", "")
    ctype = hdr.get("Content-Type", "").split(";")[0]
    print(f"\nhop {hop}: {st} {ctype} {url[:110]}")
    if loc:
        print(f"   -> {loc[:150]}")
    if st in (301, 302, 303, 307, 308) and loc:
        url = urllib.parse.urljoin(url, loc)
        continue
    if st == 200 and "/login/oauth/authorize" in url:
        print("   CONSENT SCREEN")
        forms = re.findall(r"<form[^>]*>.*?</form>", body, re.S)
        print(f"   forms={len(forms)}")
        for f in forms:
            a = re.search(r'action="([^"]*)"', f)
            print("   action=", a.group(1) if a else None)
            for nm, val in re.findall(
                r'<input[^>]*name="([^"]+)"[^>]*value="([^"]*)"', f
            ):
                print(f"      input {nm}={val[:40]}")
            for btn in re.findall(r"<button[^>]*>", f):
                print("      ", btn[:90])
        break
    print(f"   body[:200]={body[:200]!r}")
    break
