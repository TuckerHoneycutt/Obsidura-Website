"""Benchmark the caller's own figures against public market data.

The shape mirrors the report pipelines' GATHER → DESIGN split inside one
task: a live agent holds the only judgement call — which public series says
something useful about these figures — while everything around it is code.
The caller's numbers are computed deterministically from their catalogued
uploads; the page is a deterministic template; and every benchmark the agent
returns must carry the source URL of a tool call it actually made, all of
which crossed the proxy under the caller's grant. The audit trail is printed
on the page: numbers vs the market, and the receipts for the market.
"""

import json
import os

import _agent
from _agent import run_agent
from _compat import CATALOG_KEY, blob_get, index_load, requester, value_in
from extract_report_data import _extract
from render_template import STYLE, colophon, esc, fmt

MAX_TABLES = 2

INSTRUCTIONS = """\
You are a market analyst. You are given figures computed from a user's own
data, and a question. Your job: put those figures in market context using
ONLY the three public statistical APIs you hold tools for. Each tool takes
verb `request` with `method` ("GET") and `path` (relative to that API's
host — never include a scheme or hostname).

Your sources (compose your own paths for what the question needs):
- worldbank tool — api.worldbank.org, no key, JSON. Latest indicator value:
  path: /v2/country/US/indicator/FP.CPI.TOTL.ZG?format=json&mrnev=1
  Useful indicators: FP.CPI.TOTL.ZG (inflation %), NY.GDP.MKTP.KD.ZG (GDP
  growth %), SL.UEM.TOTL.ZS (unemployment %), FR.INR.LEND (lending rate %).
- datausa tool — datausa.io, no key, JSON. National average wage:
  path: /api/data?measure=Average%20Wage&drilldowns=Nation&year=latest
- bls tool — api.bls.gov, no key, JSON. Average hourly earnings series:
  path: /publicAPI/v2/timeseries/data/CES0500000003

Rules, non-negotiable:
- Every benchmark_value must come out of a tool result you fetched in this
  conversation, with its source_url set to the full URL of that request
  (the tool's host plus the path you sent). Never supply a benchmark from
  memory.
- The user's figures and the public series rarely measure the same thing.
  Say so in each comparison's note — "your average monthly gross pay per
  employee vs the US national average wage (annual)" is honest; a bare
  ratio is not. Convert units where arithmetic allows and show the basis.
- 2 to 4 comparisons is right. If a source is refused or unreachable, try
  another allowed one; if none work, return comparisons: [] and say what
  happened in the summary.
- Call final_result exactly once when done.
"""

OUTPUT_SCHEMA = {
    "type": "object",
    "required": ["summary", "comparisons"],
    "properties": {
        "summary": {"type": "string",
                    "description": "3-5 sentences: what the figures look like "
                    "next to the market, plainly"},
        "comparisons": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["metric", "our_value", "benchmark_value",
                             "benchmark_label", "source_url"],
                "properties": {
                    "metric": {"type": "string"},
                    "our_value": {"type": "string"},
                    "benchmark_value": {"type": "string"},
                    "benchmark_label": {"type": "string"},
                    "source_url": {"type": "string"},
                    "note": {"type": "string"},
                },
            },
        },
    },
}


def run(ctx, payload: dict) -> dict:
    payload = value_in(payload)
    prompt = (payload.get("prompt") or payload.get("question")
              or "Compare these figures to the market")

    who = requester(ctx, payload)
    entries = index_load(ctx, CATALOG_KEY)
    tables = sorted(
        (e for e in entries if e.get("kind") == "table"
         and e.get("requester") in (who, None, "", "unknown")),
        key=lambda e: e.get("created_at", ""), reverse=True)
    if not tables:
        raise ValueError(
            "no uploaded tables in the catalog yet — add a CSV or spreadsheet "
            "first, then run the benchmark")

    figures = {}
    for entry in tables[:MAX_TABLES]:
        key = (entry.get("detail") or {}).get("row_source_key") \
            or f"ingest/tables/{entry['sha256']}.csv"
        extract = _extract(blob_get(ctx, key))
        figures[entry["source_filename"]] = {
            "row_count": extract["row_count"],
            "totals": extract["totals"],
            "breakdowns": extract["breakdowns"],
        }

    spec = {
        "model": ("anthropic:claude-sonnet-5" if _agent._api_key()
                  else "mock:benchmark"),
        "instructions": INSTRUCTIONS,
        "tools": [{"resource": "worldbank", "verbs": ["request"]},
                  {"resource": "datausa", "verbs": ["request"]},
                  {"resource": "bls", "verbs": ["request"]}],
        "output_schema": OUTPUT_SCHEMA,
        "repair_budget": 2,
    }
    agent_prompt = (
        f"Question: {prompt}\n\nThe user's figures, computed exactly from "
        f"their uploaded data:\n{json.dumps(figures, indent=2)}")
    result = run_agent(ctx, spec, agent_prompt, _mock)

    page = _render(prompt, figures, result)
    return {"kind": "file", **ctx.blob_put(page.encode("utf-8"), "text/html")}


def _mock(run, prompt):
    """Keyless stand-in: labeled illustrative, sourced to nothing."""
    return {
        "summary": ("Illustrative benchmarks only — set a model key and the "
                    "analyst agent will fetch live figures from the allowed "
                    "public sources, with every URL audited."),
        "comparisons": [{
            "metric": "example metric",
            "our_value": "your figure",
            "benchmark_value": "market figure",
            "benchmark_label": "illustrative placeholder",
            "source_url": "",
            "note": "no model key present; nothing was fetched",
        }],
    }


def _render(prompt, figures, result) -> str:
    title = prompt.split("\n")[0].strip() or "Market benchmark"
    rows = []
    for c in result.get("comparisons") or []:
        src = str(c.get("source_url") or "")
        link = (f"<a href=\"{esc(src)}\">{esc(_short(src))}</a>" if src
                else "&mdash;")
        rows.append(
            f"<tr><td>{esc(c.get('metric', ''))}</td>"
            f"<td class=\"n\">{esc(c.get('our_value', ''))}</td>"
            f"<td class=\"n\">{esc(c.get('benchmark_value', ''))}</td>"
            f"<td>{esc(c.get('benchmark_label', ''))}<br>"
            f"<small>{esc(c.get('note', ''))} · {link}</small></td></tr>")
    table = ("<table><thead><tr><th>metric</th><th class=\"n\">yours</th>"
             "<th class=\"n\">market</th><th>basis &amp; source</th></tr>"
             f"</thead><tbody>{''.join(rows)}</tbody></table>"
             if rows else "<p>No comparisons could be made.</p>")

    audit = result.get("audit") or []
    audit_html = "".join(
        f"<li>{esc(a.get('resource', ''))} · {esc(a.get('verb', ''))} — "
        f"{esc(a.get('detail', ''))}</li>" for a in audit)

    return (
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        f"<title>{esc(title)}</title>"
        "<link rel=\"stylesheet\" href=\"https://fonts.googleapis.com/css2?"
        "family=Cormorant+Garamond:wght@400;500;600&amp;"
        "family=Instrument+Sans:wght@400;500;600&amp;display=swap\">"
        f"<style>{STYLE}"
        "a{color:var(--gold)}small{color:var(--ink3)}"
        "ul.audit{font-size:12.5px;color:var(--ink2);padding-left:20px}"
        "</style></head><body><main>"
        "<header><p class=\"kicker\">Pantheon — market benchmark</p>"
        f"<h1>{esc(title)}</h1></header>"
        f"<p>{esc(result.get('summary', ''))}</p>"
        f"<h2>Your numbers vs the market</h2>{table}"
        f"<p><small>Analysed by {esc(result.get('model', 'unknown'))}. "
        "Benchmarks are public statistics; check each basis note before "
        "acting on a comparison.</small></p>"
        f"<h3>every call it made</h3><ul class=\"audit\">{audit_html or '<li>none</li>'}</ul>"
        + colophon("benchmarks fetched live — every source in the audit above") +
        "<details><summary>Figures and result — verbatim</summary>"
        f"<pre>{esc(json.dumps({'figures': figures, 'result': result}, indent=2, ensure_ascii=False))}</pre>"
        "</details></main></body></html>")


def _short(url: str) -> str:
    return url if len(url) <= 72 else url[:69] + "…"
