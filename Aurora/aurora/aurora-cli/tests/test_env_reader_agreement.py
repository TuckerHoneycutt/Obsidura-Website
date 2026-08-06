"""Finding F3: this repository's three `.env` readers must not disagree.

There are three of them and they are not going to be merged, because they want
different things: `identity._read_env_file` must READ a non-strict file so
`production_domain()` does not raise on input the conformance gate already
independently refuses; `envfile.parse_env` must REFUSE it, because it is what
renders the file a branch is built from; and `hooks/pre-push` is POSIX sh with
no Python available at all, running in a worktree that may predate every
module here.

What they must not do is answer the same question differently, and measured on
this host on 2026-07-30 they did -- on **6 of 9** value shapes:

    shape                identity     envfile                hook
    plain                'v'          'v'                    'v'          ok
    double-quoted        'v'          '"v"'                  '"v"'        NO
    single-quoted        'v'          "'v'"                  "'v'"        NO
    trailing-space       'v'          'v '                   'v '         NO
    space-after-eq       'v'          REFUSE                 ' v'         NO
    space-before-eq      'v'          REFUSE                 ''           NO
    crlf                 'v'          'v'                    'v'          ok
    empty                ''           ''                     ''           ok
    quoted-with-space    'v w'        '"v w"'                '"v w"'      NO

That is not a cosmetic divergence. The hook derives the tailnet suffix by
stripping the first label off `DOMAIN_NAME`, so a stray quote rode along into
the suffix, a branch host stopped matching it, and the push fell through to
the allow-everything rule. Measured end to end against a fabricated repo,
pushing at `https://aurora-demo.<tailnet>/git/x/y.git`:

    DOMAIN_NAME=superserver...      verdict=reject   <- correct
    DOMAIN_NAME="superserver..."    verdict=allow    <- FAILS OPEN
    DOMAIN_NAME='superserver...'    verdict=allow    <- FAILS OPEN
    DOMAIN_NAME=superserver...      verdict=allow    <- FAILS OPEN (trailing space)
    DOMAIN_NAME = superserver...    verdict=reject   <- right answer, wrong reason:
                                                       production's domain came out
                                                       EMPTY, so production was
                                                       allowed by fall-through
                                                       rather than recognised

The last row is Task 7's M7 finding again -- `exit 0` with two possible
sources -- so it is asserted on the VERDICT, never on the exit status.

Two of those rows are ambiguous in a way that is not a matter of taste, and
this was measured rather than argued. The same `.env` line, read by the two
consumers this stack actually uses:

    .env line        `docker compose config`   `docker run --env-file`
    PLAIN=ok         'ok'                      'ok'
    TRAIL=bar␠       'bar'                     'bar␠'
    QUOTED="baz"     'baz'                     '"baz"'

Compose strips both a trailing space and a matching pair of quotes;
`--env-file` keeps both. So each of those lines means two different things
inside one stack. **That measurement reverses Task 2's stated reason for
preserving trailing whitespace** ("it is inside the value as far as every
consumer is concerned"), and it is why `parse_env` now refuses it.

The closure is both halves of "normalise or refuse":

* the hook NORMALISES, using `identity._read_env_file`'s exact rule, because
  it runs standalone, in worktrees that may predate every module here, and
  must never fail open;
* `envfile.parse_env` REFUSES, joining the padded shapes it already refused,
  so an ambiguous value cannot reach a rendered branch `.env` at all;
* `branch.assert_env_is_unambiguous` is where `branch up` calls that refusal,
  before it creates anything.

This test file is the whole story in one place on purpose.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from aurora_cli import branch, crosswire, envfile, identity


# ---------------------------------------------------------------------------
# the corpus
# ---------------------------------------------------------------------------

#: Every value shape a human plausibly writes. A LITERAL list, and the
#: expectations below are literal too: deriving "which of these are
#: ambiguous?" from the parser would make the parser its own examiner, which
#: is the self-blinding shape this project has shipped three times.
SHAPES: tuple[tuple[str, str], ...] = (
    ("plain",             "K=v"),
    ("double-quoted",     'K="v"'),
    ("single-quoted",     "K='v'"),
    ("trailing-space",    "K=v "),
    ("space-after-eq",    "K= v"),
    ("space-before-eq",   "K =v"),
    ("crlf",              "K=v\r"),
    ("empty",             "K="),
    ("quoted-with-space", 'K="v w"'),
)

#: The shapes `envfile.parse_env` must refuse, named rather than computed.
#: Delete the quote refusal and the three quoted rows redden here; delete the
#: trailing-whitespace refusal and `trailing-space` does.
MUST_BE_REFUSED = frozenset({
    "double-quoted", "single-quoted", "quoted-with-space",
    "space-after-eq", "space-before-eq", "trailing-space",
})

#: …and the shapes it must accept. Both directions, so "refuse everything" is
#: not a passing implementation.
#:
#: `crlf` is here because Python's `splitlines()` consumes the `\r` before the
#: value is ever seen, so it is not a shape the parser can even observe --
#: measured, all three readers return `'v'`.
MUST_BE_ACCEPTED = frozenset({"plain", "crlf", "empty"})


def _hook_derivation(hook_text: str, env_file: Path, key: str) -> str:
    """`env_value <file> <key>` from the shipped hook, in a real shell.

    The hook's `env_value()` definition is lifted out of the shipped file by
    matching its own boundaries and executed by `sh`. Lifting rather than
    re-implementing is the point: a re-implementation would agree with itself
    forever while the shipped hook drifted.
    """
    marker = "env_value() {"
    start = hook_text.index(marker)
    depth = 0
    end = start
    for index in range(start, len(hook_text)):
        if hook_text[index] == "{":
            depth += 1
        elif hook_text[index] == "}":
            depth -= 1
            if depth == 0:
                end = index + 1
                break
    else:  # pragma: no cover - the shipped hook always closes its braces
        raise AssertionError("could not find the end of env_value() in the hook")
    definition = hook_text[start:end]
    assert "sed" in definition, definition
    script = f'{definition}\nenv_value "{env_file}" {key}\n'
    proc = subprocess.run(
        ["sh", "-c", script], capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.rstrip("\n")


@pytest.fixture(scope="module")
def hook_text() -> str:
    text = crosswire.hook_text()
    assert "env_value()" in text, "the shipped hook defines no env_value()"
    return text


def test_the_shape_corpus_is_non_degenerate():
    """Neither expectation set may be empty, and every shape must be classified.

    Without this the two loops below can both pass over nothing: a corpus
    whose every entry was refused would make the "they agree" assertion
    vacuous, and one whose every entry was accepted would make the refusal
    assertion vacuous.
    """
    labels = {label for label, _ in SHAPES}
    assert len(labels) == len(SHAPES), "duplicate label in the corpus"
    assert MUST_BE_REFUSED, "no shape is expected to be refused"
    assert MUST_BE_ACCEPTED, "no shape is expected to be accepted"
    assert not (MUST_BE_REFUSED & MUST_BE_ACCEPTED)
    assert MUST_BE_REFUSED | MUST_BE_ACCEPTED == labels, (
        "every shape must be classified; unclassified: "
        f"{sorted(labels - (MUST_BE_REFUSED | MUST_BE_ACCEPTED))}"
    )
    # The four hazardous classes finding F3 names must each be present.
    for required in ("double-quoted", "single-quoted", "trailing-space",
                     "space-before-eq"):
        assert required in labels


def test_the_parser_refuses_every_ambiguous_shape_and_accepts_the_rest():
    """`envfile.parse_env` is the refusing half of "normalise or refuse"."""
    refused: set[str] = set()
    accepted: set[str] = set()
    for label, line in SHAPES:
        try:
            envfile.parse_env(line + "\n")
        except envfile.EnvFileError:
            refused.add(label)
        else:
            accepted.add(label)
    assert refused == MUST_BE_REFUSED, (
        f"parse_env refused {sorted(refused)}, expected {sorted(MUST_BE_REFUSED)}"
    )
    assert accepted == MUST_BE_ACCEPTED


def test_the_quote_refusal_says_which_readers_disagree_and_how():
    """The message must name the two readers and the consequence.

    `parse_env` raises one exception type from seven guards, so a bare
    `pytest.raises` proves nothing about which one fired -- Task 1's
    sequential-guard finding. This asserts on the quote rule's own wording and
    on the ABSENCE of the neighbouring rules' wording.
    """
    with pytest.raises(envfile.EnvFileError) as raised:
        envfile.parse_env('K="v"\n')
    message = str(raised.value)
    assert "--env-file" in message, message
    assert "pre-push" in message, message
    assert "quote" in message.lower(), message
    # not the padded-value rules, which raise the same type
    assert "whitespace after" not in message, message
    assert "indented" not in message, message


def test_identity_and_the_hook_agree_on_every_shape(tmp_path, hook_text):
    """The stronger half: these two agree on ALL nine shapes, refusals included.

    `envfile` refuses the ambiguous ones, so agreement between the other two
    is what keeps the hook safe when it runs on its own -- which is how it
    always runs.
    """
    checked = 0
    for label, line in SHAPES:
        path = tmp_path / f"env-{label}"
        path.write_text(line + "\n", encoding="utf-8")
        theirs = identity._read_env_file(path).get("K", "")
        hooks = _hook_derivation(hook_text, path, "K")
        assert hooks == theirs, (
            f"{label}: the hook reads {hooks!r} where identity reads "
            f"{theirs!r}. A branch host that does not match the derived "
            "tailnet suffix is a push the hook waves through."
        )
        checked += 1
    assert checked == len(SHAPES), "vacuous: no shape was compared"


def test_every_shape_the_parser_accepts_means_the_same_to_all_three(
    tmp_path, hook_text
):
    """The agreement property `branch up` relies on, stated exactly."""
    compared = 0
    for label, line in SHAPES:
        path = tmp_path / f"ok-{label}"
        path.write_text(line + "\n", encoding="utf-8")
        try:
            parsed = envfile.parse_env(line + "\n").get("K", "")
        except envfile.EnvFileError:
            continue
        assert parsed == identity._read_env_file(path).get("K", ""), label
        assert parsed == _hook_derivation(hook_text, path, "K"), label
        compared += 1
    assert compared >= 3, (
        f"vacuous: only {compared} shapes were accepted by the parser, so this "
        "test compared almost nothing"
    )


# ---------------------------------------------------------------------------
# the hook, end to end, in a fabricated repository
# ---------------------------------------------------------------------------


def _fabricate(tmp_path: Path, hook: Path, domain_line: str) -> Path:
    """A repo with a main checkout and one linked worktree, armed.

    Copied from Task 7's discipline, including the detail that earned it: the
    main checkout's `.env` and the worktree's must be DIFFERENT files with
    DIFFERENT domains, or a hook reading its own worktree's `.env` instead of
    production's is indistinguishable from a correct one.
    """
    main = tmp_path / "main"
    main.mkdir(parents=True)

    def git(*args: str, cwd: Path = main) -> None:
        proc = subprocess.run(
            ["git", "-C", str(cwd), *args], capture_output=True, text=True,
        )
        assert proc.returncode == 0, f"git {args}: {proc.stderr}"

    subprocess.run(["git", "init", "-q", str(main)], check=True)
    (main / ".env.template").write_text(
        "COMPOSE_PROJECT_NAME=aurora\n", encoding="utf-8")
    (main / ".gitignore").write_text(".env\n", encoding="utf-8")
    hooks = main / crosswire.HOOKS_DIRNAME
    hooks.mkdir()
    (hooks / crosswire.HOOK_NAME).write_text(
        hook.read_text(encoding="utf-8"), encoding="utf-8")
    (hooks / crosswire.HOOK_NAME).chmod(0o755)
    git("add", "-A")
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init")
    git("config", "core.hooksPath", crosswire.HOOKS_DIRNAME)
    # AFTER the commit, and gitignored, so the worktree does not inherit it.
    (main / ".env").write_text(domain_line + "\n", encoding="utf-8")
    worktree = tmp_path / "wt"
    git("worktree", "add", "-q", str(worktree), "-b", "demo")
    (worktree / ".env").write_text(
        "DOMAIN_NAME=aurora-demo.tailnet.example\n", encoding="utf-8")
    assert (main / ".env").read_text() != (worktree / ".env").read_text(), (
        "the fixture cannot tell production's .env from the branch's, so the "
        "derivation direction is untested"
    )
    return worktree


def _verdict(worktree: Path, url: str) -> str:
    proc = subprocess.run(
        ["git", "hook", "run", "--to-stdin=/dev/null", "pre-push", "--",
         "origin", url],
        cwd=str(worktree), capture_output=True, text=True,
        env={**os.environ, "AURORA_PRE_PUSH_EXPLAIN": "1"},
        timeout=60,
    )
    for line in (proc.stdout + proc.stderr).splitlines():
        if line.startswith("verdict="):
            return line.split("=", 1)[1].strip()
    raise AssertionError(
        f"the hook printed no verdict.\nstdout: {proc.stdout}\n"
        f"stderr: {proc.stderr}"
    )


#: The exact shapes that made the hook fail open, and the padded shape that
#: made it lose production's identity. A literal list: a corpus derived from
#: the parser's refusals would shrink silently if the parser were weakened.
HAZARDOUS_DOMAIN_LINES = (
    ("double-quoted",  'DOMAIN_NAME="prod.tailnet.example"'),
    ("single-quoted",  "DOMAIN_NAME='prod.tailnet.example'"),
    ("trailing-space", "DOMAIN_NAME=prod.tailnet.example "),
    ("space-before-eq", "DOMAIN_NAME = prod.tailnet.example"),
    ("space-after-eq", "DOMAIN_NAME= prod.tailnet.example"),
)

BRANCH_URL = "https://aurora-demo.tailnet.example/git/x/y.git"
PRODUCTION_URL = "https://prod.tailnet.example/git/x/y.git"


def test_the_hook_rejects_a_branch_forge_whatever_shape_the_domain_is_written_in(
    tmp_path,
):
    """The fail-open, closed. This is the F3 assertion.

    Asserted on the VERDICT and not the exit status, because `verdict=allow`
    and `verdict=allow-production` are both `exit 0` and only one of them
    means the hook still knows what production is (Task 7's M7).
    """
    hook = crosswire.hook_source_path()
    control = _fabricate(tmp_path / "control", hook,
                         "DOMAIN_NAME=prod.tailnet.example")
    assert _verdict(control, BRANCH_URL) == "reject", (
        "the unquoted control does not reject a branch forge, so this test "
        "cannot show that the other shapes do"
    )
    assert _verdict(control, PRODUCTION_URL) == "allow-production"

    for label, line in HAZARDOUS_DOMAIN_LINES:
        worktree = _fabricate(tmp_path / f"case-{label}", hook, line)
        assert _verdict(worktree, BRANCH_URL) == "reject", (
            f"{label}: the hook ALLOWED a push to a branch forge. A "
            "cross-wiring defence that fails open is worse than none, because "
            "the developer believes it is there."
        )
        assert _verdict(worktree, PRODUCTION_URL) == "allow-production", (
            f"{label}: production was not RECOGNISED. `allow` by fall-through "
            "and `allow-production` are both exit 0, and only the second "
            "means the hook still knows which host is production."
        )


def test_branch_up_refuses_an_ambiguous_production_env_before_creating_anything(
    tmp_path,
):
    """`branch up`'s own gate, and the message must explain the consequence."""
    text = 'DOMAIN_NAME="prod.tailnet.example"\n'
    with pytest.raises(branch.BranchError) as raised:
        branch.assert_env_is_unambiguous(text, where="a fabricated .env")
    message = str(raised.value)
    assert "a fabricated .env" in message, message
    assert "pre-push" in message, message
    assert "fails OPEN" in message or "fail OPEN" in message, message
    # and the control: production's real .env passes
    branch.assert_env_is_unambiguous(
        envfile.production_env_text(), where="production",
    )


def test_productions_env_has_no_ambiguous_value_today_so_this_gate_is_new(
):
    """The measurement that made the old agreement test vacuous.

    Production's `.env` has 30 assignments, 0 quoted and 0 whitespace-padded,
    which is exactly why nothing caught the divergence for eight tasks. Stated
    as a test so that the day production grows one, this says so here rather
    than in a branch's pre-push hook.
    """
    env = envfile.parse_env(envfile.production_env_text())
    assert len(env) >= 20, f"only {len(env)} assignments; wrong file?"
