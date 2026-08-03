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

Obsidura builds an enterprise **AI agent orchestration** platform. Agents connect directly to the systems you already run — databases, APIs, and business applications — and execute durable, auditable workflows. When confidence drops, work escalates to a human with full context. Routine toil stays with the agents; judgment stays with your team.

**Pantheon** is the orchestration suite: typed connectors, a planning layer, a durable runtime, an append-only audit log, and human-in-the-loop escalation.

Deploy in Obsidura Cloud, in your private VPC, or fully on-premises.

---

## What Pantheon does

- **Typed connectors** — Postgres, REST, gRPC, queues, and named apps (Salesforce, Slack, Stripe, and others). Credentials are scoped per step and audited.
- **Planner** — Jobs compile to a typed DAG before execution. Deterministic tools run first; model calls happen only when judgment is required.
- **Durable runtime** — Workflows are state machines with checkpoints, retries, idempotency, sandboxed executors, and schema validation at every boundary.
- **Audit log** — Every prompt, tool call, and diff is append-only and replayable.
- **Human escalation** — Low-confidence steps go to a queue with the full decision trace, not a guess.

Primary use cases on the site: finance operations, customer support, and revenue operations.

---

## Deployment

| | Obsidura Cloud | Private VPC | On-premises |
| --- | --- | --- | --- |
| **Fit** | Fully managed | Your AWS or GCP account | Air-gapped / your hardware |
| **Tenancy** | Multi-tenant | Single-tenant | Your cluster |
| **Network** | Obsidura-operated | Your boundary | No external calls |

---

## This repository

This repo is the **Obsidura marketing site** (Next.js App Router): homepage, product pages, solutions, deployment docs, security, FAQ, privacy, and contact.

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
- Platform: [obsidura.com/platform](https://obsidura.com/platform)
- Security: [obsidura.com/security](https://obsidura.com/security)
- Contact: [obsidura.com/contact](https://obsidura.com/contact)
