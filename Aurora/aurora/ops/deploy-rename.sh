#!/usr/bin/env bash
#
# Chunk 2's production restart: the tai-review -> aurora rename and deploy.
#
# THIS SCRIPT LIVES IN THE REPO ON PURPOSE. An earlier version of it sat in
# /tmp and was referenced from the ledger as though it were an artefact. /tmp
# here is tmpfs, so it evaporated and the reference dangled. Anything a human
# is expected to run during an outage belongs under version control.
#
# WHAT IT DOES, and why the order is fixed:
#   1. Point production at the reviewed commit WITHOUT merging to main.
#   2. Tear the OLD project down while .env still names it.
#   3. Rename the directory - this is the rename; Compose derives the project
#      from the directory basename unless COMPOSE_PROJECT_NAME says otherwise.
#   4. Repair the git worktrees, whose links are stored ABSOLUTELY.
#   5. Declare the new project name.
#   6. Bring the new project up.
#
# EXPECTED DOWNTIME: 60-90 seconds. Everything on the tailnet host is
# unavailable for the whole window - /git/, /affine/, /agent/*, the fjell
# landing page, the Hermes dashboards. This is a full down/up rather than a
# rolling recreate because com.docker.compose.project is fixed at container
# CREATE time: no running container can be moved between projects.
#
# YOU MUST RUN THIS WITH AURORA_ALLOW_PROD=1:
#
#     AURORA_ALLOW_PROD=1 bash ops/deploy-rename.sh
#
# ops/docker-guard refuses destructive commands that are not provably scoped
# to a br-* project, and tearing production down is exactly what it exists to
# stop. The override is the intended human escape hatch. Without it step 2
# fails with exit 13 and the script stops before touching anything.
#
# PRE-FLIGHT is enforced below, not assumed. Nothing here is cheaply
# reversible once the stack is down.

set -euo pipefail

PROD="${PROD:-$HOME/Desktop/tai-review}"
NEW="${NEW:-$HOME/Desktop/aurora}"
REF="${REF:-feat/chunk3-ephemeral-branching}"

say() { printf '\n=== %s ===\n' "$1"; }

if [ "${AURORA_ALLOW_PROD:-}" != "1" ]; then
  echo "REFUSED: re-run as  AURORA_ALLOW_PROD=1 bash ops/deploy-rename.sh" >&2
  echo "  (ops/docker-guard blocks production teardown; this is the override)" >&2
  exit 13
fi

say "pre-flight"
[ -d "$PROD" ] || { echo "no production checkout at $PROD" >&2; exit 1; }
[ -e "$NEW" ] && { echo "$NEW already exists - something is half-renamed; STOP" >&2; exit 1; }
cd "$PROD"

# The agent homes must already carry the destination project's prefix, or the
# agents boot on empty volumes. Both generations were restored on 2026-07-29.
#
# Derived from developers.yaml, never hardcoded: this list was literally
# `testuser newuser cumshit42069` until those two accounts were deleted on
# 2026-07-30, at which point a roster written into the script would have
# aborted the rename during the outage window over volumes that are SUPPOSED
# to be gone. The empty-list guard matters as much as the loop -- a `for` over
# nothing succeeds silently, which is the failure this check exists to catch.
devs=$(sed -n 's/^  username: //p' dev-administration/developers.yaml)
[ -n "$devs" ] || { echo "developers.yaml lists no developers; STOP" >&2; exit 1; }
for u in $devs; do
  docker volume inspect "aurora_hermes-$u-home" >/dev/null 2>&1 \
    || { echo "missing volume aurora_hermes-$u-home - seeding incomplete; STOP" >&2; exit 1; }
done
grep -q '^COMPOSE_PROJECT_NAME=tai-review$' .env \
  || { echo ".env does not name the OLD project; read it before proceeding" >&2; exit 1; }
echo "pre-flight OK"

say "1. point production at $REF (NO merge to main)"
# --detach, not checkout: the branch is held by a linked worktree, and this
# deliberately leaves main untouched so the merge stays the user's decision.
git checkout --detach "$REF"
git log --oneline -1

say "2. tear down the OLD project"
# --profile '*' is belt-and-braces: Compose v5.3.1's down was measured to be
# profile-agnostic, but relying on undocumented behaviour for a teardown is
# not a trade worth making.
docker compose --profile '*' down --remove-orphans
remaining=$(docker ps -a --filter label=com.docker.compose.project=tai-review -q | wc -l)
echo "containers still labelled tai-review: $remaining"
[ "$remaining" -eq 0 ] || { echo "something survived; NOT renaming" >&2; exit 1; }

say "3. rename the directory"
cd "$HOME"
mv "$PROD" "$NEW"
ls -d "$NEW"

say "4. repair the worktrees (EXPLICIT paths - a bare repair silently no-ops here)"
cd "$NEW"
git worktree repair .worktrees/* || true
git worktree list

say "5. declare the new project name"
sed -i 's/^COMPOSE_PROJECT_NAME=tai-review$/COMPOSE_PROJECT_NAME=aurora/' .env
grep -n '^COMPOSE_PROJECT_NAME=' .env
docker compose config --quiet && echo "CONFIG_OK"

say "6. bring the NEW project up"
mkdir -p "$NEW/.agent-env"
docker compose up -d

say "verify"
docker ps --format '{{.Names}}' | sort
curl -s -o /dev/null -w 'git=%{http_code}\n' --max-time 20 "https://$(grep -m1 '^DOMAIN_NAME=' .env | cut -d= -f2)/git/"
echo
echo "dev-admin should be exited(0). If it is exited(1), read its logs before"
echo "assuming the rename caused it - Chunk 2 Task 11 fixed a startup race and"
echo "the compose.agents.yml mount was fixed in 5ab7fbb."
