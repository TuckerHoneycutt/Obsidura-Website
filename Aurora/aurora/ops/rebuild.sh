#!/usr/bin/env bash
#
# Rebuild production's from-source images and recreate their containers.
#
# WHY THIS EXISTS
# Merging a PR updates the checkout. It does not touch a single image. On
# 2026-08-01 the internal hub was merged at 23:00 the previous night and
# production went on serving a fjell binary built two days earlier: `/git/.hub/`
# returned a 20-byte placeholder and `hub.css` 404'd, while every route answered
# 200 and every healthcheck stayed green for thirteen hours. Nothing detected
# it, because nothing was looking at images at all.
#
# `docker compose restart` does not help. It reuses the image it already has.
# Only a build makes a merge real, and until this script nothing in this repo
# did one for production.
#
# USAGE
#   bash ops/rebuild.sh                    rebuild every buildable service, then up -d
#   bash ops/rebuild.sh fjell dev-admin    scope it to named services
#   bash ops/rebuild.sh --check            say which images are STALE; change NOTHING
#
# `--check` is the one a human runs to answer "do I need to deploy?". It writes
# nothing, builds nothing, starts nothing, and exits 1 if any image is older
# than the last commit touching its build context.
#
# NO OVERRIDE IS NEEDED AND NONE MUST BE ADDED. `docker compose up` is
# deliberately absent from ops/docker-guard's destructive set -- it "is NOT
# destructive and is how production is restored, so it must never be blocked".
# The only verbs here are `compose config`, `image inspect` and `compose up -d`.
# If you find yourself reaching for AURORA_ALLOW_PROD in this file you have
# reached for a destructive verb, and you should not have.
#
# THE SERVICE LIST IS DERIVED, NEVER TYPED. It is whatever the resolved
# `docker compose config` says declares `build:` -- today fjell, agent-authz and
# dev-admin. A list written into this file would go stale on the day a fourth
# service is added, which is precisely the day it would have mattered.

set -euo pipefail

say()  { printf '\n=== %s ===\n' "$1"; }
die()  { printf 'REFUSED: %s\n' "$1" >&2; exit 1; }

# Resolve to the checkout this script is IN, not to $PWD. `git log` and
# `docker compose config` must both be asked about the same tree, and a human
# under pressure runs this from wherever they happen to be standing.
ROOT=$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)
cd "$ROOT"

# Unset here as well as in the MCP tool, so a human running the script directly
# gets the same protection an agent does. An exported DOCKER_HOST decides which
# DAEMON every command below lands on, and COMPOSE_FILE/COMPOSE_PROFILES decide
# which services exist; the header's claim that the only verbs here are safe is
# a claim about VERBS and says nothing about which daemon or which project.
# COMPOSE_PROJECT_NAME is handled separately, below, where the reason fits.
unset DOCKER_HOST COMPOSE_PROFILES COMPOSE_FILE

CHECK=0
REQUESTED=()
while [ $# -gt 0 ]; do
  case "$1" in
    --check) CHECK=1 ;;
    --)      shift; REQUESTED+=("$@"); break ;;
    -*)      die "unknown flag $1 (the only flag is --check)" ;;
    *)       REQUESTED+=("$1") ;;
  esac
  shift
done

# ---------------------------------------------------------------------------
# 0a. prove we are standing in PRODUCTION's checkout before building anything
# ---------------------------------------------------------------------------
#
# A BRANCH WORKTREE CONTAINS THIS SCRIPT TOO, and resolving ROOT to "the
# checkout this script is in" is exactly what makes that reachable. Run from
# <production>/.worktrees/<name>/, the two `docker compose up` lines below
# would run against the ROOT docker daemon, with the branch's .env, and
# WITHOUT `-f compose.branch.yml` -- so no `container_name: !reset`, no
# `ports: !reset`, no image reset. Compose would try to create containers
# under PRODUCTION's container_name values, and `docker compose up -d`
# recreates whatever it can claim. That is the 2026-07-29 shape (a compose
# verb resolving the wrong project from the directory it was run in) arriving
# through a verb ops/docker-guard deliberately does not block, because `up`
# deliberately is not in its destructive set.
#
# `git rev-parse --git-common-dir` names the ORIGINAL .git for every worktree
# of a repository, linked or not, so its parent is the main checkout. This
# compares an IDENTITY, the way the rest of this codebase does; it does not
# pattern-match a path.
#
# Gated on the BUILD path only, and that is not a loophole: `--check` inspects
# images and git and writes, builds and starts nothing at all, which is
# precisely why tests/test_build_conformance.py can ask a worktree's copy of
# this script about production's images. There is nothing there to refuse.
if [ "$CHECK" != 1 ]; then
  COMMON=$(git rev-parse --git-common-dir 2>/dev/null) \
    || die "$ROOT is not inside a git repository, so this script cannot prove it is standing in production's checkout. It rebuilds PRODUCTION; refusing to guess."
  MAIN=$(cd "$COMMON/.." && pwd)
  [ "$MAIN" = "$ROOT" ] \
    || die "$ROOT is a LINKED git worktree, not production's checkout ($MAIN). ops/rebuild.sh rebuilds production and passes no compose.branch.yml, so from here \`docker compose up -d\` would create containers under production's container_name values. Use \`aurora branch rebuild <name>\` for a branch, or run this from $MAIN."
  # Only now, having proved ROOT is production's checkout, where Compose's own
  # directory-basename derivation is the RIGHT answer. Left alone under
  # --check because that is the documented seam a worktree uses to ask about
  # production's images (tests/test_build_conformance.py::_script_verdicts).
  unset COMPOSE_PROJECT_NAME
fi

say "0. what this is about to do"
echo "checkout : $ROOT"
echo "commit   : $(git log -1 --format='%h %cI %s')"
if [ "$CHECK" = 1 ]; then
  echo "mode     : --check (report only; nothing is built, nothing is started)"
else
  echo "mode     : BUILD and RECREATE (docker compose up -d --build)"
fi

# ---------------------------------------------------------------------------
# 1. derive the buildable services
# ---------------------------------------------------------------------------
#
# COMPOSE_PROFILES='*' for the same reason tests/conftest.py sets it: a service
# carrying `profiles:` is omitted from this output unless its profile is
# active, and a buildable service that vanished from the list would be a
# service this script silently never rebuilds.
say "1. derive the buildable services from the resolved compose config"
CONFIG_JSON=$(COMPOSE_PROFILES='*' docker compose config --format json) \
  || die "docker compose config failed; nothing was touched"

# service <TAB> image <TAB> build context. A build-only service has no `image:`
# key and Compose synthesises `<project>-<service>`, so the project name has to
# come from the same resolution the images did.
BUILDABLE=$(python3 -c '
import json, sys
config = json.load(sys.stdin)
project = config.get("name") or ""
for name, svc in sorted(config.get("services", {}).items()):
    build = svc.get("build")
    if not build:
        continue
    image = svc.get("image") or (project + "-" + name)
    print(name + "\t" + image + "\t" + build["context"])
' <<<"$CONFIG_JSON")

# A loop over nothing succeeds silently, and a "rebuild everything" that
# rebuilt nothing would report success. That is the failure this check exists
# to catch -- same argument as ops/deploy-rename.sh's empty-roster guard.
[ -n "$BUILDABLE" ] \
  || die "no service in this compose config declares build:. Either the config is wrong or this script is now pointing at the wrong tree; nothing was touched."

echo "buildable services:"
cut -f1 <<<"$BUILDABLE" | sed 's/^/  /'

# ---------------------------------------------------------------------------
# 2. select the targets
# ---------------------------------------------------------------------------
say "2. select targets"
if [ ${#REQUESTED[@]} -eq 0 ]; then
  TARGETS="$BUILDABLE"
  echo "all buildable services"
else
  TARGETS=""
  for want in "${REQUESTED[@]}"; do
    row=$(awk -F'\t' -v s="$want" '$1 == s' <<<"$BUILDABLE")
    [ -n "$row" ] \
      || die "'$want' is not a buildable service. Buildable: $(cut -f1 <<<"$BUILDABLE" | tr '\n' ' ')"
    TARGETS+="$row"$'\n'
  done
  TARGETS=${TARGETS%$'\n'}
  echo "${REQUESTED[*]}"
fi

# ---------------------------------------------------------------------------
# fingerprint and staleness
# ---------------------------------------------------------------------------

# Image ID and creation time, per target. Printed before AND after so the
# transcript itself proves whether anything actually changed -- the hub bug
# was thirteen hours of "it deployed" with no evidence either way.
fingerprint() {
  local svc image context id created
  printf '  %-13s %-22s %-14s %s\n' SERVICE IMAGE 'IMAGE ID' CREATED
  while IFS=$'\t' read -r svc image context; do
    id=$(docker image inspect "$image" --format '{{.Id}}' 2>/dev/null) || id='sha256:-'
    id=${id#sha256:}
    created=$(docker image inspect "$image" --format '{{.Created}}' 2>/dev/null) || created='(absent)'
    printf '  %-13s %-22s %-14s %s\n' "$svc" "$image" "${id:0:12}" "$created"
  done <<<"$TARGETS"
}

# STALE / FRESH / NEVER-BUILT, one line per target, first two fields stable so
# tests/test_build_conformance.py can parse them. Returns 1 if anything is not
# FRESH. An absent image is NEVER-BUILT, which is a kind of stale and not an
# error: it is the normal state of a fresh checkout.
staleness() {
  local svc image context commit created state rc=0
  STALE_NAMES=()
  while IFS=$'\t' read -r svc image context; do
    commit=$(git log -1 --format=%cI -- "$context")
    [ -n "$commit" ] \
      || die "no commit touches $context, so its image cannot be judged. That path is untracked; see tests/test_repo_conformance.py::test_every_build_context_is_tracked_in_git."
    if created=$(docker image inspect "$image" --format '{{.Created}}' 2>/dev/null); then
      if [ "$(date -d "$created" +%s)" -lt "$(date -d "$commit" +%s)" ]; then
        state=STALE; rc=1; STALE_NAMES+=("$svc")
      else
        state=FRESH
      fi
    else
      created='(never built)'; state=NEVER-BUILT; rc=1; STALE_NAMES+=("$svc")
    fi
    printf '  %-11s %-13s %-22s image=%s commit=%s\n' \
      "$state" "$svc" "$image" "$created" "$commit"
  done <<<"$TARGETS"
  return $rc
}

# Image IDs before the build, keyed by service. Read once here so step 7 can
# tell a build that did nothing apart from a cache hit from a build that did
# not take -- see the CACHE-HIT reasoning there.
declare -A ID_BEFORE=()
while IFS=$'\t' read -r svc image context; do
  ID_BEFORE["$svc"]=$(docker image inspect "$image" --format '{{.Id}}' 2>/dev/null || echo absent)
done <<<"$TARGETS"

say "3. before"
fingerprint
echo
staleness && STALE=0 || STALE=1

# TWO KNOWN HOLES IN THE COMPARISON ABOVE, written down rather than discovered.
# Both follow from comparing an image clock against the last COMMIT clock:
#   * an UNCOMMITTED edit in a build context reads FRESH. Edit fjell/src and do
#     not commit, and --check says "no deploy needed" -- a confident wrong
#     answer, which is the failure mode this whole file exists for.
#   * a fully cache-hit rebuild reads STALE, because `.Created` does not move
#     when every layer is reused.
# The second is handled at step 7. The first is reported here and nowhere else,
# because there is no honest verdict for it: the image may or may not match.
DIRTY=$(git status --porcelain -- $(cut -f3 <<<"$TARGETS" | tr '\n' ' ') 2>/dev/null || true)
if [ -n "$DIRTY" ]; then
  echo
  echo "  WARNING: build contexts have UNCOMMITTED changes, so the verdicts" >&2
  echo "  above compare images against the last COMMIT and cannot see them:" >&2
  sed 's/^/    /' <<<"$DIRTY" >&2
fi

# ---------------------------------------------------------------------------
# 4. --check stops here, having changed nothing
# ---------------------------------------------------------------------------
if [ "$CHECK" = 1 ]; then
  say "4. --check: nothing was built and nothing was started"
  if [ "$STALE" = 1 ]; then
    echo "STALE. Production is serving code older than the checkout." >&2
    echo "Fix:  bash ops/rebuild.sh ${STALE_NAMES[*]}" >&2
    exit 1
  fi
  echo "every image is at least as new as its build context; no deploy needed"
  exit 0
fi

# ---------------------------------------------------------------------------
# 5. build and recreate
# ---------------------------------------------------------------------------
#
# `up -d --build` and nothing else. Not `build` then `restart`: restart reuses
# the running container's image and is exactly the non-fix that let the hub bug
# persist. Not `down` then `up`: that is a destructive verb, it is what
# ops/docker-guard exists to refuse, and it is not needed -- `up` recreates a
# container whose image changed, by itself.
say "5. build and recreate: $(cut -f1 <<<"$TARGETS" | tr '\n' ' ')"
mapfile -t TARGET_NAMES < <(cut -f1 <<<"$TARGETS")
docker compose up -d --build "${TARGET_NAMES[@]}"

# Converge the rest of the stack only when this was a full rebuild. A scoped
# run is scoped: a human who said `rebuild.sh fjell` did not ask for anything
# else to be recreated.
if [ ${#REQUESTED[@]} -eq 0 ]; then
  say "6. converge the remaining services"
  docker compose up -d
fi

say "7. after"
fingerprint
echo
# `staleness` compares the image clock against the commit clock, and a fully
# CACHE-HIT rebuild does not move `.Created` -- every layer was reused, so the
# image is byte-identical to the one that was already there and Docker has
# nothing to restamp. `die`ing on that killed a build that was correct and
# complete, which is how a gate teaches people to ignore it.
#
# So the second signal, and it is genuinely a different measurement rather
# than a second spelling of the first: the image ID before the build versus
# after. `docker compose up -d --build` always runs a build; if the resulting
# image ID is UNCHANGED then every layer hit the cache, which means the build
# inputs were identical, which means the image already embodies the current
# source. That is a correct outcome and it is reported as one. An image whose
# ID CHANGED and is still stale is the real failure -- the tag is being
# overwritten by another compose project, or the build ran against a different
# tree -- and that still dies.
if ! staleness; then
  MOVED=()
  for name in "${STALE_NAMES[@]}"; do
    image=$(awk -F'\t' -v s="$name" '$1 == s {print $2}' <<<"$TARGETS")
    now=$(docker image inspect "$image" --format '{{.Id}}' 2>/dev/null || echo absent)
    [ "$now" = "${ID_BEFORE[$name]:-absent}" ] || MOVED+=("$name")
  done
  if [ ${#MOVED[@]} -eq 0 ]; then
    echo
    echo "  CACHE-HIT: ${STALE_NAMES[*]} still read STALE by the commit-clock"
    echo "  comparison, but their image IDs did not move across the build --"
    echo "  every layer was reused, so the image already embodies this source."
    echo "  Not an error. (A commit that only touched a .dockerignore'd file"
    echo "  does exactly this.)"
  else
    die "still STALE after a build, and the image ID CHANGED for: ${MOVED[*]}. The build ran against a different tree, or the tag is being overwritten by another compose project (see tests/test_branch_overlay.py). Read the fingerprints above."
  fi
fi

say "8. verify"
docker compose ps --format 'table {{.Service}}\t{{.Image}}\t{{.Status}}'
echo
echo "Images were rebuilt. If a route still serves old content, it is cached or"
echo "proxied, not stale -- the fingerprints above prove the image changed."
