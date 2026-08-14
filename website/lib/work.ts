/**
 * What Pantheon runs, in two lists the homepage and the works chapter both
 * read from - so the range the site claims in one place cannot quietly
 * differ from the range it claims in another.
 */

/** The two doors a run can come in through. Same definitions behind both. */
export const FACES = [
  {
    label: "asked for",
    title: "Someone calls it.",
    plain:
      "A named process anyone permitted can start: a button in an internal tool, a sentence typed in plain English, or a call from another system. The library of processes is the part of the company anyone can use without knowing how any of it works.",
    lines: [
      "trigger  manual · press the button labelled 'month-end pack'",
      "trigger  webhook · “which suppliers slipped last quarter?”",
      "trigger  webhook · called by the ticketing system",
    ],
  },
  {
    label: "unattended",
    title: "Nobody calls it.",
    plain:
      "The same kind of job with a schedule or an event on the front of it, running while everyone is asleep. Reconciliations that happen nightly, checks that run hourly, packs that land on the first of the month before anyone has asked for them.",
    lines: [
      "trigger  cron · 0 6 * * 1  weekly exceptions pack",
      "trigger  cron · 0 2 * * *  nightly reconciliation",
      "trigger  webhook · fires when a test run finishes",
    ],
  },
] as const;

/**
 * Eight ordinary jobs from eight parts of a company. The range is the
 * argument, and it is made with examples rather than with the word
 * "anything" - though the last one earns the word. `short` is the homepage
 * strip; `line` is the chapter, where there is room to say what the job does.
 */
export const WORK = [
  {
    domain: "reporting",
    short: "The monthly performance pack, finished in minutes.",
    line: "The monthly performance pack — numbers gathered from wherever they live, made sense of, and handed back finished in minutes.",
  },
  {
    domain: "engineering",
    short: "Rocket test diagnostics, checked against the standard the programme is held to.",
    line: "Rocket test diagnostics — telemetry read against the test log, anomalies called out, checked against the standard the programme is held to.",
  },
  {
    domain: "finance",
    short: "Ledger reconciliation, with the entries that do not tie out listed.",
    line: "Ledger reconciliation — the ledger against the receipts against an outside rate feed, with the entries that do not tie out listed.",
  },
  {
    domain: "clinical",
    short: "Cohort summaries, scoped to the clinician who asked.",
    line: "Cohort summaries — records and scans drawn together, scoped to the clinician who asked and nobody else.",
  },
  {
    domain: "it",
    short: "Standing up a new network segment, with the change gated on a human.",
    line: "Standing up a new network segment — addresses assigned, rules written, the change gated on a human, the whole sequence recorded.",
  },
  {
    domain: "operations",
    short: "Nightly data hygiene, with the owner of each gap told about it.",
    line: "Nightly data hygiene — duplicates merged, gaps flagged, the owner of each gap told about it.",
  },
  {
    domain: "back office",
    short: "Invoices matched against purchase orders, exceptions handed to a person.",
    line: "Invoices matched against purchase orders, the ones that do not match handed to a person with the reason attached.",
  },
  {
    domain: "facilities",
    short: "Turning the office lights on. A schedule and one HTTP call.",
    line: "Turning the office lights on. A schedule and one HTTP call — the same shape of job as all of the above, and worth saying out loud.",
  },
] as const;
