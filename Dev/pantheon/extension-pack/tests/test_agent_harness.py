#!/usr/bin/env python3
"""The agent harness: model routing, the capability envelope, the audit."""

import base64
import os

from _fakes import FakeCtx, run_tests

import _agent
from _agent import AgentRun, active_model

ENV_KEYS = ("PANTHEON_AGENT_MODEL", "PANTHEON_LLM_ANTHROPIC_API_KEY",
            "ANTHROPIC_API_KEY")


def clean_env(fn):
    def wrapped():
        saved = {k: os.environ.pop(k, None) for k in ENV_KEYS}
        try:
            fn()
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
    wrapped.__name__ = fn.__name__
    return wrapped


@clean_env
def test_model_routing_override_key_upgrade_and_default():
    assert active_model("mock:v0") == "mock:v0"
    os.environ["PANTHEON_LLM_ANTHROPIC_API_KEY"] = "sk-test"
    assert active_model("mock:v0") == _agent.ANTHROPIC_DEFAULT
    os.environ["PANTHEON_AGENT_MODEL"] = "anthropic:claude-sonnet-5"
    assert active_model("mock:v0") == "anthropic:claude-sonnet-5"


def test_the_envelope_refuses_ungrated_resources_and_verbs():
    run = AgentRun(FakeCtx(), [{"resource": "blob_store", "verbs": ["get"]}])
    try:
        run.call("financial_ledger", "query", sql="select 1")
        raise AssertionError("expected PermissionError")
    except PermissionError:
        pass
    try:
        run.call("blob_store", "put", key="x", b64="")
        raise AssertionError("expected PermissionError")
    except PermissionError:
        pass
    assert run.audit == []  # refused calls never reach the audit


def test_calls_are_audited_and_row_envelopes_unwrap():
    ctx = FakeCtx(objects={"ingest/catalog.json": b"[]"})
    run = AgentRun(ctx, [{"resource": "blob_store", "verbs": ["get"]}])
    out = run.call("blob_store", "get", key="ingest/catalog.json")
    assert out["b64"] == base64.b64encode(b"[]").decode("ascii")
    assert run.audit == [{"resource": "blob_store", "verb": "get",
                          "detail": "ingest/catalog.json"}]


def test_http_bodies_reach_the_model_as_text_not_base64():
    ctx = FakeCtx(http={("worldbank", "/v2/x"): (200, "application/json",
                                                 b'{"value": 2.95}')})
    run = AgentRun(ctx, [{"resource": "worldbank", "verbs": ["request"]}])
    out = run.call("worldbank", "request", method="GET", path="/v2/x")
    assert out["body_text"] == '{"value": 2.95}'
    assert "body_b64" not in out


def test_run_agent_mock_path_stamps_model_and_audit():
    ctx = FakeCtx()
    spec = {"model": "mock:test", "instructions": "",
            "tools": [{"resource": "blob_store", "verbs": ["get"]}],
            "output_schema": {"required": ["answer"]}}
    saved = {k: os.environ.pop(k, None) for k in ENV_KEYS}
    try:
        result = _agent.run_agent(ctx, spec, "q", lambda run, p: {"answer": "a"})
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v
    assert result["answer"] == "a"
    assert result["model"] == "mock:test"
    assert result["audit"] == []


if __name__ == "__main__":
    run_tests(globals())
