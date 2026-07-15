---
name: status
description: Inspect or resume durable Phasemill runs in the current repository. Use for "Phasemill status", "what phase is running", "resume the run", or "continue Phasemill".
---

# Status and resume

Use `mcp__phasemill__run_status` with the absolute repository root. Pass a plan
only when the user names one; otherwise discover all active runs. This read is
non-mutating and is the source of truth for run id, phase, revision, plan, and
failure state.

Report active runs first. For each run show the plan, phase, status, current
task, revision, restart count, and last update. Do not infer progress from the
conversation transcript or `update_plan` when durable state exists.

When the user asks to resume, read the plan and applicable `AGENTS.md`, then
invoke the `phasemill:run` skill with the selected plan. That workflow calls
`run_next` and continues from the stored revision. Never call `run_start` merely
to inspect status, because starting increments restart state.

If the MCP server is unavailable, resolve `../../engine/plan_state.py` relative
to this skill and use `state-show` for a named plan. Do not scan or edit state
files directly except to report a corrupted-state diagnostic from the adapter.
