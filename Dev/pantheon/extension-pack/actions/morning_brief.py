"""The morning brief: every saved prompt, answered from fresh data, one page.

Fired by cron (daily, as the `system` user under its own grants) and by
webhook for on-demand runs. Deterministic end to end: the same extractor
computes the figures and the same template voice lays them out — a saved
prompt costs nothing to re-answer, which is what makes a *daily* report
reasonable. A prompt whose data has gone missing gets its say on the page
rather than failing the brief.
"""

import json

from _compat import index_load, value_in
from extract_report_data import gather_figures
from render_template import STYLE, _file_section, esc
from schedule_add import SCHEDULES_KEY

MAX_PER_BRIEF = 5


def run(ctx, payload: dict) -> dict:
    payload = value_in(payload)
    tick = payload.get("ts", "")
    schedules = index_load(ctx, SCHEDULES_KEY)

    sections = []
    for entry in schedules[:MAX_PER_BRIEF]:
        prompt = entry.get("prompt") or ""
        sections.append(f"<section><h2 class=\"ask\">{esc(prompt)}</h2>")
        try:
            for filename, extract in gather_figures(ctx, prompt).items():
                sections.append(_file_section(filename, extract))
        except ValueError as exc:
            sections.append(f"<p class=\"miss\">{esc(exc)}</p>")
        sections.append("</section>")
    if len(schedules) > MAX_PER_BRIEF:
        sections.append(f"<p class=\"miss\">{len(schedules) - MAX_PER_BRIEF} "
                        "more schedule(s) not shown — the brief caps at "
                        f"{MAX_PER_BRIEF}.</p>")
    if not schedules:
        sections.append(
            "<p class=\"miss\">No saved prompts yet — write one in the "
            "console and press Schedule, and it will be answered here every "
            "morning.</p>")

    page = (
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        "<title>Morning brief</title>"
        "<link rel=\"stylesheet\" href=\"https://fonts.googleapis.com/css2?"
        "family=Cormorant+Garamond:wght@400;500;600&amp;"
        "family=Instrument+Sans:wght@400;500;600&amp;display=swap\">"
        f"<style>{STYLE}"
        "h2.ask{font-style:italic;border-bottom:1px solid var(--line);"
        "padding-bottom:8px}"
        "p.miss{color:var(--ink3);font-size:13.5px}"
        "section{margin-bottom:34px}"
        "</style></head><body><main>"
        "<header><p class=\"kicker\">Pantheon — morning brief</p>"
        f"<h1>Your saved prompts, answered fresh</h1></header>"
        + "".join(sections) +
        "<details><summary>Schedules and tick — verbatim</summary>"
        f"<pre>{esc(json.dumps({'tick': tick, 'schedules': schedules}, indent=2, ensure_ascii=False))}</pre>"
        "</details></main></body></html>")

    return {"kind": "file", **ctx.blob_put(page.encode("utf-8"), "text/html")}
