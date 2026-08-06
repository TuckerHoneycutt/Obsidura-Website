"""Does the CLI actually hand its flags to the functions behind it?

Nothing in this suite exercised `aurora_cli.__main__` before 2026-08-01, and
the gap had a measurable cost. `aurora branch up --limits` was declared on the
parser, documented in `--help`, and then dropped on the floor: `_cmd_branch_up`
never passed it to `branch.branch_up`, so every branch a human created silently
got the default profile no matter what they asked for. Two adversarial review
passes read that function without seeing it, because reading a call and
noticing an ARGUMENT THAT IS NOT THERE are different acts. A measurement found
it, by setting a profile and watching the wrong numbers arrive at the daemon.

These tests are behavioural on purpose. A source assertion --
`"limits=args.limits" in inspect.getsource(_cmd_branch_up)` -- would have
caught that one bug and nothing else, and this repository already has five
tests that read a function's source and missed the defect inside it. Capturing
the call catches the whole class, including the next flag somebody adds.
"""

from __future__ import annotations

import argparse

import pytest

from aurora_cli import __main__ as cli
from aurora_cli import overlay


# ---------------------------------------------------------------------------
# reaching the subparsers
# ---------------------------------------------------------------------------
#
# `_SubParsersAction` is private, and it is still the supported way to walk a
# built parser: argparse exposes no public accessor for a subcommand's own
# parser. The alternative is duplicating the flag list here, which is the one
# thing these tests exist to avoid -- a second copy goes stale in the same
# commit that adds the flag.
def _subparsers(parser: argparse.ArgumentParser) -> dict:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action.choices
    raise AssertionError(f"{parser.prog!r} declares no subcommands")


def _up_parser() -> argparse.ArgumentParser:
    return _subparsers(_subparsers(cli.build_parser())["branch"])["up"]


#: Every `dest` the `branch up` parser declares, mapped to the keyword
#: `branch.branch_up` receives it as -- or to None where the flag legitimately
#: shapes OUTPUT rather than the branch. Adding a flag without adding a line
#: here fails `test_every_flag_branch_up_declares_is_accounted_for`, which is
#: the point: the failure lands on the person adding the flag, at the moment
#: they add it, instead of on a developer months later wondering why their
#: profile did nothing.
UP_DEST_TO_KWARG: dict[str, str | None] = {
    "name": "name",
    "from_ref": "from_ref",
    "limits": "limits",
    "devs": "devs",
    "without": "without",
    "no_seed": "no_seed",
    "seed": "seed_strategy",
    "no_build": "build",
    "force": "force",
    "runtime": "runtime",
    "json": None,          # selects the output format, not a branch_up input
}


@pytest.fixture
def captured_up(monkeypatch, tmp_path):
    """Run `main(argv)` and return the kwargs `branch_up` was called with.

    `refresh_branch_docs` is stubbed to a real file because `_cmd_branch_up`
    reads the document back and prints it verbatim -- spec 7.4 makes that
    string the product, so the handler is not going to stop reading it.
    """
    document = tmp_path / "BRANCH-ACCESS.md"
    document.write_text("stub access document\n", encoding="utf-8")
    seen: dict = {}

    def fake_branch_up(name, **kwargs):
        seen["name"] = name
        seen.update(kwargs)
        return object()

    monkeypatch.setattr(cli.branch, "branch_up", fake_branch_up)
    monkeypatch.setattr(
        cli.branch, "refresh_branch_docs",
        lambda result: (document, tmp_path / "INDEX.md"),
    )

    def run(argv: list[str]) -> dict:
        assert cli.main(argv) == 0
        return seen

    return run


# ---------------------------------------------------------------------------
# the bug, and the class it belongs to
# ---------------------------------------------------------------------------


def test_branch_up_forwards_the_limits_profile(captured_up):
    """The regression, stated at its smallest.

    `--limits tight` reaching `branch_up` is the whole difference between a
    ceiling a developer chose and a ceiling they were silently given.
    """
    seen = captured_up(["branch", "up", "demo", "--devs", "none",
                        "--limits", "tight"])
    assert seen.get("limits") == "tight", (
        "`branch up --limits tight` did not reach `branch.branch_up`. The flag "
        "is parsed and documented in --help, so a developer has every reason "
        "to believe it worked; what they get is the default profile."
    )


def test_branch_up_forwards_every_flag_it_declares(captured_up):
    """One argv exercising every optional flag, checked value by value.

    Written as one call rather than a test per flag because the failure this
    guards against is a MISSING line in a single call site: a flag dropped
    there is dropped for everyone, and the per-flag split would only make the
    same defect report ten times.
    """
    seen = captured_up([
        "branch", "up", "demo",
        "--from", "HEAD",
        "--limits", "tight",
        "--devs", "none",
        "--without", "affine",
        "--no-seed",
        "--seed", "filecopy",
        "--no-build",
        "--force",
        "--runtime", "podman",
    ])
    assert seen["name"] == "demo"
    assert seen["from_ref"] == "HEAD"
    assert seen["limits"] == "tight"
    assert seen["devs"] == "none"
    assert tuple(seen["without"]) == ("affine",)
    assert seen["no_seed"] is True
    assert seen["seed_strategy"] == "filecopy"
    assert seen["force"] is True
    assert seen["runtime"] == "podman"
    # Inverted at the boundary: the flag is `--no-build`, the parameter is
    # `build`. Asserted explicitly because an inversion that is dropped looks
    # exactly like an inversion that is wrong.
    assert seen["build"] is False


def test_every_flag_branch_up_declares_is_accounted_for():
    """A new flag cannot be added without deciding where it goes.

    This is the test that generalises: the one above proves today's flags are
    wired, this one fails the moment tomorrow's is not.
    """
    declared = {
        action.dest for action in _up_parser()._actions
        if action.dest not in ("help", "func")
    }
    unaccounted = declared - set(UP_DEST_TO_KWARG)
    assert not unaccounted, (
        f"`branch up` declares {sorted(unaccounted)}, which UP_DEST_TO_KWARG "
        "in this file does not mention. Add each one with the `branch_up` "
        "keyword it becomes -- or None if it shapes output rather than the "
        "branch -- and extend "
        "test_branch_up_forwards_every_flag_it_declares to cover it. A flag "
        "that is parsed and never forwarded is worse than one that does not "
        "exist: --help promises it works."
    )


# ---------------------------------------------------------------------------
# the second half of the documented selection mechanism
# ---------------------------------------------------------------------------
#
# The spec offers two ways to choose a profile: `--limits <name>` and
# `$AURORA_BRANCH_LIMITS`. `overlay.LIMITS_ENV_VAR` held the variable's name
# and nothing read it, so the documented half was a constant.


def test_the_limits_env_var_selects_a_profile():
    default, _ = overlay.resolve_limits(
        None, environ={overlay.LIMITS_ENV_VAR: "tight"})
    tight, _ = overlay.resolve_limits("tight")
    assert default == tight and default, (
        f"${overlay.LIMITS_ENV_VAR} did not select the `tight` profile. The "
        "spec documents it as one of the two ways to choose ceilings."
    )


def test_an_explicit_profile_beats_the_env_var():
    """Precedence, in the direction that cannot surprise anyone.

    An exported variable outliving the session that set it is ordinary; a
    typed flag losing to one is not.
    """
    chosen, _ = overlay.resolve_limits(
        "measured", environ={overlay.LIMITS_ENV_VAR: "tight"})
    measured, _ = overlay.resolve_limits("measured")
    assert chosen == measured


def test_the_env_var_can_ask_for_no_ceilings_at_all():
    """`AURORA_BRANCH_LIMITS=none` has to mean what `--limits none` means.

    It is the case an early-return would have skipped: the fallback has to be
    resolved BEFORE the `none` comparison, not after it.
    """
    assert overlay.resolve_limits(
        None, environ={overlay.LIMITS_ENV_VAR: overlay.LIMITS_NONE},
    ) == ({}, {})


def test_an_empty_env_var_is_not_a_profile_name():
    """An exported-but-empty variable must fall through to the default.

    `AURORA_BRANCH_LIMITS=` is what an unset-looking shell leaves behind, and
    resolving it as a profile name raises 'is not a profile in
    branch-limits.yaml' on a machine where nothing appears to be set.
    """
    fallback, _ = overlay.resolve_limits(None, environ={overlay.LIMITS_ENV_VAR: ""})
    default, _ = overlay.resolve_limits(None, environ={})
    assert fallback == default and default
