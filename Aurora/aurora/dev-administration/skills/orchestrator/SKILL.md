---
name: orchestrator
description: "Provision and manage per-developer Hermes containers. Use when asked about developer onboarding, container lifecycle, or system reconciliation."
---

# Aurora Dev Administration

Use `dev-admin` CLI to manage developer containers.

## Commands

### reconcile
Reads `developers.yaml`, diffs against Docker state, applies changes.
Provisions new developers, deprovisions removed ones, verifies existing ones.
Idempotent — safe to run repeatedly.

```bash
dev-admin reconcile
```

### status
Shows all developers, their containers, volumes, and health status.

```bash
dev-admin status
```

### add
Add a developer entry to `developers.yaml`. Does not provision —
run `reconcile` after adding.

```bash
dev-admin add <username> --display-name "Full Name" --forgejo-user <forgejo_username>
```

### remove
Remove a developer entry from `developers.yaml`. Does not deprovision —
run `reconcile` after removing.

```bash
dev-admin remove <username>
```

### deprovision
Stop a developer's container immediately. Volume is preserved.

```bash
dev-admin deprovision <username>
```

## Config format (developers.yaml)

```yaml
developers:
  - username: juan
    display_name: Juan Martinez
    forgejo_user: juan
```

No secrets in this file. Developers provide their own API keys and SSH keys
via the fjell setup form at `/agent/<username>/setup`.

## Events emitted

| Event type | Severity | When |
|---|---|---|
| `volume.created` | info | New Docker volume created |
| `oauth2.created` | info | New Forgejo OAuth2 app created |
| `developer.provisioned` | info | Container started for a developer |
| `container.unhealthy` | warning | Existing container not responding |
| `volume.orphaned` | warning | Container stopped, volume preserved |

## When to use

- New developer added to `developers.yaml` → run `reconcile`
- Developer removed → `reconcile` handles deprovisioning automatically
- Routine health check → `status` or `doctor` (can be cron-scheduled)
- Master orchestrator Hermes can call any of these as shell commands
