"""Spec 5.4's three cross-wiring defences, tested through the paths git and
Compose actually take.

What this file is written around
-------------------------------
**A hook that is not installed, not armed, or not executable does NOTHING, and
says nothing about it.** That is the vacuous-pass trap with a filesystem bit
instead of an empty set, and it is worse than the set version because
`git hook run` exits **1** for a missing hook -- the same code as a refusal. So
"exit != 0" proves nothing here. Every rejection assertion checks for the
hook's own marker in its output, and
`test_a_refusal_and_a_missing_hook_are_distinguishable` pins that the two are
telling apart. `test_a_hook_that_is_not_executable_lets_the_push_through`
measures the silent-do-nothing case directly, because that is the shape a
future "simplification" would produce.

**A pre-push hook is a thing that can push.** Git contacts the remote to
discover its refs BEFORE it runs pre-push -- the hook is fed the remote's sha1s
on stdin, which cannot be known otherwise -- so a test that pushed at an
`https://` URL would reach the network whatever the hook then decided. Every
push in this file goes to a **local bare repository**, and every git invocation
carries `GIT_ALLOW_PROTOCOL=file`, which makes git itself refuse any other
transport. `test_the_harness_cannot_reach_the_network` proves that tripwire is
real rather than assumed; the reject-a-real-push case works because the bare
repo lives in a *directory named like a branch host*, which the hook's
fail-safe rule catches with no DNS involved.

**Installation must not touch production, and proving that cannot be done in
production.** Git worktrees share `.git/hooks`; measured from this repository's
own worktree, `git rev-parse --git-path hooks` resolves into production's
checkout. So the tests build a FABRICATED repository -- a main checkout plus a
linked worktree -- in `tmp_path`, and the mutation "install writes to
.git/hooks/pre-push" reddens against the fabricated common directory rather
than against production's. `test_installing_the_hook_does_not_touch_production`
additionally fingerprints production's real `.git/hooks` and `.git/config`, and
wraps the module's single write seam in a tripwire that refuses any destination
outside `tmp_path` -- because Task 5's lesson is that a tripwire over the
function which moves bytes misses the one which touches the destination.

Nothing here types production's project name, hostname or tailnet suffix; all
three are derived, both because `test_no_tracked_file_outside_docs_names_the_
old_project` forbids one of them and because a typed identity is the defect
`identity.py` exists to prevent.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from aurora_cli import crosswire, envfile, identity

#: The hook's own user-visible marker, typed here on purpose. This is the test's
#: independent statement of what the developer must see; deriving it from the
#: hook's source would make every assertion follow whatever the hook happens to
#: print, including nothing.
MARKER = "aurora pre-push:"

#: Neither of production's names, and not a real credential.
FIXTURE_BRANCH = "zz-fixture-branch"
FIXTURE_TOKEN = "zzfixturetoken-not-a-real-credential"

#: Git environment for every subprocess in this file.
#:
#: `GIT_ALLOW_PROTOCOL=file` is the network tripwire: git refuses http, https
#: and ssh outright, so no assertion in this file can be satisfied by a real
#: connection to production's Forgejo -- or to anyone else's.
#: `GIT_CONFIG_GLOBAL`/`GIT_CONFIG_SYSTEM` keep the developer's own config
#: (an `insteadOf`, a `core.hooksPath`) out of the measurements.
GIT_ENV = {
    "GIT_ALLOW_PROTOCOL": "file",
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_SSH_COMMAND": "/bin/false",
    "GIT_ASKPASS": "/bin/false",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
    "GIT_AUTHOR_NAME": "fixture",
    "GIT_AUTHOR_EMAIL": "fixture@invalid",
    "GIT_COMMITTER_NAME": "fixture",
    "GIT_COMMITTER_EMAIL": "fixture@invalid",
}


def _git(*args: str, cwd: Path, extra_env: dict[str, str] | None = None,
         stdin: str = "") -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.update(GIT_ENV)
    env.update(extra_env or {})
    return subprocess.run(
        ["git", *args], cwd=str(cwd), input=stdin,
        capture_output=True, text=True, env=env,
    )


def _output(proc: subprocess.CompletedProcess) -> str:
    """Both streams. `git hook run` sends a hook's stdout to stderr so it
    cannot interleave with the calling command's output, so a test that read
    only one stream would miss half of what the hook said."""
    return proc.stdout + proc.stderr


def _redact(url: str) -> str:
    """Drop userinfo before a URL goes anywhere a human might read it.

    This repository's `origin` carries a Forgejo access token in the URL. An
    assertion message, a pytest diff or a CI log is exactly the kind of place
    that must never contain it.
    """
    if "://" in url:
        scheme, _, rest = url.partition("://")
        return f"{scheme}://***@{rest.partition('@')[2]}" if "@" in rest else url
    return f"***@{url.partition('@')[2]}" if "@" in url else url


def _host_of(url: str) -> str:
    """The host of a remote URL, for the STRUCTURAL assertion only.

    Deliberately not used to decide anything the hook decides: a Python copy of
    the hook's matcher would be a decoy that reimplements the logic it claims
    to pin, which this repository has already shipped once. Layer 2 is only
    ever exercised by invoking the hook.
    """
    rest = url.partition("://")[2] or url
    authority = rest.split("/", 1)[0]
    if ":" in authority and "@" not in authority and not rest.startswith("/"):
        authority = authority.split(":", 1)[0]
    return authority.rpartition("@")[2].partition(":")[0]


# ---------------------------------------------------------------------------
# a fabricated repository: a main checkout plus a linked worktree
# ---------------------------------------------------------------------------


@dataclass
class Fabricated:
    """A stand-in for the real repository, in `tmp_path`.

    `main` plays production's checkout and `worktree` a branch worktree, so the
    hooks directory really is shared between them and an install that reached
    for `.git/hooks` reaches for a directory in `tmp_path` -- red, with nothing
    at risk.
    """

    root: Path
    main: Path
    worktree: Path
    refs: Path
    #: A commit that predates `hooks/pre-push`, so the pre-merge case -- a
    #: branch worktree whose checkout does not contain the hook -- can be built.
    commit_before_hook: str

    @property
    def common_git_dir(self) -> Path:
        return (self.main / ".git").resolve()

    def legacy_worktree(self) -> Path:
        """A worktree checked out from before the hook was tracked."""
        path = self.root / "legacy"
        proc = _git("worktree", "add", "-q", "--detach", str(path),
                    self.commit_before_hook, cwd=self.main)
        assert proc.returncode == 0, proc.stderr
        assert not (path / crosswire.HOOKS_DIRNAME).exists()
        return path

    def arm(self) -> None:
        """The one-time human step, applied to the fabricated repository."""
        command = crosswire.arming_command(self.main)
        assert command.endswith(f"config core.hooksPath {crosswire.HOOKS_DIRNAME}")
        proc = _git("config", "core.hooksPath", crosswire.HOOKS_DIRNAME,
                    cwd=self.main)
        assert proc.returncode == 0, proc.stderr

    def bare(self, name: str) -> Path:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        assert _git("init", "--bare", "-q", str(path), cwd=self.root).returncode == 0
        return path

    def refs_in(self, bare: Path) -> list[str]:
        proc = _git("for-each-ref", "--format=%(refname)", cwd=bare)
        return [line for line in proc.stdout.splitlines() if line.strip()]

    def run_hook(self, remote: str, url: str,
                 extra_env: dict[str, str] | None = None
                 ) -> subprocess.CompletedProcess:
        """Invoke the hook the way git does, through git's own resolution.

        `git hook run` finds the hook via `core.hooksPath`, honours the
        executable bit and propagates the hook's exit status -- so it exercises
        installation and arming, not just the file's contents -- while touching
        no transport at all.
        """
        return _git("hook", "run", f"--to-stdin={self.refs}", crosswire.HOOK_NAME,
                    "--", remote, url, cwd=self.worktree, extra_env=extra_env)

    def push(self, target: Path) -> subprocess.CompletedProcess:
        return _git("push", str(target), "fixture", cwd=self.worktree)


@pytest.fixture
def fabricated(tmp_path) -> Fabricated:
    root = tmp_path / "repo"
    main = root / "main"
    main.mkdir(parents=True)
    assert _git("init", "-q", ".", cwd=main).returncode == 0

    # The two files the hook derives from, with REAL values so that the hook
    # under test answers the same questions it will answer in this repository:
    # the tracked template supplies the product name, production's `.env` the
    # domain. Both copied/derived, never typed.
    (main / ".env.template").write_text(
        (identity.package_root() / ".env.template").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    # `.env` is gitignored here exactly as it is in the real repository, and
    # that is load-bearing rather than tidy: the MAIN checkout's `.env` carries
    # production's domain and the WORKTREE's carries the branch's own. Without
    # that difference, a hook that read its own worktree's `.env` -- and so
    # treated the branch's forge as production and waved every push at it
    # through -- would be indistinguishable from a correct one.
    (main / ".gitignore").write_text(".env\n", encoding="utf-8")
    (main / ".env").write_text(
        f"DOMAIN_NAME={identity.production_domain()}\n", encoding="utf-8"
    )
    assert _git("add", "-A", cwd=main).returncode == 0
    assert _git("commit", "-qm", "fixture: before the hook", cwd=main).returncode == 0
    before = _git("rev-parse", "HEAD", cwd=main).stdout.strip()
    assert before

    # The hook as a TRACKED file with the executable bit in the index, exactly
    # as a worktree of a branch carrying this commit has it.
    hooks = main / crosswire.HOOKS_DIRNAME
    hooks.mkdir()
    (hooks / crosswire.HOOK_NAME).write_text(crosswire.hook_text(), encoding="utf-8")
    (hooks / crosswire.HOOK_NAME).chmod(0o755)
    assert _git("add", "-A", cwd=main).returncode == 0
    assert _git("commit", "-qm", "fixture: the hook", cwd=main).returncode == 0

    worktree = root / "wt"
    proc = _git("worktree", "add", "-q", str(worktree), "-b", "fixture", cwd=main)
    assert proc.returncode == 0, proc.stderr

    # The branch's own `.env`, as `aurora branch up` renders it. Different from
    # the main checkout's by construction; asserted, because the whole value of
    # this fixture rests on the two not being the same file.
    branch_env = f"DOMAIN_NAME={identity.branch_domain(FIXTURE_BRANCH)}\n"
    assert branch_env != (main / ".env").read_text(encoding="utf-8")
    (worktree / ".env").write_text(branch_env, encoding="utf-8")

    refs = root / "refs.txt"
    refs.write_text(
        "refs/heads/fixture " + "1" * 40 + " refs/heads/fixture " + "0" * 40 + "\n",
        encoding="utf-8",
    )
    return Fabricated(root=root, main=main, worktree=worktree, refs=refs,
                      commit_before_hook=before)


@pytest.fixture
def armed(fabricated) -> Fabricated:
    fabricated.arm()
    assert crosswire.hook_is_armed(fabricated.worktree), (
        "the fabricated repository did not arm; every hook assertion below "
        "would then be measuring a hook git never runs"
    )
    return fabricated


# ---------------------------------------------------------------------------
# the fact the whole design rests on
# ---------------------------------------------------------------------------


def test_worktrees_share_the_hooks_directory_until_a_relative_path_is_set(
    fabricated,
):
    """Pins the git behaviour, in both directions, in a fabricated repo.

    Direction one is the DISQUALIFYING fact: with nothing configured, a linked
    worktree's hooks directory is inside the COMMON git dir -- production's.
    Anyone who "simplifies" `install_pre_push` into writing `.git/hooks/pre-push`
    is writing into production, and this is where that shows up.

    Direction two is the mechanism this module chose: a RELATIVE
    `core.hooksPath` resolves against each worktree's own root, so one line in
    the shared config arms every worktree separately. Measured on git 2.55; it
    is a property of git, not of this host, so it is pinned rather than
    assumed.
    """
    shared = crosswire.resolved_hooks_dir(fabricated.worktree)
    assert fabricated.common_git_dir in shared.parents, (
        f"expected an unconfigured worktree to resolve hooks inside the common "
        f"git dir {fabricated.common_git_dir}, got {shared}"
    )
    assert not crosswire.hook_is_armed(fabricated.worktree)

    fabricated.arm()

    assert crosswire.resolved_hooks_dir(fabricated.worktree) == \
        fabricated.worktree.resolve() / crosswire.HOOKS_DIRNAME
    assert crosswire.resolved_hooks_dir(fabricated.main) == \
        fabricated.main.resolve() / crosswire.HOOKS_DIRNAME
    assert crosswire.hook_is_armed(fabricated.worktree)
    assert crosswire.hook_is_armed(fabricated.main)


def test_the_hooks_path_is_relative_and_a_single_component():
    """An absolute `core.hooksPath` would arm one worktree and DISARM every
    other one, production included, because the setting is shared. The
    relativeness is the safety property, so it is asserted rather than left to
    the constant's spelling."""
    assert not Path(crosswire.HOOKS_DIRNAME).is_absolute()
    assert Path(crosswire.HOOKS_DIRNAME).parts == (crosswire.HOOKS_DIRNAME,)
    assert crosswire.HOOKS_DIRNAME not in ("", ".", "..")


def test_the_harness_cannot_reach_the_network(armed):
    """The tripwire's own non-vacuity.

    Git discovers the remote's refs BEFORE running pre-push, so a push at an
    https URL contacts the remote whatever the hook decides. Every git call in
    this file therefore runs under `GIT_ALLOW_PROTOCOL=file`. If that ever
    stopped working, the reject-a-real-push test would start reaching
    production's Forgejo -- so it is measured here, not trusted.
    """
    branch_url = f"https://{identity.branch_domain(FIXTURE_BRANCH)}/git/x.git"
    proc = _git("push", branch_url, "fixture", cwd=armed.worktree)

    assert proc.returncode != 0
    assert "transport 'https' not allowed" in _output(proc), (
        "git no longer honours GIT_ALLOW_PROTOCOL; the pushes in this file "
        f"could reach the network. Output was: {_output(proc)!r}"
    )


# ---------------------------------------------------------------------------
# layer 2, through git: refusals
# ---------------------------------------------------------------------------


def _branch_urls() -> list[str]:
    """Every shape a branch forge can be named by, derived from identity."""
    domain = identity.branch_domain(FIXTURE_BRANCH)
    host = identity.branch_hostname(FIXTURE_BRANCH)
    return [
        f"https://{domain}/git/supergoodname77/x.git",
        f"http://{domain}/git/supergoodname77/x.git",
        # The credential-bearing shape this repository's own origin uses.
        f"https://supergoodname77:{FIXTURE_TOKEN}@{domain}/git/x.git",
        f"ssh://git@{domain}:222/supergoodname77/x.git",
        f"git@{domain}:supergoodname77/x.git",
        # MagicDNS resolves the bare label on the tailnet, so it is reachable
        # and must be refused too.
        f"http://{host}/git/x.git",
    ]


def test_the_hook_rejects_a_branch_remote(armed):
    """The named case: a push at a branch's forge is refused."""
    url = f"https://{identity.branch_domain(FIXTURE_BRANCH)}/git/x.git"
    proc = armed.run_hook("branchforge", url)

    assert proc.returncode == 1, _output(proc)
    assert MARKER in _output(proc), (
        "exit 1 alone proves nothing -- `git hook run` exits 1 for a MISSING "
        f"hook too. Output was: {_output(proc)!r}"
    )
    assert "BRANCH forge" in _output(proc)


def test_the_hook_rejects_every_shape_a_branch_forge_can_be_named_by(armed):
    urls = _branch_urls()
    assert len(urls) >= 5, "too few URL shapes to be checking anything"

    allowed = []
    for url in urls:
        proc = armed.run_hook("branchforge", url)
        if proc.returncode == 0 or MARKER not in _output(proc):
            allowed.append((_redact(url), proc.returncode, _output(proc)[:200]))

    assert allowed == [], (
        f"the hook let a branch forge through in {len(allowed)} shape(s): "
        f"{allowed}"
    )


def test_the_hook_redacts_the_credential_it_is_shown(armed):
    """`origin` in this repository embeds a Forgejo token. A refusal that
    echoed the URL verbatim would print a live credential into the developer's
    terminal, their scrollback and any log that captured it."""
    url = f"https://supergoodname77:{FIXTURE_TOKEN}@" \
          f"{identity.branch_domain(FIXTURE_BRANCH)}/git/x.git"
    output = _output(armed.run_hook("branchforge", url))

    assert MARKER in output
    assert FIXTURE_TOKEN not in output, (
        "the refusal message leaked the credential from the remote URL"
    )
    assert "***@" in output, (
        "the refusal names no remote at all, which makes it much harder to act "
        f"on: {output!r}"
    )


# ---------------------------------------------------------------------------
# layer 2, through git: the pushes that must still work
# ---------------------------------------------------------------------------


def _production_urls() -> list[str]:
    domain = identity.production_domain()
    return [
        f"https://{domain}/git/supergoodname77/x.git",
        # The shape a worktree actually inherits: userinfo included. A parser
        # that failed to strip it would not recognise production and would
        # block the one push that must always work.
        f"https://supergoodname77:{FIXTURE_TOKEN}@{domain}/git/x.git",
        f"ssh://git@{domain}:222/supergoodname77/x.git",
        f"git@{domain}:supergoodname77/x.git",
    ]


def test_the_hook_allows_production(armed):
    """A hook that blocks the legitimate push is deleted by the first developer
    who hits it, which is strictly worse than no hook. Production's domain and
    a branch's domain share a tailnet suffix, so this is the assertion that
    catches a matcher which fires on the suffix.

    Allowed FOR THE RIGHT REASON, not merely allowed. `exit 0` has two sources
    here -- the explicit production rule, and falling off the end of the rules --
    and a hook that mis-parsed the host would take the second one and look
    identical. Measured: deleting the userinfo strip makes
    `https://user:token@<production>/...` parse to host `user`, which is not a
    branch host either, so an exit-code-only assertion passed against a hook
    that could no longer recognise production at all -- and that same hook lets
    a CREDENTIALLED push to a branch forge through. So the verdict is asserted,
    not the status.
    """
    urls = _production_urls()
    assert len(urls) >= 4

    wrong = []
    for url in urls:
        proc = armed.run_hook("origin", url,
                              extra_env={"AURORA_PRE_PUSH_EXPLAIN": "1"})
        output = _output(proc)
        if proc.returncode != 0 or "verdict=allow-production" not in output:
            wrong.append((
                _redact(url), proc.returncode,
                [line for line in output.splitlines()
                 if line.startswith(("verdict=", "remote-host="))],
            ))

    assert wrong == [], (
        f"the hook did not recognise PRODUCTION in {len(wrong)} shape(s): "
        f"{wrong}. Every developer's normal push goes here, and one that is "
        "allowed only because the host was misparsed is a hook that has "
        "stopped telling production from anything else."
    )


def test_the_hook_allows_a_non_forgejo_remote(armed):
    """Allowed by falling through the rules -- `verdict=allow`, distinct from
    production's `allow-production`. Asserting which of the two fired keeps the
    paths separable, which is what M7 showed matters."""
    for url in (
        "https://github.com/owner/repo.git",
        "git@github.com:owner/repo.git",
        # Shares the product prefix but not the tailnet: not a branch forge.
        f"https://{identity.declared_project()}-mirror.github.com/o/r.git",
    ):
        proc = armed.run_hook("elsewhere", url,
                              extra_env={"AURORA_PRE_PUSH_EXPLAIN": "1"})
        assert proc.returncode == 0, (
            f"{_redact(url)} was refused: {_output(proc)!r}"
        )
        assert "verdict=allow\n" in _output(proc), (
            f"{_redact(url)} was allowed by an unexpected rule: "
            f"{_output(proc)!r}"
        )


def test_the_hook_allows_a_host_that_merely_shares_the_tailnet(armed):
    """Another host on the same tailnet is not a branch forge. This is the case
    a suffix-only matcher gets wrong along with production's own domain."""
    url = f"https://otherhost.{identity.tailnet_suffix()}/git/x.git"
    assert armed.run_hook("peer", url).returncode == 0


def test_the_hook_allows_an_ordinary_local_remote(armed):
    for url in ("/tmp/somewhere/bare.git", "../sibling.git",
                f"/srv/{identity.declared_project()}-mirror.git"):
        proc = armed.run_hook("local", url)
        assert proc.returncode == 0, f"{url} was refused: {_output(proc)!r}"


# ---------------------------------------------------------------------------
# layer 2, through a real `git push`
# ---------------------------------------------------------------------------


def _branch_named_bare(fab: Fabricated) -> Path:
    """A bare repo inside a directory named like a branch forge.

    This is what makes a REAL push testable with no network: git talks to a local
    path, the hook is handed that path, and the hook's fail-safe rule -- a URL
    with no parsable host that nevertheless spells `<prefix>...<tailnet>` --
    catches it. No DNS, no transport, and the whole of git's push machinery
    exercised.
    """
    return fab.bare(f"{identity.branch_domain(FIXTURE_BRANCH)}/forge.git")


def test_a_real_push_at_a_branch_forge_is_aborted_and_nothing_arrives(armed):
    crosswire.install_pre_push(armed.worktree)
    bare = _branch_named_bare(armed)

    proc = armed.push(bare)

    assert proc.returncode != 0, (
        f"the push was NOT aborted: {_output(proc)!r}"
    )
    assert MARKER in _output(proc)
    assert armed.refs_in(bare) == [], (
        "the push was reported as failed but a ref arrived anyway"
    )


def test_a_real_push_at_an_ordinary_remote_succeeds(armed):
    """The over-block control, on the same code path as the test above.

    Without this, a hook that refused everything would satisfy every rejection
    assertion in this file -- and over-blocking is the realistic failure, since
    production's domain and a branch's share a tailnet suffix.
    """
    crosswire.install_pre_push(armed.worktree)
    bare = armed.bare("plain.git")

    proc = armed.push(bare)

    assert proc.returncode == 0, f"an ordinary push was refused: {_output(proc)!r}"
    assert armed.refs_in(bare) == ["refs/heads/fixture"]


def test_a_hook_that_is_not_executable_lets_the_push_through(armed):
    """The vacuous pass with a filesystem bit instead of an empty set.

    Measured, not reasoned about: git SKIPS a non-executable hook with nothing
    but an advice hint and the push succeeds. So `install_pre_push` chmodding is
    load-bearing, and any assertion of the form "exit != 0" would be satisfied
    by a hook that is merely absent.
    """
    install = crosswire.install_pre_push(armed.worktree)
    install.path.chmod(0o644)
    bare = _branch_named_bare(armed)

    proc = armed.push(bare)

    assert proc.returncode == 0, (
        "git now refuses to push when a hook is present but non-executable; "
        "that would be an improvement, but this test's premise -- and the "
        f"reason install chmods -- has changed: {_output(proc)!r}"
    )
    assert armed.refs_in(bare) == ["refs/heads/fixture"], (
        "the ref did not arrive, so this test is not measuring what it claims"
    )
    assert MARKER not in _output(proc)

    # And install repairs it.
    repaired = crosswire.install_pre_push(armed.worktree)
    assert repaired.executable
    assert repaired.path.stat().st_mode & 0o111


def test_a_refusal_and_a_missing_hook_are_distinguishable(armed):
    """Both exit 1. Only one of them is a defence.

    This is the sequential-guard trap in a subprocess costume: an assertion on
    the exit code alone passes against a repository where the hook was never
    installed at all.
    """
    crosswire.install_pre_push(armed.worktree)
    url = f"https://{identity.branch_domain(FIXTURE_BRANCH)}/git/x.git"

    refusal = armed.run_hook("branchforge", url)
    assert refusal.returncode == 1
    assert MARKER in _output(refusal)

    (armed.worktree / crosswire.HOOKS_DIRNAME / crosswire.HOOK_NAME).unlink()
    missing = armed.run_hook("branchforge", url)

    assert missing.returncode == 1, (
        "a missing hook no longer exits 1; check whether the marker assertions "
        "elsewhere in this file are still the thing keeping them honest"
    )
    assert MARKER not in _output(missing)
    assert "cannot find a hook" in _output(missing)


# ---------------------------------------------------------------------------
# layer 2: failing closed, and agreeing with identity.py
# ---------------------------------------------------------------------------


def test_the_hook_refuses_when_it_cannot_tell_a_branch_from_production(armed):
    """Two fail-closed paths, and each must be recognisable on its own.

    A hook that cannot make the distinction must not wave the push through: the
    developer would believe a defence is in place that is not. Both messages
    are asserted to name the OTHER case's wording nowhere, so a single
    catch-all refusal cannot satisfy both.
    """
    crosswire.install_pre_push(armed.worktree)

    no_url = _git("hook", "run", f"--to-stdin={armed.refs}", crosswire.HOOK_NAME,
                  cwd=armed.worktree)
    assert no_url.returncode == 1
    assert "cannot determine which remote" in _output(no_url)
    assert "cannot derive the product name" not in _output(no_url)

    (armed.worktree / ".env.template").unlink()
    no_product = armed.run_hook("origin", "https://github.com/o/r.git")
    assert no_product.returncode == 1
    assert "cannot derive the product name" in _output(no_product)
    assert "cannot determine which remote" not in _output(no_product)
    assert ".env.template" in _output(no_product), (
        "the refusal does not say what to fix, which is how a hook gets deleted"
    )


def test_the_hook_derives_the_same_identity_as_the_python_module():
    """A drift test between two independent implementations.

    The hook is POSIX sh and reads `.env.template` and production's `.env` with
    `sed`; `identity.py` reads them in Python. That is a THIRD env-file parser
    in this repository, and the ledger already records two "identical" docker
    queries drifting apart twice. Run against the REAL checkout, read-only, so
    it compares what the hook will actually derive in production's tree.
    """
    proc = subprocess.run(
        [str(crosswire.hook_source_path()), "origin",
         f"https://{identity.production_domain()}/git/x.git"],
        cwd=str(identity.package_root()), input="", capture_output=True,
        text=True, env={**os.environ, "AURORA_PRE_PUSH_EXPLAIN": "1"},
    )
    assert proc.returncode == 0, _output(proc)

    reported = dict(
        line.split("=", 1) for line in _output(proc).splitlines() if "=" in line
    )
    assert reported, f"the hook explained nothing: {_output(proc)!r}"
    assert reported == {
        "product": identity.declared_project(),
        "branch-hostname-prefix": identity.branch_hostname_prefix(),
        "production-domain": identity.production_domain(),
        "tailnet-suffix": identity.tailnet_suffix(),
        "remote-name": "origin",
        "remote-host": identity.production_domain(),
        "verdict": "allow-production",
    }


def test_the_hook_derives_productions_domain_not_its_own_worktrees(armed):
    """The direction that is easy to get exactly backwards.

    Running inside a BRANCH worktree, the hook must derive PRODUCTION's domain
    -- from the main worktree's `.env` -- and not the domain in the `.env` next
    to it, which is the branch's own. A hook that read its own worktree's `.env`
    would treat the branch's forge as production and allow every push to the one
    forge that is about to be deleted.
    """
    crosswire.install_pre_push(armed.worktree)
    own = envfile.parse_env(
        (armed.worktree / ".env").read_text(encoding="utf-8")
    )["DOMAIN_NAME"]
    assert own == identity.branch_domain(FIXTURE_BRANCH)

    reported = dict(
        line.split("=", 1)
        for line in _output(armed.run_hook(
            "origin", f"https://{identity.production_domain()}/git/x.git",
            extra_env={"AURORA_PRE_PUSH_EXPLAIN": "1"},
        )).splitlines()
        if "=" in line
    )

    assert reported.get("production-domain") == identity.production_domain(), (
        f"the hook derived {reported.get('production-domain')!r} as production, "
        f"and the worktree it ran in declares {own!r}"
    )
    assert reported.get("production-domain") != own
    assert reported.get("verdict") == "allow-production"


def test_explaining_does_not_change_the_verdict(armed):
    """The diagnostic mode must not be a bypass."""
    crosswire.install_pre_push(armed.worktree)
    url = f"https://{identity.branch_domain(FIXTURE_BRANCH)}/git/x.git"

    quiet = armed.run_hook("branchforge", url)
    loud = armed.run_hook("branchforge", url,
                          extra_env={"AURORA_PRE_PUSH_EXPLAIN": "1"})

    assert quiet.returncode == loud.returncode == 1
    assert MARKER in _output(quiet) and MARKER in _output(loud)
    assert "verdict=reject" in _output(loud)
    assert "verdict=" not in _output(quiet)


def test_the_hook_names_neither_production_nor_the_tailnet(armed):
    """The hook derives every identity; a literal here would be a copy-paste
    source and would be wrong in one of the two worlds the blocked rename
    leaves this repository in.

    The declared PRODUCT name is deliberately not in scope: the hook's own
    user-visible marker carries it, and the package's import path carries it
    everywhere else -- the same exemption Task 6 recorded for `seed.py`, for the
    same reason. The behavioural rules are what pin the derivation.
    """
    text = crosswire.hook_text()
    # The project name is dropped when it is a prefix of this package's own
    # import name -- which it became when production was renamed to `aurora`.
    # The docstring above already declared that exemption for the PRODUCT
    # name; the rename made product and project the same token. Conditional,
    # so a rename to an unrelated name re-arms it with no edit here.
    package = crosswire.__name__.split(".")[0]
    banned = {
        label: literal for label, literal in {
            "production's project name": identity.production_project(),
            "production's domain": identity.production_domain(),
            "the tailnet suffix": identity.tailnet_suffix(),
        }.items()
        if not package.startswith(literal)
    }
    assert banned, "every identity was exempted; this scan checks nothing"
    for label, literal in banned.items():
        assert len(literal) > 3, f"{label} derived to something degenerate"
        assert literal not in text, f"hooks/{crosswire.HOOK_NAME} types {label}"


# ---------------------------------------------------------------------------
# installation
# ---------------------------------------------------------------------------


def _fingerprint(git_dir: Path) -> dict:
    """Content and mtime of a git directory's `hooks/` and `config`.

    mtimes as well as bytes: a write that happened to produce identical content
    is still a write into a live checkout, and `mkdir`/`copystat` moved
    production's `forgejo/` mtime in Task 5 without changing a single file.
    """
    hooks = git_dir / "hooks"
    entries = {}
    if hooks.is_dir():
        for path in sorted(hooks.iterdir()):
            stat = path.stat()
            entries[path.name] = (
                stat.st_mtime_ns,
                stat.st_mode,
                hashlib.sha256(path.read_bytes()).hexdigest(),
            )
    config = git_dir / "config"
    return {
        "hooks_dir_mtime_ns": hooks.stat().st_mtime_ns if hooks.is_dir() else None,
        "hooks": entries,
        "config": (
            config.stat().st_mtime_ns,
            hashlib.sha256(config.read_bytes()).hexdigest(),
        ) if config.is_file() else None,
    }


@pytest.fixture
def write_tripwire(monkeypatch, tmp_path):
    """Refuse, before it happens, any write outside this test's `tmp_path`.

    Wraps `crosswire._write_hook` rather than replacing it, so the real write
    still happens and the assertions after it remain meaningful. It wraps THAT
    function specifically because it is the one that touches the DESTINATION --
    `mkdir`, the bytes and `chmod` all live there. Task 5 tripwired the two
    functions that moved bytes and missed the one that did `mkdir` +
    `copystat`, and production's `forgejo/` mtime moved.
    """
    calls: list[Path] = []
    real = crosswire._write_hook

    def guarded(destination, text, *, worktree):
        resolved = Path(destination).resolve()
        assert tmp_path.resolve() in resolved.parents, (
            f"TRIPWIRE: the installer tried to write OUTSIDE this test's "
            f"temporary directory: {resolved}. Production's checkout, and the "
            "git directory every worktree of it shares, are both outside it."
        )
        calls.append(resolved)
        return real(destination, text, worktree=worktree)

    monkeypatch.setattr(crosswire, "_write_hook", guarded)
    return calls


def test_installing_the_hook_does_not_touch_production(fabricated, write_tripwire):
    """The test that justifies the whole installation design.

    Production's real `.git/hooks` and `.git/config` are fingerprinted, the
    install runs against a FABRICATED worktree, and both fingerprints must be
    unchanged. The fabricated repository is what lets the mutation "install
    writes to .git/hooks/pre-push" actually redden -- it lands in the
    fabricated common git dir, which is inside `tmp_path`, so the tripwire
    catches it with nothing at risk. A test that ran the same mutation against
    a worktree of the real repository would have written into production.
    """
    # Installed into a checkout that does NOT already contain the hook, so a
    # write genuinely happens and the tripwire has something to have allowed.
    # Created before the fingerprints: `git worktree add` writes under
    # `.git/worktrees/`, which is neither `hooks/` nor `config` but is no reason
    # to blur the measurement.
    target = fabricated.legacy_worktree()

    production_git = identity.production_root() / ".git"
    before = _fingerprint(production_git)
    assert before["hooks"], (
        f"{production_git}/hooks is empty, so 'unchanged' would be vacuous"
    )
    assert before["config"] is not None
    fabricated_before = _fingerprint(fabricated.common_git_dir)
    assert fabricated_before["hooks"], (
        "the fabricated repository has no shared hooks directory to protect, "
        "so this test cannot see a write into one"
    )

    install = crosswire.install_pre_push(target)

    assert write_tripwire, "the installer wrote nothing, so nothing was proved"
    assert install.path == \
        target.resolve() / crosswire.HOOKS_DIRNAME / crosswire.HOOK_NAME
    assert _fingerprint(fabricated.common_git_dir) == fabricated_before, (
        "installing into a worktree modified the git directory it SHARES with "
        "the main checkout -- which for every worktree of this repository is "
        "production's"
    )
    assert _fingerprint(production_git) == before, (
        "installing into a fabricated worktree modified PRODUCTION's git "
        "directory"
    )


def test_install_puts_an_executable_copy_of_the_tracked_hook_in_the_worktree(
    fabricated, write_tripwire
):
    """Artifact and generator, in one assertion each way: what install writes
    is byte-identical to the tracked file, and the tracked file is executable in
    git's index -- so a fresh worktree is armed by the checkout alone."""
    install = crosswire.install_pre_push(fabricated.worktree)

    assert install.path.read_text(encoding="utf-8") == crosswire.hook_text()
    assert install.path.stat().st_mode & 0o111
    assert install.executable

    listed = subprocess.run(
        ["git", "ls-files", "-s",
         f"{crosswire.HOOKS_DIRNAME}/{crosswire.HOOK_NAME}"],
        cwd=str(identity.package_root()), capture_output=True, text=True,
    ).stdout.split()
    assert listed and listed[0] == "100755", (
        f"hooks/{crosswire.HOOK_NAME} is not tracked as executable ({listed}); "
        "git would check it out non-executable and git silently skips a "
        "non-executable hook"
    )


def test_install_is_idempotent_and_leaves_a_merged_worktree_clean(
    fabricated, write_tripwire
):
    """In a worktree whose checkout already contains the hook -- every worktree
    of a branch carrying this commit -- installing must be a no-op the working
    tree cannot see. Writing a rendered or reformatted hook would leave every
    branch worktree permanently dirty."""
    first = crosswire.install_pre_push(fabricated.worktree)
    assert not write_tripwire, (
        "the hook was already checked out and identical, so install had "
        "nothing to write"
    )
    second = crosswire.install_pre_push(fabricated.worktree)

    assert first.path.read_text() == second.path.read_text()
    status = _git("status", "--porcelain", cwd=fabricated.worktree).stdout
    assert status.strip() == "", (
        f"installing the hook dirtied the worktree: {status!r}"
    )


def test_install_creates_the_hook_even_in_a_checkout_that_predates_it(
    fabricated, write_tripwire
):
    """The pre-merge case, and its known cost.

    A worktree branched from a commit without `hooks/pre-push` -- every branch
    taken from `main` until this work merges -- gets the file as an UNTRACKED
    addition. That is the right trade, since the defence should exist before the
    merge does, but it is a cost, so it is asserted rather than discovered.
    """
    legacy = fabricated.legacy_worktree()

    install = crosswire.install_pre_push(legacy)

    assert write_tripwire == [install.path]
    assert install.path.is_file() and install.executable
    assert install.path.read_text(encoding="utf-8") == crosswire.hook_text()
    status = _git("status", "--porcelain", cwd=legacy).stdout
    assert f"?? {crosswire.HOOKS_DIRNAME}/" in status, (
        f"expected the hook to appear as untracked in a pre-merge checkout, "
        f"git reported: {status!r}"
    )


def test_install_reports_whether_git_will_actually_run_the_hook(fabricated):
    """`armed` is not decoration: until a human runs the arming command the
    mechanical layer is INERT, and an installer that returned nothing about
    that would let Task 8 report success for a defence that does not exist."""
    unarmed = crosswire.install_pre_push(fabricated.worktree)
    assert unarmed.executable and not unarmed.armed and not unarmed.effective
    assert crosswire.arming_command() in unarmed.advice()
    assert str(unarmed.hooks_dir) in unarmed.advice()

    fabricated.arm()
    now = crosswire.install_pre_push(fabricated.worktree)
    assert now.armed and now.effective
    assert now.advice() == ""


def test_install_refuses_productions_checkout(write_tripwire):
    """Production's copy of the hook is a TRACKED FILE, arriving by merge. An
    installer that wrote it there would be writing into a live checkout."""
    with pytest.raises(crosswire.CrosswireError) as excinfo:
        crosswire.install_pre_push(identity.production_root())

    assert "PRODUCTION" in str(excinfo.value)
    assert write_tripwire == [], "it refused, but only after writing"


def test_the_destination_guards_each_refuse_on_their_own(fabricated):
    """Three refusals of one exception type, so `pytest.raises` alone would be
    satisfied by any of them -- including by a guard that had been deleted,
    since the next one raises on the same input. Each case therefore asserts
    its own wording AND the absence of the other two, and the control at the
    end is what stops an unconditionally-raising guard from passing all three.
    """
    worktree = fabricated.worktree
    wordings = {
        "production": "PRODUCTION's checkout",
        "shared": "SHARED git",
        "escape": "not inside the worktree",
    }

    def message(destination: Path, target: Path) -> str:
        with pytest.raises(crosswire.CrosswireError) as excinfo:
            crosswire.assert_hook_destination(destination, target)
        return str(excinfo.value)

    production = identity.production_root()
    cases = {
        "production": message(
            production / crosswire.HOOKS_DIRNAME / crosswire.HOOK_NAME, production
        ),
        "shared": message(
            fabricated.common_git_dir / "hooks" / crosswire.HOOK_NAME, worktree
        ),
        "escape": message(fabricated.root / "elsewhere" / "pre-push", worktree),
    }
    for case, text in cases.items():
        assert wordings[case] in text, f"{case} refusal said: {text!r}"
        for other, wording in wordings.items():
            if other != case:
                assert wording not in text, (
                    f"the {case} refusal also carries the {other} wording, so "
                    "deleting either guard would leave the other's test green"
                )

    # The control. Without it, `assert_hook_destination` could refuse
    # everything and satisfy all three assertions above.
    assert crosswire.assert_hook_destination(
        worktree / crosswire.HOOKS_DIRNAME / crosswire.HOOK_NAME, worktree
    ) is None


def test_the_arming_command_is_a_relative_hooks_path_for_productions_checkout():
    command = crosswire.arming_command()

    assert str(identity.production_root()) in command
    assert f"core.hooksPath {crosswire.HOOKS_DIRNAME}" in command
    assert "--worktree" not in command, (
        "`git config --worktree` requires extensions.worktreeConfig, and "
        "enabling that is itself a write to the config every worktree shares "
        "with production -- besides making the repository unreadable to older "
        "git"
    )


def test_the_documented_arming_step_matches_the_code():
    """Docs and code, pinned to each other.

    Only the mechanism is compared, not the absolute path: production's
    checkout is renamed the moment Chunk 2's blocked rename lands, and a test
    that pinned the path would go red for a reason that has nothing to do with
    this hook.
    """
    doc = (identity.package_root() / "docs" / "post-implementation-steps.md")
    text = doc.read_text(encoding="utf-8")

    assert f"core.hooksPath {crosswire.HOOKS_DIRNAME}" in text, (
        f"{doc.name} does not document the arming step, which is the only "
        "thing that makes the hook run at all"
    )
    assert f"{crosswire.HOOKS_DIRNAME}/{crosswire.HOOK_NAME}" in text


# ---------------------------------------------------------------------------
# layer 1: structural
# ---------------------------------------------------------------------------


def test_a_worktree_inherits_an_origin_that_points_at_production():
    """Spec 5.4 layer 1, asserted rather than built.

    Remotes live in the config every worktree shares, so a branch worktree
    inherits production's `origin` and reaching a branch forge takes a
    deliberate `git remote add`. The URL itself is never asserted on or printed
    -- it carries a Forgejo token.
    """
    proc = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=str(identity.package_root()), capture_output=True, text=True,
    )
    assert proc.returncode == 0 and proc.stdout.strip(), (
        "this worktree has no `origin`, so layer 1 of spec 5.4 does not exist "
        "and the claim that a branch worktree inherits production's remote is "
        "untrue"
    )
    host = _host_of(proc.stdout.strip())

    assert host == identity.production_domain(), (
        f"origin resolves to host {host!r}, not production's "
        f"{identity.production_domain()!r}"
    )
    assert not host.startswith(identity.branch_hostname_prefix())


def test_a_branch_forge_is_a_different_host_that_shares_the_tailnet():
    """Why layer 2 needs a real distinction rather than a suffix match: the two
    hosts differ, and they differ only in the label before the tailnet."""
    branch = identity.branch_domain(FIXTURE_BRANCH)
    production = identity.production_domain()
    suffix = identity.tailnet_suffix()

    assert branch != production
    assert branch.endswith(f".{suffix}") and production.endswith(f".{suffix}")
    assert branch.startswith(identity.branch_hostname_prefix())
    assert not production.startswith(identity.branch_hostname_prefix())


# ---------------------------------------------------------------------------
# layer 3: the visual marker
# ---------------------------------------------------------------------------


def test_branch_app_name_marks_the_branch():
    base = crosswire.production_app_name()
    assert base, "production's application name derived to nothing"

    assert crosswire.branch_app_name("demo") == f"{base} [BRANCH: demo]"
    # Sanitised, like every other branch-derived name: the marker must match
    # the hostname and the project a developer sees everywhere else.
    assert crosswire.branch_app_name("Feature/Foo Bar") == \
        f"{base} [BRANCH: feature-foo-bar]"
    assert crosswire.branch_marker("demo") == "[BRANCH: demo]"


def test_the_app_name_base_is_read_from_compose_not_typed(tmp_path, monkeypatch):
    """Derived, so that renaming production's forge renames every branch's too
    and the marker stays the only difference. Pointed at a fabricated
    compose.yml with a different default, which a typed base would ignore."""
    monkeypatch.setattr(identity, "production_env", lambda: {})
    (tmp_path / "compose.yml").write_text(
        "services:\n  forgejo:\n    environment:\n"
        "      - FORGEJO____APP_NAME=${FORGEJO_APP_NAME:-fabricated-forge}\n",
        encoding="utf-8",
    )
    assert crosswire.production_app_name(tmp_path) == "fabricated-forge"
    assert crosswire.branch_app_name("demo", tmp_path) == \
        "fabricated-forge [BRANCH: demo]"


def test_an_unparameterised_or_empty_app_name_is_refused(tmp_path, monkeypatch):
    """Both failures the parameterisation exists to prevent, from the module's
    side. The repo-conformance test asserts the same thing about the real
    compose.yml from three independent directions; this pins the reader."""
    monkeypatch.setattr(identity, "production_env", lambda: {})

    (tmp_path / "compose.yml").write_text(
        "      - FORGEJO____APP_NAME=null-hub\n", encoding="utf-8"
    )
    with pytest.raises(crosswire.CrosswireError, match="parameterised"):
        crosswire.production_app_name(tmp_path)

    (tmp_path / "compose.yml").write_text(
        "      - FORGEJO____APP_NAME=${FORGEJO_APP_NAME:-}\n", encoding="utf-8"
    )
    with pytest.raises(crosswire.CrosswireError, match="EMPTY default"):
        crosswire.production_app_name(tmp_path)


def test_productions_own_env_wins_over_the_compose_default(tmp_path, monkeypatch):
    """If production ever sets the variable, that is what production runs and
    what a branch must be marked against -- otherwise every branch would be
    marked against a default production stopped using."""
    monkeypatch.setattr(
        identity, "production_env",
        lambda: {crosswire.APP_NAME_VAR: "renamed-forge"},
    )
    (tmp_path / "compose.yml").write_text(
        "      - FORGEJO____APP_NAME=${FORGEJO_APP_NAME:-null-hub}\n",
        encoding="utf-8",
    )
    assert crosswire.production_app_name(tmp_path) == "renamed-forge"


def test_a_rendered_branch_env_marks_the_branch_and_stays_safe():
    """End to end: the manifest entry, the derivation and the checker together.

    The value contains spaces and brackets, which is exactly the kind of thing a
    dotenv writer gets wrong, so the strict-`KEY=value` predicate the whole repo
    is held to is applied here too.
    """
    rendered = envfile.render_branch_env(
        FIXTURE_BRANCH, devs=("testuser",), authkey="tskey-zz-fixture"
    )
    values = envfile.parse_env(rendered)

    assert values[crosswire.APP_NAME_VAR] == \
        crosswire.branch_app_name(FIXTURE_BRANCH)
    assert crosswire.branch_marker(FIXTURE_BRANCH) in values[crosswire.APP_NAME_VAR]
    # Rendered as one strict `KEY=value` line despite the spaces and brackets
    # in the value. `tests/test_branch_env.py` holds the whole rendered file to
    # the repository's dotenv predicate; this checks the line survives intact.
    assert f"{crosswire.APP_NAME_VAR}={values[crosswire.APP_NAME_VAR]}" in \
        rendered.splitlines()
    assert envfile.missing_overrides(rendered, FIXTURE_BRANCH) == []


def test_the_manifest_requires_the_marker_and_calls_it_fatal():
    """A branch whose forge is not marked has lost a whole layer of spec 5.4,
    silently. The manifest is where that judgement is recorded, so it is
    asserted rather than left to the YAML being read by nobody."""
    entries = {req.name: req for req in envfile.load_manifest()}

    assert crosswire.APP_NAME_VAR in entries, (
        f"branch-env.yaml does not list {crosswire.APP_NAME_VAR}, so a branch "
        "inherits production's forge name and renders as production"
    )
    entry = entries[crosswire.APP_NAME_VAR]
    assert entry.fatal
    assert entry.derive == "branch_app_name"
    assert entry.why.strip(), "the entry records no reason, so it will be deleted"
