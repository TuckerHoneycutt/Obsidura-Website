# Multi-Developer Setup (admin)

## Prerequisites

- Forgejo running with admin access
- Aurora stack deployed (`docker compose up -d`)
- `FORGEJO_ADMIN_TOKEN` in `.env`
- `dev-administration` repo present at `./dev-administration/`

## Adding a developer

1. Add the developer to `developers.yaml`:

```bash
docker exec dev-admin python -m dev_administration.cli add juan --display-name "Juan Martinez" --forgejo-user juan
```

2. Run reconcile:

```bash
docker exec dev-admin python -m dev_administration.cli reconcile
```

3. Create a Forgejo account for the developer (if not already):
   Forgejo → Site Administration → Users → New User

4. Tell the developer to visit:
   `https://superserver.tailc67a98.ts.net/agent/<username>/setup`
   They provide their OpenRouter API key and (optional) SSH public key.

5. Verify: `docker exec dev-admin python -m dev_administration.cli status`

6. Grant the repositories — a token proves identity and grants nothing, so
   without this they authenticate fine and see no repo at all:

```bash
docker exec dev-admin python -m dev_administration.cli access authorize juan -p read
```

   `-p read` because `-p write` (the default) is refused while the repo's
   default branch has no protection rule, and none of them do yet.

7. Tell them to change their Forgejo password and mint a token:
   `docs/setup/user/forgejo-setup.md`.

8. (Optional) Let them spawn their own stacks:
   `docs/post-implementation-steps.md` §10.

Commands, flags and what `authorize` refuses: `USERGUIDE.md` §2.

## Removing a developer

1. Remove from `developers.yaml`:

```bash
docker exec dev-admin python -m dev_administration.cli remove juan
```

2. Run reconcile:

```bash
docker exec dev-admin python -m dev_administration.cli reconcile
```

Container is stopped. Volume is preserved. Admin can manually clean up:
`docker volume rm hermes-juan-home`

3. **`reconcile` cannot delete their token** — Forgejo answers 401 to an admin
   token on that route. It removes their repository access and emits a
   `token.orphaned` warning. Finish the job yourself:

```bash
docker exec dev-admin python -m dev_administration.cli access suspend juan
docker exec dev-admin python -m dev_administration.cli access ls juan
```

   `suspend` is reversible by `restore`; only the developer can `revoke`.

4. Stop their spawn broker if one is running, and destroy any stack they still
   have: `./aurora dev-spawn ls`.

## Scheduled health check (cron)

```bash
0 * * * * docker exec dev-admin python -m dev_administration.cli reconcile
```

This reconciles state and restarts unhealthy containers.

## Developer SSH access

Developers can SSH into their own container:

```bash
ssh <username>@superserver.tailc67a98.ts.net -p 222
```

This drops them directly into their Hermes container via a forced `docker exec` command.
No host shell access. They must provide their SSH public key via the setup form first.
