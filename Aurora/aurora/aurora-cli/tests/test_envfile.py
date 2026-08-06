"""Pins `aurora_cli.envfile`'s parser, renderer and manifest loader.

The conformance half -- "does a rendered branch `.env` actually stop a branch
reaching production" -- lives in `tests/test_branch_env.py`, which can import
the repo's own strict-dotenv predicate. This file is about the mechanics:
strict `KEY=value`, byte-exact round-tripping of production's real file, and
a manifest loader that refuses to guess.

Nothing here types a project name or a tailnet suffix, for the same two
reasons `test_identity.py` does not: `tests/test_repo_conformance.py::
test_no_tracked_file_outside_docs_names_the_old_project` forbids one of them,
and a test that hardcodes the answer it checks is the defect it exists to
catch.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from aurora_cli import envfile, identity

FIXTURE_BRANCH = "zz-fixture-branch"
FIXTURE_KEY = "tskey-auth-zzfixture-notarealkey"


def _production_text() -> str:
    return envfile.production_env_text()


# ---------------------------------------------------------------------------
# strict KEY=value, against the real file
# ---------------------------------------------------------------------------


def test_round_trip_of_productions_real_env_is_byte_identical():
    """`render_env(parse_env(text)) == text`, on the 11 KB real thing.

    Against a toy fixture this would prove nothing. Production's `.env` is
    ~260 lines of which 185 are commented-out configuration for an unrelated
    product, much of it containing `=` inside comment text (`# NTFY_BASE_URL=`,
    `# ============`). A parser that mistakes any of that for an assignment,
    or a renderer that reformats it, shows up here and nowhere else.
    """
    text = _production_text()
    assert envfile.render_env(envfile.parse_env(text)) == text


#: A `.env` shaped like every case the parser can get wrong, so the properties
#: below cannot rot with production's own file. They used to be asserted
#: against the real thing -- ">100 comment lines", and five keys that appear
#: only inside comment text. All of those lines were a vendored template for
#: an unrelated product, deleted on 2026-07-30; the assertions went red for a
#: reason that had nothing to do with the parser. The property was right, tying
#: it to whatever production happened to contain was not. The real file is
#: still round-tripped byte-for-byte by the test above, and
#: `test_productions_real_env_still_contains_all_three_kinds` keeps that
#: subject from degenerating into pure assignments.
HOSTILE_ENV = """\
# ============================================================
# a banner rule whose text is nothing but = signs
# ============================================================

# NTFY_BASE_URL=http://localhost:8091
# LLM_HOSTS=llm-host.local,backup-llm.local
# DATABASE_URL=sqlite:///./data/app.db
# SEARXNG_SECRET=

REAL_KEY=real-value

# AUTH_ENABLED appears above only as comment text; this one is an assignment.
AUTH_ENABLED=false
"""


def test_round_trip_preserves_comments_blanks_and_assignments():
    """Non-vacuity for the test above: the file must contain all three kinds.

    Without this, a `.env` that happened to be nothing but assignments would
    round-trip perfectly while proving that comments survive -- which is the
    part that is easy to get wrong.
    """
    parsed = envfile.parse_env(HOSTILE_ENV)
    kinds = [line.kind for line in parsed.lines]

    assert envfile.render_env(parsed) == HOSTILE_ENV
    assert kinds.count("comment") > 0
    assert kinds.count("blank") > 0
    assert kinds.count("assignment") > 0
    assert len(parsed) == kinds.count("assignment"), (
        "the mapping lost assignments relative to the line list"
    )

    # Counted independently of the parser: an assignment is an uncommented,
    # non-blank line containing `=`. If the parser were fooled by `=` inside
    # comment text these two numbers would diverge.
    expected = sum(
        1 for raw in HOSTILE_ENV.splitlines()
        if raw.strip() and not raw.lstrip().startswith("#") and "=" in raw
    )
    assert kinds.count("assignment") == expected

    # ...and concretely: keys that appear ONLY inside comment text must not
    # have become variables. `AUTH_ENABLED` is deliberately not in this
    # list -- it appears both commented and, further down, for real, which is
    # exactly the case a naive "is this key mentioned anywhere" check gets
    # wrong.
    commented_only = ("NTFY_BASE_URL", "LLM_HOSTS", "DATABASE_URL",
                      "SEARXNG_SECRET")
    for key in commented_only:
        assert any(
            line.kind == "comment" and key in line.raw for line in parsed.lines
        ), f"premise wrong: {key} is no longer mentioned in a comment"
        assert key not in parsed, f"{key} was parsed out of comment text"
    assert parsed["AUTH_ENABLED"] == "false", (
        "the real assignment lost out to the commented mention of the same key"
    )


def test_productions_real_env_still_contains_all_three_kinds():
    """Keeps the byte-exact round-trip above from becoming a tautology.

    That test is only interesting while production's `.env` actually holds
    comments and blanks. If it ever degenerates into pure assignments the
    round-trip would still pass while proving nothing, so the degeneration is
    asserted against here rather than discovered later.
    """
    kinds = [line.kind for line in envfile.parse_env(_production_text()).lines]
    assert kinds.count("comment") > 0, "production's .env has no comments left"
    assert kinds.count("blank") > 0
    assert kinds.count("assignment") > 10


def test_the_mapping_and_the_lines_agree():
    parsed = envfile.parse_env(_production_text())
    for line in parsed.lines:
        if line.kind == "assignment":
            assert parsed[line.key] == line.value


def test_parse_agrees_with_identitys_private_reader_on_the_real_file():
    """One file, two parsers, pinned together.

    `identity._read_env_file` predates this module and is deliberately
    lenient -- it must READ a non-strict file so `production_domain()` does
    not raise on something the conformance gate already independently
    refuses. Merging them is not free, so instead they are held to the same
    answer on the real input. Two "identical" helpers drifting apart twice is
    already in this project's ledger.
    """
    path = envfile.production_env_path()
    assert dict(envfile.parse_env(path.read_text(encoding="utf-8"))) == \
        identity._read_env_file(path)


# ---------------------------------------------------------------------------
# what the parser refuses
# ---------------------------------------------------------------------------


def test_parse_rejects_whitespace_before_the_equals():
    with pytest.raises(envfile.EnvFileError) as excinfo:
        envfile.parse_env("DOMAIN_NAME = value\n")
    message = str(excinfo.value)
    assert "--env-file" in message, (
        "the refusal must name the tool that rejects the whole file, or the "
        "next reader 'fixes' it by making the parser lenient"
    )
    assert "DOMAIN_NAME " in message


def test_parse_rejects_whitespace_after_the_equals():
    with pytest.raises(envfile.EnvFileError) as excinfo:
        envfile.parse_env("DOMAIN_NAME= value\n")
    assert "after `=`" in str(excinfo.value)


def test_parse_rejects_an_indented_assignment():
    with pytest.raises(envfile.EnvFileError) as excinfo:
        envfile.parse_env("  DOMAIN_NAME=value\n")
    assert "indented" in str(excinfo.value)


def test_parse_rejects_a_line_that_is_not_an_assignment():
    with pytest.raises(envfile.EnvFileError) as excinfo:
        envfile.parse_env("FORGEJO_URL\n")
    assert "neither blank, a comment, nor a KEY=value" in str(excinfo.value)


def test_parse_rejects_an_invalid_key():
    for bad in ("1FOO=x\n", "FOO-BAR=x\n", "FOO.BAR=x\n"):
        with pytest.raises(envfile.EnvFileError) as excinfo:
            envfile.parse_env(bad)
        assert "valid environment variable name" in str(excinfo.value)


def test_parse_rejects_a_duplicate_key():
    """The file would mean two things depending on who read it."""
    with pytest.raises(envfile.EnvFileError) as excinfo:
        envfile.parse_env("A=1\nB=2\nA=3\n")
    message = str(excinfo.value)
    assert "line 3" in message and "line 1" in message


def test_parse_keeps_comments_and_blanks():
    parsed = envfile.parse_env("# c\n\nA=1\n")
    assert parsed["A"] == "1"
    assert [line.kind for line in parsed.lines] == \
        ["comment", "blank", "assignment"]


def test_parse_refuses_trailing_whitespace_in_a_value():
    """REVERSED by Task 8, on a measurement, and the reversal is deliberate.

    This test used to assert `parse_env("A=1 ")["A"] == "1 "` with the comment
    "trailing whitespace is inside the value". Measured on this host
    2026-07-30, that is false in this stack:

        .env line     docker compose config    docker run --env-file
        TRAIL=bar␠    'bar'                    'bar␠'

    Compose strips it and `--env-file` keeps it, so the line means two
    different things depending on which reader sees it -- the same ambiguity as
    a quoted value, and invisible in a diff. Finding F3 measured the
    consequence: a trailing space on production's `DOMAIN_NAME` made
    `hooks/pre-push` return verdict=allow on a push to a BRANCH forge.

    The message must name the trailing-whitespace rule and not the neighbouring
    ones: `parse_env` raises this one type from eight guards, so a bare
    `pytest.raises` would be satisfied by any of them (Task 1's
    sequential-guard finding).
    """
    with pytest.raises(envfile.EnvFileError) as excinfo:
        envfile.parse_env("A=1 \n")
    message = str(excinfo.value)
    assert "TRAILING WHITESPACE" in message, message
    assert "--env-file" in message, message
    assert "QUOTES" not in message, message
    assert "indented" not in message, message
    # A tab counts, and it is the shape nobody sees at all.
    with pytest.raises(envfile.EnvFileError):
        envfile.parse_env("A=1\t\n")
    # …and the control: the clean form still parses.
    assert envfile.parse_env("A=1\n")["A"] == "1"


# ---------------------------------------------------------------------------
# what the renderer refuses, and what it emits
# ---------------------------------------------------------------------------


def test_render_emits_no_whitespace_around_the_equals():
    assert envfile.render_env({"A": "1", "B": "two words"}) == "A=1\nB=two words\n"


def test_render_rejects_a_value_containing_a_newline():
    for value in ("a\nb", "a\rb"):
        with pytest.raises(envfile.EnvFileError) as excinfo:
            envfile.render_env({"A": value})
        assert "newline" in str(excinfo.value)


def test_render_rejects_a_non_string_value():
    with pytest.raises(envfile.EnvFileError):
        envfile.render_env({"A": 1})


def test_render_rejects_an_invalid_key():
    with pytest.raises(envfile.EnvFileError):
        envfile.render_env({"FOO BAR": "1"})


def test_the_parser_is_at_least_as_strict_as_the_repos_own_predicate():
    """Anything the repo's dotenv gate refuses, this parser must refuse too.

    `tests/test_repo_conformance.py::strict_dotenv_offenders` is the rule the
    whole repo is held to. This module is allowed to be stricter -- it also
    refuses duplicate keys and whitespace after `=` -- but never laxer, or a
    branch `.env` could pass here and be refused by the gate.
    """
    import sys

    sys.path.insert(0, str(identity.package_root() / "tests"))
    try:
        from test_repo_conformance import strict_dotenv_offenders
    finally:
        sys.path.pop(0)

    for bad in ("A = 1\n", "  A=1\n", "A\t=1\n"):
        assert strict_dotenv_offenders(bad), f"premise wrong for {bad!r}"
        with pytest.raises(envfile.EnvFileError):
            envfile.parse_env(bad)


# ---------------------------------------------------------------------------
# the manifest loader
# ---------------------------------------------------------------------------


def test_the_manifest_loads_and_every_entry_is_answerable():
    requirements = envfile.load_manifest()
    assert len(requirements) >= 10, "the manifest lost most of its entries"
    for req in requirements:
        assert (req.derive is None) != (req.literal is None)
        if req.derive is not None:
            assert req.derive in envfile.DERIVATIONS
        assert isinstance(req.fatal, bool)


def test_every_manifest_entry_records_why():
    """`why:` is what stops the next reader deleting an entry they don't
    understand, which is the failure mode this manifest is guarding against
    in the first place."""
    missing = [req.name for req in envfile.load_manifest() if not req.why.strip()]
    assert missing == [], f"manifest entries with no `why:`: {missing}"


_counter = iter(range(1000))


def _manifest(tmp_path: Path, body: str) -> Path:
    path = tmp_path / f"{next(_counter)}-{envfile.MANIFEST_NAME}"
    path.write_text(body, encoding="utf-8")
    return path


def test_the_loader_refuses_an_entry_that_omits_fatal(tmp_path):
    """Fatal-vs-optional is explicit per entry, or the file is refused.

    Defaulting it either way is wrong: default `true` and an advisory entry
    blocks every branch, default `false` and the manifest stops being a
    safety artefact the first time somebody adds an entry without thinking.
    """
    path = _manifest(tmp_path, "variables:\n  - name: FOO\n    literal: bar\n")
    with pytest.raises(envfile.ManifestError) as excinfo:
        envfile.load_manifest(path)
    message = str(excinfo.value)
    assert "FOO" in message and "fatal" in message
    assert "derive" not in message, (
        "this must be the missing-`fatal:` refusal, not the "
        "derive/literal check tripping over the same entry for its own "
        "reason -- if the `fatal:` requirement is deleted, this test has to "
        "notice"
    )


def test_the_loader_refuses_a_non_boolean_fatal(tmp_path):
    """`fatal: maybe` is not an answer either."""
    path = _manifest(
        tmp_path,
        "variables:\n  - name: FOO\n    literal: bar\n    fatal: maybe\n",
    )
    with pytest.raises(envfile.ManifestError) as excinfo:
        envfile.load_manifest(path)
    assert "boolean" in str(excinfo.value)


def test_the_loader_refuses_both_or_neither_of_derive_and_literal(tmp_path):
    both = _manifest(
        tmp_path,
        "variables:\n  - name: FOO\n    literal: bar\n"
        "    derive: branch_project\n    fatal: true\n",
    )
    neither = _manifest(
        tmp_path, "variables:\n  - name: FOO\n    fatal: true\n"
    )
    for path in (both, neither):
        with pytest.raises(envfile.ManifestError) as excinfo:
            envfile.load_manifest(path)
        assert "exactly one" in str(excinfo.value)


def test_the_loader_refuses_an_unknown_derivation(tmp_path):
    path = _manifest(
        tmp_path,
        "variables:\n  - name: FOO\n    derive: summon_a_value\n    fatal: true\n",
    )
    with pytest.raises(envfile.ManifestError) as excinfo:
        envfile.load_manifest(path)
    assert "summon_a_value" in str(excinfo.value)


def test_the_loader_refuses_a_duplicate_entry(tmp_path):
    path = _manifest(
        tmp_path,
        "variables:\n"
        "  - name: FOO\n    literal: a\n    fatal: true\n"
        "  - name: FOO\n    literal: b\n    fatal: true\n",
    )
    with pytest.raises(envfile.ManifestError) as excinfo:
        envfile.load_manifest(path)
    assert "twice" in str(excinfo.value)


def test_the_loader_refuses_an_empty_or_shapeless_manifest(tmp_path):
    empty = _manifest(tmp_path, "variables: []\n")
    shapeless = _manifest(tmp_path, "nothing: here\n")
    missing = tmp_path / "does-not-exist.yaml"
    for path in (empty, shapeless, missing):
        with pytest.raises(envfile.ManifestError):
            envfile.load_manifest(path)


# ---------------------------------------------------------------------------
# resolution: fatal vs optional
# ---------------------------------------------------------------------------


def test_a_fatal_requirement_with_no_value_is_a_hard_error():
    """Not a warning. A warning on a branch-creation path is a line of output
    nobody reads, and the consequence here is a Tailscale node that never
    logs in while the stack reports success."""
    fatal = envfile.Requirement(
        name="TS_AUTHKEY", fatal=True, derive="ephemeral_authkey",
        why="the sidecar stays logged out",
    )
    ctx = envfile.BranchContext(name=FIXTURE_BRANCH, authkey=None)

    with pytest.raises(envfile.BranchEnvError) as excinfo:
        envfile._resolve([fatal], ctx)
    message = str(excinfo.value)
    assert "TS_AUTHKEY" in message
    assert "logged out" in message, "the refusal must carry the entry's `why:`"


def test_an_optional_requirement_with_no_value_is_simply_omitted():
    optional = envfile.Requirement(
        name="TS_AUTHKEY", fatal=False, derive="ephemeral_authkey", why="x",
    )
    ctx = envfile.BranchContext(name=FIXTURE_BRANCH, authkey=None)

    assert envfile._resolve([optional], ctx) == {}


def test_an_empty_derived_value_is_a_value_and_not_a_missing_one():
    """`--devs none` renders `COMPOSE_PROFILES=`, which is how "no agents" is
    spelled. Treating "" as missing would make a fatal entry raise on a
    perfectly legitimate request."""
    req = envfile.Requirement(
        name="COMPOSE_PROFILES", fatal=True, derive="agent_profiles", why="x",
    )
    resolved = envfile._resolve([req], envfile.BranchContext(name=FIXTURE_BRANCH))

    assert resolved == {"COMPOSE_PROFILES": ""}


def test_agent_profiles_never_emit_the_all_developers_profile():
    ctx = envfile.BranchContext(name=FIXTURE_BRANCH, devs=("juan", "ada"))
    req = envfile.Requirement(
        name="COMPOSE_PROFILES", fatal=True, derive="agent_profiles",
    )

    value = envfile._resolve([req], ctx)["COMPOSE_PROFILES"]
    assert value == "agent-juan,agent-ada"
    assert envfile.ALL_DEVELOPERS_PROFILE not in value.split(",")


def test_branch_url_is_the_branch_domain_plus_the_declared_suffix():
    req = envfile.Requirement(
        name="FORGEJO_URL", fatal=True, derive="branch_url", suffix="/git",
    )
    value = envfile._resolve([req], envfile.BranchContext(name=FIXTURE_BRANCH))

    assert value["FORGEJO_URL"] == \
        f"https://{identity.branch_domain(FIXTURE_BRANCH)}/git"
    assert identity.production_domain() not in value["FORGEJO_URL"]


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------


def test_a_rendered_branch_env_parses_and_round_trips():
    text = envfile.render_branch_env(
        FIXTURE_BRANCH, devs=("testuser",), authkey=FIXTURE_KEY
    )
    assert envfile.render_env(envfile.parse_env(text)) == text


def test_rendering_without_an_authkey_refuses():
    with pytest.raises(envfile.BranchEnvError) as excinfo:
        envfile.render_branch_env(FIXTURE_BRANCH, devs=(), authkey=None)
    assert "TS_AUTHKEY" in str(excinfo.value)


def test_rendering_leaves_productions_env_untouched():
    """The renderer reads production's `.env`; nothing in this package writes
    to it. Cheap to assert, and production is live."""
    path = envfile.production_env_path()
    before = path.read_bytes()
    envfile.render_branch_env(FIXTURE_BRANCH, devs=(), authkey=FIXTURE_KEY)
    assert path.read_bytes() == before


def test_exclusions_env_is_applied_after_the_manifest():
    """Task 4's `on_exclude.env` is situational and wins over the manifest --
    "this branch has no AFFiNE" is a statement about one branch."""
    text = envfile.render_branch_env(
        FIXTURE_BRANCH, devs=(), authkey=FIXTURE_KEY,
        exclusions_env={"AFFINE_UPSTREAM": "unused:0"},
    )
    assert envfile.parse_env(text)["AFFINE_UPSTREAM"] == "unused:0"
