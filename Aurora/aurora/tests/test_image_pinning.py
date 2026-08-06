"""Every external image is pinned by digest, and nothing floats.

Measured 2026-08-01: FIVE of the stack's compose images were floating tags and
every one had ALREADY DRIFTED away from what production was running. A rebuild
on any host that had to pull would have replaced five services with different
software — no diff, no commit, nothing to roll back to. A withdrawn tag fails
loudly; a floating tag succeeds quietly, which is worse.

The pins were taken from the RUNNING digests, so applying them changed nothing.
Pinning to what a tag resolved to that day would itself have been the upgrade.

## Why there are three checks and not one

The first version of this file had one hand-written list of files, and adversarial
review found two whole classes it could not see:

* **Dockerfile `FROM` lines.** `agent-authz:local` and `dev-admin:local` are
  exempt from the digest rule because this repository builds them — but what it
  BUILT THEM FROM was `FROM python:3.13-slim`, floating. The `:local` exemption
  was a hole with a `build:` on it. `Dockerfile` has no suffix, so a
  suffix-based file filter skipped it silently.
* **Untagged references.** `image="alpine"` names an image with no tag at all,
  and a matcher requiring `repo:tag` cannot see it. `redis` — the example the
  issue doc leads with — is the same shape.

So the checks are split by what they can actually prove, and none of them
depends on a person remembering to add a file:

1. `_pinned` — one validator. `repo:tag@sha256:<64 hex>`, everywhere.
2. Tagged references in shipped code, Dockerfiles included.
3. Image references the AST can identify by ROLE — an `image=` argument or an
   `*IMAGE*` constant — which is how an untagged one is caught.

The AST matters for a second reason: this repository is full of ACCURATE prose
naming unpinned images (`#: Measured on codeberg.org/forgejo/forgejo:15`, a
docstring transcript of a probe run in `python:3.14-slim`). Those are records of
what was measured, and rewriting them to carry digests would falsify them. A
grep cannot tell a record from an instruction; an AST can.
"""

from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]

#: Compose files carrying `image:` keys, including the generated-but-COMMITTED
#: branch overlay, which is passed to every `docker compose` call for every
#: branch and was omitted from the first version of this list.
COMPOSE_FILES = ("compose.yml", "affine/compose.yml", "compose.agents.yml",
                 "compose.branch.yml")

#: Repositories this stack depends on. Used only by the TAGGED scan; the
#: role-based scan needs no such list, which is the point of having it.
KNOWN_IMAGE_REPOSITORIES = (
    "ghcr.io/toeverything/affine", "codeberg.org/forgejo/forgejo",
    "codeberg.org/goern/forgejo-mcp", "nousresearch/hermes-agent",
    "arcadedata/arcadedb", "pgvector/pgvector", "tailscale/tailscale",
    "caddy", "redis", "python", "alpine", "debian", "rust",
)

SCANNED_SUFFIXES = (".py", ".yml", ".yaml", ".sh")
DOCKERFILE_NAMES = ("Dockerfile", "Containerfile")
LOCAL_SUFFIX = ":local"

#: A pin, in full. The digest length is checked HERE and nowhere else, because
#: review found `python:3.13-slim@sha256:` — a digest of zero characters —
#: satisfying a `"@sha256:" in image` test. A substring that the value is
#: guaranteed to contain proves nothing about the value.
_PINNED = re.compile(r"^[\w./-]+:[\w.-]+@sha256:[0-9a-f]{64}$")


def _pinned(ref: str) -> bool:
    return bool(_PINNED.match(ref))


def _tracked_files() -> list[Path]:
    out = subprocess.run(["git", "-C", str(REPO), "ls-files"],
                         capture_output=True, text=True)
    if out.returncode != 0:
        pytest.skip("not a git checkout, so the file list cannot be derived")
    return [REPO / line for line in out.stdout.split("\n") if line]


def _shipped(path: Path) -> bool:
    """Excludes tests: a fixture inventing a compose fragment pulls nothing."""
    return (path.is_file()
            and not path.name.startswith("test_")
            and "tests" not in path.parts
            and path.name != Path(__file__).name)


# ---------------------------------------------------------------------------
# 1. the compose files
# ---------------------------------------------------------------------------


def _compose_images(rel: str) -> dict[str, str]:
    text = (REPO / rel).read_text(encoding="utf-8")
    loader = yaml.SafeLoader
    if rel == "compose.branch.yml":
        # The overlay carries `!reset` / `!override`, which SafeLoader refuses.
        class _Tolerant(yaml.SafeLoader):
            pass
        _Tolerant.add_multi_constructor(
            "!", lambda loader, suffix, node: None)
        loader = _Tolerant
    body = yaml.load(text, Loader=loader) or {}
    return {
        name: svc["image"]
        for name, svc in (body.get("services") or {}).items()
        if isinstance(svc, dict) and isinstance(svc.get("image"), str)
    }


@pytest.mark.parametrize("rel", COMPOSE_FILES)
def test_every_compose_image_is_pinned_by_digest(rel):
    unpinned = {
        name: image for name, image in _compose_images(rel).items()
        if not image.endswith(LOCAL_SUFFIX) and not _pinned(image)
    }
    assert not unpinned, (
        f"{rel} names images that are not pinned to a full digest: {unpinned}. "
        "Take the digest from the image production is ALREADY RUNNING "
        "(`docker image inspect <ref> --format '{{index .RepoDigests 0}}'`), "
        "not from what the tag resolves to today — the latter silently "
        "upgrades the service you were trying to freeze."
    )


def test_a_local_image_is_only_a_service_this_repository_builds():
    """`:local` is the one exemption, so it must not be forgeable.

    Note what this does NOT license: the Dockerfile behind a `:local` service
    still has to pin its own base image. See the FROM test below, which exists
    because that hole was real.
    """
    for rel in COMPOSE_FILES:
        for name, image in _compose_images(rel).items():
            if image.endswith(LOCAL_SUFFIX):
                body = yaml.safe_load(
                    (REPO / rel).read_text(encoding="utf-8")) or {}
                assert (body["services"][name].get("build")), (
                    f"{rel}: service {name!r} claims {image!r} but declares no "
                    "`build:`. Only a service this repository builds may skip "
                    "the digest requirement."
                )


# ---------------------------------------------------------------------------
# 2. every FROM, in every Dockerfile
# ---------------------------------------------------------------------------


def test_every_dockerfile_base_image_is_pinned():
    """The hole the `:local` exemption opened.

    `agent-authz:local` and `dev-admin:local` are exempt above because we build
    them. What they were built FROM floated, so `ops/rebuild.sh` on a cold host
    rebuilt four production services on whatever the base tags resolved to that
    day. Exempting the output while ignoring the input is not an exemption, it
    is a gap.
    """
    offenders = []
    for path in _tracked_files():
        if not path.is_file() or not path.name.startswith(DOCKERFILE_NAMES):
            continue
        for number, line in enumerate(
                path.read_text(encoding="utf-8").split("\n"), 1):
            if not line.upper().startswith("FROM "):
                continue
            ref = line.split()[1]
            # `FROM <stage>` referring to an earlier named build stage is not
            # an external image and has nothing to pin.
            if "/" not in ref and ":" not in ref:
                continue
            if not _pinned(ref):
                offenders.append(f"{path.relative_to(REPO)}:{number}: {ref}")
    assert not offenders, (
        "Dockerfile base images are not pinned:\n  " + "\n  ".join(offenders)
    )


# ---------------------------------------------------------------------------
# 3. shipped code
# ---------------------------------------------------------------------------


def _code_strings(path: Path) -> list[tuple[int, str]]:
    """String literals that are VALUES, not documentation.

    Docstrings are excluded because they record measurements; comments never
    become string nodes at all.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return []
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef))
        and getattr(node, "body", None)
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    }
    return [
        (node.lineno, node.value) for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
        and id(node) not in docstrings
    ]


def _image_valued_nodes(path: Path) -> list[tuple[int, str]]:
    """Strings the AST can identify as an image BY ROLE, tagged or not.

    An `image=` argument and an `*IMAGE*` constant are images whatever they
    contain, so `image="alpine"` — no tag, invisible to any `repo:tag` matcher
    — is caught here. This is the check that needs no list of repositories.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return []
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg == "image" and isinstance(kw.value, ast.Constant) \
                        and isinstance(kw.value.value, str):
                    found.append((kw.value.lineno, kw.value.value))
        elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) \
                and isinstance(node.value.value, str):
            for target in node.targets:
                if isinstance(target, ast.Name) and "IMAGE" in target.id:
                    found.append((node.value.lineno, node.value.value))
    return found


def test_no_shipped_code_names_an_image_by_role_without_a_digest():
    """`image=<literal>` and `*IMAGE* = <literal>` must be fully pinned.

    Caught `provision.py` twice: once passing `HERMES_IMAGE` (fine) and twice
    passing a bare `"alpine"` straight to `run_temp_container` three lines
    above it — untagged, and in no compose file, so nothing else in this
    module could see it.
    """
    offenders = [
        f"{path.relative_to(REPO)}:{line}: {value!r}"
        for path in _tracked_files()
        if _shipped(path) and path.suffix == ".py"
        for line, value in _image_valued_nodes(path)
        if not _pinned(value)
    ]
    assert not offenders, (
        "these name an image and are not pinned to a full digest:\n  "
        + "\n  ".join(offenders)
    )


def test_no_shipped_code_names_a_known_image_with_a_floating_tag():
    """The wide net: any known repository, tagged, anywhere that can pull."""
    offenders = []
    for path in _tracked_files():
        if not _shipped(path):
            continue
        if path.suffix == ".py":
            items = _code_strings(path)
        elif path.suffix in SCANNED_SUFFIXES or path.name.startswith(DOCKERFILE_NAMES):
            items = [
                (n, line) for n, line in
                enumerate(path.read_text(encoding="utf-8",
                                         errors="replace").split("\n"), 1)
                if not line.lstrip().startswith("#")
            ]
        else:
            continue
        for line, text in items:
            for repository in KNOWN_IMAGE_REPOSITORIES:
                for match in re.finditer(
                    rf"(?<![\w./-]){re.escape(repository)}:[A-Za-z0-9._-]+",
                    text,
                ):
                    rest = text[match.end():]
                    digest = re.match(r"@sha256:([0-9a-f]{64})(?![0-9a-f])", rest)
                    if not digest:
                        offenders.append(
                            f"{path.relative_to(REPO)}:{line}: {match.group(0)}")
    assert not offenders, (
        "shipped code names a known image with a tag and no full digest:\n  "
        + "\n  ".join(offenders)
        + "\nA tag is a pointer, not a version, and this is code that can pull."
    )
