<div align="center">

<pre>
  .-.   .-.   .-.   .-.   .-.   .-.   .-.
 (   \ /   \ /   \ /   \ /   \ /   \ /   )
  '-'   '-'   '-'   '-'   '-'   '-'   '-'
</pre>

# OBSIDURA

### Backend-native AI agent orchestration

<p>
  <em>The toil belongs to the agents.<br/>Only judgment ascends Olympus.</em>
</p>

<p>
  <a href="https://obsidura.com"><strong>obsidura.com</strong></a>
  &nbsp;&middot;&nbsp;
  Pantheon orchestration suite
  &nbsp;&middot;&nbsp;
  Next.js 16
</p>

<pre>
  .-.   .-.   .-.   .-.   .-.   .-.   .-.
 (   \ /   \ /   \ /   \ /   \ /   \ /   )
  '-'   '-'   '-'   '-'   '-'   '-'   '-'
</pre>

</div>

---

## What this is

**Obsidura** is the marketing site for an enterprise AI agent orchestration platform. The product surface is **Pantheon**: agents mounted on your databases, APIs, and business systems, running durable, auditable workflows that escalate to a human only when judgment is required.

The site itself is built as a classical composition — Greek mythology as brand language, museum-plate engravings as illustration, monochrome paper and ink as the entire palette (with a single gilt accent reserved for the deployment “dominions”).

| Layer | Name | Role |
| --- | --- | --- |
| Company | Obsidura | Brand, trust, contact |
| Product | Pantheon | Agent orchestration suite |
| Runtime metaphor | The forge (Hephaestus) | Durability, sandboxes, checkpoints |
| Deployment | The dominions | Cloud / VPC / on-prem |

---

## Mythology map

The homepage is organized as a descent from Olympus through the labors, the forge, and the three dominions.

| Section | Myth | Product meaning |
| --- | --- | --- |
| **i — Olympus** | The seat of the gods | Hero: category, promise, demo CTA |
| **ii — The labors** | Herakles & the Nemean Lion | Agents take the toil; humans keep judgment |
| **Interlude** | Mount Olympus watermark | *Only judgment ascends Olympus* |
| **iii — The forge** | Hephaestus at the anvil | Runtime reliability, not chatbot fragility |
| **iv — The dominions** | Zeus · Poseidon · Hades | Cloud · Private VPC · On-prem |
| **Integrations** | Plain product language | Connectors into systems of record |
| **Mnemosyne** | Memory / audit log | Append-only, replayable agent runs |

### The three dominions

| Dominion | God | Deployment | Motif |
| --- | --- | --- | --- |
| Heavens | **Zeus** | Obsidura Cloud | Thunderbolt, eagle |
| Sea | **Poseidon** | Private VPC | Trident, waves |
| Underworld | **Hades** | On-premises | Throne, Cerberus |

Illustrations are dense ASCII engravings derived from black-figure sources (`lib/engravings/`), rendered in sealed frames — unlabeled plates, not cartoons.

---

## Design system

### Typography

Loaded via `next/font` in `app/layout.tsx`.

| Role | Face | Use |
| --- | --- | --- |
| **Display / body** | [Cormorant Garamond](https://fonts.google.com/specimen/Cormorant+Garamond) | Headlines, nav, body — classical serif, light weights, italics for emphasis |
| **Mono / UI** | [Cutive Mono](https://fonts.google.com/specimen/Cutive+Mono) | Kickers, audit log, forms, ASCII plates, technical asides |

Kickers are uppercase, tracked (`letter-spacing: 0.22em`), and used as section labels (`ii - pantheon, the labors`). Headlines use a light display cut; emphasis lines use italic soft ink (`.headline-emph`).

### Color — light theme (default)

True white paper, black ink. One sacred accent: **gilt**.

| Token | Hex | Role |
| --- | --- | --- |
| `--paper` | `#ffffff` | Page ground |
| `--paper-warm` | `#f2f2f2` | Framed panels, mounts |
| `--ink` | `#000000` | Primary text, engravings |
| `--ink-soft` | `#2e2e2e` | Supporting copy |
| `--ink-mute` | `#5c5c5c` | Kickers, secondary |
| `--ink-faint` | `#8f8f8f` | Quiet chrome |
| `--rule` | `#dcdcdc` | Hairlines, seals |
| `--accent` | `#000000` | Primary CTA fill / text |
| `--gilt` | `#a5854a` | Dominion hover / sacred accent |
| `--gilt-glow` | `rgba(165, 133, 74, 0.12)` | Soft radial halos |

### Color — dark theme

Inverse monochrome; gilt shifts slightly brighter.

| Token | Hex |
| --- | --- |
| `--paper` | `#000000` |
| `--paper-warm` | `#101010` |
| `--ink` | `#ffffff` |
| `--ink-soft` | `#d6d6d6` |
| `--ink-mute` | `#9c9c9c` |
| `--rule` | `#2e2e2e` |
| `--gilt` | `#c9a86a` |

Theme toggle uses a short uniform **color cross-fade** (no view-transition ripple). Tokens live in `app/globals.css`.

### Motifs and motion

- **Meander** (Greek key) — section dividers and footer frieze (`components/ui/meander-mark.tsx`)
- **Frame panels** — hairline borders with corner registration seals
- **Paper grain** — fine dotted texture over the ground
- **Traced mark** — SVG path-trace of the brand scales on first load only
- **Lenis** — smooth scrolling; same-page nav hashes scroll in place (no remount)
- **View transitions** — route enter/exit between pages (Contact, docs, etc.)
- **Engraved plates** — static high-density ASCII, full ink, no captions

Avoid: purple gradients, cream/terracotta AI tropes, emoji, pill clusters in the hero.

---

## Site map

### Homepage (`/`)

1. Hero — brand, H1, lede, demo CTA, traced mark
2. Integrations marquee
3. Agent run / Mnemosyne audit log
4. Platform (the labors) + Nemean Lion plate
5. Olympus interlude
6. Runtime (the forge) + Hephaestus plate
7. Deploy (the dominions) + Zeus / Poseidon / Hades plates

### Interior pages

| Path | Intent |
| --- | --- |
| `/platform` | Architecture |
| `/integrations` | Connectors |
| `/security` | Credentials, audit, deployment posture |
| `/faq` | FAQ (+ FAQPage JSON-LD) |
| `/privacy` | Privacy policy |
| `/contact` | Demo request |
| `/solutions/finance-operations` | Use case |
| `/solutions/customer-support` | Use case |
| `/solutions/revenue-operations` | Use case |
| `/deployment/cloud` | Zeus / managed |
| `/deployment/private-vpc` | Poseidon / VPC |
| `/deployment/on-premises` | Hades / air-gapped |

SEO: `app/sitemap.ts`, `app/robots.ts`, canonical URLs, Organization / WebSite / SoftwareApplication JSON-LD. Security headers in `next.config.ts`.

---

## Stack

| Piece | Choice |
| --- | --- |
| Framework | Next.js 16 (App Router, Turbopack) |
| UI | React 19, Tailwind CSS 4 |
| Motion | `motion` (Framer Motion) |
| Scroll | Lenis |
| Theme | `next-themes` (class strategy, light default) |
| Language | TypeScript |

Notable paths:

```text
app/                     routes, layout, globals.css, SEO files
components/              hero, nav, deploy, plates, forms
lib/engravings/          dense ASCII plates (zeus, poseidon, hades, ...)
lib/scroll-to-section.ts same-page section navigation
public/                  logo-mark.svg, icons
```

---

## Local development

```bash
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

| Script | Purpose |
| --- | --- |
| `npm run dev` | Development server |
| `npm run build` | Production build |
| `npm run start` | Serve production build |
| `npm run lint` | ESLint |

Contact form posts to `/api/contact` (JSON or form-urlencoded). Keep secrets in `.env.local` — never commit them.

---

## Brand voice (for copy)

- Category-first in titles and H1s (*AI agent orchestration*, *backend-native*, *auditable*).
- Mythology as the brand layer in kickers and plates — not a substitute for search language.
- Prefer Roman numerals, meander ornaments, and plate-like figures over icons and emoji.
- One job per section; hero stays spare (brand, one headline, one lede, one CTA group, one mark).

---

<div align="center">

<pre>
  .-.   .-.   .-.   .-.   .-.   .-.   .-.
 (   \ /   \ /   \ /   \ /   \ /   \ /   )
  '-'   '-'   '-'   '-'   '-'   '-'   '-'
</pre>

<p><em>forged on pantheon</em></p>

<p>&copy; Obsidura &middot; <a href="https://obsidura.com">obsidura.com</a></p>

</div>
