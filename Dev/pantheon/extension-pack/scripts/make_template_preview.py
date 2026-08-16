#!/usr/bin/env python3
"""Generate the template-preview document the console embeds.

The preview borrows STYLE and the colophon from render_template — the same
module the real pages are built from — so the preview cannot drift from the
look of the real thing. Figures are placeholder marks (italic, gold,
"your data here") in the exact positions real numbers land.

Regenerate after any template restyle and re-embed:

    .venv/bin/python3 extension-pack/scripts/make_template_preview.py \
        > /tmp/template-preview.html

then paste the output into demo.html's `text/x-template` block (the build
note there points back at this script).
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
    ".tpl-label{margin:54px 0 0;padding-top:16px;border-top:2px solid var(--ink);"
    "font-size:11px;font-weight:600;letter-spacing:.24em;"
    "text-transform:uppercase;color:var(--ink2)}"
    ".tpl-label:first-of-type{margin-top:26px}"
    ".tpl-note{font-size:13px;color:var(--ink3);margin:6px 0 0}"
)


def ph(text):
    return f"<span class=\"ph\">{text}</span>"


def bar(width):
    return (f"<td class=\"sharecell\"><div class=\"track\">"
            f"<i style=\"width:{width}%\"></i></div>"
            f"<span class=\"pct\">··%</span></td>")


def build() -> str:
    your_data = (
        "<p class=\"tpl-label\">Template · the your-data report</p>"
        "<p class=\"tpl-note\">What you get in about a second when you run a "
        "report on files you've added. Every gold italic is where your "
        "numbers land.</p>"
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
        f"<td>{ph('your data here')}</td></tr></tbody></table>"
    )

    brief = (
        "<p class=\"tpl-label\">Template · the morning brief</p>"
        "<p class=\"tpl-note\">Every prompt you schedule, re-answered from "
        "fresh data daily at 07:00 UTC — each section repeats the report "
        "structure above.</p>"
        f"<h2 style=\"font-style:italic\">{ph('a prompt you scheduled')}</h2>"
        f"<p class=\"tpl-note\">…its report, from the data as it stands this "
        "morning…</p>"
        f"<h2 style=\"font-style:italic\">{ph('another saved prompt')}</h2>"
        "<p class=\"tpl-note\">…and so on, one section per saved prompt.</p>"
    )

    benchmark = (
        "<p class=\"tpl-label\">Template · the benchmark page</p>"
        "<p class=\"tpl-note\">Your figures against public statistics — every "
        "market number cites the exact URL it was fetched from, and the full "
        "audit of calls is printed.</p>"
        f"<p>{ph('a plain-language read of how your figures sit next to the market')}</p>"
        "<h2>Your numbers vs the market</h2>"
        "<table><thead><tr><th>metric</th><th class=\"n\">yours</th>"
        "<th class=\"n\">market</th><th>basis &amp; source</th></tr></thead>"
        "<tbody>"
        f"<tr><td>{ph('your metric')}</td><td class=\"n\">{ph('·····')}</td>"
        f"<td class=\"n\">{ph('·····')}</td><td>{ph('what was compared, honestly')}"
        f"<br><small><a>{ph('source-url')}</a></small></td></tr>"
        "</tbody></table>"
        "<h3>every call it made</h3>"
        "<ul class=\"audit\"><li>" + ph("each request the analyst made — "
                                        "including the ones that failed")
        + "</li></ul>"
    )

    designed_note = (
        "<p class=\"tpl-label\">No template · the designed reports</p>"
        "<p class=\"tpl-note\">Financial, flight, clinical and freeform have "
        "no fixed template on purpose: a live designer builds each page "
        "fresh around your question. Run one to see what it chooses.</p>"
    )

    return (
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        "<title>Report templates</title>"
        "<link rel=\"stylesheet\" href=\"https://fonts.googleapis.com/css2?"
        "family=Cormorant+Garamond:ital,wght@0,400;0,500;0,600;1,500&amp;"
        "family=Instrument+Sans:wght@400;500;600&amp;display=swap\">"
        f"<style>{STYLE}{PH_CSS}"
        "ul.audit{font-size:12.5px;color:var(--ink2);padding-left:20px}"
        "small{color:var(--ink3)}"
        "</style></head><body><main>"
        "<header><p class=\"kicker\">Pantheon — report templates</p>"
        "<h1>What your pages look like, before your data arrives</h1>"
        "<p class=\"provenance\">gold italics mark where your numbers land</p>"
        "</header>"
        + your_data + brief + benchmark + designed_note
        + colophon("a preview — run a report to fill it with your figures")
        + "</main></body></html>")


if __name__ == "__main__":
    sys.stdout.write(build())
