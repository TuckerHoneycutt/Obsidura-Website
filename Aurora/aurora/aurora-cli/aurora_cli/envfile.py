"""Strict `KEY=value` env files, and the branch `.env` renderer.

A branch's `.env` is rendered **from production's**. That is deliberate --
a branch is meant to be a test of production, not a test of a fiction -- but
it has one consequence that has already cost this project a review cycle and
would eventually cost it an outage:

    anything not explicitly overridden is INHERITED, and the omission is
    invisible. No error, no warning, just a branch quietly wired to
    production.

`branch-env.yaml` is the machine-readable answer to that: every variable a
branch must override, how it is derived, and -- required on every entry --
whether omitting it is fatal.

Two detectors, and they must stay independent
---------------------------------------------
The obvious design fails. If the renderer and the checker are both driven by
`branch-env.yaml`, then deleting an entry blinds both at once and the
manifest pins nothing: the rendered file inherits production's value and the
checker no longer asks about it. That is the same "test that passes while
testing nothing" this project has shipped ten times.

So `missing_overrides()` is the union of two rule sets:

* `manifest_gaps()`   -- what the manifest says must be overridden;
* `inherited_hazards()` -- manifest-FREE invariants about the rendered file:
  production's domain must not survive into any value, the project name must
  carry the branch namespace, `COMPOSE_PROFILES` must not activate every
  developer, and no upstream may point at loopback.

Delete `FORGEJO_URL` from the manifest and the hazard rules still catch it,
because production's hostname is then sitting in a rendered value. Delete
`COMPOSE_PROFILES` and the hazard rules still catch it, because `agents`
activates every developer. That is the property the manifest exists to have.

Strict `KEY=value` (trap 7)
---------------------------
`KEY = value` is accepted by Compose, which trims, and by nothing else:
`docker run --env-file` refuses the whole file and `. ./.env` mis-parses it as
a command. Production ran for months with `DOMAIN_NAME = ...` on line 1 and it
surfaced as a Caddy error that named neither. `parse_env` refuses it; the
renderer emits nothing but `KEY=value`; and
`tests/test_repo_conformance.py::test_dotenv_files_use_strict_key_equals_value`
is imported by this package's tests rather than restated, so there is one
predicate rather than two that drift.

Dependencies: standard library plus `pyyaml` (decision D-A).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import yaml

from aurora_cli import crosswire, identity

MANIFEST_NAME = "branch-env.yaml"
ENV_FILE_NAME = ".env"

#: The Compose profile one developer's agent is parked behind: `agent-<user>`,
#: never the collective `agents` (spec D7). Defined once because it is written
#: in one direction by `_derive_agent_profiles` and read back in the other by
#: `developers_from_profiles`.
AGENT_PROFILE_PREFIX = "agent-"

# A POSIX-ish environment variable name. Anything else -- `export FOO`,
# `FOO-BAR`, a leading digit -- is refused rather than silently accepted,
# because every consumer of this file (Compose, `--env-file`, a shell) draws
# the line in a different place and the intersection is this.
_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# The compose profile that activates EVERY developer's agent. Production sets
# it; spec D7 says a branch provisions only the requesting developer, so a
# branch carrying this profile is a defect no matter what the manifest says.
ALL_DEVELOPERS_PROFILE = "agents"

# Addresses that reach nothing from inside the Tailscale sidecar's network
# namespace, which is where a branch's Caddy runs (`network_mode:
# service:tailscale`). An upstream pointing at one of these produces a stack
# that starts, serves 502s, and looks healthy.
_LOOPBACK_MARKERS = ("127.0.0.1", "localhost", "[::1]", "::1")

# Rendered variables that may legitimately still name production.
#
# Empty, on purpose, and that is the strongest form this can take: there is
# currently no variable a branch's `.env` has any business pointing at
# production. It exists as a NAMED escape hatch so that the day one is needed,
# the exemption is a reviewed line in this file with a reason next to it
# rather than a weakened scan. `tests/test_branch_env.py` pins the mechanism
# in both directions so an empty set does not make the check vacuous.
ALLOWED_PRODUCTION_REFERENCES: frozenset[str] = frozenset()


class EnvFileError(ValueError):
    """A `.env` file, or a rendering of one, is not strict `KEY=value`.

    A `ValueError` rather than an `IdentityError`: this is a malformed file,
    not a failure to work out which stack is production. Every message names
    the offending line and, where the rule is non-obvious, the tool that
    refuses it -- "invalid syntax" with no operand is the error that gets
    suppressed.
    """


class ManifestError(ValueError):
    """`branch-env.yaml` is missing, malformed, or an entry is under-specified."""


class BranchEnvError(ValueError):
    """A branch `.env` cannot be rendered: a fatal variable has no value."""


# ---------------------------------------------------------------------------
# strict KEY=value
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EnvLine:
    """One physical line: an assignment, a comment, or a blank."""

    kind: str                       # "assignment" | "comment" | "blank"
    raw: str                        # verbatim, for comments and blanks
    key: str | None = None
    value: str | None = None

    def render(self) -> str:
        if self.kind == "assignment":
            return f"{self.key}={self.value}"
        return self.raw


class EnvFile(dict):
    """A `.env` as both a mapping and an ordered list of lines.

    A plain `dict` cannot round-trip: production's `.env` is 11 KB of which
    185 lines are commented-out configuration for an unrelated product,
    much of it containing `=` inside comment text. Losing that on every
    render would turn "the branch `.env` is production's with N variables
    changed" into "the branch `.env` is a fresh file that happens to look
    similar", and the diff a human reads to check a branch would be useless.

    Mapping access answers "what is the value of X"; `lines` answers "what
    does the file look like". Both are needed and neither is derivable from
    the other.
    """

    def __init__(self, lines: Sequence[EnvLine]):
        self.lines: tuple[EnvLine, ...] = tuple(lines)
        super().__init__(
            (line.key, line.value)
            for line in self.lines
            if line.kind == "assignment"
        )


def parse_env(text: str) -> EnvFile:
    """Parse strict `KEY=value` text. Refuses anything Compose merely tolerates.

    Refused, each with the line number and the line:

    * whitespace before the key, or between the key and `=` -- the exact
      shape `docker run --env-file` rejects the whole file over;
    * whitespace immediately after `=`, which a shell reads as a command;
    * a key that is not a valid environment variable name;
    * a line that is neither blank, nor a comment, nor an assignment;
    * a duplicate key, because Compose takes the last and other readers take
      the first, so the file means two things at once;
    * a QUOTED value, and a value with TRAILING WHITESPACE. Both added by
      Task 8, and both for the reason the padded shapes were already refused.

    **The trailing-whitespace rule reverses what this docstring used to say,
    and the reversal is a measurement.** Task 2 preserved trailing whitespace
    on the grounds that it "is inside the value as far as every consumer is
    concerned". That is false in this stack, verified on this host 2026-07-30:

        .env line        docker compose config     docker run --env-file
        TRAIL=bar        'bar'                     'bar'
        TRAIL=bar␠       'bar'                     'bar␠'
        QUOTED="baz"     'baz'                     '"baz"'

    Compose strips both; `--env-file` keeps both. So a trailing space is
    exactly as ambiguous as a quote, it is invisible in a diff, and finding F3
    measured the consequence: with `DOMAIN_NAME=<host>␠` in production's
    `.env`, `hooks/pre-push` returned **verdict=allow** on a push to a branch
    forge where the clean form correctly rejects. A cross-wiring defence that
    fails open is the worst available outcome, so the ambiguous input is
    refused here rather than interpreted.

    `identity._read_env_file` and the hook both NORMALISE these shapes, and
    after Task 8 they agree with each other on all nine;
    `aurora-cli/tests/test_env_reader_agreement.py` holds the whole
    measurement and the agreement property in one place.
    """
    lines: list[EnvLine] = []
    seen: dict[str, int] = {}
    for number, raw in enumerate(text.splitlines(), 1):
        if not raw.strip():
            lines.append(EnvLine("blank", raw))
            continue
        if raw.lstrip().startswith("#"):
            lines.append(EnvLine("comment", raw))
            continue
        if raw != raw.lstrip():
            raise EnvFileError(
                f"line {number}: {raw!r} is indented. A dotenv assignment must "
                "start at column 1; `docker run --env-file` rejects the entire "
                "file over leading whitespace."
            )
        key, sep, value = raw.partition("=")
        if not sep:
            raise EnvFileError(
                f"line {number}: {raw!r} is neither blank, a comment, nor a "
                "KEY=value assignment."
            )
        if key != key.strip():
            raise EnvFileError(
                f"line {number}: {raw!r} has whitespace around `=`. Compose "
                "trims it and everything else does not -- `docker run "
                "--env-file` refuses the file with \"variable "
                f"'{key}' contains whitespaces\", and `. ./.env` in a shell "
                "mis-parses the line as a command."
            )
        if value[:1].isspace():
            raise EnvFileError(
                f"line {number}: {raw!r} has whitespace after `=`. The space "
                "becomes part of the value for `docker run --env-file`, and a "
                "shell reads the rest of the line as a command."
            )
        if not _KEY.match(key):
            raise EnvFileError(
                f"line {number}: {key!r} is not a valid environment variable "
                "name (letters, digits and underscore, not starting with a "
                "digit)."
            )
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            raise EnvFileError(
                f"line {number}: {raw!r} QUOTES its value. Measured on this "
                "host 2026-07-30: `docker compose config` resolves "
                '`QUOTED="baz"` to `baz` and `docker run --env-file` resolves '
                'it to `"baz"`, so the line means two different things '
                "depending on which reader sees it -- and one of the readers "
                "is `hooks/pre-push`, where a quoted DOMAIN_NAME makes the "
                "hook ALLOW a push to a branch forge (finding F3: "
                "verdict=allow where the unquoted form correctly rejects). "
                "Write the value unquoted."
            )
        if value != value.rstrip():
            raise EnvFileError(
                f"line {number}: {raw!r} has TRAILING WHITESPACE in its value. "
                "Measured on this host 2026-07-30: `docker compose config` "
                "resolves `TRAIL=bar ` to `bar` while `docker run --env-file` "
                "resolves it to `bar `, so this is exactly as ambiguous as a "
                "quoted value and for the same reason. It is also invisible in "
                "a diff, and it made `hooks/pre-push` allow a push to a branch "
                "forge (finding F3). Strip it."
            )
        if key in seen:
            raise EnvFileError(
                f"line {number}: {key} was already assigned on line "
                f"{seen[key]}. Compose takes the last assignment and other "
                "readers take the first, so the file would mean two different "
                "things depending on who read it."
            )
        seen[key] = number
        lines.append(EnvLine("assignment", raw, key, value))
    return EnvFile(lines)


def render_env(pairs: EnvFile | Mapping[str, str]) -> str:
    """Render to strict `KEY=value` text, ending in exactly one newline.

    An `EnvFile` renders its lines, so comments and blanks survive; a plain
    mapping renders one assignment per item in iteration order. Either way
    every assignment is emitted as `KEY=value` with no spaces -- there is no
    code path in this module that can emit `KEY = value`.
    """
    if isinstance(pairs, EnvFile):
        lines = list(pairs.lines)
    else:
        lines = [EnvLine("assignment", "", k, v) for k, v in pairs.items()]

    out: list[str] = []
    for line in lines:
        if line.kind == "assignment":
            key, value = line.key, line.value
            if not isinstance(key, str) or not _KEY.match(key):
                raise EnvFileError(
                    f"{key!r} is not a valid environment variable name."
                )
            if not isinstance(value, str):
                raise EnvFileError(
                    f"{key}: value must be a string, got "
                    f"{type(value).__name__} ({value!r})."
                )
            if "\n" in value or "\r" in value:
                raise EnvFileError(
                    f"{key}: value contains a newline. A dotenv file has no "
                    "line-continuation syntax, so the remainder would be read "
                    "as a separate -- and almost certainly invalid -- line."
                )
        out.append(line.render())
    return "".join(f"{piece}\n" for piece in out)


def production_env_path() -> Path:
    """Production's `.env`. The render source, and the only seam that names it.

    A function rather than a constant so a test can point the whole pipeline
    at a doctored copy in `tmp_path` -- production's own `.env` is never
    written to by anything in this package.
    """
    return identity.production_root() / ENV_FILE_NAME


def production_env_text() -> str:
    path = production_env_path()
    if not path.is_file():
        raise EnvFileError(f"Expected production's {ENV_FILE_NAME} at {path}.")
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# the manifest
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Requirement:
    """One entry of `branch-env.yaml`."""

    name: str
    fatal: bool
    derive: str | None = None
    literal: str | None = None
    suffix: str = ""
    secret: bool = False
    why: str = ""


def manifest_path() -> Path:
    return identity.package_root() / MANIFEST_NAME


def load_manifest(path: Path | None = None) -> list[Requirement]:
    """Load and validate `branch-env.yaml`.

    Validation is strict because this file is a safety artefact:

    * `fatal:` must be present on every entry. Defaulting it either way is
      wrong -- default `true` and an optional entry blocks a branch, default
      `false` and the whole point of the manifest evaporates the first time
      somebody adds an entry without thinking about it. So the loader refuses
      to guess.
    * exactly one of `derive:` or `literal:` must be given, because "how is
      this value obtained" has one answer.
    * `suffix:` only means anything to a derivation that consumes it.
    """
    path = path or manifest_path()
    if not path.is_file():
        raise ManifestError(f"No must-override manifest at {path}.")
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, Mapping) or "variables" not in document:
        raise ManifestError(f"{path} has no top-level `variables:` list.")
    entries = document["variables"]
    if not isinstance(entries, Sequence) or not entries:
        raise ManifestError(f"{path} declares an empty `variables:` list.")

    requirements: list[Requirement] = []
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        where = f"{path} entry {index}"
        if not isinstance(entry, Mapping):
            raise ManifestError(f"{where} is not a mapping: {entry!r}")
        name = entry.get("name")
        if not isinstance(name, str) or not _KEY.match(name):
            raise ManifestError(f"{where} has no valid `name:`: {name!r}")
        if name in seen:
            raise ManifestError(f"{path} lists {name} twice.")
        seen.add(name)
        if "fatal" not in entry:
            raise ManifestError(
                f"{path}: {name} does not declare `fatal:`. Whether omitting a "
                "variable breaks a branch or merely leaves it imperfect is the "
                "one question this manifest exists to answer, and it is not "
                "defaulted -- say `fatal: true` or `fatal: false` explicitly."
            )
        fatal = entry["fatal"]
        if not isinstance(fatal, bool):
            raise ManifestError(
                f"{path}: {name} declares `fatal: {fatal!r}`, which is not a "
                "boolean."
            )
        derive, literal = entry.get("derive"), entry.get("literal")
        if (derive is None) == (literal is None):
            raise ManifestError(
                f"{path}: {name} must declare exactly one of `derive:` or "
                f"`literal:`, got derive={derive!r} literal={literal!r}."
            )
        if derive is not None and derive not in DERIVATIONS:
            raise ManifestError(
                f"{path}: {name} asks for derivation {derive!r}, which is not "
                f"implemented. Known: {sorted(DERIVATIONS)}."
            )
        requirements.append(Requirement(
            name=name,
            fatal=fatal,
            derive=derive,
            literal=None if literal is None else str(literal),
            suffix=str(entry.get("suffix", "")),
            secret=bool(entry.get("secret", False)),
            why=str(entry.get("why", "")),
        ))
    return requirements


# ---------------------------------------------------------------------------
# derivations
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BranchContext:
    """Everything a derivation is allowed to read.

    Deliberately small. A derivation that needed the compose config, or the
    filesystem, would be doing something this manifest should not be
    describing.
    """

    name: str
    devs: tuple[str, ...] = ()
    authkey: str | None = None


def _derive_branch_project(ctx: BranchContext, req: Requirement) -> str:
    return identity.branch_project(ctx.name)


def _derive_branch_hostname(ctx: BranchContext, req: Requirement) -> str:
    return identity.branch_hostname(ctx.name)


def _derive_branch_domain(ctx: BranchContext, req: Requirement) -> str:
    return identity.branch_domain(ctx.name)


def _derive_branch_url(ctx: BranchContext, req: Requirement) -> str:
    return f"https://{identity.branch_domain(ctx.name)}{req.suffix}"


def _derive_agent_profiles(ctx: BranchContext, req: Requirement) -> str:
    """`agent-<user>` per requested developer -- never `agents` (spec D7).

    Returns `""` for `--devs none`, and `""` is a real value, not a missing
    one: a branch with no agents is a supported request, and an EMPTY
    COMPOSE_PROFILES is precisely how you express it. See `_resolve` for why
    that distinction is load-bearing.
    """
    return ",".join(f"{AGENT_PROFILE_PREFIX}{dev}" for dev in ctx.devs)


def developers_from_profiles(value: str) -> tuple[str, ...]:
    """The inverse of `_derive_agent_profiles`: which developers a branch runs.

    Here, beside its inverse, so the two spellings of `agent-<user>` cannot
    drift. Task 10 needs it: `aurora branch access` regenerates a branch's
    document from live state weeks after `up` ran, and the requested
    developers survive only in the branch `.env`'s `COMPOSE_PROFILES`.

    Anything that is not an agent profile is ignored rather than mangled --
    `COMPOSE_PROFILES` is a general Compose variable and a branch may
    legitimately carry other profiles in it.
    """
    out: list[str] = []
    for piece in (p.strip() for p in (value or "").split(",")):
        if piece.startswith(AGENT_PROFILE_PREFIX) and piece != AGENT_PROFILE_PREFIX:
            out.append(piece[len(AGENT_PROFILE_PREFIX):])
    return tuple(out)


def _derive_ephemeral_authkey(ctx: BranchContext, req: Requirement) -> str | None:
    """The supplied ephemeral key, or `None` if the caller had none.

    D-D: the key is supplied, never minted -- minting needs a Tailscale API
    key or OAuth client that does not exist on this host. `None` here is what
    turns into the hard error, because a sidecar with no key does not fail:
    it starts, stays `Logged out.`, and the branch "succeeds" with a dead URL.
    """
    return ctx.authkey


def _derive_minted_after_up(ctx: BranchContext, req: Requirement) -> str | None:
    """Always `None`: this variable cannot be derived at render time.

    `FORGEJO_ADMIN_TOKEN` (spec 2026-08-01, P3). Its branch value is minted by
    the branch's OWN Forgejo, which does not exist when this file is rendered
    -- and minting it needs the inherited token, so the render MUST leave
    production's value in place. `fatal: false` plus a `None` here is exactly
    that: `_resolve` omits the variable, production's value is inherited, and
    `aurora_cli.forgejo_token.rotate_admin_token` replaces it after the
    branch's Forgejo is serving.

    So this is a manifest entry that deliberately does NOT override anything
    at render time. It earns its place for the two other things a manifest
    entry does: `secret: true` puts the variable under `access_doc`'s
    redaction, by NAME and by VALUE, and `why:` is where a reader who has just
    learned that "anything absent here is INHERITED" finds out that this one
    is handled somewhere else rather than forgotten.
    """
    return None


def _derive_branch_app_name(ctx: BranchContext, req: Requirement) -> str:
    """Spec 5.4 layer 3: `<production's app name> [BRANCH: <name>]`.

    Delegated to `crosswire`, which derives the base from `compose.yml`'s
    declared default rather than typing it, so a branch's forge is always
    production's name plus a marker instead of a literal that can drift out of
    agreement with production.

    This derivation reads a tracked file, which `BranchContext` deliberately
    cannot carry. That is the same shape as every other derivation here: they
    all reach production through a module function (`identity.production_env`,
    `identity.production_domain`) rather than through the context. What the
    context must not carry is state a *manifest* has no business describing.
    """
    return crosswire.branch_app_name(ctx.name)


DERIVATIONS = {
    "branch_project": _derive_branch_project,
    "branch_hostname": _derive_branch_hostname,
    "branch_domain": _derive_branch_domain,
    "branch_url": _derive_branch_url,
    "agent_profiles": _derive_agent_profiles,
    "ephemeral_authkey": _derive_ephemeral_authkey,
    "branch_app_name": _derive_branch_app_name,
    "minted_after_up": _derive_minted_after_up,
}


def _resolve(
    requirements: Iterable[Requirement], ctx: BranchContext
) -> dict[str, str]:
    """Resolve every requirement to a value, or refuse.

    The fatal/optional distinction is applied here and nowhere else:

    * a value of `None` means the derivation had nothing to work with. For a
      `fatal: true` entry that is a hard error -- an exception, not a warning,
      because a warning on a branch-creation path is a line of output nobody
      reads. For a `fatal: false` entry the variable is simply omitted and
      production's value is inherited.
    * a value of `""` is a VALUE. `COMPOSE_PROFILES=` is how "no agents" is
      spelled, and treating it as missing would make `--devs none`
      unrepresentable.
    """
    resolved: dict[str, str] = {}
    for req in requirements:
        if req.literal is not None:
            value: str | None = req.literal
        else:
            value = DERIVATIONS[req.derive](ctx, req)
        if value is None:
            if req.fatal:
                raise BranchEnvError(
                    f"{req.name} has no value and `branch-env.yaml` marks it "
                    f"fatal: {req.why or 'no reason recorded'} "
                    f"(derivation {req.derive!r} for branch {ctx.name!r})."
                )
            continue
        if not isinstance(value, str):
            # `str(value)` used to be enough here, and it is how a secret got
            # into a rendered `.env` as its own redacted `repr`: `branch up`
            # passed `AuthKey` where it meant `AuthKey.value`, and the file
            # came out `TS_AUTHKEY=AuthKey(..., value=<redacted>)`. That is a
            # sidecar which starts, stays `Logged out.` and serves a dead URL
            # -- trap 9 by a new route, and invisible in a diff unless you
            # know what a key looks like. A coercion that turns a wrong TYPE
            # into a plausible STRING is not a convenience.
            raise BranchEnvError(
                f"{req.name}: the derivation {req.derive!r} returned "
                f"{type(value).__name__}, not a string. Nothing is coerced "
                "here: a `repr` written into a `.env` is a value that looks "
                "fine and means nothing."
            )
        resolved[req.name] = value
    return resolved


# ---------------------------------------------------------------------------
# rendering a branch .env
# ---------------------------------------------------------------------------


_OVERRIDE_HEADER = (
    "# --- branch overrides (generated from branch-env.yaml) "
    "-------------------"
)


def _with_overrides(
    source: EnvFile,
    overrides: Mapping[str, str],
    *,
    notes: Mapping[str, str] | None = None,
) -> EnvFile:
    """Production's file with values replaced in place, new keys appended.

    In place, so the branch `.env` diffs against production's as a handful of
    changed lines rather than as a rewritten file.
    """
    notes = notes or {}
    applied: set[str] = set()
    lines: list[EnvLine] = []
    for line in source.lines:
        if line.kind == "assignment" and line.key in overrides:
            lines.append(EnvLine(
                "assignment", line.raw, line.key, overrides[line.key]
            ))
            applied.add(line.key)
        else:
            lines.append(line)

    remaining = [key for key in overrides if key not in applied]
    if remaining:
        lines.append(EnvLine("blank", ""))
        lines.append(EnvLine("comment", _OVERRIDE_HEADER))
        for key in remaining:
            note = notes.get(key, "")
            if note:
                lines.append(EnvLine("comment", f"# {key}: {note}"))
            lines.append(EnvLine("assignment", "", key, overrides[key]))
    return EnvFile(lines)


def render_branch_env(
    name: str,
    *,
    devs: Sequence[str] = (),
    authkey: str | None = None,
    exclusions_env: Mapping[str, str] | None = None,
    source: str | None = None,
) -> str:
    """Render a branch's `.env` from production's.

    `exclusions_env` is Task 4's `on_exclude.env` rewiring and is applied
    LAST, after the manifest, because it is situational: "this branch has no
    AFFiNE, so point X somewhere else" is a statement about one branch, while
    the manifest is a statement about every branch. Applying it last also
    means `missing_overrides()` sees its effects -- an exclusion that
    reintroduced production's hostname would be caught by the same hazard
    rules as anything else.
    """
    requirements = load_manifest()
    ctx = BranchContext(
        name=name, devs=tuple(devs), authkey=authkey,
    )
    overrides = _resolve(requirements, ctx)
    notes = {req.name: req.why for req in requirements}
    if exclusions_env:
        overrides.update(exclusions_env)
    base = parse_env(source if source is not None else production_env_text())
    return render_env(_with_overrides(base, overrides, notes=notes))


# ---------------------------------------------------------------------------
# checking, in both directions
# ---------------------------------------------------------------------------


def hostname_bearing_variables(
    env: Mapping[str, str], domain: str | None = None
) -> list[str]:
    """Variables whose VALUE embeds `domain` as a literal.

    This is the query that found N1 -- `FORGEJO_URL`,
    `AFFINE_SERVER_EXTERNAL_URL`, `AURORA_PROFILE_URL` -- and it is the query
    that will find the next one, which is the entire reason it is a function
    rather than a list somebody maintains.
    """
    domain = domain or identity.production_domain()
    if not domain:
        raise EnvFileError(
            "Refusing to scan for an empty domain: every value would match."
        )
    return sorted(key for key, value in env.items() if domain in (value or ""))


def unlisted_hostname_variables(
    env: Mapping[str, str],
    requirements: Iterable[Requirement] | None = None,
    domain: str | None = None,
) -> list[str]:
    """The manifest's blind spots: hostname-bearing variables it does not list.

    The inverse direction. `hostname_bearing_variables` applied to a RENDERED
    branch file catches a bad render; this, applied to the RENDER SOURCE,
    catches a manifest that has fallen behind reality -- which is what happens
    when somebody adds a variable to `.env.template` and nobody remembers
    this file exists.
    """
    listed = {req.name for req in (
        load_manifest() if requirements is None else requirements
    )}
    return [
        key for key in hostname_bearing_variables(env, domain)
        if key not in listed
    ]


def manifest_gaps(
    rendered: Mapping[str, str],
    requirements: Iterable[Requirement] | None = None,
    source: Mapping[str, str] | None = None,
    *,
    allowed_production_references: Iterable[str] = (),
) -> list[str]:
    """Manifest entries the rendered file fails to satisfy.

    A `fatal` entry must be present AND, where production declares the same
    variable, must differ from production's value. The second half is what
    catches a "derivation" that quietly returns the inherited value -- a
    present-but-identical variable is exactly as dangerous as an absent one
    and looks completely fine in a diff.
    """
    requirements = list(
        load_manifest() if requirements is None else requirements
    )
    # Same narrow escape hatch as `inherited_hazards`, and it has to be here
    # too: a variable an exclusion deliberately points AT production is
    # byte-identical to production, which is exactly the shape this rule
    # exists to catch. Both halves of the checker must be told, or a branch
    # with `--without forgejo` is unrenderable. The set is derived per render
    # from the exclusion actually applied, never kept as a standing list.
    permitted = set(allowed_production_references)
    gaps: list[str] = []
    for req in requirements:
        if req.name not in rendered:
            gaps.append(
                f"{req.name}: absent from the rendered branch .env; "
                f"{'FATAL -- ' if req.fatal else ''}"
                f"{req.why or 'branch-env.yaml requires it'}"
            )
            continue
        if req.name in permitted:
            continue
        if not req.fatal or source is None or req.name not in source:
            continue
        if rendered[req.name] == source[req.name]:
            gaps.append(
                f"{req.name}: rendered value is byte-identical to "
                f"production's ({source[req.name]!r}), so it was inherited "
                f"rather than derived. {req.why}"
            )
    return gaps


def inherited_hazards(
    rendered: Mapping[str, str],
    name: str | None = None,
    domain: str | None = None,
    *,
    allowed_production_references: Iterable[str] = (),
) -> list[str]:
    """Invariants about a branch `.env` that owe NOTHING to the manifest.

    This is the half that survives somebody deleting a manifest entry. Each
    rule is a property of what a branch IS, derived from the stack's own
    structure rather than from a list:

    1. production's domain must not appear in any value. A branch that names
       production's hostname reaches production over HTTP, and the spec 5.3
       container-label guard cannot see that -- there is no container in the
       path to guard.
    2. `COMPOSE_PROJECT_NAME` must carry the branch namespace. It is the only
       thing standing between a branch's `down -v` and production's volumes.
    3. `COMPOSE_PROFILES` must not activate every developer (spec D7).
    4. no `*_UPSTREAM` may point at loopback: a branch's Caddy shares the
       sidecar's network namespace, where those addresses reach nothing, and
       the symptom is a 502 rather than a failure to start.
    """
    domain = domain or identity.production_domain()
    hazards: list[str] = []

    # The module-level set is EMPTY and stays empty: no variable a branch
    # renders has any business naming production by default. The parameter is
    # the narrow, per-render escape hatch Task 4 needs -- `--without forgejo`
    # deliberately points FORGEJO_URL at production's forge (spec 5.4), and it
    # is only defensible because forgejo, forgejo-mcp and dev-admin are all
    # absent from that branch. `exclusions.production_reference_exemptions()`
    # DERIVES the set from the exclusion actually applied, so it is empty
    # whenever nothing is excluded and cannot drift into a standing allowance.
    permitted = set(ALLOWED_PRODUCTION_REFERENCES) | set(
        allowed_production_references
    )

    for key in hostname_bearing_variables(rendered, domain):
        if key in permitted:
            continue
        hazards.append(
            f"{key}: value {rendered[key]!r} embeds production's domain "
            f"({domain}), so this branch would reach production over HTTP. "
            "The container-label guard cannot catch this."
        )

    project = rendered.get("COMPOSE_PROJECT_NAME")
    if project is None:
        hazards.append(
            "COMPOSE_PROJECT_NAME: absent, so Compose falls back to the "
            "directory basename and the branch may adopt another project's "
            "containers and volumes."
        )
    elif not project.startswith(identity.BRANCH_PROJECT_PREFIX):
        hazards.append(
            f"COMPOSE_PROJECT_NAME: {project!r} is outside the "
            f"{identity.BRANCH_PROJECT_PREFIX!r} namespace, so nothing stops "
            "this branch's `down -v` from reaching another stack's volumes."
        )
    elif name is not None and project != identity.branch_project(name):
        hazards.append(
            f"COMPOSE_PROJECT_NAME: {project!r} is not this branch's project "
            f"({identity.branch_project(name)!r})."
        )

    profiles = rendered.get("COMPOSE_PROFILES")
    if profiles is None:
        hazards.append(
            "COMPOSE_PROFILES: absent, so the branch inherits production's "
            "and starts every developer's agent."
        )
    elif ALL_DEVELOPERS_PROFILE in [
        p.strip() for p in profiles.split(",") if p.strip()
    ]:
        hazards.append(
            f"COMPOSE_PROFILES: {profiles!r} activates "
            f"{ALL_DEVELOPERS_PROFILE!r}, which starts EVERY developer's "
            "agent; spec D7 says a branch provisions only the developers it "
            "was asked for."
        )

    for key, value in sorted(rendered.items()):
        if not key.endswith("_UPSTREAM"):
            continue
        if any(marker in (value or "") for marker in _LOOPBACK_MARKERS):
            hazards.append(
                f"{key}: {value!r} is a loopback address. A branch's Caddy "
                "shares the tailscale sidecar's network namespace, where no "
                "loopback port of this stack exists; the route would 502 "
                "while the stack looked healthy."
            )
    return hazards


def missing_overrides(
    text: str,
    name: str | None = None,
    *,
    source: str | Mapping[str, str] | None = None,
    allowed_production_references: Iterable[str] = (),
) -> list[str]:
    """Everything wrong with a rendered branch `.env`, as `"KEY: reason"`.

    The union of the two independent detectors. Empty means the file is safe
    to hand to `docker compose`; anything else names the variable and says
    what would happen.
    """
    rendered = parse_env(text)
    if source is None:
        source_env: Mapping[str, str] = parse_env(production_env_text())
    elif isinstance(source, str):
        source_env = parse_env(source)
    else:
        source_env = source
    requirements = load_manifest()
    defects = manifest_gaps(
        rendered,
        requirements,
        source_env,
        allowed_production_references=allowed_production_references,
    )
    defects += inherited_hazards(
        rendered,
        name,
        allowed_production_references=allowed_production_references,
    )
    return sorted(set(defects))


def defect_variables(defects: Iterable[str]) -> list[str]:
    """The variable names out of `missing_overrides()`'s messages."""
    return sorted({defect.split(":", 1)[0] for defect in defects})
