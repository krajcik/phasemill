---
name: wrong
description: Stop and re-evaluate an approach that is failing or heading in the wrong direction. Use for "wrong", "bad direction", "this isn't working", "start over", "try another approach", or a demonstrated dead end.
---

# Wrong: re-evaluate

Stop the active approach immediately, but preserve the current diff, state,
logs, and failed commands as evidence. Do not reset, revert, stash, delete,
force-checkout, rewrite history, or discard work merely because the direction
is wrong.

Reconstruct the original objective, success criteria, constraints, and the
assumption that failed. Read applicable `AGENTS.md` and the relevant repository
state from scratch. Explain why the current path failed with concrete evidence,
including what remains reusable and what should be abandoned.

Present 2-3 materially different alternatives grounded in existing project
patterns. For each, explain mechanism, trade-offs, migration from current
changes, validation, and rollback. Lead with a recommendation; include stopping
or keeping the current behavior when that is a legitimate choice.

Ask the user to choose before resuming mutation. After selection, invoke
`phasemill:plan` for a non-trivial redesign or continue directly only when the
new change is small and explicitly authorized. Never treat "start over" as
permission for destructive cleanup.
