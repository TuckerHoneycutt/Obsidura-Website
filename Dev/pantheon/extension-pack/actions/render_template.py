"""Deterministic design seat for reports over uploaded data (kernel.file@1).

The extract stage already computed every figure; laying out KPI tiles and
tables needs no model. This template renders the page in milliseconds and
costs nothing — the same GATHER → DESIGN seam, with the design seat held by
code. The full extract JSON rides at the foot of the page, so everything
shown is checkable against everything computed.
"""

import html as _html
import json

from _compat import value_in

MAX_GROUP_ROWS = 12
MAX_SAMPLE_ROWS = 10

STYLE = (
    ":root{--paper:#FAFAF7;--card:#fff;--ink:#141412;--ink2:#55534E;"
    "--ink3:#8D8A82;--line:#E7E5DF;--gold:#A5854A}"
    "*{box-sizing:border-box}"
    "body{margin:0;background:var(--paper);color:var(--ink);"
    "font:15px/1.55 'Instrument Sans',system-ui,sans-serif}"
    "main{max-width:880px;margin:0 auto;padding:44px 28px 64px}"
    "header{border-bottom:1px solid var(--line);padding-bottom:20px;margin-bottom:28px}"
    ".kicker{font-size:11px;font-weight:600;letter-spacing:.2em;"
    "text-transform:uppercase;color:var(--gold);margin:0 0 10px}"
    "h1{font-family:'Cormorant Garamond',Georgia,serif;font-weight:500;"
    "font-size:34px;line-height:1.15;margin:0}"
    "h2{font-family:'Cormorant Garamond',Georgia,serif;font-weight:600;"
    "font-size:24px;margin:34px 0 12px}"
    "h3{font-size:13px;font-weight:600;letter-spacing:.06em;"
    "text-transform:uppercase;color:var(--ink3);margin:24px 0 8px}"
    ".kpis{display:flex;gap:10px;flex-wrap:wrap;margin:0 0 6px}"
    ".kpi{background:var(--card);border:1px solid var(--line);"
    "border-radius:12px;padding:12px 18px;min-width:130px}"
    ".kpi b{display:block;font-family:'Cormorant Garamond',Georgia,serif;"
    "font-weight:600;font-size:24px}"
    ".kpi span{font-size:11.5px;color:var(--ink3);letter-spacing:.04em;"
    "text-transform:uppercase}"
    "table{border-collapse:collapse;width:100%;margin:10px 0 4px;"
    "background:var(--card);border:1px solid var(--line);border-radius:12px;"
    "overflow:hidden;font-size:13.5px}"
    "th{font-size:11px;font-weight:600;letter-spacing:.06em;"
    "text-transform:uppercase;color:var(--ink3);text-align:left;"
    "padding:9px 12px;border-bottom:1px solid var(--line)}"
    "td{padding:8px 12px;border-bottom:1px solid var(--line)}"
    "tr:last-child td{border-bottom:0}"
    "td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}"
    "details{margin-top:40px;border-top:1px solid var(--line);padding-top:14px}"
    "summary{font-size:12.5px;color:var(--ink3);cursor:pointer}"
    "pre{white-space:pre-wrap;font-size:12px;color:var(--ink2);"
    "background:var(--card);border:1px solid var(--line);border-radius:12px;"
    "padding:14px;overflow-wrap:anywhere}"
)


def run(ctx, payload: dict) -> dict:
    doc = value_in(payload)
    question = str(doc.get("question") or "Report")
    title = question.split("\n")[0].strip() or "Report"
    data = doc.get("data") or {}

    parts = []
    for filename, extract in data.items():
        parts.append(_file_section(filename, extract))

    page = (
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        f"<title>{esc(title)}</title>"
        "<link rel=\"stylesheet\" href=\"https://fonts.googleapis.com/css2?"
        "family=Cormorant+Garamond:wght@400;500;600&amp;"
        "family=Instrument+Sans:wght@400;500;600&amp;display=swap\">"
        f"<style>{STYLE}</style></head><body><main>"
        "<header><p class=\"kicker\">Pantheon — from your data</p>"
        f"<h1>{esc(title)}</h1></header>"
        + "".join(parts) +
        "<details><summary>Every figure computed — verbatim</summary>"
        f"<pre>{esc(json.dumps(doc, indent=2, ensure_ascii=False))}</pre>"
        "</details></main></body></html>")

    return {"kind": "file", **ctx.blob_put(page.encode("utf-8"), "text/html")}


def esc(v) -> str:
    return _html.escape(str(v), quote=False)


def fmt(v) -> str:
    if isinstance(v, float):
        return f"{v:,.2f}".rstrip("0").rstrip(".") if v % 1 else f"{v:,.0f}"
    if isinstance(v, int) and not isinstance(v, bool):
        return f"{v:,}"
    return str(v)


def _file_section(filename, extract) -> str:
    if not isinstance(extract, dict):
        return f"<h2>{esc(filename)}</h2><p>{esc(extract)}</p>"
    out = [f"<h2>{esc(filename)}</h2>"]

    kpis = [f"<div class=\"kpi\"><b>{fmt(extract.get('row_count', 0))}</b>"
            "<span>rows</span></div>"]
    for name, stats in (extract.get("totals") or {}).items():
        kpis.append(f"<div class=\"kpi\"><b>{esc(fmt(stats.get('sum', 0)))}</b>"
                    f"<span>total {esc(name)}</span></div>")
    out.append(f"<div class=\"kpis\">{''.join(kpis)}</div>")

    for label, groups in (extract.get("breakdowns") or {}).items():
        ranked = sorted(groups.items(),
                        key=lambda kv: kv[1].get("sum", 0), reverse=True)
        rows = "".join(
            f"<tr><td>{esc(k)}</td><td class=\"n\">{fmt(v.get('count', 0))}</td>"
            f"<td class=\"n\">{esc(fmt(v.get('sum', 0)))}</td></tr>"
            for k, v in ranked[:MAX_GROUP_ROWS])
        out.append(
            f"<h3>{esc(label)}</h3><table><thead><tr><th>group</th>"
            "<th class=\"n\">count</th><th class=\"n\">sum</th></tr></thead>"
            f"<tbody>{rows}</tbody></table>")

    sample = extract.get("sample_rows") or {}
    cols, rows = sample.get("columns") or [], sample.get("rows") or []
    if cols and rows:
        head = "".join(f"<th>{esc(c)}</th>" for c in cols)
        body = "".join(
            "<tr>" + "".join(f"<td>{esc(c)}</td>" for c in r) + "</tr>"
            for r in rows[:MAX_SAMPLE_ROWS])
        out.append(f"<h3>sample rows</h3><table><thead><tr>{head}</tr></thead>"
                   f"<tbody>{body}</tbody></table>")
    return "".join(out)
