# Prime directives

Audience: every agent session in this system, injected before any task. Job: the three rules that are never scaled down.

1. All development and testing happens in an ephemeral worktree and ephemeral environment. Never in prod. No task is too small for this.
2. Prod writes require explicit human consent given in this session. Prod reads are fine. Standing up an ephemeral cluster using prod-resident tooling, when the given task obviously requires it, is fine.
3. About to modify anything outside your worktree or lease: stop and open G-CHECKPOINT.

Adapters MUST put this file in front of the agent before any task (Claude: every plugin command's first step reads this file; Hermes: SOUL.md marked block, injected at session level). Every pipeline lists `prime-directives` as its first invariant. The routing skill points here before anything else.
