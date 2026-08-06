"""The stdio MCP facade (Task 11): bytes on a pipe, and nothing else.

Decision D-B: the transport is hand-written, so it is pinned against a
RECORDED TRANSCRIPT of the bytes this server emits rather than against a
library's behaviour. No network, no SDK, no version drift -- a test writes
bytes into a `BytesIO`, `serve` reads them, and the bytes that come back out
are compared whole.

Trap shapes this file was written against, each already paid for once by this
project:

* **non-discriminating evidence** -- Task 10's M21 survived because its
  recorded transcript was one the mutant could also have produced. So the
  transcript here is compared BYTE FOR BYTE including `protocolVersion` and
  `serverInfo`, the tool list is checked against a set spelled out
  independently of `mcp.TOOLS`, and the "same function as the CLI" test
  patches a `branch` function and requires BOTH surfaces to observe the patch
  rather than comparing two things that merely look alike.
* **sequential-guard `raises`** -- the refusals here come from several
  distinct conditions, so every one asserts on the MESSAGE and on the absence
  of the other condition's wording, and each such test ends with a CONTROL
  that passes, without which a server that refused everything would satisfy
  all of them.
* **code-path vacuity** -- Task 9's first mutation run caught 6 of 10 because
  two tests never executed the branch of the `if` they asserted about. Every
  test here that asserts about a response first asserts a response was
  produced at all, and every test that asserts about a subprocess argv first
  asserts at least one command was issued.
* **vacuous pass** -- no assertion over a set without asserting the set is
  non-empty, and the fixture asserts its own non-degeneracy.
* **self-blinding artefact** -- the secret check delegates to the ONE
  implementation (`access_doc._assert_no_secret_leaked`, driven by
  `branch-env.yaml`'s `secret:` flag, which refuses an empty set). A test
  patches that function and asserts this module actually calls it, so a second
  private scan added here would be caught.
"""

import io
import json
from pathlib import Path

import pytest

from aurora_cli import access_doc, branch, crosswire, envfile, guards, identity, mcp
from aurora_cli import __main__ as cli

# ---------------------------------------------------------------------------
# doubles
# ---------------------------------------------------------------------------

PRODUCTION_DOMAIN = "prod-host.example.invalid"
PRODUCTION_PROJECT = "prod-project"

#: The branch `.env`'s auth key. Fake, obviously, but shaped like the real
#: thing so a substring check over the wire is testing what it claims to.
AUTHKEY = "tskey-auth-kFAKEfake0000000000"

#: A container name Compose would produce that no concatenation of project,
#: service and `-1` produces (Task 10's M21 lesson, carried forward).
SURPRISING = "br-demo-forgejo-2"

ROWS = (
    access_doc.ContainerRow("caddy", "br-demo-caddy-1", "running", "Up 3m"),
    access_doc.ContainerRow("forgejo", SURPRISING, "running", "Up 3m", "healthy"),
)

#: Spelled out here rather than read from `mcp.TOOLS`. A checker that
#: enumerates the constant it validates is self-blinding -- Tasks 5 and 6 both
#: hit it -- and `tools/list` losing a tool is exactly the mutation this set
#: exists to catch.
EXPECTED_TOOLS = {
    "branch_up", "branch_down", "branch_list", "branch_access", "rebuild",
}


class FakeRunner(branch.CommandRunner):
    """Canned stdout per command, and a full recording. No subprocess."""

    def __init__(self, replies=None):
        super().__init__()
        self.replies = list(replies or [])

    def _execute(self, argv, *, cwd, env, input, stdin, timeout):
        for match, stdout in self.replies:
            if all(token in argv for token in match):
                return branch.CommandResult(argv, 0, stdout, "")
        return branch.CommandResult(argv, 0, "", "")


class ExplodingRunner(branch.CommandRunner):
    """Any command at all is a failure. Not a recorder -- a mine."""

    def run(self, argv, **kwargs):  # pragma: no cover - must never run
        raise AssertionError(f"a guard let a command through: {list(argv)!r}")


def ps_reply(rows, project="br-demo"):
    lines = "".join(
        json.dumps({
            "Service": r.service, "Name": r.name, "State": r.state,
            "Status": r.status, "Health": r.health,
        }) + "\n"
        for r in rows
    )
    return ((project, "ps"), lines)


def _daemon(projects, rows_by_project=None):
    """A runner double whose `ps`/`inspect` answers describe a live daemon."""
    replies = [(("ps", "-aq"), "".join(f"cid-{p}\n" for p in projects))]
    for project in projects:
        replies.append(((f"cid-{project}",), f"{project}\n"))
        replies.append(ps_reply((rows_by_project or {}).get(project, ROWS), project))
    return FakeRunner(replies)


# ---------------------------------------------------------------------------
# the fabricated production
# ---------------------------------------------------------------------------


@pytest.fixture
def fabricated(tmp_path, monkeypatch):
    """A production checkout, a branch worktree, and nothing real anywhere.

    Production's `.env` and the branch's `.env` are DIFFERENT files carrying
    DIFFERENT domains, deliberately (Task 7's fixture lesson): with one shared
    file, code that read the branch's own `.env` instead of production's would
    be indistinguishable from correct code.
    """
    root = tmp_path / "production"
    (root / ".worktrees" / "demo").mkdir(parents=True)
    (root / ".env").write_text(f"DOMAIN_NAME={PRODUCTION_DOMAIN}\n", encoding="utf-8")
    monkeypatch.setattr(identity, "production_root", lambda: root)
    monkeypatch.setattr(identity, "production_project", lambda: PRODUCTION_PROJECT)

    worktree = root / ".worktrees" / "demo"
    (worktree / ".env").write_text(
        "COMPOSE_PROJECT_NAME=br-demo\n"
        "COMPOSE_PROFILES=agent-testuser\n"
        f"TS_AUTHKEY={AUTHKEY}\n",
        encoding="utf-8",
    )
    (worktree / "compose.yml").write_text("services: {}\n", encoding="utf-8")

    paths = identity.branch_paths("demo")
    # Non-degeneracy, asserted rather than assumed.
    assert paths.domain != PRODUCTION_DOMAIN
    assert identity.production_domain() == PRODUCTION_DOMAIN
    assert paths.env_file.read_text(encoding="utf-8").count(AUTHKEY) == 1
    return paths


def make_result(paths, **kwargs):
    result = branch.BranchResult(requested_name="demo", paths=paths)
    result.devs = kwargs.pop("devs", ("testuser",))
    result.hook = kwargs.pop("hook", crosswire.HookInstall(
        path=paths.worktree / "hooks" / "pre-push",
        worktree=paths.worktree,
        hooks_dir=identity.production_root() / ".git" / "hooks",
        executable=True, armed=False,
        activation_command="git -C <production> config core.hooksPath hooks",
    ))
    for key, value in kwargs.items():
        setattr(result, key, value)
    return result


# ---------------------------------------------------------------------------
# the pipe
# ---------------------------------------------------------------------------


def pipe(*lines: str) -> bytes:
    """Exactly what a client writes: UTF-8, newline-delimited."""
    return "".join(line + "\n" for line in lines).encode("utf-8")


def serve_bytes(payload: bytes) -> bytes:
    """`serve` over two byte streams. This IS the transport."""
    out = io.BytesIO()
    assert mcp.serve(io.BytesIO(payload), out) == 0
    return out.getvalue()


def frames(payload: bytes) -> list[dict]:
    raw = serve_bytes(payload)
    if not raw:
        return []
    return [json.loads(line) for line in raw.decode("utf-8").splitlines()]


def request(rpc_id, method, params=None) -> str:
    body = {"jsonrpc": "2.0", "id": rpc_id, "method": method}
    if params is not None:
        body["params"] = params
    return json.dumps(body)


def call(name, arguments=None, rpc_id=1) -> str:
    return request(rpc_id, "tools/call", {"name": name, "arguments": arguments or {}})


# ---------------------------------------------------------------------------
# the recorded transcript
# ---------------------------------------------------------------------------
#
# Byte for byte. A mutant that drops `protocolVersion`, renames `serverInfo`,
# stops declaring the `tools` capability or reorders the keys produces
# different bytes and fails here -- which is the property Task 10's M21
# established a transcript must have to be evidence at all.

INITIALIZE_REQUEST = (
    '{"jsonrpc":"2.0","id":1,"method":"initialize","params":'
    '{"protocolVersion":"2025-06-18","capabilities":{},'
    '"clientInfo":{"name":"probe","version":"0"}}}'
)

EXPECTED_INITIALIZE_RESPONSE = (
    '{"id":1,"jsonrpc":"2.0","result":{"capabilities":{"tools":'
    '{"listChanged":false}},"instructions":' + json.dumps(mcp.INSTRUCTIONS)
    + ',"protocolVersion":"2025-06-18","serverInfo":{"name":"aurora-branch",'
    '"version":"' + mcp.SERVER_VERSION + '"}}}\n'
).encode("utf-8")


def test_initialize_handshake():
    """The recorded transcript, compared whole."""
    raw = serve_bytes(pipe(INITIALIZE_REQUEST))
    assert raw == EXPECTED_INITIALIZE_RESPONSE, raw.decode("utf-8")

    # And the properties that transcript is a transcript OF, asserted
    # separately so a future re-record cannot quietly drop one.
    body = json.loads(raw.decode("utf-8"))["result"]
    assert body["protocolVersion"] in mcp.SUPPORTED_PROTOCOL_VERSIONS
    assert "tools" in body["capabilities"], (
        "a server that does not declare the tools capability will never be "
        "asked for tools/list"
    )
    assert body["serverInfo"]["name"] and body["serverInfo"]["version"]


def test_initialize_negotiates_rather_than_insisting():
    """Echo a version we speak; fall back to ours for one we do not.

    Both directions, because a server that always echoed would claim to speak
    anything, and one that never echoed would be wrong the day a client is
    upgraded.
    """
    older = mcp.SUPPORTED_PROTOCOL_VERSIONS[-1]
    assert older != mcp.PROTOCOL_VERSION, (
        "the supported set has collapsed to one entry, so this test asserts "
        "nothing about negotiation"
    )
    spoken = frames(pipe(
        request(1, "initialize", {"protocolVersion": older}),
        request(2, "initialize", {"protocolVersion": "1999-01-01"}),
        request(3, "initialize", {}),
    ))
    assert len(spoken) == 3
    assert spoken[0]["result"]["protocolVersion"] == older
    assert spoken[1]["result"]["protocolVersion"] == mcp.PROTOCOL_VERSION
    assert spoken[2]["result"]["protocolVersion"] == mcp.PROTOCOL_VERSION


def test_tools_list_declares_every_tool():
    responses = frames(pipe(request(7, "tools/list")))
    assert len(responses) == 1
    tools = responses[0]["result"]["tools"]
    assert tools, "tools/list returned an empty list; every assertion below would be vacuous"
    names = {tool["name"] for tool in tools}
    assert names == EXPECTED_TOOLS, names
    for tool in tools:
        assert tool["description"].strip(), tool["name"]
        schema = tool["inputSchema"]
        assert schema["type"] == "object", tool["name"]
        assert "properties" in schema, tool["name"]


def test_the_initialized_notification_gets_no_response_at_all():
    """A notification has no `id` and JSON-RPC forbids answering it.

    Answering would hand the client an unpaired frame it cannot match to any
    request, which is a hang in a client that reads one response per request.
    """
    raw = serve_bytes(pipe(
        '{"jsonrpc":"2.0","method":"notifications/initialized"}',
        '{"jsonrpc":"2.0","method":"notifications/somethingUnknown"}',
        request(1, "tools/list"),
    ))
    lines = raw.decode("utf-8").splitlines()
    assert len(lines) == 1, f"a notification was answered: {lines}"
    assert json.loads(lines[0])["id"] == 1


def test_malformed_json_gets_a_parse_error_not_a_traceback():
    """-32700, and the server is still there for the next message."""
    raw = serve_bytes(pipe(
        "{not json at all",
        "",
        request(2, "tools/list"),
    ))
    responses = [json.loads(line) for line in raw.decode("utf-8").splitlines()]
    assert len(responses) == 2, responses
    assert responses[0]["error"]["code"] == mcp.PARSE_ERROR
    assert responses[0]["id"] is None
    assert "error" not in responses[1] and responses[1]["id"] == 2, (
        "the server did not survive a malformed line; an agent cannot see "
        "stderr and would simply hang"
    )


def test_unknown_method_returns_method_not_found():
    responses = frames(pipe(request(3, "resources/list")))
    assert len(responses) == 1
    error = responses[0]["error"]
    assert error["code"] == mcp.METHOD_NOT_FOUND
    assert "resources/list" in error["message"]
    # Discriminating: a server that answered -32601 to EVERYTHING would pass
    # the line above.
    assert "error" not in frames(pipe(request(4, "tools/list")))[0]


def test_a_frame_that_is_not_an_object_is_an_invalid_request():
    responses = frames(pipe("[1, 2, 3]", '"a bare string"', "17"))
    assert len(responses) == 3
    assert {r["error"]["code"] for r in responses} == {mcp.INVALID_REQUEST}


def test_a_request_with_no_method_is_an_invalid_request():
    responses = frames(pipe('{"jsonrpc":"2.0","id":5}'))
    assert len(responses) == 1
    assert responses[0]["error"]["code"] == mcp.INVALID_REQUEST


def test_every_response_is_exactly_one_line_of_utf8(fabricated, monkeypatch):
    """The framing IS the transport: one frame per line, or nothing works.

    Fed a document full of newlines on purpose -- `BRANCH-ACCESS.md` is
    hundreds of lines and is returned verbatim, so "JSON escapes the newlines"
    is a property this transport depends on rather than a detail.
    """
    monkeypatch.setattr(branch, "CommandRunner", lambda: _daemon(["br-demo"]))
    monkeypatch.setattr(branch, "branch_access",
                        lambda name, **kw: "line one\nline two\r\nline three\n")
    raw = serve_bytes(pipe(
        INITIALIZE_REQUEST,
        request(2, "tools/list"),
        call("branch_access", {"name": "demo"}, rpc_id=3),
    ))
    lines = raw.split(b"\n")
    assert lines[-1] == b"", "the stream is not newline-terminated"
    frames_out = lines[:-1]
    assert len(frames_out) == 3, frames_out
    for line in frames_out:
        decoded = line.decode("utf-8")          # raises on invalid UTF-8
        assert json.loads(decoded)["jsonrpc"] == "2.0"
    assert "line two" in json.loads(
        frames_out[2].decode("utf-8"))["result"]["content"][0]["text"]


# ---------------------------------------------------------------------------
# one implementation, two surfaces
# ---------------------------------------------------------------------------


def test_tools_call_invokes_the_same_function_as_the_cli(
    fabricated, monkeypatch, capsys
):
    """Not "they look alike" -- one patch, observed through both surfaces.

    Chunk 2 shipped a test that reimplemented the comprehension it claimed to
    pin and stayed green under the mutation it existed to catch. So this
    replaces `branch.branch_up` with a recorder and requires the CLI path AND
    the MCP path to land in it. A `tools/call` that reimplemented the work
    would record nothing.
    """
    seen: list[tuple] = []
    result = make_result(fabricated)

    def recorder(name, **kwargs):
        seen.append((name, kwargs.get("devs")))
        return result

    monkeypatch.setattr(branch, "branch_up", recorder)
    monkeypatch.setattr(branch, "CommandRunner", lambda: _daemon(["br-demo"]))

    assert cli.main(["branch", "up", "demo", "--devs", "testuser"]) == 0
    from_cli = capsys.readouterr().out

    responses = frames(pipe(call(
        "branch_up", {"name": "demo", "devs": "testuser"}, rpc_id=11,
    )))
    assert len(responses) == 1, responses
    payload = responses[0]["result"]

    assert seen == [("demo", "testuser"), ("demo", "testuser")], (
        f"both surfaces must reach the SAME branch.branch_up; observed {seen}"
    )
    assert payload["isError"] is False
    text = payload["content"][0]["text"]
    assert text == from_cli, (
        "the MCP result and the CLI's stdout are the same product (spec 7.4) "
        "and they disagree"
    )
    assert text == fabricated.access_doc.read_text(encoding="utf-8")


@pytest.mark.parametrize("tool,function,arguments", [
    ("branch_down", "branch_down", {"name": "demo"}),
    ("branch_list", "branch_ls", {}),
    ("branch_access", "branch_access", {"name": "demo"}),
])
def test_every_other_tool_also_calls_the_function_the_cli_calls(
    fabricated, monkeypatch, tool, function, arguments
):
    """Deletion pressure on the seam, for the three tools above.

    A tool that grew its own docker invocation would not observe this patch.
    """
    seen: list[str] = []
    original = getattr(branch, function)

    def recorder(*args, **kwargs):
        seen.append(function)
        return original(*args, **kwargs)

    monkeypatch.setattr(branch, function, recorder)
    monkeypatch.setattr(branch, "CommandRunner", lambda: _daemon(["br-demo"]))

    responses = frames(pipe(call(tool, arguments, rpc_id=21)))
    assert len(responses) == 1, responses
    assert seen == [function], (
        f"{tool} did not reach branch.{function}; observed {seen}"
    )
    assert responses[0]["result"]["isError"] is False, responses


def test_the_cli_wires_mcp_to_the_server():
    """Deletion pressure on the wiring, and on the stub that used to be here.

    `aurora mcp` printed "not implemented yet" until this task. A parser that
    still routed to a stub -- or to nothing -- would leave every other test in
    this file passing while the actual command did nothing.
    """
    parser = cli.build_parser()
    assert parser.parse_args(["mcp"]).func is cli._cmd_mcp
    assert not hasattr(cli, "_cmd_not_yet_implemented"), (
        "the not-implemented stub is still reachable"
    )


def test_the_mcp_subcommand_runs_the_server(monkeypatch):
    """The adapter is thin, and it is connected."""
    called: list[str] = []
    monkeypatch.setattr(mcp, "serve", lambda *a, **kw: called.append("served") or 0)
    assert cli.main(["mcp"]) == 0
    assert called == ["served"]


# ---------------------------------------------------------------------------
# a tool that fails is a result, not a corpse
# ---------------------------------------------------------------------------


def test_tool_error_is_returned_as_an_error_result_not_a_crash(
    fabricated, monkeypatch
):
    """MCP's error model, and the reason it matters here.

    A JSON-RPC error means "this frame was wrong". A tool result with
    `isError` means "the frame was fine and the operation failed" -- and for
    `branch_up` that text carries the `aurora branch down` command for the
    half-built branch now sitting on the host. Losing it to a traceback loses
    the only instruction that matters.
    """
    def boom(name, **kwargs):
        raise branch.BranchUpFailed(
            "branch 'demo' was not completed: the sidecar never reached "
            "Running. Remove it with: aurora branch down demo",
            teardown_command="aurora branch down demo",
        )

    monkeypatch.setattr(branch, "branch_up", boom)
    monkeypatch.setattr(branch, "CommandRunner", lambda: _daemon([]))

    responses = frames(pipe(
        call("branch_up", {"name": "demo"}, rpc_id=31),
        request(32, "tools/list"),
    ))
    assert len(responses) == 2, responses
    first = responses[0]
    assert "error" not in first, (
        "a failing TOOL became a JSON-RPC error; an agent reads that as "
        "'your frame was malformed' and re-reads the schema instead of the "
        "teardown command"
    )
    assert first["result"]["isError"] is True
    assert "aurora branch down demo" in first["result"]["content"][0]["text"]
    assert "Traceback" not in first["result"]["content"][0]["text"]
    assert responses[1]["result"]["tools"], "the server did not survive"


def test_an_unknown_tool_is_a_frame_error_and_not_a_tool_result():
    """The other side of the same line, so neither can swallow the other."""
    responses = frames(pipe(
        call("branch_delete_everything", {}, rpc_id=41),
        call("branch_list", None, rpc_id=42),
    ))
    assert len(responses) == 2
    assert responses[0]["error"]["code"] == mcp.INVALID_PARAMS
    assert "branch_delete_everything" in responses[0]["error"]["message"]
    # Control: a real tool with the same shape of frame is NOT an error, so
    # this is not passing against a server that errors on every tools/call.
    assert "error" not in responses[1] or responses[1].get("result")


@pytest.mark.parametrize("arguments,why", [
    ({}, "no name at all"),
    ({"name": ""}, "an empty name"),
    ({"name": "   "}, "whitespace"),
    ({"name": 17}, "not a string"),
])
def test_a_lifecycle_tool_without_a_usable_name_is_refused(arguments, why):
    responses = frames(pipe(call("branch_up", arguments, rpc_id=51)))
    assert len(responses) == 1, why
    assert responses[0]["error"]["code"] == mcp.INVALID_PARAMS, why
    assert "name" in responses[0]["error"]["message"], why


def test_a_malformed_argument_type_is_refused_before_anything_runs(
    fabricated, monkeypatch
):
    monkeypatch.setattr(branch, "CommandRunner", ExplodingRunner)
    monkeypatch.setattr(branch, "branch_up", lambda *a, **kw: pytest.fail(
        "branch_up ran with a malformed argument"))
    responses = frames(pipe(
        call("branch_up", {"name": "demo", "without": [1, 2]}, rpc_id=61),
        call("branch_up", {"name": "demo", "force": "yes"}, rpc_id=62),
    ))
    assert len(responses) == 2
    assert responses[0]["error"]["code"] == mcp.INVALID_PARAMS
    assert "without" in responses[0]["error"]["message"]
    assert responses[1]["error"]["code"] == mcp.INVALID_PARAMS
    assert "force" in responses[1]["error"]["message"]


# ---------------------------------------------------------------------------
# the guards: an MCP caller is not trusted
# ---------------------------------------------------------------------------


def _paths_with(paths, **kwargs):
    from dataclasses import replace
    return replace(paths, **kwargs)


def test_the_lifecycle_tools_refuse_a_project_outside_the_branch_namespace(
    fabricated, monkeypatch
):
    """The incident, with a pipe in front of it.

    A tool that took a name off the wire and handed the resulting project to
    Compose is `docker compose -p <production> down -v` again. Asserted on the
    MESSAGE and on the ABSENCE of the path guard's wording, because
    `GuardViolation` comes from several conditions and a bare type assertion
    would pass against a mutant whose first guard was deleted.
    """
    monkeypatch.setattr(branch, "CommandRunner", ExplodingRunner)
    monkeypatch.setattr(
        identity, "branch_paths",
        lambda name: _paths_with(fabricated, project=PRODUCTION_PROJECT),
    )
    for tool in ("branch_up", "branch_down"):
        responses = frames(pipe(call(tool, {"name": "demo"}, rpc_id=71)))
        assert len(responses) == 1, tool
        message = responses[0]["result"]["content"][0]["text"]
        assert responses[0]["result"]["isError"] is True, tool
        assert "not in the 'br-' namespace" in message, (tool, message)
        assert "not inside" not in message, (
            f"{tool}: the PATH guard's message appeared; the project guard "
            "did not fire first and this test would pass against a mutant "
            "that deleted it"
        )


def test_the_lifecycle_tools_refuse_a_worktree_outside_the_branch_directory(
    fabricated, monkeypatch, tmp_path
):
    monkeypatch.setattr(branch, "CommandRunner", ExplodingRunner)
    monkeypatch.setattr(
        identity, "branch_paths",
        lambda name: _paths_with(fabricated, worktree=tmp_path / "elsewhere"),
    )
    for tool in ("branch_up", "branch_down"):
        responses = frames(pipe(call(tool, {"name": "demo"}, rpc_id=72)))
        assert len(responses) == 1, tool
        message = responses[0]["result"]["content"][0]["text"]
        assert responses[0]["result"]["isError"] is True, tool
        assert "not inside" in message, (tool, message)
        assert "namespace" not in message, (tool, message)


def test_a_refused_tool_issues_no_command_at_all(fabricated, monkeypatch):
    """"It refused" and "it refused before doing anything" are different claims.

    `ExplodingRunner` is a mine rather than a recorder, so a single subprocess
    on the refusal path fails this outright.
    """
    monkeypatch.setattr(branch, "CommandRunner", ExplodingRunner)
    monkeypatch.setattr(
        identity, "branch_paths",
        lambda name: _paths_with(fabricated, project=PRODUCTION_PROJECT),
    )
    responses = frames(pipe(call("branch_down", {"name": "demo"}, rpc_id=73)))
    assert responses[0]["result"]["isError"] is True


def test_the_read_only_tools_are_a_control_and_still_work(fabricated, monkeypatch):
    """Without this, a server that refused every tool would satisfy the three
    tests above."""
    monkeypatch.setattr(branch, "CommandRunner", lambda: _daemon(["br-demo"]))
    responses = frames(pipe(
        call("branch_list", {}, rpc_id=74),
        call("branch_access", {"name": "demo"}, rpc_id=75),
    ))
    assert len(responses) == 2
    for response in responses:
        assert response["result"]["isError"] is False, response
        assert response["result"]["content"][0]["text"].strip()


# ---------------------------------------------------------------------------
# the documents, refreshed by both surfaces
# ---------------------------------------------------------------------------


def test_branch_up_over_mcp_refreshes_both_documents(fabricated, monkeypatch):
    """Task 10 open item 2: without this, a branch minted over MCP has no
    access document and `.worktrees/INDEX.md` goes stale.

    `refresh_branch_docs` lives at the surface layer, not inside `branch_up`,
    so nothing else in the package proves the MCP path calls it.
    """
    monkeypatch.setattr(branch, "branch_up",
                        lambda name, **kw: make_result(fabricated))
    monkeypatch.setattr(branch, "CommandRunner", lambda: _daemon(["br-demo"]))
    index = fabricated.worktree.parent / access_doc.INDEX_NAME
    assert not index.exists() and not fabricated.access_doc.exists()

    responses = frames(pipe(call("branch_up", {"name": "demo"}, rpc_id=81)))
    assert responses[0]["result"]["isError"] is False, responses

    assert fabricated.access_doc.is_file(), "no BRANCH-ACCESS.md was written"
    assert index.is_file(), "the branch index was not regenerated"
    assert "br-demo" in index.read_text(encoding="utf-8")


def test_branch_down_over_mcp_regenerates_the_index(fabricated, monkeypatch):
    monkeypatch.setattr(
        branch, "branch_down",
        lambda name, **kw: branch.DownResult(
            project="br-demo", worktree=fabricated.worktree,
            containers_removed=("cid",), worktree_removed=True,
        ),
    )
    monkeypatch.setattr(branch, "CommandRunner", lambda: _daemon([]))
    index = fabricated.worktree.parent / access_doc.INDEX_NAME
    index.write_text("# stale\n\n| ghost | `br-ghost` |\n", encoding="utf-8")

    responses = frames(pipe(call("branch_down", {"name": "demo"}, rpc_id=82)))
    assert responses[0]["result"]["isError"] is False, responses
    text = index.read_text(encoding="utf-8")
    assert "ghost" not in text, (
        "the index was left stale, or read from the file rather than derived "
        "from the daemon"
    )
    assert "No branch stack is running." in text
    assert "br-demo" in responses[0]["result"]["content"][0]["text"]


def test_the_teardown_tool_does_not_resurrect_the_worktree(
    fabricated, monkeypatch
):
    """Plan/ledger defect: `refresh_branch_docs` is WRONG after a teardown.

    Task 10's open item 2 says both MCP lifecycle tools must call
    `refresh_branch_docs`. For `branch_down` that is not possible: the
    worktree is gone by then, `write_access_doc` goes through
    `_write_document`, and `_write_document` creates parents -- so the call
    would re-create the directory the teardown just removed, leaving residue
    inside production's checkout on every teardown. The tool therefore does
    exactly what `__main__._cmd_branch_down` does: `write_index` and nothing
    else. This pins that.
    """
    worktree = fabricated.worktree

    def teardown(name, **kwargs):
        for child in sorted(worktree.rglob("*"), reverse=True):
            child.unlink() if child.is_file() else child.rmdir()
        worktree.rmdir()
        return branch.DownResult(project="br-demo", worktree=worktree,
                                 worktree_removed=True)

    monkeypatch.setattr(branch, "branch_down", teardown)
    monkeypatch.setattr(branch, "CommandRunner", lambda: _daemon([]))

    responses = frames(pipe(call("branch_down", {"name": "demo"}, rpc_id=83)))
    assert responses[0]["result"]["isError"] is False, responses
    assert not worktree.exists(), (
        f"{worktree} came back after a teardown: the teardown tool wrote a "
        "document into the worktree it had just removed"
    )
    assert (worktree.parent / access_doc.INDEX_NAME).is_file()


def test_both_surfaces_render_a_teardown_with_the_same_words(
    fabricated, monkeypatch, capsys
):
    """One event, one wording -- including the RESIDUE notes.

    `branch_down` reports residue in `notes` rather than raising, so a surface
    that dropped the notes would tell its caller a teardown was clean while
    containers were still running.
    """
    result = branch.DownResult(
        project="br-demo", worktree=fabricated.worktree,
        containers_removed=("a", "b"), volumes_removed=("v",),
        notes=("RESIDUE: 1 containers still carry br-demo: ['zz']",),
    )
    monkeypatch.setattr(branch, "branch_down", lambda name, **kw: result)
    monkeypatch.setattr(branch, "CommandRunner", lambda: _daemon([]))

    assert cli.main(["branch", "down", "demo"]) == 0
    from_cli = capsys.readouterr().out

    responses = frames(pipe(call("branch_down", {"name": "demo"}, rpc_id=84)))
    from_mcp = responses[0]["result"]["content"][0]["text"]
    assert "RESIDUE" in from_cli and "RESIDUE" in from_mcp
    assert from_cli == from_mcp, (from_cli, from_mcp)


# ---------------------------------------------------------------------------
# no secret crosses the wire
# ---------------------------------------------------------------------------


def test_a_real_tool_call_response_never_carries_the_branchs_auth_key(
    fabricated, monkeypatch
):
    """The property, stated over the BYTES rather than over a structure.

    The branch `.env` in the fixture holds a real-shaped key, asserted present
    there, so "the key is not in the response" is a claim about a value that
    exists rather than about an empty string.
    """
    monkeypatch.setattr(branch, "CommandRunner", lambda: _daemon(["br-demo"]))
    raw = serve_bytes(pipe(
        call("branch_access", {"name": "demo"}, rpc_id=91),
        call("branch_list", {}, rpc_id=92),
    ))
    assert AUTHKEY in fabricated.env_file.read_text(encoding="utf-8")
    assert AUTHKEY.encode("utf-8") not in raw
    assert b"TS_AUTHKEY" not in raw
    responses = [json.loads(line) for line in raw.decode("utf-8").splitlines()]
    assert len(responses) == 2
    for response in responses:
        assert response["result"]["isError"] is False, response


def test_the_wire_refuses_a_result_carrying_a_secrets_value(
    fabricated, monkeypatch
):
    """A key printed under some other label, which is the leak that matters.

    Nothing in this package puts it there today; that is precisely the
    property that has to keep being true, and the only way to know it is
    checked is to put one there.
    """
    monkeypatch.setattr(branch, "CommandRunner", lambda: _daemon(["br-demo"]))
    monkeypatch.setattr(
        branch, "branch_access",
        lambda name, **kw: f"# demo\n\n- node registration token: {AUTHKEY}\n",
    )
    raw = serve_bytes(pipe(call("branch_access", {"name": "demo"}, rpc_id=93)))
    assert AUTHKEY.encode("utf-8") not in raw, raw
    assert b"marked secret" in raw, raw.decode("utf-8")


def test_the_wire_refuses_a_result_carrying_a_secrets_name(
    fabricated, monkeypatch
):
    monkeypatch.setattr(branch, "CommandRunner", lambda: _daemon(["br-demo"]))
    monkeypatch.setattr(
        branch, "branch_access",
        lambda name, **kw: "# demo\n\n- set TS_AUTHKEY before starting\n",
    )
    raw = serve_bytes(pipe(call("branch_access", {"name": "demo"}, rpc_id=94)))
    assert b"TS_AUTHKEY" not in raw, raw
    assert b"marked secret" in raw, raw.decode("utf-8")


def test_an_error_frame_carrying_a_secret_is_replaced_rather_than_emitted():
    """The second leg, over frames no tool composed.

    `_tool_payload` checks tool output. This checks EVERY outgoing line,
    including error frames built from exception text -- the strings no test
    has seen. Name leg only: this layer holds no branch and so has no `.env`
    to read values from, which is stated here so the gap is recorded rather
    than assumed away.
    """
    out = io.BytesIO()
    line = mcp._emit(out, mcp._error(9, mcp.INTERNAL_ERROR, "TS_AUTHKEY was unset"))
    assert b"TS_AUTHKEY" not in line, line
    assert b"marked secret" in line
    assert out.getvalue() == line
    assert json.loads(line.decode("utf-8"))["id"] == 9
    # Control: an innocent frame is emitted unchanged, so this is not passing
    # against an `_emit` that replaced everything.
    innocent = mcp._emit(io.BytesIO(), mcp._error(9, mcp.INTERNAL_ERROR, "boom"))
    assert b"boom" in innocent


def test_the_wire_check_delegates_to_the_one_implementation(fabricated, monkeypatch):
    """Self-blinding pressure: this module must not grow its own scanner.

    `access_doc._assert_no_secret_leaked` is driven by `branch-env.yaml`'s
    `secret:` flag and refuses an empty set. A private re-implementation here
    would drift from it the first time the manifest changed, and would not
    observe this patch.
    """
    seen: list[tuple[bool, object]] = []
    original = access_doc._assert_no_secret_leaked

    def recorder(text, env_file):
        seen.append((AUTHKEY in text, env_file))
        return original(text, env_file)

    monkeypatch.setattr(access_doc, "_assert_no_secret_leaked", recorder)
    monkeypatch.setattr(branch, "CommandRunner", lambda: _daemon(["br-demo"]))

    responses = frames(pipe(call("branch_access", {"name": "demo"}, rpc_id=95)))
    assert responses[0]["result"]["isError"] is False
    assert seen, "the outgoing payload was never shown to the leak check"
    # The VALUE leg needs the branch `.env`; at least one call must carry it,
    # or only the name leg ever ran and a key under another label crosses.
    assert any(env_file == fabricated.env_file for _leaked, env_file in seen), (
        f"the branch .env was never handed to the leak check: {seen}"
    )


def test_an_unreadable_manifest_stops_tool_results_and_not_the_handshake(
    fabricated, monkeypatch
):
    """The coupling `_emit`'s one degradation rests on, pinned from both sides.

    An `aurora-cli:local` container started with no repository mounted cannot
    read `branch-env.yaml`, so the leak check cannot run. `_emit` passes such
    a frame through -- which is sound ONLY because `_tool_payload` calls the
    same function and therefore lets no tool result exist in that state. Both
    halves are asserted here: if a future edit let a `tools/call` succeed with
    an unreadable manifest, that result would reach `_emit` unchecked, and
    this test is what goes red.
    """
    def unreadable(*args, **kwargs):
        raise envfile.ManifestError("No must-override manifest at /app/x.yaml")

    monkeypatch.setattr(envfile, "load_manifest", unreadable)
    monkeypatch.setattr(branch, "CommandRunner", lambda: _daemon(["br-demo"]))

    responses = frames(pipe(
        INITIALIZE_REQUEST,
        request(2, "tools/list"),
        call("branch_access", {"name": "demo"}, rpc_id=3),
    ))
    assert len(responses) == 3, responses
    assert responses[0]["result"]["protocolVersion"], (
        "the handshake broke, so a misconfigured container cannot tell its "
        "caller what is wrong"
    )
    assert {t["name"] for t in responses[1]["result"]["tools"]} == EXPECTED_TOOLS
    assert "result" not in responses[2], (
        "a tool produced a result while the leak check could not run; "
        "`_emit`'s degradation is now a hole"
    )
    assert responses[2]["error"]["code"] == mcp.INTERNAL_ERROR


def test_the_secret_set_is_the_manifest_flag_and_is_not_empty():
    """Independent pressure on the artefact the whole check hangs from."""
    names = access_doc.secret_variables()
    assert names, "an empty secret set makes every check above vacuous"
    assert "TS_AUTHKEY" in names, (
        "branch-env.yaml no longer marks the branch auth key `secret: true`, "
        "so nothing on this wire is being scrubbed"
    )


# ---------------------------------------------------------------------------
# the tool table itself
# ---------------------------------------------------------------------------


def test_every_declared_tool_has_a_handler_and_every_handler_is_declared():
    assert set(mcp.TOOLS_BY_NAME) == EXPECTED_TOOLS
    assert len(mcp.TOOLS) == len(EXPECTED_TOOLS), "a tool is declared twice"
    for tool in mcp.TOOLS:
        assert callable(tool.handler), tool.name
    handlers = {
        name: getattr(mcp, f"_tool_{name}", None) for name in EXPECTED_TOOLS
    }
    assert all(handlers.values()), handlers
    assert {tool.name: tool.handler for tool in mcp.TOOLS} == handlers


class _FakeCompleted:
    def __init__(self, returncode, stdout="", stderr=""):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr


def _rebuild_over_the_wire(monkeypatch, tmp_path, completed, arguments):
    """Call the `rebuild` tool through `serve`, and return its result frame.

    Through the wire rather than by calling the handler, because the thing
    worth pinning is that a non-zero exit becomes a RESULT and not a dead
    server -- and only the dispatch layer decides that.
    """
    issued = []

    def fake_run(argv, **kwargs):
        issued.append((list(argv), kwargs.get("cwd"), kwargs.get("env")))
        return completed

    monkeypatch.setattr(mcp.subprocess, "run", fake_run)
    monkeypatch.setattr(identity, "production_root", lambda: tmp_path)
    (tmp_path / envfile.ENV_FILE_NAME).write_text("DOMAIN_NAME=x\n")

    responses = frames(pipe(call("rebuild", arguments, rpc_id=71)))
    assert len(responses) == 1, responses
    assert issued, "no command was issued; every assertion below is vacuous"
    return responses[0]["result"], issued


def test_rebuild_check_reports_staleness_as_a_result_not_an_error(
    monkeypatch, tmp_path
):
    """Exit 1 from `--check` IS the answer, and an agent has to be able to
    read it. Returning `isError` would tell the agent the call was broken and
    that it should stop -- when in fact production is stale and it should
    rebuild."""
    result, issued = _rebuild_over_the_wire(
        monkeypatch, tmp_path,
        _FakeCompleted(1, "  STALE       fjell         aurora-fjell\n"),
        {"check": True},
    )
    assert result["isError"] is False
    text = result["content"][0]["text"]
    assert text.startswith("STALE"), text
    assert "aurora-fjell" in text, "the report itself was dropped"

    argv, cwd, _env = issued[0]
    assert argv == ["bash", mcp.REBUILD_SCRIPT, "--check"], argv
    assert cwd == tmp_path, (
        "the rebuild ran somewhere other than production's checkout"
    )


def test_rebuild_check_that_could_not_run_is_an_error_not_a_verdict(
    monkeypatch, tmp_path
):
    """`bash` exits 127 on a missing script -- the normal state of a checkout
    that has not merged this branch yet. Reporting that as STALE would be a
    confident wrong answer, which is the exact failure mode this whole tool
    exists to end."""
    result, _issued = _rebuild_over_the_wire(
        monkeypatch, tmp_path,
        _FakeCompleted(127, "", "bash: ops/rebuild.sh: No such file or directory"),
        {"check": True},
    )
    assert result["isError"] is True
    text = result["content"][0]["text"]
    assert "could not be run" in text, text
    assert "STALE" not in text, (
        "a script that never ran was reported as a staleness verdict"
    )


def test_rebuild_refuses_a_service_name_that_is_not_one(monkeypatch, tmp_path):
    """The refusal happens before anything is issued, on the wire path too."""
    monkeypatch.setattr(mcp.subprocess, "run", lambda *a, **k: pytest.fail(
        "a command was issued for a service name that should have been refused"
    ))
    monkeypatch.setattr(identity, "production_root", lambda: tmp_path)
    responses = frames(pipe(
        call("rebuild", {"services": ["--project-name"]}, rpc_id=72),
        call("rebuild", {"services": ["fjell; rm -rf /"]}, rpc_id=73),
    ))
    assert len(responses) == 2, responses
    assert {r["error"]["code"] for r in responses} == {mcp.INVALID_PARAMS}


def test_the_required_arguments_are_declared_in_the_schema():
    """A schema that did not mark `name` required would have an agent
    discovering the requirement by breaking something."""
    schemas = {tool.name: tool.input_schema for tool in mcp.TOOLS}
    assert schemas["branch_up"]["required"] == ["name"]
    assert schemas["branch_access"]["required"] == ["name"]
    # `branch_down` takes `all` INSTEAD of a name, so a blanket `required`
    # would forbid the shape it exists to offer.
    assert "required" not in schemas["branch_down"]
    assert "all" in schemas["branch_down"]["properties"]
    assert schemas["branch_list"]["properties"] == {}
    # `rebuild` takes neither -- omitting `services` means "every buildable
    # service", which is the shape an operator wants after a merge. A blanket
    # `required` would forbid the default case.
    assert "required" not in schemas["rebuild"]
    assert set(schemas["rebuild"]["properties"]) == {"services", "check"}


def test_the_rebuild_tool_strips_the_ambient_compose_variables(
    monkeypatch, tmp_path
):
    """The one command pointed at PRODUCTION on purpose was the one inheriting
    the environment.

    `branch.stripped_environ()` exists because an exported
    COMPOSE_PROJECT_NAME / COMPOSE_PROFILES / COMPOSE_FILE silently redirects
    a Compose command -- and `DOCKER_HOST`, added to that tuple by this same
    branch, redirects the DAEMON. With a podman session's DOCKER_HOST exported
    the tool reported every image NEVER-BUILT (they are not in podman's
    store), built them into the rootless store, brought a SECOND copy of
    production's stack up there, and returned a transcript saying it deployed,
    while production went on serving the stale images the tool exists to catch.

    `env=` is asserted as PRESENT and SCRUBBED, not merely present: `env=None`
    means "inherit", which is the defect.
    """
    for name in branch.STRIPPED_COMPOSE_VARS:
        monkeypatch.setenv(name, "poison")
    monkeypatch.setenv("PATH", "/usr/bin")

    _result, issued = _rebuild_over_the_wire(
        monkeypatch, tmp_path, _FakeCompleted(0, "fresh\n"), {"check": True},
    )
    _argv, _cwd, env = issued[0]
    assert env is not None, (
        "the rebuild inherited the ambient environment; an exported "
        "DOCKER_HOST would have built production's images into another daemon"
    )
    leaked = sorted(v for v in branch.STRIPPED_COMPOSE_VARS if v in env)
    assert leaked == [], leaked
    # ...and it is a real environment, not an empty dict that happens to pass.
    assert env.get("PATH") == "/usr/bin"
