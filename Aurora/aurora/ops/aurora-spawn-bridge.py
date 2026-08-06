#!/usr/bin/env python3
"""stdio <-> AF_UNIX relay: what runs INSIDE a developer's agent container.

An MCP client speaks to a subprocess over stdin/stdout. The broker listens on
a unix socket. This is the twenty lines in between, and it is written in
plain Python for one measured reason: `socat` is NOT installed in
`nousresearch/hermes-agent:latest` (checked, 2026-07-31), `python3` is, and
adding a package to a third-party image to move bytes between two file
descriptors is a dependency this does not need.

It holds no credential and makes no decision. Everything it can do, a
developer with a shell in their own container can already do by opening the
socket themselves -- which is the point: the security boundary is the broker
and the bind mount, never this file.

Register it with:

    hermes mcp add aurora -- python3 /run/aurora-spawn/bridge.py
"""

import os
import socket
import sys
import threading

SOCKET_PATH = os.environ.get("AURORA_SPAWN_SOCKET", "/run/aurora-spawn/spawn.sock")


#: One relay read. Big enough that a BRANCH-ACCESS.md is a couple of reads,
#: small enough to stay off the stack of a thread that only moves bytes.
CHUNK_BYTES = 65536


def _pump(read, write, close=lambda: None) -> None:
    try:
        while chunk := read():
            write(chunk)
    except (OSError, ValueError):
        # ValueError: `read1` on an already-closed stdin, which is what the
        # other direction shutting down looks like from in here.
        pass
    finally:
        try:
            close()
        except OSError:
            pass


def main() -> int:
    try:
        conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        conn.connect(SOCKET_PATH)
    except OSError as exc:
        # An MCP client shows stderr on a failed start-up and nothing else, so
        # this message is the entire diagnostic a developer gets.
        sys.stderr.write(
            f"aurora-spawn-bridge: cannot reach {SOCKET_PATH}: {exc}\n"
            "The broker is not running, or this container has no "
            "/run/aurora-spawn mount. Ask an operator.\n"
        )
        return 1

    # Two threads, not select(): stdin here is a pipe and the socket is a
    # socket, and the readable-both case has to keep moving in both directions
    # or a large BRANCH-ACCESS.md deadlocks against a full pipe buffer.
    up = threading.Thread(
        target=_pump,
        args=(lambda: sys.stdin.buffer.read1(CHUNK_BYTES), conn.sendall,
              lambda: conn.shutdown(socket.SHUT_WR)),
        daemon=True,
    )
    up.start()
    _pump(
        lambda: conn.recv(CHUNK_BYTES),
        lambda b: (sys.stdout.buffer.write(b), sys.stdout.buffer.flush()),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
