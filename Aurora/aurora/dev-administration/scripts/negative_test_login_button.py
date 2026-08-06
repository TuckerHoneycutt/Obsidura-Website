#!/usr/bin/env python3
"""Negative test: prove check_login_button_target actually catches the bug.

Writes an agents.conf WITHOUT the Referer rescue route, reloads Caddy, and
reports what the sign-in button does. A check that never fails is worthless,
so this confirms the check fails when the fix is absent.

Restores the real config on exit, always.
"""
from __future__ import annotations

import subprocess
import sys
import time

CADDY = "aurora-caddy-1"
CONF = "/etc/caddy/Caddyfile.d/agents.conf"
BAK = "/tmp/agents.realbak"


def sh(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def dexec(*args):
    return sh(["docker", "exec", CADDY, *args])


def reload_caddy():
    return dexec("caddy", "reload", "--config", "/etc/caddy/Caddyfile")


def main() -> int:
    # Back up the real config
    dexec("cp", CONF, BAK)
    original = dexec("cat", CONF).stdout

    # Rebuild it without the rescue block: drop the @auth_escape matcher
    # (3 lines + closing brace) and its redir line.
    out, skip = [], False
    for line in original.splitlines():
        s = line.strip()
        if s.startswith("@auth_escape_"):
            skip = True
            continue
        if skip:
            if s == "}":
                skip = False
            continue
        if s.startswith("redir @auth_escape_"):
            continue
        out.append(line)
    stripped = "\n".join(out) + "\n"

    try:
        p = subprocess.run(
            ["docker", "exec", "-i", CADDY, "sh", "-c", f"cat > {CONF}"],
            input=stripped, capture_output=True, text=True,
        )
        if p.returncode != 0:
            print("could not write stripped config:", p.stderr[:200])
            return 2

        v = dexec("caddy", "validate", "--config", "/etc/caddy/Caddyfile")
        if "Valid configuration" not in (v.stdout + v.stderr):
            print("stripped config is INVALID — test inconclusive")
            print((v.stdout + v.stderr)[-300:])
            return 2
        reload_caddy()
        time.sleep(2)

        sys.path.insert(0, "..")
        from dev_administration.verify import (  # noqa: E402
            Results, check_login_button_target,
        )

        r = Results()
        check_login_button_target(r, "testuser")
        row = r.rows[0]
        print(f"WITHOUT the rescue route: {row['status']}  {row['detail']}")
        return 0 if row["status"] == "FAIL" else 1
    finally:
        dexec("cp", BAK, CONF)
        reload_caddy()
        time.sleep(2)
        print("restored real config")


if __name__ == "__main__":
    rc = main()
    print("\nnegative test", "PASSED (check catches the bug)" if rc == 0
          else "FAILED (check would not have caught it)")
    sys.exit(rc)
