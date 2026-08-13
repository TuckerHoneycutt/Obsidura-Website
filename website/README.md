<div align="center">
  <img src="public/logo-mark.svg" alt="Obsidura mark" width="96" />

  # Obsidura

  **Backend-native agents for auditable operations.**

  [obsidura.com](https://obsidura.com)
  &nbsp;&middot;&nbsp;
  [Book a demo](https://obsidura.com/contact)
</div>

---

## The company

Obsidura builds an enterprise **AI agent orchestration** platform. Agents connect to the systems you already run — databases, object stores, and internal APIs — and execute durable, auditable workflows. Anything consequential waits for a human. Routine toil stays with the agents; judgment stays with your team.

**Pantheon** is the engine: YAML definitions compiled into a typed graph, contracts checked at every seam, a run-scoped resource proxy holding every credential, and an append-only run log.

Deploy in Obsidura Cloud, in your private VPC, or fully on-premises.

Site copy is derived from `specs/pantheon-spec-v0.md`; that spec wins where the two disagree.

---

## What Pantheon does

- **Four primitives** — Trigger, Task, Resource, Approval. Each is a tagged union whose variant carries its own config. Edges are derived from `on:` / `then:` / `uses:` references, never authored.
- **Definitions are data** — YAML compiles into a typed graph in Postgres. `ptn plan` diffs against the registry; `ptn apply` registers. No expression language in the config, ever.
- **A closed kernel of values** — Text, File, Table, Record, Error. Business meaning lives in Records, which is what keeps the executor constant in the number of business types.
- **Contracts at every seam** — Envelopes carry run/task/attempt, schema ref, producer, causing event, taint, and budget. Agent outputs get a bounded repair loop before anything downstream sees them.
- **Run log as the product** — One append-only `run_events` table; executor state is a fold of it. Status, audit, durable approval suspend/resume, and crash recovery all read from it.
- **Resource proxy** — A per-run Unix socket is the capability. The container never holds a credential; grants are enforced per call (row filter / key prefix / URL allowlist).

Report pipelines on the site: financial audit, flight diagnostics, clinical summaries — the three verticals in the spec.

---

## Deployment

| | Obsidura Cloud | Private VPC | On-premises |
| --- | --- | --- | --- |
| **Fit** | Fully managed | Your cloud account | Isolated / your hardware |
| **Tenancy** | Multi-tenant | Single-tenant | Yours |
| **Network** | Obsidura-operated | Your boundary | No outbound calls |

Note: spec v0 covers no deployment postures. This section is positioning, not
something the spec backs — treat it as the intended shape rather than shipped.

---

## This package

This folder is the **Obsidura marketing site** (Next.js App Router). The homepage is a door: one claim and an index of five chapters — reports, workflows, governance, runtime, deploy — each with a page of its own. Below them sit the detail pages: solutions, deployment, security, integrations, FAQ, privacy, and contact. It lives at `website/` in the company monorepo.

| | |
| --- | --- |
| Framework | Next.js 16, React 19, TypeScript |
| Styling | Tailwind CSS 4 |
| Motion / scroll | `motion`, Lenis |
| Theme | `next-themes` (light default, dark available) |

```text
app/           Routes, layout, SEO (sitemap, robots, JSON-LD), globals
components/    Hero, nav, sections, forms, UI
lib/           Helpers and engraving assets used on the homepage
public/        Logo mark and static assets
```

---

## Brand (site)

The public site uses a Greek classical register — Pantheon, labors, forge, dominions — as a brand layer under plain product language. Visually it stays monochrome: paper and ink, hairline rules, and a single gilt accent on deployment cards.

**Type**

- Display / body: [Cormorant Garamond](https://fonts.google.com/specimen/Cormorant+Garamond)
- Mono / UI: [Cutive Mono](https://fonts.google.com/specimen/Cutive+Mono)

**Palette (light)**

| Token | Value |
| --- | --- |
| Paper | `#ffffff` |
| Ink | `#000000` |
| Soft / mute | `#2e2e2e` / `#5c5c5c` |
| Rule | `#dcdcdc` |
| Gilt | `#a5854a` |

Dark mode inverts paper and ink; gilt becomes `#c9a86a`. Tokens live in `app/globals.css`.

---

## Develop

```bash
npm install
npm run dev      # http://localhost:3000
npm run build
npm run start
npm run lint
```

Contact submissions hit `POST /api/contact`. Keep secrets in `.env.local`.

---

## Links

- Site: [obsidura.com](https://obsidura.com)
- Workflows: [obsidura.com/workflows](https://obsidura.com/workflows)
- Security: [obsidura.com/security](https://obsidura.com/security)
- Contact: [obsidura.com/contact](https://obsidura.com/contact)
