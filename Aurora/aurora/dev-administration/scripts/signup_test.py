#!/usr/bin/env python3
"""Prove self-service registration actually creates a usable account.

Registers a throwaway user through the real web form (not the admin API),
then confirms it can log in. Verifies the whole path a new developer takes,
including that no email-confirmation wall leaves the account unactivated.
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

USER = sys.argv[1] if len(sys.argv) > 1 else "signuptest"
PW = sys.argv[2] if len(sys.argv) > 2 else "SignUp!Test9xQ"
EMAIL = f"{USER}@obsidura.local"

jar = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
op.addheaders = [("User-Agent", "Mozilla/5.0 signup-test")]


def go(url, data=None, referer=None):
    body = urllib.parse.urlencode(data).encode() if data else None
    headers = {}
    if data:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    if referer:
        headers["Referer"] = referer
    try:
        with op.open(urllib.request.Request(url, data=body, headers=headers), timeout=25) as r:
            return r.status, r.geturl(), r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, url, (e.read().decode("utf-8", "replace") if e.fp else "")


def csrf(html):
    m = re.search(r'name="_csrf"\s+value="([^"]+)"', html)
    return m.group(1) if m else ""


st, _, html = go(f"{FJ}/user/sign_up")
if st != 200:
    print(f"FAIL: sign_up page status={st}")
    sys.exit(1)
if "user_name" not in html:
    print("FAIL: no registration form (registration still disabled?)")
    sys.exit(1)
print("[1] sign-up form reachable")

st, url, body = go(
    f"{FJ}/user/sign_up",
    {"_csrf": csrf(html), "user_name": USER, "email": EMAIL,
     "password": PW, "retype": PW},
    referer=f"{FJ}/user/sign_up",
)
print(f"[2] submit -> {st} {url}")
for pat in ("already been used", "already taken", "must be valid",
            "Password", "captcha"):
    if re.search(pat, body, re.I) and "sign_up" in url:
        snippet = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body))
        m = re.search(r"(error|invalid|already|must)[^.]{0,90}", snippet, re.I)
        print(f"    form error: {m.group(0) if m else pat}")
        break

# Fresh jar: prove the account can log in on its own.
jar2 = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar2))
op.addheaders = [("User-Agent", "Mozilla/5.0 signup-test")]
_, _, html = go(f"{FJ}/user/login")
go(f"{FJ}/user/login",
   {"_csrf": csrf(html), "user_name": USER, "password": PW},
   referer=f"{FJ}/user/login")
st, url, _ = go(f"{FJ}/user/settings")
ok = st == 200 and "/user/login" not in url
print(f"[3] login as new user -> {st} {url}")
print()
print("SELF-SERVICE SIGNUP", "WORKS" if ok else "FAILED")
sys.exit(0 if ok else 1)
