#!/usr/bin/env python3
"""Standalone wrapper around ``dev_administration.verify``.

The checks themselves live in the package (``dev_administration/verify.py``)
so that ``dev-admin verify`` and this script can never drift apart. This
wrapper exists for running the suite from a plain checkout / the Docker host
without installing the CLI.

    python3 scripts/pipeline_check.py testuser
    python3 scripts/pipeline_check.py testuser --json

Exit code is 0 only when every check passes, so it works as a loop condition:

    until python3 scripts/pipeline_check.py testuser; do sleep 5; done
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from dev_administration.verify import render, run_checks  # noqa: E402


def _load_token() -> str:
    """FORGEJO_ADMIN_TOKEN from the env, else the stack's .env.

    Without it the oidc.app_live check can't run and SKIPs, which counts as
    a non-pass — a confusing failure that looks like a stale OAuth2 app.
    """
    tok = os.environ.get("FORGEJO_ADMIN_TOKEN", "")
    if tok:
        return tok
    here = os.path.dirname(os.path.abspath(__file__))
    for candidate in (
        os.path.join(here, "..", "..", ".env"),
        os.path.join(here, "..", ".env"),
    ):
        try:
            with open(candidate) as fh:
                for line in fh:
                    if line.startswith("FORGEJO_ADMIN_TOKEN="):
                        return line.split("=", 1)[1].strip().strip("\"'")
        except OSError:
            continue
    return ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("username", nargs="?", default="testuser")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()
    results = run_checks(args.username, token=_load_token())
    render(results, args.username, as_json=args.json)
    return 0 if results.ok() else 1


if __name__ == "__main__":
    sys.exit(main())
