---
status: stub
---

# Guard SPEC

Audience: whoever implements the destructive-operation guard and the adapter hook that calls it. Job: pin the argv contract, exit codes, and refusal predicate so the implementation has nothing left to invent.

`core/guard/check.py` is an interface stub. The argv layer is real and tested; the predicate raises `NotImplementedError`. Build against this document, not against the stub's silence.

## Contract

```
check.py <verb> <target> [--labels k=v ...]
```

| Exit | Meaning |
|---|---|
| `0` | Allow. Verb is a recovery verb, or the positive predicate held. |
| `2` | Bad argv. Missing verb, missing target, unparseable flags. |
| `3` | Refuse. Destructive verb, predicate did not hold. Emits a `guard.refused` journal line. |
| `4` | Unknown verb. Not in either whitelist. |

## The positive predicate

Implement exactly this, and nothing looser:

> Allow a destructive verb only when `target labels ⊇ {lease: <this session's lease>}`.

1. Unlabeled target → refuse. Absence of a lease label is not permission.
2. Foreign lease label → refuse. Another session's resource is not yours to delete.
3. Session holds no lease → refuse. There is no set to be a superset of.

`!= production` is NOT a guard. A negative predicate passes on empty string, on `None`, on `prodution`, and on every name nobody thought to blacklist. Only membership in a known-good set fails closed.

## Verb whitelist rationale

| Set | Members | Behavior |
|---|---|---|
| `RECOVERY_VERBS` | `compose-up`, `restore`, `start` | Always exit `0`. Never gate the way out of a hole. |
| `DESTRUCTIVE_VERBS` | `compose-down`, `volume-rm`, `container-rm`, `image-rm`, `rm-rf`, `db-drop`, `prune` | Run the predicate. |
| Everything else | — | Exit `4`. |

Exit `4` on the unanticipated spelling is the point. A destructive verb nobody enumerated gets refused by default rather than waved through as "not on the list". Adding a verb to `DESTRUCTIVE_VERBS` is a one-line change; discovering a deletion that bypassed the guard is not.

## Override

Exactly one: `AURORA_GUARD_OVERRIDE=1` → exit `0` with `OVERRIDE:` on stderr.

1. One override, not a family. Every additional escape hatch is a hatch nobody audits.
2. It must be typed on the command line, so it lands in shell history and in the journal.
3. Loud stderr is the feature. A silent bypass is indistinguishable from a guard that never ran.

## Testing

Guard tests run against stubs and tripwires — never live tools. A test that proves the guard refuses `compose-down` must not be able to bring down a stack when the guard regresses. Assert on exit codes and stderr from `check.py`; wire the tripwire so a bypass fails the test instead of deleting the resource.

## Enforcement home

| Adapter | Where the guard runs |
|---|---|
| Claude | `PreToolUse` hook, before `Bash` / `Write` / `Edit` execute. |
| Hermes | Tool wrapper, inline before exec. |
| generic shell | `subprocess` wrapper that shells out to `check.py` first. |

Not built yet. When it is built, the guard is called by the adapter, not by the pipeline — a pipeline that has to remember to ask permission is a pipeline that will forget.
