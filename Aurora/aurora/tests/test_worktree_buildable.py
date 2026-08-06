"""Chunk 1 acceptance: a throwaway worktree must be able to resolve the
full compose configuration, which is the property that was broken before
dev-administration was absorbed."""

import subprocess
import sys
import tempfile
from pathlib import Path

from conftest import REPO_ROOT


def test_fresh_worktree_resolves_compose_config():
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "probe"
        subprocess.run(
            ["git", "worktree", "add", "--detach", str(target), "HEAD"],
            cwd=REPO_ROOT, capture_output=True, text=True, check=True,
        )
        try:
            # The worktree has no .env; supply the production one so this
            # tests structure rather than secret availability.
            subprocess.run(
                ["cp", str(REPO_ROOT / ".env"), str(target / ".env")],
                check=True,
            )
            result = subprocess.run(
                ["docker", "compose", "config", "--quiet"],
                cwd=target, capture_output=True, text=True,
            )
            assert result.returncode == 0, (
                "A fresh worktree cannot resolve compose config:\n"
                f"{result.stderr}"
            )

            # Every build context must physically exist in the worktree.
            for context in ("fjell", "agent-authz", "dev-administration"):
                assert (target / context).is_dir(), (
                    f"Build context {context!r} is missing from a fresh "
                    "worktree — it is still not tracked in git"
                )
        finally:
            cleanup = subprocess.run(
                ["git", "worktree", "remove", "--force", str(target)],
                cwd=REPO_ROOT, capture_output=True, text=True,
            )
            if cleanup.returncode != 0:
                message = (
                    "Failed to remove the throwaway worktree — a dangling "
                    f".git/worktrees/probe registration may remain:\n"
                    f"{cleanup.stderr}"
                )
                # Don't let a cleanup failure mask an exception already
                # propagating from the try block (the real failure matters
                # more) — but never let cleanup fail silently either.
                if sys.exc_info()[0] is None:
                    raise AssertionError(message)
                print(message, file=sys.stderr)
