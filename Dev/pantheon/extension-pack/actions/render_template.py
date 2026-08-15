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

# The document voice all deterministic pages share: paper and ink, one gold,
# Cormorant for what speaks and Instrument Sans for what informs. A report,
# not an admin panel — one hero figure at real scale, supporting figures as
# quiet understated tiles, tables ruled like a ledger (strong rule under the
# heads, hairlines between rows), proportional share bars drawn in pure CSS,
# and a colophon that states the provenance claim.
STYLE = (
    ":root{--paper:#FBFAF6;--card:#fff;--ink:#141412;--ink2:#55534E;"
    "--ink3:#8D8A82;--line:#E8E5DE;--line2:#D8D4CB;--gold:#A5854A;"
    "--gold2:#C9A86A;--rust:#A05C33}"
    "*{box-sizing:border-box}"
    "body{margin:0;background:var(--paper);color:var(--ink);"
    "font:15px/1.6 'Instrument Sans',system-ui,sans-serif;"
    "-webkit-font-smoothing:antialiased}"
    "main{max-width:860px;margin:0 auto;padding:56px 30px 60px}"
    "header{margin-bottom:8px}"
    ".kicker{font-size:11px;font-weight:600;letter-spacing:.24em;"
    "text-transform:uppercase;color:var(--gold);margin:0 0 12px}"
    "h1{font-family:'Cormorant Garamond',Georgia,serif;font-weight:500;"
    "font-size:clamp(30px,5vw,42px);line-height:1.1;margin:0 0 10px;"
    "max-width:680px}"
    ".provenance{font-size:12.5px;color:var(--ink3);margin:0;"
    "padding-bottom:20px;border-bottom:1px solid var(--ink)}"
    "h2{font-family:'Cormorant Garamond',Georgia,serif;font-weight:600;"
    "font-size:25px;margin:40px 0 4px}"
    "h3{font-size:11px;font-weight:600;letter-spacing:.14em;"
    "text-transform:uppercase;color:var(--ink3);margin:30px 0 10px}"
    ".hero{margin:20px 0 2px;display:flex;align-items:baseline;gap:14px;"
    "flex-wrap:wrap}"
    ".hero b{font-family:'Cormorant Garamond',Georgia,serif;font-weight:500;"
    "font-size:clamp(44px,7vw,62px);line-height:1;letter-spacing:-.01em}"
    ".hero span{font-size:11px;font-weight:600;color:var(--ink3);"
    "letter-spacing:.16em;text-transform:uppercase}"
    ".heroline{margin:6px 0 20px;font-size:13px;color:var(--ink2)}"
    ".kpis{display:flex;gap:28px;flex-wrap:wrap;margin:0 0 8px}"
    ".kpi{border-top:2px solid var(--line2);padding-top:8px;min-width:104px}"
    ".kpi b{display:block;font-family:'Cormorant Garamond',Georgia,serif;"
    "font-weight:600;font-size:23px}"
    ".kpi span{font-size:10.5px;color:var(--ink3);letter-spacing:.12em;"
    "text-transform:uppercase}"
    "table{border-collapse:collapse;width:100%;margin:6px 0 4px;"
    "font-size:13.5px}"
    "th{font-size:10.5px;font-weight:600;letter-spacing:.12em;"
    "text-transform:uppercase;color:var(--ink3);text-align:left;"
    "padding:0 12px 8px 0;border-bottom:1px solid var(--ink)}"
    "td{padding:8px 12px 8px 0;border-bottom:1px solid var(--line)}"
    "tr:last-child td{border-bottom:0}"
    "td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}"
    "td.g{font-weight:500}"
    ".sharecell{width:32%;min-width:120px}"
    ".track{position:relative;height:6px;background:var(--line);"
    "border-radius:3px;overflow:hidden}"
    ".track i{position:absolute;top:0;bottom:0;left:0;"
    "background:linear-gradient(90deg,var(--gold),var(--gold2));"
    "border-radius:3px}"
    ".pct{display:inline-block;margin-top:3px;font-size:11px;"
    "color:var(--ink3);font-variant-numeric:tabular-nums}"
    "aside.issues{margin:16px 0 0;border-left:2px solid var(--rust);"
    "padding:9px 14px;background:rgba(160,92,51,.05)}"
    "aside.issues h3{margin:0 0 5px;color:var(--rust)}"
    "aside.issues ul{margin:0;padding-left:16px;font-size:13px;"
    "color:var(--rust)}"
    "footer.colophon{margin-top:48px;border-top:1px solid var(--ink);"
    "padding-top:10px;display:flex;justify-content:space-between;gap:12px;"
    "flex-wrap:wrap;font-size:10.5px;font-weight:600;letter-spacing:.16em;"
    "text-transform:uppercase;color:var(--ink3)}"
    "details{margin-top:16px}"
    "summary{font-size:12.5px;color:var(--ink3);cursor:pointer}"
    "pre{white-space:pre-wrap;font-size:12px;color:var(--ink2);"
    "background:var(--card);border:1px solid var(--line);border-radius:10px;"
    "padding:14px;overflow-wrap:anywhere}"
    "a{color:var(--gold)}"
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
        f"<h1>{esc(title)}</h1>"
        f"<p class=\"provenance\">{esc(provenance(ctx, data))}</p></header>"
        + "".join(parts) +
        colophon("deterministic render — no model touched these figures") +
        "<details><summary>Every figure computed — verbatim</summary>"
        f"<pre>{esc(json.dumps(doc, indent=2, ensure_ascii=False))}</pre>"
        "</details></main></body></html>")

    return {"kind": "file", **ctx.blob_put(page.encode("utf-8"), "text/html")}


def esc(v) -> str:
    return _html.escape(str(v), quote=False)


def provenance(ctx, data) -> str:
    """One quiet line of where and when: date, files, rows."""
    date = str((getattr(ctx, "envelope", None) or {}).get("ts", ""))[:10]
    names = list(data)
    rows = sum(e.get("row_count", 0) for e in data.values()
               if isinstance(e, dict))
    bits = []
    if date:
        bits.append(date)
    if names:
        bits.append(", ".join(names[:3]) + ("…" if len(names) > 3 else ""))
    if rows:
        bits.append(f"{fmt(rows)} rows examined")
    return " · ".join(bits) or "from the catalog"


def colophon(claim: str) -> str:
    return ("<footer class=\"colophon\"><span>pantheon</span>"
            f"<span>{claim}</span></footer>")


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

    # The largest total is the story; it gets the page's one moment of
    # scale. Everything else stands quietly under a thin rule.
    totals = extract.get("totals") or {}
    hero = max(totals, key=lambda n: abs(totals[n].get("sum", 0))) \
        if totals else None
    if hero:
        stats = totals[hero]
        out.append(f"<div class=\"hero\"><b>{esc(fmt(stats.get('sum', 0)))}</b>"
                   f"<span>total {esc(hero)}</span></div>")
        out.append(
            f"<p class=\"heroline\">mean {esc(fmt(stats.get('mean', 0)))}"
            f" · spans {esc(fmt(stats.get('min', 0)))} to "
            f"{esc(fmt(stats.get('max', 0)))}</p>")

    kpis = [f"<div class=\"kpi\"><b>{fmt(extract.get('row_count', 0))}</b>"
            "<span>rows</span></div>"]
    for name, stats in totals.items():
        if name == hero:
            continue
        kpis.append(f"<div class=\"kpi\"><b>{esc(fmt(stats.get('sum', 0)))}</b>"
                    f"<span>total {esc(name)}</span></div>")
    out.append(f"<div class=\"kpis\">{''.join(kpis)}</div>")

    issues = extract.get("quality_issues") or []
    if issues:
        items = "".join(f"<li>{esc(i)}</li>" for i in issues)
        out.append("<aside class=\"issues\">"
                   "<h3>data quality — noted at ingest</h3>"
                   f"<ul>{items}</ul></aside>")

    for label, groups in (extract.get("breakdowns") or {}).items():
        ranked = sorted(groups.items(),
                        key=lambda kv: kv[1].get("sum", 0), reverse=True)
        shown = ranked[:MAX_GROUP_ROWS]
        peak = max((abs(v.get("sum", 0)) for _, v in shown), default=0) or 1
        whole = sum(v.get("sum", 0) for _, v in ranked)
        rows = []
        for k, v in shown:
            total = v.get("sum", 0)
            width = max(2, round(100 * abs(total) / peak))
            share = (f"<span class=\"pct\">{100 * total / whole:.1f}%</span>"
                     if whole > 0 and total >= 0 else "")
            rows.append(
                f"<tr><td class=\"g\">{esc(k)}</td>"
                f"<td class=\"n\">{fmt(v.get('count', 0))}</td>"
                f"<td class=\"n\">{esc(fmt(total))}</td>"
                f"<td class=\"sharecell\"><div class=\"track\">"
                f"<i style=\"width:{width}%\"></i></div>{share}</td></tr>")
        out.append(
            f"<h3>{esc(label)}</h3><table><thead><tr><th>group</th>"
            "<th class=\"n\">count</th><th class=\"n\">sum</th>"
            "<th>share</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table>")

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
