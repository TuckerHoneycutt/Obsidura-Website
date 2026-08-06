#!/usr/bin/env python3
"""Ephemeral resource lease — interface stub. Both subcommands unimplemented by design.

Contract: lease.py acquire            -> prints a fresh lease id on stdout
          lease.py release <lease-id> -> verifies zero residue, then frees
Lease id format: aurora-eph-[0-9a-f]{8}
Exit: 0 success, 2 bad argv. Release is a task-completion gate, not a courtesy.
"""
import argparse, sys

def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("acquire")
    release = sub.add_parser("release")
    release.add_argument("lease_id", metavar="lease-id")
    try:
        args = parser.parse_args()
    except SystemExit:
        return 2
    if args.command == "acquire":
        raise NotImplementedError(
            "lease allocation not implemented; see core/lease/SPEC.md")
    raise NotImplementedError(
        "lease release and residue check not implemented; see core/lease/SPEC.md")

if __name__ == "__main__":
    sys.exit(main())
