#!/usr/bin/env bash
# Test the DEVELOPER MCP surface against a STUB docker and a FAKE production
# root. Never the real daemon, never the real checkout.
#
# This is `ops/guardtest.sh`'s lesson applied one layer up. That script exists
# because a guard tested against a live daemon has its failure mode as the
# thing it guards against: the first version passed the incident command
# straight through, and a live-daemon test would have destroyed production a
# second time to discover it.
#
# Here the thing under test is "a developer's frames cannot leave their
# namespace". Proving that against the real host would mean issuing
# `docker compose -p ... down -v` and inspecting the wreckage afterwards. So:
#
#   * PATH gets a stub `docker` that EXECUTES NOTHING and LOGS ITS ARGV;
#   * everything runs against a throwaway git repo in /tmp, which is what
#     `identity.production_root()` resolves to, so even a fully disarmed run
#     writes only into /tmp;
#   * the roster is SYNTHETIC and has TWO developers, `alice` and `bob`. The
#     live roster has one, and a cross-tenant test on a one-developer roster
#     is vacuous.
#
# THE CENTRAL ASSERTION IS NOT "IT WAS REFUSED". A developer asking to destroy
# `bob-thing` is not refused -- the label lands in their OWN namespace and
# `br-alice-bob-thing` is torn down. That is the design: containment by
# construction, so the hostile input has nowhere to go. The assertion is
# therefore over the ARGV the daemon would have seen: every object named must
# be `br-alice-*`, and nothing may name `aurora` or `br-bob-*`.
#
# THE MUTATIONS ARE PART OF THE TEST. M2 asserts the tripwire FIRES, because a
# harness that has never once seen a mutating docker verb cannot claim to have
# proven their absence.
set -uo pipefail

#: How much of a frame a failure message quotes: enough to see the
#: refusal and its reason, short enough to stay readable.
EXCERPT=220

WORK="${TMPDIR:-/tmp}/devspawntest"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
rm -rf "$WORK"
mkdir -p "$WORK/bin" "$WORK/root/.worktrees" "$WORK/root/dev-administration" \
         "$WORK/root/aurora-cli" "$WORK/mut"

# --- the stub daemon -------------------------------------------------------
# Logs every invocation and EXECUTES NOTHING.
#
# It must INVENT OBJECTS for whatever project it is asked about, and that is
# not decoration. A stub answering every enumeration emptily makes the teardown
# path issue no `rm` at all, so "no mutating docker call was made" would pass
# on a completely disarmed server -- the vacuous-filter shape from the
# practices note, in a shell script. Measured: with an empty stub, mutation M2
# could not make the tripwire fire.
#
# It also reports ONE PRE-EXISTING STACK owned by alice, so the quota case is
# a real refusal rather than arithmetic on an empty list.
cat > "$WORK/bin/docker" <<'STUB'
#!/bin/sh
echo "$@" >> "$DOCKER_LOG"
proj=""
bare_label=0
for a in "$@"; do
  case "$a" in
    label=com.docker.compose.project=*) proj="${a#label=com.docker.compose.project=}" ;;
    label=com.docker.compose.project)   bare_label=1 ;;
    name=*)                             proj="${a#name=}" ;;
  esac
done
case "$1 $2" in
  "ps -aq"|"ps -q")
      [ "$bare_label" = 1 ] && { echo "occupied-stub-1"; exit 0; }
      [ -n "$proj" ] && echo "${proj}-stub-1"
      exit 0 ;;
esac
case "$1" in
  inspect) echo "br-alice-occupied"; exit 0 ;;
esac
case "$1 $2 $3" in
  "volume ls -q")  [ -n "$proj" ] && echo "${proj}_stubvol"; exit 0 ;;
  "network ls -q") [ -n "$proj" ] && echo "${proj}_stubnet"; exit 0 ;;
esac
exit 0
STUB
chmod +x "$WORK/bin/docker"

# --- the fake production root ---------------------------------------------
printf 'COMPOSE_PROJECT_NAME=aurora\nDOMAIN_NAME=fake.example.ts.net\n' \
    > "$WORK/root/.env.template"
# A `.env` as well as the template: `identity.tailnet_suffix()` reads the live
# one. Without it EVERY case below failed with an IdentityError from
# `tailnet_suffix()`, which `isError:true` alone reported as a successful
# refusal -- the sequential-guard shape from the practices note, caught in this
# harness by its own first run. Hence also: every check asserts on the MESSAGE.
cp "$WORK/root/.env.template" "$WORK/root/.env"
cat > "$WORK/root/dev-administration/developers.yaml" <<'YAML'
developers:
- display_name: alice
  forgejo_user: alice
  username: alice
- display_name: bob
  forgejo_user: bob
  username: bob
YAML
ln -sf dev-administration/developers.yaml "$WORK/root/developers.yaml"
cp "$REPO_ROOT/branch-env.yaml" "$REPO_ROOT/branch-services.yaml" "$WORK/root/"
cp -a "$REPO_ROOT/aurora-cli/aurora_cli" "$WORK/root/aurora-cli/aurora_cli"
git -C "$WORK/root" init -q
git -C "$WORK/root" config user.email t@example.invalid
git -C "$WORK/root" config user.name t
git -C "$WORK/root" add -A >/dev/null 2>&1
git -C "$WORK/root" commit -qm init >/dev/null 2>&1

ENTRY="$WORK/root/aurora-cli/aurora_cli/__main__.py"
fail=0
ok ()   { printf '  ok    %-50s %s\n' "$1" "$2"; }
bad ()  { printf '  FAIL  %-50s %s\n' "$1" "$2"; fail=1; }

drive () {                                  # drive <developer> <frames-file>
    DOCKER_LOG="$WORK/docker.log" \
    PATH="$WORK/bin:/usr/bin:/bin" \
    PYTHONPATH="${MUTATION_PATH:-}" \
    AURORA_SPAWN_MAX_PER_DEV="${QUOTA_PER_DEV:-1}" \
        python3 "$ENTRY" mcp --as-developer "$1" < "$2" 2>>"$WORK/stderr.log"
}

frame () {                                  # frame <tool> <json-args>
    printf '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"%s","arguments":%s}}\n' \
        "$1" "$2"
}

call () {                                   # call <tool> <args> -> $out, log
    : > "$WORK/docker.log"
    frame "$1" "$2" > "$WORK/frames"
    out=$(drive alice "$WORK/frames")
}

MUTATING='compose .* up|compose .* down|(^| )run |(^| )rm |volume rm|network rm|(^| )stop |(^| )kill |prune'
mutating_calls () { grep -Ec "$MUTATING" "$WORK/docker.log" || true; }

# Every whitespace-separated word the daemon was asked about that looks like a
# compose object, minus the ones inside alice's namespace. Non-empty means the
# session reached something that is not hers.
foreign_objects () {
    tr ' ' '\n' < "$WORK/docker.log" \
      | grep -E '^(br-[a-z0-9-]+|aurora[a-z0-9_-]*)' \
      | grep -Ev '^br-alice-' | sort -u | tr '\n' ' '
}

# ---------------------------------------------------------------------------
echo "=== every label lands inside the caller's namespace ==="
# NOT refusals. `destroy {"label":"bob-thing"}` succeeds -- against
# br-alice-bob-thing. The proof is the argv, and the tripwire must be alive:
# each of these MUST issue mutating docker calls, or the assertion is vacuous.
for label in bob-thing bob aurora ../../aurora 'BR-x' '  aurora  ' 'bob/thing'; do
    call destroy "$(printf '{"label":"%s"}' "$label")"
    m=$(mutating_calls); foreign=$(foreign_objects)
    if [ "$m" -gt 0 ] && [ -z "$foreign" ]; then
        ok "label '$label'" "$m mutating calls, all br-alice-*"
    else
        bad "label '$label'" "mutating=$m foreign='$foreign'"
    fi
done

echo "=== labels that cannot be resolved at all are refused ==="
refuse () {                                 # refuse <desc> <want> <tool> <args>
    call "$3" "$4"
    m=$(mutating_calls)
    if echo "$out" | grep -q '"isError":true' \
       && echo "$out" | grep -qF "$2" && [ "$m" -eq 0 ]; then
        ok "$1" "refused: $2"
    else
        bad "$1" "want='$2' mutating=$m  ${out:0:$EXCERPT}"
    fi
}
refuse "an empty label"        "must be a non-empty string" destroy '{"label":""}'
refuse "a non-string label"    "must be a non-empty string" destroy '{"label":42}'
refuse "a punctuation label"   "no alphanumeric character"  destroy '{"label":"///"}'
refuse "an over-long label"    "namespace"                  destroy \
    '{"label":"aaaaaaaaaabbbbbbbbbbccccccccccddddddddddeeeeeeeeeeffffffffffgggg"}'

echo "=== the quota is enforced before anything is created ==="
call spawn '{"label":"second"}'
m=$(mutating_calls)
# Directories, not `ls -A`: the teardown cases above legitimately leave an
# INDEX.md behind, and asserting an empty directory would fail on that while
# still being blind to the thing that matters -- a worktree having been made.
made=$(find "$WORK/root/.worktrees" -mindepth 1 -maxdepth 1 -type d | tr '\n' ' ')
if echo "$out" | grep -q 'quota:' && [ "$m" -eq 0 ] && [ -z "$made" ]; then
    ok "a second stack for the same developer" "refused, no worktree created"
else
    bad "a second stack for the same developer" \
        "mutating=$m worktrees='$made' ${out:0:$EXCERPT}"
fi

echo "=== the wire has no field for identity ==="
# `additionalProperties:false` is advisory; nothing validates it server-side.
# The real property is that no handler READS such a field, so a frame carrying
# one behaves identically to one that does not.
call destroy '{"label":"thing","developer":"bob","name":"aurora","devs":"all","force":true}'
foreign=$(foreign_objects)
if echo "$out" | grep -q 'br-alice-thing' && [ -z "$foreign" ]; then
    ok "forged developer/name/devs/force arguments" "still br-alice-thing"
else
    bad "forged developer/name/devs/force arguments" "foreign='$foreign' ${out:0:$EXCERPT}"
fi

echo "=== the admin tool table is not reachable from a developer session ==="
call branch_down '{"name":"aurora"}'
m=$(mutating_calls)
if echo "$out" | grep -q 'unknown tool' && [ "$m" -eq 0 ]; then
    ok "branch_down over a developer session" "unknown tool, 0 mutating calls"
else
    bad "branch_down over a developer session" "${out:0:$EXCERPT}"
fi

echo "=== tools/list offers only the namespaced four ==="
# Parsed, not grepped. A substring search over the whole frame is satisfied by
# the PROSE in a description -- `destroy`'s `force` (remove an uncommitted
# worktree) is a legitimate parameter and would have failed a grep for
# `"force"`, while a `developer` property buried in a schema would have been
# missed by a grep that happened to match a docstring. The claim is about
# SCHEMA KEYS, so read the schema keys.
printf '{"jsonrpc":"2.0","id":1,"method":"tools/list"}\n' > "$WORK/frames"
out=$(drive alice "$WORK/frames")
verdict=$(printf '%s' "$out" | python3 -c '
import json, sys
tools = json.load(sys.stdin)["result"]["tools"]
names = sorted(t["name"] for t in tools)
props = {k for t in tools for k in t["inputSchema"].get("properties", {})}
banned = props & {"developer", "devs", "name", "project", "as_developer"}
spawn = next(t for t in tools if t["name"] == "spawn")
problems = []
if names != ["access", "destroy", "list_mine", "spawn"]:
    problems.append(f"tools={names}")
if banned:
    problems.append(f"identity-bearing properties: {sorted(banned)}")
if "force" in spawn["inputSchema"]["properties"]:
    problems.append("spawn exposes force (the resource-guard override)")
if not all(t["inputSchema"].get("additionalProperties") is False for t in tools):
    problems.append("a schema permits additional properties")
print("; ".join(problems) if problems else f"OK {names} props={sorted(props)}")
' 2>&1)
case "$verdict" in
  OK\ *) ok "no admin tool, no identity parameter, no force" "$verdict" ;;
  *)     bad "tools/list" "$verdict" ;;
esac

echo "=== an unknown developer cannot start a session at all ==="
printf '{"jsonrpc":"2.0","id":1,"method":"tools/list"}\n' > "$WORK/frames"
if drive mallory "$WORK/frames" >/dev/null 2>&1; then
    bad "broker for a name not on the roster" "started"
else
    ok "broker for a name not on the roster" "refused to start"
fi

echo "=== a roster whose namespaces nest is refused, not silently accepted ==="
cp "$WORK/root/dev-administration/developers.yaml" "$WORK/roster.bak"
cat > "$WORK/root/dev-administration/developers.yaml" <<'YAML'
developers:
- display_name: alice
  forgejo_user: alice
  username: alice
- display_name: alice-two
  forgejo_user: alice-two
  username: alice-two
YAML
printf '{"jsonrpc":"2.0","id":1,"method":"tools/list"}\n' > "$WORK/frames"
if drive alice "$WORK/frames" 2>/dev/null | grep -q spawn; then
    bad "nesting roster (alice / alice-two)" "session started anyway"
else
    ok "nesting roster (alice / alice-two)" "refused to start"
fi
cp "$WORK/roster.bak" "$WORK/root/dev-administration/developers.yaml"

# --- mutations -------------------------------------------------------------
mutate () {                                 # mutate <python>
    rm -rf "$WORK/mut"; mkdir -p "$WORK/mut"
    { echo "import sys; sys.path.insert(0, '$WORK/root/aurora-cli')"
      echo "from aurora_cli import devspawn"
      echo "$1"; } > "$WORK/mut/sitecustomize.py"
    MUTATION_PATH="$WORK/mut:$WORK/root/aurora-cli"
}

echo "=== M1: delete the NAME CONSTRUCTION — the guard must still refuse ==="
mutate "devspawn.branch_name_for = lambda dev, label, root=None: str(label)"
call destroy '{"label":"bob-thing"}'
m=$(mutating_calls)
if echo "$out" | grep -q 'is not yours' && [ "$m" -eq 0 ]; then
    ok "M1" "assert_developer_owns still refuses, 0 mutating calls"
else
    bad "M1" "mutating=$m ${out:0:$EXCERPT}"
fi

echo "=== M2: delete BOTH layers — the tripwire must FIRE ==="
mutate "devspawn.branch_name_for = lambda dev, label, root=None: str(label)
devspawn.assert_developer_owns = lambda dev, project, root=None: project"
call destroy '{"label":"bob-thing"}'
m=$(mutating_calls); foreign=$(foreign_objects)
if [ "$m" -gt 0 ] && echo "$foreign" | grep -q 'br-bob-thing'; then
    ok "M2" "$m mutating calls reached '$foreign' — harness is not blind"
else
    bad "M2" "tripwire never fired: mutating=$m foreign='$foreign'"
fi

echo "=== M3: even fully disarmed, the br- namespace is STRUCTURAL ==="
# Same mutation, aimed at production. `identity.branch_paths` forces `br-` on
# the way through, so a disarmed server issues commands against `br-aurora` --
# which does not exist -- and never against `aurora`. That property is the only
# reason running M2 at all was safe.
call destroy '{"label":"aurora"}'
prod=$(tr ' ' '\n' < "$WORK/docker.log" | grep -E '^aurora' | sort -u | tr '\n' ' ')
br=$(grep -c 'br-aurora' "$WORK/docker.log" || true)
if [ -z "$prod" ] && [ "$br" -gt 0 ]; then
    ok "M3" "$br calls, all against br-aurora, none against production"
else
    bad "M3" "production-named='$prod' br-named=$br"
fi

echo "=== M4: delete the QUOTA — the request must get past policy ==="
mutate "devspawn.assert_within_quota = lambda dev, live, quota=None, root=None: None"
call spawn '{"label":"second"}'
if echo "$out" | grep -q 'quota:'; then
    bad "M4" "still refused by quota — the mutation did not bind"
else
    ok "M4" "past policy: ${out:0:$EXCERPT}"
fi

MUTATION_PATH=""
echo
if [ "$fail" -eq 0 ]; then
    echo "ALL DEVELOPER-SURFACE GUARD TESTS PASSED"
else
    echo "*** DEVELOPER-SURFACE GUARD TESTS FAILED ***"
fi
exit $fail
