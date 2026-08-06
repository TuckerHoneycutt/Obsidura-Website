# Superpowers + Hermes: Technical Difficulties

Source: PR [obra/superpowers#2025](https://github.com/obra/superpowers/pull/2025) — commit `b661305`, branch `hermes-harness-rebase`.
Analyzed against Hermes Agent v0.19.0 (upstream `8208fc52`), Docker install.

## 1. Compression kills the bootstrap

Hermes' context compressor exposes no `post_compression` hook. When compression
rewrites the first user message, `drop_stale_api_content()` (`turn_context.py:102`)
discards the `api_content` sidecar that holds the injected superpowers bootstrap.

**Impact:** Long sessions that trigger compression lose superpowers behavior
silently — no re-injection seam. The model stops invoking skills and drifts
back to baseline.

**Fix:** Upstream Hermes needs a `post_compression` hook so the plugin can
re-inject after compaction. No workaround today. Start a new session if
behavior drifts.

## 2. Plugin skills not in `<available_skills>` index

`ctx.register_skill()` (`plugins.py:1198-1209`) explicitly does NOT list
plugin skills in the system prompt's `<available_skills>` block — they're
opt-in via `skill_view("superpowers:<name>")` only.

**Impact:** The model won't auto-discover superpowers skills from the prompt.
The `pre_llm_call` bootstrap compensates by telling the model to use
`skill_view`. But if the bootstrap is lost (see #1), the hint is also lost —
the model has no way to discover the skills exist.

**Fix:** Either upstream Hermes adds plugin skills to `<available_skills>`,
or the bootstrap survives compression (see #1).

## 3. Bootstrap size vs 10k-char spill threshold

Hermes spills oversized `pre_llm_call` context to disk (`turn_context.py:713`),
giving the model a file reference instead of inline content. The PR includes
a test guarding bootstrap size under the 10k threshold.

**Impact:** Fine now. If superpowers skills grow, the bootstrap may spill —
the model gets a path instead of the full instructions, reducing effectiveness.

**Fix:** Monitor. If the bootstrap spills, consider trimming the
`using-superpowers` SKILL.md or splitting the bootstrap.

## 4. `--depth 1` shallow clone

`hermes plugins install` clones with `git clone --depth 1` (`plugins_cmd.py:473`).
No git history; can't `git pull` to update.

**Impact:** To upgrade, must reinstall with `--force`. Not a real problem,
just an operational note.

**Fix:** `hermes plugins install --force <url> --enable` to upgrade.

## 5. Private repo auth for `hermes plugins install`

The install command git-clones the repo URL. If the Forgejo repo is private,
the clone needs credentials — either embedded in the URL or via a credential
helper.

**Impact:** Blocks installation if the repo is private and no auth is configured.

**Fix:** Make the Forgejo `superpowers` repo public (it's open-source, no
secrets). Or configure a git credential helper for the Forgejo domain.

## 6. Ponytail + superpowers coexistence

Both plugins inject context via `pre_llm_call`. Both append to the same user
message. Combined context size could exceed the 10k spill threshold (see #3).

**Impact:** Probably fine — ponytail's bootstrap is small (the rules text you
see above), and superpowers' bootstrap is under 10k. But worth watching if
either grows.

**Fix:** If combined size becomes an issue, the spill mechanism handles it
gracefully (spills to disk). No action needed unless behavior degrades.
