/**
 * What Pantheon runs, in two lists the homepage and the works chapter both
 * read from - so the range the site claims in one place cannot quietly
 * differ from the range it claims in another.
 */

/** The four kinds of work that run against the layer. */
export const FACES = [
  {
    label: "cron jobs",
    title: "It recurs on a schedule.",
    plain:
      "Work with a cadence on the front of it, running while everyone is asleep — nightly reconciliations, hourly checks, the morning pack landing before anyone has asked.",
    lines: [
      "trigger  cron · 0 2 * * *  nightly reconciliation",
      "trigger  cron · 0 6 * * 1  weekly exceptions pack",
    ],
  },
  {
    label: "actions",
    title: "It fires once.",
    plain:
      "A single named operation anyone permitted can trigger — a button in an internal tool, or a call from another system — done, recorded, and out of the way.",
    lines: [
      "trigger  manual · press the button labelled 'month-end pack'",
      "trigger  webhook · called by the ticketing system",
    ],
  },
  {
    label: "workflows",
    title: "It carries a process end to end.",
    plain:
      "Several steps chained across systems — scripts where the path is fixed, agents where judgement is needed, and a person to sign off where you say so.",
    lines: [
      "agent gathers → render task → approval gate → filed",
      "every seam schema-checked · every step on the record",
    ],
  },
  {
    label: "chat",
    title: "It answers from your data.",
    plain:
      "A question asked in plain English, answered from the context of the layer — scoped to what you are allowed to see, with the sources on the record.",
    lines: [
      "“which suppliers slipped last quarter?”",
      "answer drawn from the layer · scoped to your role",
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
