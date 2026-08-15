"""Provider-generic agent harness for the extension pack's agent actions.

Mirrors the prototype's design commitments so these actions drop into the
real pantheon_llm layer with minimal reconciliation:

- The model is a string in the definition (`mock:v0`, `anthropic:<model>`),
  overridable via PANTHEON_AGENT_MODEL. `mock:` is deterministic and keyless.
- Final output is forced through a tool call, never native structured output
  (issues I4: NativeOutput suppressed tool-calling and produced fabrication).
- Resource tools expose typed, described argument slots — sql / key / method /
  path / body — the names the connectors actually read (issues I5).
- Model-correctable errors are fed back in-conversation as error tool results
  (implementation D1); the repair budget for a bad final result is capped.
- Every proxied call lands in an audit list carried on the output record —
  the run log's governance beat, visible in the UI.

The live path prefers the official anthropic SDK when importable and falls
back to the raw Messages API over urllib (this harness runs on a bare,
externally-managed host python where pip installs are unavailable).
"""

import base64
import json
import os
import urllib.request

ANTHROPIC_DEFAULT = "anthropic:claude-opus-5"
MAX_ITERATIONS = 10


def active_model(spec_model="mock:v0"):
    override = os.environ.get("PANTHEON_AGENT_MODEL")
    if override:
        return override
    if spec_model.startswith("mock:") and _api_key():
        return ANTHROPIC_DEFAULT  # a key in the env upgrades mock specs to live
    return spec_model


def _api_key():
    return os.environ.get("PANTHEON_LLM_ANTHROPIC_API_KEY") or os.environ.get(
        "ANTHROPIC_API_KEY"
    )


class AgentRun:
    """Binds an agent to the run's proxied resources and records the audit."""

    def __init__(self, ctx, tools):
        self.ctx = ctx
        self.allowed = {t["resource"]: t["verbs"] for t in tools}
        self.audit = []

    def call(self, resource, verb, **args):
        if resource not in self.allowed:
            raise PermissionError(f"resource '{resource}' not in this agent's envelope")
        if verb not in self.allowed[resource]:
            raise PermissionError(
                f"verb '{verb}' not granted on {resource}; allowed: {self.allowed[resource]}"
            )
        detail = args.get("sql") or args.get("key") or args.get("path") or ""
        result = getattr(self.ctx.resource(resource), verb)(**args)
        if isinstance(result, dict) and "rows" in result:
            result = result["rows"]  # unwrap the postgres connector envelope
        if isinstance(result, dict) and result.get("body_b64"):
            # HTTP bodies arrive base64-encoded; the model reads text.
            try:
                text = base64.b64decode(result["body_b64"]).decode("utf-8", "replace")
                result = {k: v for k, v in result.items() if k != "body_b64"}
                result["body_text"] = text[:8000]
            except Exception:
                pass
        summary = str(detail)[:200]
        if isinstance(result, list):
            summary += f" -> {len(result)} rows"
        self.audit.append({"resource": resource, "verb": verb, "detail": summary})
        return result


def run_agent(ctx, spec, prompt, mock_fn):
    """Execute an agent action: deterministic mock, or a live tool loop."""
    model = active_model(spec.get("model", "mock:v0"))
    run = AgentRun(ctx, spec["tools"])
    if model.startswith("mock:"):
        result = mock_fn(run, prompt)
    else:
        result = _run_live(run, spec, prompt, model.split(":", 1)[1])
    result["model"] = model
    result["audit"] = run.audit
    return result


# --------------------------- live tool loop ---------------------------------

ARG_SLOTS = {
    "sql": "SQL text for the query verb",
    "key": "object key for get/put",
    "method": "HTTP method for the request verb",
    "path": "URL or path for the request verb",
    "body": "request/put body",
}


def _resource_tool(name, verbs):
    return {
        "name": name,
        "description": (
            f"Access the {name} resource through the run-scoped proxy. "
            f"Allowed verbs: {', '.join(verbs)}. "
            "query requires sql; get and put require key; request requires method and path."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "verb": {"type": "string", "enum": list(verbs)},
                **{k: {"type": "string", "description": v} for k, v in ARG_SLOTS.items()},
            },
            "required": ["verb"],
            "additionalProperties": False,
        },
    }


def _run_live(run, spec, prompt, model_id):
    output_schema = spec["output_schema"]
    required = output_schema.get("required", [])
    tools = [_resource_tool(t["resource"], t["verbs"]) for t in spec["tools"]]
    tools.append({
        "name": "final_result",
        "description": "Submit your final result. Call exactly once, when you are done.",
        "input_schema": output_schema,
    })
    messages = [{"role": "user", "content": prompt}]
    repairs = spec.get("repair_budget", 2)

    for _ in range(MAX_ITERATIONS):
        resp = _messages_call(model_id, spec["instructions"], tools, messages)
        if resp["stop_reason"] == "refusal":
            raise RuntimeError("model declined the request (stop_reason: refusal)")
        blocks = resp["content"]
        tool_uses = [b for b in blocks if b["type"] == "tool_use"]
        if not tool_uses:
            # Answered in prose without the final tool — salvage the text.
            text = " ".join(b["text"] for b in blocks if b["type"] == "text").strip()
            return {"answer": text} if "answer" in required else {"description": text, "tags": []}

        messages.append({"role": "assistant", "content": blocks})
        results = []
        for tu in tool_uses:
            if tu["name"] == "final_result":
                missing = [k for k in required if k not in tu["input"]]
                if not missing:
                    return tu["input"]
                if repairs <= 0:
                    raise RuntimeError("agent_repair_exhausted: final result invalid")
                repairs -= 1
                results.append(_tool_error(tu["id"], f"missing required fields: {missing}"))
                continue
            try:
                args = {k: v for k, v in tu["input"].items() if k in ARG_SLOTS and v}
                out = run.call(tu["name"], tu["input"].get("verb", ""), **args)
                results.append({
                    "type": "tool_result",
                    "tool_use_id": tu["id"],
                    "content": json.dumps(out, default=str)[:6000],
                })
            except Exception as exc:  # correctable: refusal text goes back in-conversation (D1)
                results.append(_tool_error(tu["id"], f"{type(exc).__name__}: {exc}"))
        messages.append({"role": "user", "content": results})

    raise RuntimeError("agent exceeded its iteration budget")


def _tool_error(tool_use_id, text):
    return {"type": "tool_result", "tool_use_id": tool_use_id,
            "content": str(text)[:1000], "is_error": True}


def _messages_call(model_id, system, tools, messages):
    """One Messages API call, normalized to plain dicts.

    Prefers the official anthropic SDK; falls back to raw HTTP when the SDK
    is not installed (thinking stays on by default on current models — no
    thinking param, no sampling params).
    """
    try:
        import anthropic
    except ImportError:
        return _messages_http(model_id, system, tools, messages)
    client = anthropic.Anthropic(api_key=_api_key())
    resp = client.messages.create(
        model=model_id, max_tokens=4096, system=system, tools=tools, messages=messages
    )
    content = []
    for b in resp.content:
        if b.type == "text":
            content.append({"type": "text", "text": b.text})
        elif b.type == "tool_use":
            content.append({"type": "tool_use", "id": b.id, "name": b.name, "input": b.input})
    return {"stop_reason": resp.stop_reason, "content": content}


def _messages_http(model_id, system, tools, messages):
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps({
            "model": model_id,
            "max_tokens": 4096,
            "system": system,
            "tools": tools,
            "messages": messages,
        }).encode(),
        headers={
            "Content-Type": "application/json",
            "x-api-key": _api_key() or "",
            "anthropic-version": "2023-06-01",
        },
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        body = json.loads(resp.read())
    content = [b for b in body["content"] if b["type"] in ("text", "tool_use")]
    return {"stop_reason": body["stop_reason"], "content": content}
