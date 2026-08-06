"""Host-side branch lifecycle for this stack.

Standard library plus `pyyaml`, driven by `argparse` (decision D-A):
`aurora branch up` has to run before a branch worktree owns a venv, so every
runtime dependency is a thing that must exist in the host venv, in a fresh
worktree and in the `aurora-cli:local` image. `pyyaml` earns its place --
Compose and three manifests are YAML. Nothing else has.

`identity` is the only module that answers "what is production?"; everything
else asks it.
"""

__all__ = ["identity"]
