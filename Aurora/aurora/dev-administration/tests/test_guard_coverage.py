"""Spec 10.2: the project-label guard requires exhaustive coverage --
"every mutating entry point, not a representative sample".

This test is deliberately structural. A behavioural test per function would
keep passing while a NEW unguarded function was added tomorrow; this fails
the moment the enumeration and the source disagree.

It walks the AST for real call nodes rather than substring-matching the
source. Three separate times in this project a test has reported success by
matching text that never executed -- including one satisfied entirely by a
docstring that happened to contain the literal being searched for. A
docstring reading "this deliberately does not call assert_same_project"
must not satisfy a guard-coverage check. Docstrings, comments and string
literals are invisible to an AST call-walk by construction.
"""

import ast
import inspect
import textwrap

from unittest.mock import patch

from dev_administration import (
    caddy_utils, cli, docker_utils, forgejo_access, project, provision, verify,
)

# Any one of these, actually CALLED, establishes that the function proved its
# target was in scope before mutating. assert_same_project guards a named
# container; network_name and current_project guard the two functions whose
# target is a network or a volume name rather than a container. The forgejo
# helpers are the same idea against the other daemon this package mutates:
# _assert_managed / _managed_user / assert_self_grantable all refuse a Forgejo
# account that is not in developers.yaml, so a one-argument command cannot
# reach an arbitrary account on the host.
GUARD_CALLS = frozenset({
    "assert_same_project", "network_name", "current_project",
    "_assert_managed", "_managed_user", "assert_self_grantable",
})

# Every function that changes container, volume, network or Forgejo state.
# Adding a mutating function without adding it here is itself the bug.
MUTATING = {
    docker_utils: [
        "create_volume",
        "run_temp_container",
        "stop_and_remove_container",
        "docker_exec",
    ],
    caddy_utils: [
        "reload_caddy",
        "write_via_caddy",
        "write_denied_page",
        "write_agent_chooser",
    ],
    forgejo_access: [
        "mint_token",
        "revoke_token",
        "set_active",
        "authorize_repo",
        "deauthorize_repo",
    ],
}


def _called_names(func) -> set[str]:
    """Return the set of names actually invoked in func's body."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(func)))
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        target = node.func
        if isinstance(target, ast.Name):
            names.add(target.id)
        elif isinstance(target, ast.Attribute):
            names.add(target.attr)
    return names


def test_every_mutating_function_consults_the_guard():
    """Deliberately named "consults", not "enforces".

    An AST call-walk cannot see call ORDER, whether the call is
    unconditional, or whether the value handed to the guard is the value
    that later gets mutated. Deleting a raise while leaving the guard call
    in place still reads as guarded here. This catches an entry point that
    never consults its project at all -- the Chunk 1 defect -- and nothing
    finer. Per-function behavioural tests carry the rest.
    """
    unguarded = []
    for module, names in MUTATING.items():
        for name in names:
            called = _called_names(getattr(module, name))
            if not (called & GUARD_CALLS):
                unguarded.append(f"{module.__name__}.{name}")
    assert unguarded == [], (
        "Mutating functions with no scope guard -- per spec D12 the docker "
        "socket is not enforced by Docker, and the Forgejo admin token is "
        f"scope `all`, so this IS the boundary: {unguarded}"
    )


def test_the_guard_detector_is_not_fooled_by_prose():
    """Pins the AST walk itself.

    If _called_names ever regressed to substring matching, this function --
    whose docstring and comments name every guard token without calling any
    of them -- would be reported as guarded. It calls only len().

    Tokens appearing as prose only: assert_same_project, network_name,
    current_project.
    """

    def decoy():
        """This function does not call assert_same_project."""
        # current_project and network_name are named here as comments only.
        marker = "assert_same_project current_project network_name"
        return len(marker)

    assert not (_called_names(decoy) & GUARD_CALLS)


def _strip_docstrings(source: str) -> str:
    """Source text with every docstring blanked, comments kept.

    Takes TEXT, not a module, so the pin test below can exercise this exact
    function against hand-written fixtures instead of re-implementing it --
    a decoy that reimplements the thing it pins proves nothing about the
    thing it pins.

    Comments stay in scope on purpose -- a comment naming the old production
    network is a latent copy-paste source. Docstrings are removed because
    prose explaining WHICH literal a replacement supersedes is the one form
    of mention that is informative rather than dangerous.

    Blanking beats exempting a whole module: an earlier version of this test
    skipped project.py entirely on that reasoning, and adding EXECUTABLE
    module-level constants there --
        _FALLBACK_CADDY = "tai-review-caddy-1"
    -- kept every guard-coverage test green. project.py is the single most
    plausible home for such a fallback, since it owns find_service_container
    and network_name.
    """
    tree = ast.parse(source)
    spans = []
    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) \
                and isinstance(first.value.value, str):
            spans.append((
                first.lineno, first.col_offset,
                first.end_lineno, first.end_col_offset,
            ))

    # Blanked by COLUMN, not by whole line. Blanking whole lines erased any
    # statement sharing a line with a docstring, and all three of these are
    # valid Python that hid the literal from the scan entirely:
    #     def f(): "doc"; CADDY = "tai-review-caddy-1"
    #     class C:
    #         """Doc."""; NET = "tai-review_default"
    # -- i.e. the over-blanking reproduced the module-exemption hole this
    # function was written to close.
    lines = source.splitlines()
    for start_line, start_col, end_line, end_col in spans:
        for i in range(start_line - 1, end_line):
            line = lines[i]
            lo = start_col if i == start_line - 1 else 0
            hi = end_col if i == end_line - 1 else len(line)
            lines[i] = line[:lo] + " " * (hi - lo) + line[hi:]
    return "\n".join(lines)


def test_no_hardcoded_project_identity_remains():
    """The literals M5 exists to delete.

    provision and cli are scanned as of Task 5, which is what removed their
    three surviving literals -- until then this test covered only the two
    modules Task 4 touched, so `provision.py`'s `network="tai-review_default"`
    sat here unnoticed while the suite reported the guard fully wired.

    verify is scanned for completeness, but see the ledger: it still defaults
    DOMAIN to production's hostname and resolves agents by global container
    name. Those are Task 7's, and this test does NOT cover them -- its
    presence here should not be read as saying otherwise.
    """
    offenders = []
    for module in (caddy_utils, docker_utils, provision, cli, verify, project):
        source = _strip_docstrings(inspect.getsource(module))
        # The new names are banned too: a regression test that only
        # forbids a name nobody would type any more is a museum piece.
        for literal in (
            "tai-review_default", "tai-review-caddy-1",
            "aurora_default", "aurora-caddy-1",
        ):
            if literal in source:
                offenders.append(f"{module.__name__}: {literal}")
    assert offenders == [], f"Hardcoded production identity still present: {offenders}"


def test_the_literal_scan_sees_through_a_module_that_only_documents_the_literal():
    """Pins _strip_docstrings from both sides.

    A docstring mentioning the literal must NOT trip the scan; executable
    code carrying it must. Without the second half, blanking docstrings could
    silently over-blank and reproduce the module-exemption hole it replaced.
    """
    module_doc = '"""Replaces the old tai-review-caddy-1 default."""\nX = 1\n'
    func_doc = (
        "def f():\n"
        '    """Supersedes tai-review_default."""\n'
        "    return 1\n"
    )
    executable = 'CADDY = "tai-review-caddy-1"\n'
    commented = "# fall back to tai-review_default\nX = 1\n"

    assert "tai-review-caddy-1" not in _strip_docstrings(module_doc)
    assert "tai-review_default" not in _strip_docstrings(func_doc)
    assert "tai-review-caddy-1" in _strip_docstrings(executable), (
        "executable code carrying the literal must survive stripping"
    )
    assert "tai-review_default" in _strip_docstrings(commented), (
        "comments are a latent copy-paste source and must still be scanned"
    )

    # Same-line constructions. Blanking by whole line erased these, which hid
    # the literal from the scan -- reproducing the module-exemption hole this
    # function replaced. All three are valid Python.
    same_line_def = 'def f(): "doc"; CADDY = "tai-review-caddy-1"\n'
    same_line_class = (
        "class C:\n"
        '    """Doc."""; NET = "tai-review_default"\n'
    )
    same_line_module = '"""Doc."""; CADDY = "tai-review-caddy-1"\n'
    for src, literal in (
        (same_line_def, "tai-review-caddy-1"),
        (same_line_class, "tai-review_default"),
        (same_line_module, "tai-review-caddy-1"),
    ):
        assert literal in _strip_docstrings(src), (
            "a statement sharing a line with a docstring must not be blanked "
            f"along with it: {src!r}"
        )


def test_provision_imports_its_side_effecting_helpers_at_module_level():
    """A function-local import of a side-effecting function is unpatchable.

    `reconcile` used to do `from ... import write_via_caddy` INSIDE the
    function body. `@patch("dev_administration.provision.write_via_caddy")`
    then binds a name nothing ever reads, the patch silently does nothing,
    and the real function runs. That is not hypothetical: running this suite
    once wrote an empty agents.conf into PRODUCTION's Caddy container and
    returned 502 for every /agent/<user>/ route until it was repaired by
    hand.

    Scoped to the writers -- the functions that mutate a live container.
    Local imports elsewhere (urllib, delete_oauth2_app) are cycle-breaking
    and harmless.
    """
    tree = ast.parse(inspect.getsource(provision))
    writers = {
        "write_via_caddy", "write_agent_chooser", "write_denied_page",
        "write_owners_map", "reload_caddy",
    }
    module_level = {node for node in tree.body if isinstance(node, ast.ImportFrom)}

    local_imports = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or node in module_level:
            continue
        for alias in node.names:
            if alias.name in writers:
                local_imports.append(alias.name)

    assert local_imports == [], (
        "Imported inside a function, so @patch cannot reach them and a unit "
        f"test will mutate whatever container is live: {local_imports}"
    )


def test_run_container_detached_is_gone():
    """Per M4 agents are Compose services now. A surviving imperative
    `docker run` path would recreate the exact defect M4 removes: a
    container Compose cannot see, stop, or tear down."""
    assert not hasattr(docker_utils, "run_container_detached")


def test_load_config_does_not_read_the_project_from_the_environment(monkeypatch):
    """The single line standing between a branch and production.

    ProvisionConfig resolves `project` via project.current_project(), which
    is LABEL-first and falls back to COMPOSE_PROJECT_NAME only on the host.
    An earlier draft of _load_config read the env var directly and used
    current_project() only as a fallback -- exactly backwards. Spec §4.1
    renders a branch's .env FROM production's, and compose.yml injects
    COMPOSE_PROJECT_NAME into dev-admin, so under the env-first form a branch
    whose override silently failed would read `tai-review`, and reconcile
    would rewrite PRODUCTION's Caddy config and OAuth2 apps while believing
    it was operating on itself.

    Nothing else in the suite covers this: restoring the env-first version
    leaves every other test green (verified by mutation).
    """
    for key, value in {
        "FORGEJO_URL": "https://example.invalid/git",
        "FORGEJO_ADMIN_TOKEN": "t",
        "AURORA_PROFILE_URL": "https://example.invalid/git/a/b.git",
        "DOMAIN_NAME": "example.invalid",
    }.items():
        monkeypatch.setenv(key, value)
    # The stale/inherited value a branch would carry.
    monkeypatch.setenv("COMPOSE_PROJECT_NAME", "tai-review")

    with patch("dev_administration.provision.current_project", return_value="br-demo"):
        config = cli._load_config()

    assert config.project == "br-demo", (
        "ProvisionConfig took the project from COMPOSE_PROJECT_NAME instead "
        "of the container's own compose label -- a branch would act on "
        f"{config.project!r}"
    )


def test_provision_config_fills_the_project_when_left_empty():
    """Pins __post_init__ rather than the call site.

    Deleting the `if not self.project` fill left the whole suite green: every
    other consumer passes `project` explicitly or re-derives it, so the field
    documented as this object's single source of scope was never asserted on.
    Without it, container.missing renders "in project ''".
    """
    with patch("dev_administration.provision.current_project", return_value="br-demo"):
        config = provision.ProvisionConfig(
            forgejo_url="u", forgejo_token="t", aurora_profile_url="a",
            domain="d", caddy_container="", authorized_keys_path="/tmp/k",
        )
    assert config.project == "br-demo"
