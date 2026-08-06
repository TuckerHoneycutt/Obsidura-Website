#!/usr/bin/env bash
# Test ops/docker-guard against a STUB docker, never the real one.
#
# This is the direct lesson of the 2026-07-29 incident: the test that
# destroyed production proved a guard worked by actually invoking the call it
# guards against, which is safe only while every guard holds -- precisely the
# condition under test. Here, a broken guard prints a FAIL line.
mkdir -p /tmp/gtest/bin
cat > /tmp/gtest/bin/docker <<'STUB'
#!/bin/sh
# The guard resolves an object's compose project with `<kind> inspect -f ...`.
# Answer ONLY that form, and answer it BY NAME, so a production object still
# looks like production. A stub that called everything a branch would make the
# guard look correct while it waved production through.
case "$*" in
  *inspect*-f*)
    for a in "$@"; do last="$a"; done
    case "$last" in
      br-*) echo "br-guardtest-probe" ;;
      *)    echo "tai-review" ;;
    esac
    ;;
  *) echo "STUB-DOCKER-EXECUTED" ;;
esac
STUB
chmod +x /tmp/gtest/bin/docker
cp ~/.local/bin/docker /tmp/gtest/docker-guard
chmod +x /tmp/gtest/docker-guard

fail=0

check () {
  want="$1"; desc="$2"; shift 2
  out=$(PATH=/tmp/gtest/bin:/usr/bin /tmp/gtest/docker-guard "$@" 2>&1); rc=$?
  got="REFUSED"
  echo "$out" | grep -q "STUB-DOCKER-EXECUTED" && got="PASSTHROUGH"
  if [ "$got" = "$want" ]; then
    printf '  ok    %-46s %s\n' "$desc" "$got"
  else
    printf '  FAIL  %-46s got=%s want=%s (rc=%s)\n' "$desc" "$got" "$want" "$rc"
    fail=1
  fi
}

echo "=== must REFUSE (destructive, not provably branch-scoped) ==="
check REFUSED "the exact incident command" compose --profile '*' -p tai-review down -v --remove-orphans
check REFUSED "bare compose down -v"         compose down -v
check REFUSED "compose down (no -v)"         compose down
check REFUSED "volume rm production volume"  volume rm tai-review_caddy_data
check REFUSED "system prune -af"             system prune -af
check REFUSED "stop a production container"  stop forgejo
check REFUSED "rm -f a production container" rm -f forgejo
check REFUSED "compose -p aurora down"       compose -p aurora down -v

echo "=== must PASS THROUGH (read-only, recovery, or branch-scoped) ==="
check PASSTHROUGH "ps -a"                    ps -a
check PASSTHROUGH "compose up -d (RECOVERY)" compose up -d
check PASSTHROUGH "compose config --quiet"   compose config --quiet
check PASSTHROUGH "inspect forgejo"          inspect forgejo
check PASSTHROUGH "volume ls"                volume ls
check PASSTHROUGH "logs forgejo"             logs forgejo
check PASSTHROUGH "compose -p br-x down -v"  compose -p br-x down -v
check PASSTHROUGH "--project-name=br-y down" --project-name=br-y down
check PASSTHROUGH "rm -f a br- container"    rm -f br-guardtest-probe
check PASSTHROUGH "stop a br- container"     stop br-guardtest-probe

echo "=== F2: an env var must NOT prove branch scope for by-name verbs ==="
# Until 2026-07-29 every one of these was ALLOWED. COMPOSE_PROJECT_NAME was
# accepted as proof of branch scope, but `volume rm` / `rm` / `stop` ignore the
# compose project entirely -- they act on the NAME. The 5-7 review measured it.
envcheck () {
  want="$1"; desc="$2"; shift 2
  out=$(PATH=/tmp/gtest/bin:/usr/bin COMPOSE_PROJECT_NAME=br-x /tmp/gtest/docker-guard "$@" 2>&1)
  got="REFUSED"
  echo "$out" | grep -q "STUB-DOCKER-EXECUTED" && got="PASSTHROUGH"
  if [ "$got" = "$want" ]; then
    printf '  ok    %-46s %s\n' "$desc" "$got"
  else
    printf '  FAIL  %-46s got=%s want=%s\n' "$desc" "$got" "$want"; fail=1
  fi
}
envcheck REFUSED "env br- + volume rm production volume" volume rm tai-review_caddy_data
envcheck REFUSED "env br- + rm -f production container"  rm -f forgejo
envcheck REFUSED "env br- + stop production container"   stop forgejo
envcheck REFUSED "env br- + system prune -af"            system prune -af
# A compose subcommand IS project-scoped by construction, so -p br-x is real
# proof there. The env var alone still is not.
check PASSTHROUGH "compose -p br-x down -v (flag, scoped)" compose -p br-x down -v
envcheck REFUSED "env br- + bare compose down"           compose down -v

echo "=== F1: a br--NAMED object with NO project label ==="
# The stub answers `inspect -f` by NAME: anything not starting with br- is
# reported as production. To model "no label at all" we ask about a br- name,
# which the stub reports as br-guardtest-probe; the NAME rule is what must
# carry it, so also assert a production name in the same list still refuses.
check PASSTHROUGH "volume rm br-x_data (name-only proof)" volume rm br-x_data
check PASSTHROUGH "rm -f br-x-caddy-1"                    rm -f br-x-caddy-1
check REFUSED "mixed list: one br-, one production"       rm -f br-x-caddy-1 forgejo

echo "=== prunes are never object-scoped ==="
check REFUSED "volume prune"                 volume prune
check REFUSED "network prune"                network prune
check REFUSED "container prune"              container prune

echo "=== human override ==="
out=$(PATH=/tmp/gtest/bin:/usr/bin AURORA_ALLOW_PROD=1 /tmp/gtest/docker-guard compose -p tai-review down -v 2>&1)
if echo "$out" | grep -q "STUB-DOCKER-EXECUTED"; then
  printf '  ok    %-46s PASSTHROUGH\n' "AURORA_ALLOW_PROD=1"
else
  printf '  FAIL  %-46s refused\n' "AURORA_ALLOW_PROD=1"; fail=1
fi

echo
if [ "$fail" -eq 0 ]; then echo "ALL GUARD TESTS PASSED"; else echo "*** GUARD TESTS FAILED ***"; fi
exit $fail
