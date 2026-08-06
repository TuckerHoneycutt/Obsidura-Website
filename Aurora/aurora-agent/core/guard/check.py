#!/usr/bin/env python3
"""Destructive-operation guard — interface stub. Predicate unimplemented by design.

Contract: check.py <verb> <target> [--labels k=v ...]
Exit: 0 allow, 3 refuse, 4 unknown-verb, 2 bad argv.
AURORA_GUARD_OVERRIDE=1 -> allow with loud stderr (visible in shell history).
"""
import argparse, os, sys

DESTRUCTIVE_VERBS = {"compose-down", "volume-rm", "container-rm", "image-rm",
                     "rm-rf", "db-drop", "prune"}
RECOVERY_VERBS = {"compose-up", "restore", "start"}

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("verb")
    parser.add_argument("target")
    parser.add_argument("--labels", nargs="*", default=[])
    try:
        args = parser.parse_args()
    except SystemExit:
        return 2
    if os.environ.get("AURORA_GUARD_OVERRIDE") == "1":
        print("OVERRIDE: guard bypassed by AURORA_GUARD_OVERRIDE=1", file=sys.stderr)
        return 0
    if args.verb in RECOVERY_VERBS:
        return 0
    if args.verb not in DESTRUCTIVE_VERBS:
        return 4
    raise NotImplementedError(
        "positive lease-label predicate not implemented; see core/guard/SPEC.md")

if __name__ == "__main__":
    sys.exit(main())
