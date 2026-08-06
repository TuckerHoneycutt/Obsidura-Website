# Obsidura

Company monorepo for the public site and internal Aurora systems.

```text
website/          Obsidura marketing site (Next.js)
Aurora/
  aurora/         Aurora platform / ops stack
  aurora-agent/   Agent skills, pipelines, and plugins
```

## Website

Public marketing site for [obsidura.com](https://obsidura.com).

```bash
cd website
npm install
npm run dev
```

See [website/README.md](website/README.md) for brand, stack, and page structure.

If you deploy with Vercel (or similar), set the project **Root Directory** to `website`.

## Aurora

Internal company systems under `Aurora/`. Each package has its own README:

- [Aurora/aurora/README.md](Aurora/aurora/README.md)
- [Aurora/aurora-agent/README.md](Aurora/aurora-agent/README.md)
