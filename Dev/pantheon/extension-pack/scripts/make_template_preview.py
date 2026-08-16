#!/usr/bin/env python3
"""Generate the template-preview documents the console embeds.

One standalone document per deterministic template — the your-data report,
the morning brief, the benchmark page — each borrowing STYLE and the
colophon from render_template, the same module the real pages are built
from, so a preview cannot drift from the look of the real thing. Figures
are placeholder marks (italic, gold, "your data here") in the exact
positions real numbers land.

Regenerate after any template restyle and re-embed:

    .venv/bin/python3 extension-pack/scripts/make_template_preview.py /tmp

writes tpl-yourdata.html, tpl-brief.html and tpl-benchmark.html into the
given directory; each belongs in the matching text/x-template block in
demo.html (the build note there points back at this script).
"""

import os
import sys

ACTIONS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "actions")
sys.path.insert(0, ACTIONS)

from render_template import STYLE, colophon  # noqa: E402

PH_CSS = (
    ".ph{font-family:'Cormorant Garamond',Georgia,serif;font-style:italic;"
    "color:var(--gold);font-weight:500}"
    ".tpl-note{font-size:13px;color:var(--ink3);margin:18px 0 0}"
    "ul.audit{font-size:12.5px;color:var(--ink2);padding-left:20px}"
    "small{color:var(--ink3)}"
)


def ph(text):
    return f"<span class=\"ph\">{text}</span>"


def bar(width):
    return (f"<td class=\"sharecell\"><div class=\"track\">"
            f"<i style=\"width:{width}%\"></i></div>"
            f"<span class=\"pct\">··%</span></td>")


def shell(title: str, note: str, body: str) -> str:
    return (
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        f"<title>{title}</title>"
        "<link rel=\"stylesheet\" href=\"https://fonts.googleapis.com/css2?"
        "family=Cormorant+Garamond:ital,wght@0,400;0,500;0,600;1,500&amp;"
        "family=Instrument+Sans:wght@400;500;600&amp;display=swap\">"
        f"<style>{STYLE}{PH_CSS}</style></head><body><main>"
        "<header><p class=\"kicker\">Pantheon — template</p>"
        f"<h1>{title}</h1>"
        f"<p class=\"provenance\">{note} · gold italics mark where your "
        "numbers land</p></header>"
        + body
        + colophon("a preview — run the report to fill it with your figures")
        + "</main></body></html>")


def build_yourdata() -> str:
    body = (
        f"<h2>{ph('your-file.csv')}</h2>"
        f"<div class=\"hero\"><b>{ph('your total here')}</b>"
        f"<span>total {ph('your largest metric')}</span></div>"
        f"<p class=\"heroline\">mean {ph('·····')} · spans {ph('·····')} to "
        f"{ph('·····')}</p>"
        "<div class=\"kpis\">"
        f"<div class=\"kpi\"><b>{ph('···')}</b><span>rows</span></div>"
        f"<div class=\"kpi\"><b>{ph('·····')}</b>"
        f"<span>total {ph('another metric')}</span></div>"
        "</div>"
        "<aside class=\"issues\"><h3>data quality — noted at ingest</h3>"
        "<ul><li>" + ph("any issues measured at upload appear here — "
                        "empties, duplicates, outliers") + "</li></ul></aside>"
        f"<h3>{ph('metric')} by {ph('category')}</h3>"
        "<table><thead><tr><th>group</th><th class=\"n\">count</th>"
        "<th class=\"n\">sum</th><th>share</th></tr></thead><tbody>"
        f"<tr><td class=\"g\">{ph('largest category')}</td>"
        f"<td class=\"n\">{ph('··')}</td><td class=\"n\">{ph('·····')}</td>{bar(78)}</tr>"
        f"<tr><td class=\"g\">{ph('second category')}</td>"
        f"<td class=\"n\">{ph('··')}</td><td class=\"n\">{ph('·····')}</td>{bar(46)}</tr>"
        f"<tr><td class=\"g\">{ph('third category')}</td>"
        f"<td class=\"n\">{ph('··')}</td><td class=\"n\">{ph('·····')}</td>{bar(21)}</tr>"
        "</tbody></table>"
        "<h3>sample rows</h3>"
        "<table><thead><tr><th>column</th><th>column</th><th>column</th></tr>"
        f"</thead><tbody><tr><td>{ph('your data here')}</td>"
        f"<td>{ph('your data here')}</td><td>{ph('your data here')}</td></tr>"
        f"<tr><td>{ph('your data here')}</td><td>{ph('your data here')}</td>"
        f"<td>{ph('your data here')}</td></tr></tbody></table>")
    return shell("The your-data report",
                 "built in about a second, deterministically", body)


def build_brief() -> str:
    body = (
        f"<h2 style=\"font-style:italic\">{ph('a prompt you scheduled')}</h2>"
        "<p class=\"tpl-note\">…its full report — hero figure, tiles, "
        "breakdowns with share bars — from the data as it stands this "
        "morning…</p>"
        f"<h2 style=\"font-style:italic\">{ph('another saved prompt')}</h2>"
        "<p class=\"tpl-note\">…and so on: one section per saved prompt, "
        "re-answered fresh daily at 07:00 UTC or on demand with Run "
        "brief.</p>")
    return shell("The morning brief",
                 "every saved prompt, re-answered daily", body)


def build_benchmark() -> str:
    body = (
        "<p class=\"tpl-note\">"
        + ph("a plain-language read of how your figures sit next to the market")
        + "</p>"
        "<h2>Your numbers vs the market</h2>"
        "<table><thead><tr><th>metric</th><th class=\"n\">yours</th>"
        "<th class=\"n\">market</th><th>basis &amp; source</th></tr></thead>"
        "<tbody>"
        f"<tr><td>{ph('your metric')}</td><td class=\"n\">{ph('·····')}</td>"
        f"<td class=\"n\">{ph('·····')}</td>"
        f"<td>{ph('what was compared, honestly')}"
        f"<br><small><a>{ph('source-url')}</a></small></td></tr>"
        f"<tr><td>{ph('another metric')}</td><td class=\"n\">{ph('·····')}</td>"
        f"<td class=\"n\">{ph('·····')}</td>"
        f"<td>{ph('its basis note')}"
        f"<br><small><a>{ph('source-url')}</a></small></td></tr>"
        "</tbody></table>"
        "<h3>every call it made</h3>"
        "<ul class=\"audit\"><li>" + ph("each request the analyst made — "
                                        "including the ones that failed")
        + "</li></ul>")
    return shell("The benchmark page",
                 "live public statistics, every source cited", body)


DOCS = {
    "tpl-yourdata.html": build_yourdata,
    "tpl-brief.html": build_brief,
    "tpl-benchmark.html": build_benchmark,
}


if __name__ == "__main__":
    outdir = sys.argv[1] if len(sys.argv) > 1 else "."
    for name, builder in DOCS.items():
        path = os.path.join(outdir, name)
        with open(path, "w") as fh:
            fh.write(builder())
        print(path)
